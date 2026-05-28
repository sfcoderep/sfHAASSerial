import socket
import time

class HaasClient:
    def __init__(self, ip, port=5000, timeout=3):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))
        time.sleep(0.3)
        try:
            self.sock.recv(1024)
        except:
            pass

    def query(self, qcode):
        try:
            self.sock.sendall((qcode + "\r\n").encode("ascii"))
            response = b""
            deadline = time.time() + self.timeout

            while time.time() < deadline:
                chunk = self.sock.recv(1024)
                if chunk:
                    response += chunk
                    if b"\x17" in response:
                        break
            return response.decode("ascii", errors="replace")
        except:
            return None

    def close(self):
        if self.sock:
            self.sock.close()