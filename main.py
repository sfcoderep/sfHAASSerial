import yaml
import time
import threading
import logging

from haas_client import HaasClient
from parser import parse_responses
from storage import Storage
from state import MachineState
from events import detect_events

logging.basicConfig(level=logging.INFO)

AXIS_Q = {
    "X": "Q501",
    "Y": "Q502",
    "Z": "Q503",
    "A": "Q504",
    "B": "Q505"
}

BASE_Q = ["Q100","Q104","Q200","Q201","Q301","Q500"]

state_map = {}


def build_qcodes(model, profiles):
    axes = profiles.get(model, [])
    return BASE_Q + [AXIS_Q[a] for a in axes]


def poll_machine(machine, config, storage, profiles):
    log = logging.getLogger(machine["id"])

    qcodes = build_qcodes(machine["model"], profiles)

    while True:
        try:
            client = HaasClient(machine["ip"], config["socket_port"], config["socket_timeout"])
            client.connect()

            if machine["id"] not in state_map:
                state_map[machine["id"]] = MachineState()

            while True:
                raw = {}
                for q in qcodes:
                    raw[q] = client.query(q)
                    time.sleep(0.1)

                parsed = parse_responses(raw)

                prev = state_map[machine["id"]].last
                events = detect_events(prev, parsed)

                for evt, payload in events:
                    storage.insert_event(machine["id"], evt, payload)

                state_map[machine["id"]].last = parsed

                storage.insert_data(machine["id"], parsed, raw)
                storage.heartbeat(machine["id"])

                log.info(f"{machine['id']} | {parsed}")

                time.sleep(config["poll_interval"])

        except Exception as e:
            log.warning(f"Reconnect: {e}")
            time.sleep(10)


def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    storage = Storage(config["database"])

    threads = []
    for m in config["machines"]:
        t = threading.Thread(
            target=poll_machine,
            args=(m, config, storage, config["profiles"]),
            daemon=True
        )
        t.start()
        threads.append(t)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()