import threading
from datetime import datetime


class MachineState:
    """
    Per-machine mutable state, shared between the poll loop and the
    alerting watchdog.  All access is protected by a lock so threads
    can't race.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Last parsed snapshot
        self.last = {}

        # Cycle timing
        self.cycle_start_ts = None      # datetime when RUNNING began

        # Active alarms  {alarm_code: datetime first seen}
        self.active_alarms = {}

        # Historian: last value that was actually written to the DB
        # and when we last forced a write regardless of deadband
        self.last_written = {}
        self.last_force_write = None    # datetime

    # ------------------------------------------------------------------
    # Helpers to update safely from the poll thread
    # ------------------------------------------------------------------

    def update(self, parsed: dict):
        with self._lock:
            self.last = parsed

    def get_last(self) -> dict:
        with self._lock:
            return dict(self.last)

    def start_cycle(self):
        with self._lock:
            self.cycle_start_ts = datetime.now()

    def stop_cycle(self) -> float | None:
        """Return elapsed seconds, or None if start was never recorded."""
        with self._lock:
            if self.cycle_start_ts is None:
                return None
            elapsed = (datetime.now() - self.cycle_start_ts).total_seconds()
            self.cycle_start_ts = None
            return elapsed

    def set_alarms(self, alarm_dict: dict):
        """
        alarm_dict: {code: message} currently active on the machine.
        Returns (new_alarms, cleared_alarms) as sets of codes.
        """
        with self._lock:
            prev_codes = set(self.active_alarms.keys())
            curr_codes = set(alarm_dict.keys())

            new_codes = curr_codes - prev_codes
            cleared_codes = prev_codes - curr_codes

            for code in new_codes:
                self.active_alarms[code] = datetime.now()
            for code in cleared_codes:
                del self.active_alarms[code]

            return new_codes, cleared_codes
