import socket
import time
import logging

log = logging.getLogger(__name__)

# Q-codes to query for active alarms.
# HAAS exposes up to 10 simultaneous alarms on Q400–Q409.
ALARM_QCODES = [f"Q{400 + i}" for i in range(10)]


class HaasClient:
    def __init__(self, ip: str, port: int = 5000, timeout: float = 3):
        self.ip      = ip
        self.port    = port
        self.timeout = timeout
        self.sock    = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))
        time.sleep(0.3)
        # Drain the welcome banner HAAS sends on connect
        try:
            self.sock.recv(1024)
        except OSError:
            pass

    def query(self, qcode: str) -> str | None:
        try:
            self.sock.sendall((qcode + "\r\n").encode("ascii"))
            response  = b""
            deadline  = time.time() + self.timeout

            while time.time() < deadline:
                try:
                    chunk = self.sock.recv(1024)
                except socket.timeout:
                    break
                if chunk:
                    response += chunk
                    if b"\x17" in response:   # ETB = end of HAAS response
                        break

            return response.decode("ascii", errors="replace") if response else None
        except OSError as exc:
            log.debug("query %s failed: %s", qcode, exc)
            return None

    def query_alarms(self) -> dict[str, str | None]:
        """Query all alarm Q-codes and return raw responses keyed by qcode."""
        return {q: self.query(q) for q in ALARM_QCODES}

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            finally:
                self.sock = None
