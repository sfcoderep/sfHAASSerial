"""
Alerting module.

Runs as a background thread; checks heartbeat table every 30 seconds
and fires Slack / email when:
  - A machine hasn't been heard from in heartbeat_timeout seconds
  - An alarm_active event fires (called directly from the poll loop)

Deduplication: once an alert fires for a machine, it won't fire again
until the machine recovers and goes offline again.
"""

import logging
import smtplib
import threading
import time
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone
from email.message import EmailMessage

log = logging.getLogger(__name__)


class Alerter:
    def __init__(self, cfg: dict, storage):
        self.cfg     = cfg          # the alerting: block from config.yaml
        self.storage = storage
        self._alerted: set[str] = set()   # machine IDs currently in "lost" state
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Background watchdog — call start() once at startup
    # ------------------------------------------------------------------
    def start(self):
        t = threading.Thread(target=self._watchdog, daemon=True)
        t.start()

    def _watchdog(self):
        timeout = self.cfg.get("heartbeat_timeout", 120)
        while True:
            try:
                rows = self.storage.get_heartbeats()
                now  = datetime.now()

                for row in rows:
                    mid      = row["machine_id"]
                    last     = row["last_seen"]
                    # mysql-connector returns datetime objects
                    if hasattr(last, "tzinfo") and last.tzinfo is not None:
                        now_cmp = datetime.now(timezone.utc)
                    else:
                        now_cmp = now

                    age = (now_cmp - last).total_seconds()

                    with self._lock:
                        already_alerted = mid in self._alerted

                    if age > timeout and not already_alerted:
                        msg = (f"Machine {mid} has not reported in "
                               f"{int(age)}s (timeout={timeout}s).")
                        log.warning(msg)
                        self._fire(f"[HAAS LOST] {mid}", msg)
                        with self._lock:
                            self._alerted.add(mid)

                    elif age <= timeout:
                        # Recovery
                        with self._lock:
                            if mid in self._alerted:
                                self._alerted.discard(mid)
                                rec_msg = f"Machine {mid} is back online."
                                log.info(rec_msg)
                                self._fire(f"[HAAS RECOVERED] {mid}", rec_msg)

            except Exception as exc:
                log.error("Alerting watchdog error: %s", exc)

            time.sleep(30)

    # ------------------------------------------------------------------
    # Called from poll loop when alarm_active event fires
    # ------------------------------------------------------------------
    def on_alarm(self, machine_id: str, code: str, message: str):
        subject = f"[HAAS ALARM] {machine_id} — {code}"
        body    = f"Machine {machine_id} raised alarm {code}: {message}"
        log.warning(body)
        self._fire(subject, body)

    def on_alarm_cleared(self, machine_id: str, code: str):
        subject = f"[HAAS ALARM CLEARED] {machine_id} — {code}"
        body    = f"Machine {machine_id}: alarm {code} has been cleared."
        log.info(body)
        self._fire(subject, body)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------
    def _fire(self, subject: str, body: str):
        self._send_slack(body)
        self._send_email(subject, body)

    def _send_slack(self, text: str):
        webhook = self.cfg.get("slack_webhook")
        if not webhook:
            return
        try:
            payload = json.dumps({"text": text}).encode()
            req = urllib.request.Request(
                webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.URLError as exc:
            log.error("Slack alert failed: %s", exc)

    def _send_email(self, subject: str, body: str):
        smtp_host = self.cfg.get("smtp_host")
        if not smtp_host:
            return
        try:
            msg               = EmailMessage()
            msg["From"]       = self.cfg["alert_from"]
            msg["To"]         = ", ".join(self.cfg.get("alert_to", []))
            msg["Subject"]    = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, self.cfg.get("smtp_port", 587)) as s:
                s.starttls()
                user = self.cfg.get("smtp_user")
                pw   = self.cfg.get("smtp_pass")
                if user and pw:
                    s.login(user, pw)
                s.send_message(msg)
        except Exception as exc:
            log.error("Email alert failed: %s", exc)
