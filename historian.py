"""
Historian-style write filtering.

Instead of writing every poll to the database (10-second rows that are
identical for hours during an alarm), we only write when:
  1. A value has changed by more than its configured deadband, OR
  2. The force_write_interval has elapsed (heartbeat record so Grafana
     doesn't show gaps).

This mirrors how Ignition's Tag Historian and OSIsoft PI work.

Discrete / string fields (program_status, program, mode, current_tool,
parts_count, tool_changes, active_alarms) are always written on any
change — deadband only applies to numeric analog values.
"""

from datetime import datetime

# Fields treated as discrete (write on any change, no deadband)
DISCRETE_FIELDS = {
    "program_status",
    "program",
    "mode",
    "serial_number",
    "software_ver",
}


def _changed(field: str, prev_val, curr_val, deadbands: dict) -> bool:
    """Return True if this field has changed enough to warrant a write."""
    if field in DISCRETE_FIELDS:
        return prev_val != curr_val

    if prev_val is None or curr_val is None:
        return prev_val != curr_val

    deadband = deadbands.get(field, 0)
    try:
        return abs(float(curr_val) - float(prev_val)) > deadband
    except (TypeError, ValueError):
        return prev_val != curr_val


def should_write(parsed: dict, state, historian_cfg: dict) -> bool:
    """
    Return True if this poll result should be written to cnc_data.

    state.last_written  — dict of the last values written
    state.last_force_write — datetime of last forced write
    """
    deadbands = historian_cfg.get("deadbands", {})
    force_interval = historian_cfg.get("force_write_interval", 300)

    now = datetime.now()

    # Force write if we've never written or interval has elapsed
    if state.last_force_write is None:
        return True
    if (now - state.last_force_write).total_seconds() >= force_interval:
        return True

    # Write if any tracked field has changed beyond deadband
    for field, curr_val in parsed.items():
        prev_val = state.last_written.get(field)
        if _changed(field, prev_val, curr_val, deadbands):
            return True

    return False


def record_write(parsed: dict, state):
    """Call this after a successful DB write to update historian state."""
    state.last_written = dict(parsed)
    state.last_force_write = datetime.now()
