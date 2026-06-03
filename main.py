"""
sfHAASSerial — HAAS CNC data collection daemon.

Improvements over v1:
  - Credentials from environment variables (not config.yaml)
  - Historian-style write filtering (deadband + force interval)
  - Alarm polling and alarm events
  - Cycle time measurement
  - Slack / email alerting
  - Thread-safe MachineState
  - Connection leak fix in Storage
  - Dead Q-codes fixed (Q101, Q300 now actually queried)
"""

import os
import yaml
import time
import threading
import logging

from haas_client import HaasClient
from parser import parse_responses, parse_alarms
from storage import Storage
from state import MachineState
from events import detect_events, detect_alarm_events
from historian import should_write, record_write
from alerting import Alerter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)s %(message)s",
)

AXIS_Q = {
    "X": "Q501",
    "Y": "Q502",
    "Z": "Q503",
    "A": "Q504",
    "B": "Q505",
}

# Q-codes always queried for every machine
BASE_Q = ["Q100", "Q101", "Q104", "Q200", "Q201", "Q300", "Q301", "Q500"]

# ✅ ADD THIS — macro queries for classic controls
MACRO_QUERIES = {
    "x_position_macro": "Q600 5021",
    "y_position_macro": "Q600 5022",
    "z_position_macro": "Q600 5023",
    "spindle_speed_macro": "Q600 3026",
    "feed_rate_macro": "Q600 30003",
}

state_lock = threading.Lock()
state_map: dict[str, MachineState] = {}


def build_qcodes(model: str, profiles: dict) -> list[str]:
    axes = profiles.get(model, [])
    return BASE_Q + [AXIS_Q[a] for a in axes if a in AXIS_Q]


def get_or_create_state(machine_id: str) -> MachineState:
    with state_lock:
        if machine_id not in state_map:
            state_map[machine_id] = MachineState()
        return state_map[machine_id]


def poll_machine(machine: dict, config: dict, storage: Storage,
                 alerter: Alerter, profiles: dict):

    log      = logging.getLogger(machine["id"])
    qcodes   = build_qcodes(machine["model"], profiles)
    hist_cfg = config.get("historian", {})
    mid      = machine["id"]
    state    = get_or_create_state(mid)

    delay = machine.get("delay", 0.2)

    while True:
        client = None
        try:
            client = HaasClient(
                machine["ip"],
                config["socket_port"],
                config["socket_timeout"]
            )
            client.connect()
            log.info("Connected")

            while True:
                # ---- 1. Query machine data Q-codes ------------------
                raw = {}

                for q in qcodes:
                    raw[q] = client.query(q)
                    time.sleep(delay)

                # ✅ ADD THIS — macro queries (classic control support)
                for key, cmd in MACRO_QUERIES.items():
                    raw[key] = client.query(cmd)
                    time.sleep(delay)

                # ---- 2. Query alarms --------------------------------
                alarm_raw    = client.query_alarms()
                alarm_dict   = parse_alarms(alarm_raw)
                new_a, clr_a = state.set_alarms(alarm_dict)

                # ---- 3. Parse data ----------------------------------
                parsed = parse_responses(raw)

                # ---- 4. Stabilize BUSY responses --------------------
                prev = state.get_last()

                if prev:
                    if parsed.get("program") is None:
                        parsed["program"] = prev.get("program")

                    if parsed.get("parts_count") is None:
                        parsed["parts_count"] = prev.get("parts_count")

                    if parsed.get("program_status") is None:
                        parsed["program_status"] = prev.get("program_status")

                # ---- 5. Detect and store events ---------------------
                events = detect_events(prev, parsed, state)
                events += detect_alarm_events(new_a, clr_a, alarm_dict)

                for evt, payload in events:
                    storage.insert_event(mid, evt, payload)

                    # Fire alerts for alarm transitions
                    if evt == "alarm_active":
                        alerter.on_alarm(
                            mid,
                            payload["code"],
                            payload.get("message", "")
                        )
                    elif evt == "alarm_cleared":
                        alerter.on_alarm_cleared(mid, payload["code"])

                # ---- 6. Persist alarm rows --------------------------
                for code in new_a:
                    storage.upsert_alarm(mid, code, alarm_dict[code])
                for code in clr_a:
                    storage.clear_alarm(mid, code)

                # ---- 7. Historian write gate ------------------------
                if should_write(parsed, state, hist_cfg):
                    storage.insert_data(mid, parsed, raw)
                    record_write(parsed, state)
                    log.debug("Wrote row (historian)")
                else:
                    log.debug("Skipped write (no change beyond deadband)")

                # ---- 8. Always update state and heartbeat -----------
                state.update(parsed)
                storage.heartbeat(mid)

                log.info(
                    "%s | status=%s tool=%s parts=%s alarms=%s",
                    mid,
                    parsed.get("program_status"),
                    parsed.get("current_tool"),
                    parsed.get("parts_count"),
                    list(alarm_dict.keys()) or "none"
                )

                time.sleep(config["poll_interval"])

        except Exception as exc:
            log.warning("Connection lost (%s) — retrying in 10s", exc)
        finally:
            if client:
                client.close()

        time.sleep(10)


def load_db_config(cfg: dict) -> dict:
    """
    Merge config.yaml database block with environment variable overrides.
    """
    db = dict(cfg)
    db["host"]     = os.environ.get("HAAS_DB_HOST",  db.get("host", "localhost"))
    db["user"]     = os.environ.get("HAAS_DB_USER",  db.get("user", ""))
    db["password"] = os.environ.get("HAAS_DB_PASS",  db.get("password", ""))
    db["database"] = os.environ.get("HAAS_DB_NAME",  db.get("database", ""))
    return db


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    db_cfg  = load_db_config(config.get("database", {}))
    storage = Storage(db_cfg)
    alerter = Alerter(config.get("alerting", {}), storage)
    alerter.start()

    threads = []
    for m in config["machines"]:
        t = threading.Thread(
            target=poll_machine,
            args=(m, config, storage, alerter, config["profiles"]),
            daemon=True,
            name=m["id"],
        )
        t.start()
        threads.append(t)
        time.sleep(0.5)

    logging.getLogger("main").info(
        "Polling %d machines", len(config["machines"])
    )

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()