
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import json

class Storage:
    def __init__(self, config):
        self.pool = pooling.MySQLConnectionPool(
            pool_name="haas_pool",
            pool_size=5,
            **config
        )

    def get_conn(self):
        return self.pool.get_connection()

    def insert_data(self, machine_id, parsed, raw):
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute("""
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
            machine_id,
            datetime.now(),

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

            json.dumps(raw)
        ))

        conn.commit()
        cursor.close()
        conn.close()

    def insert_event(self, machine_id, event_type, payload):
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO cnc_events (machine_id, event_type, event_time, payload)
            VALUES (%s,%s,%s,%s)
        """, (
            machine_id,
            event_type,
            datetime.now(),
            json.dumps(payload)
        ))

        conn.commit()
        cursor.close()
        conn.close()

    def heartbeat(self, machine_id):
        conn = self.get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO cnc_heartbeat (machine_id, last_seen)
            VALUES (%s,%s)
            ON DUPLICATE KEY UPDATE last_seen=VALUES(last_seen)
        """, (machine_id, datetime.now()))

        conn.commit()
        cursor.close()
        conn.close()
