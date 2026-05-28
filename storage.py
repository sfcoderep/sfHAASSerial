import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import json
import logging

log = logging.getLogger(__name__)


class Storage:
    def __init__(self, config: dict):
        self.pool = pooling.MySQLConnectionPool(
            pool_name="haas_pool",
            pool_size=10,        # raised — 14 machines × occasional bursts
            **config
        )

    # ------------------------------------------------------------------
    # Internal helper — always use as a context manager so connections
    # are returned to the pool even if an exception is raised.
    # ------------------------------------------------------------------
    def _conn(self):
        return _ConnectionCtx(self.pool)

    # ------------------------------------------------------------------
    # cnc_data  (historian-filtered; written only when values change)
    # ------------------------------------------------------------------
    def insert_data(self, machine_id: str, parsed: dict, raw: dict):
        with self._conn() as (conn, cur):
            cur.execute("""
                INSERT INTO cnc_data (
                    machine_id, collected_at,
                    serial_number, software_ver, mode,
                    tool_changes, current_tool,
                    power_on_time, cycle_start_time,
                    program, program_status, parts_count,
                    x_position, y_position, z_position,
                    a_position, b_position,
                    spindle_speed, feed_rate,
                    raw_response
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                machine_id, datetime.now(),
                parsed.get("serial_number"),
                parsed.get("software_ver"),
                parsed.get("mode"),
                parsed.get("tool_changes"),
                parsed.get("current_tool"),
                parsed.get("power_on_time"),
                parsed.get("cycle_start_time"),
                parsed.get("program"),
                parsed.get("program_status"),
                parsed.get("parts_count"),
                parsed.get("x_position"),
                parsed.get("y_position"),
                parsed.get("z_position"),
                parsed.get("a_position"),
                parsed.get("b_position"),
                parsed.get("spindle_speed"),
                parsed.get("feed_rate"),
                json.dumps(raw),
            ))
            conn.commit()

    # ------------------------------------------------------------------
    # cnc_events  (always written — not historian-filtered)
    # ------------------------------------------------------------------
    def insert_event(self, machine_id: str, event_type: str, payload: dict):
        with self._conn() as (conn, cur):
            cur.execute("""
                INSERT INTO cnc_events
                    (machine_id, event_type, event_time, payload)
                VALUES (%s,%s,%s,%s)
            """, (
                machine_id,
                event_type,
                datetime.now(),
                json.dumps(payload),
            ))
            conn.commit()

    # ------------------------------------------------------------------
    # cnc_alarms  (separate table for active alarm state)
    # ------------------------------------------------------------------
    def upsert_alarm(self, machine_id: str, code: str, message: str):
        """Insert or update an active alarm row."""
        with self._conn() as (conn, cur):
            cur.execute("""
                INSERT INTO cnc_alarms
                    (machine_id, alarm_code, alarm_message, first_seen, last_seen)
                VALUES (%s,%s,%s,NOW(),NOW())
                ON DUPLICATE KEY UPDATE
                    alarm_message = VALUES(alarm_message),
                    last_seen     = NOW()
            """, (machine_id, code, message))
            conn.commit()

    def clear_alarm(self, machine_id: str, code: str):
        """Mark an alarm as cleared (set cleared_at)."""
        with self._conn() as (conn, cur):
            cur.execute("""
                UPDATE cnc_alarms
                SET cleared_at = NOW()
                WHERE machine_id = %s AND alarm_code = %s AND cleared_at IS NULL
            """, (machine_id, code))
            conn.commit()

    # ------------------------------------------------------------------
    # cnc_heartbeat
    # ------------------------------------------------------------------
    def heartbeat(self, machine_id: str):
        with self._conn() as (conn, cur):
            cur.execute("""
                INSERT INTO cnc_heartbeat (machine_id, last_seen)
                VALUES (%s, NOW())
                ON DUPLICATE KEY UPDATE last_seen = NOW()
            """, (machine_id,))
            conn.commit()

    def get_heartbeats(self) -> list[dict]:
        """Return all heartbeat rows (used by alerting watchdog)."""
        with self._conn() as (conn, cur):
            cur.execute(
                "SELECT machine_id, last_seen FROM cnc_heartbeat"
            )
            rows = cur.fetchall()
        return [{"machine_id": r[0], "last_seen": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Context manager wrapper so every caller is leak-proof
# ---------------------------------------------------------------------------
class _ConnectionCtx:
    def __init__(self, pool):
        self._pool = pool
        self._conn = None
        self._cur  = None

    def __enter__(self):
        self._conn = self._pool.get_connection()
        self._cur  = self._conn.cursor()
        return self._conn, self._cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._cur:
                self._cur.close()
        except Exception:
            pass
        try:
            if self._conn:
                self._conn.close()   # returns to pool
        except Exception:
            pass
        return False   # do not suppress exceptions
