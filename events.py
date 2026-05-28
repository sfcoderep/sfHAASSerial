"""
Event detection between consecutive polls.

Events are written to cnc_events and are always recorded regardless of
historian deadband — they represent discrete state transitions that must
not be dropped.
"""


def detect_events(prev: dict, curr: dict, state) -> list[tuple]:
    """
    Compare prev and curr parsed snapshots and return a list of
    (event_type, payload) tuples.

    state is the MachineState object; it is mutated here for cycle
    timing (start_cycle / stop_cycle).
    """
    events = []

    if not prev:
        return events

    prev_status = prev.get("program_status")
    curr_status  = curr.get("program_status")

    prev_tool  = prev.get("current_tool")
    curr_tool  = curr.get("current_tool")

    prev_parts = prev.get("parts_count")
    curr_parts = curr.get("parts_count")

    prev_program = prev.get("program")
    curr_program = curr.get("program")

    # ------------------------------------------------------------------
    # Status change (generic — always emit so the event log is complete)
    # ------------------------------------------------------------------
    if prev_status != curr_status:
        events.append(("status_change", {
            "from": prev_status,
            "to":   curr_status,
        }))

    # ------------------------------------------------------------------
    # Cycle start
    # ------------------------------------------------------------------
    if prev_status != "RUNNING" and curr_status == "RUNNING":
        state.start_cycle()
        events.append(("cycle_start", {
            "program": curr_program,
        }))

    # ------------------------------------------------------------------
    # Cycle stop — include measured cycle time
    # ------------------------------------------------------------------
    if prev_status == "RUNNING" and curr_status != "RUNNING":
        elapsed = state.stop_cycle()   # seconds, or None
        events.append(("cycle_stop", {
            "program":          prev_program,
            "status_after":     curr_status,
            "cycle_time_sec":   elapsed,
        }))

    # ------------------------------------------------------------------
    # Tool change
    # ------------------------------------------------------------------
    if prev_tool is not None and curr_tool is not None and prev_tool != curr_tool:
        events.append(("tool_change", {
            "from": prev_tool,
            "to":   curr_tool,
        }))

    # ------------------------------------------------------------------
    # Part complete (parts_count incremented)
    # ------------------------------------------------------------------
    if prev_parts is not None and curr_parts is not None:
        if curr_parts > prev_parts:
            events.append(("part_complete", {
                "count": curr_parts,
                "delta": curr_parts - prev_parts,
            }))

    # ------------------------------------------------------------------
    # Program change (operator loaded a different program)
    # ------------------------------------------------------------------
    if prev_program and curr_program and prev_program != curr_program:
        events.append(("program_change", {
            "from": prev_program,
            "to":   curr_program,
        }))

    return events


def detect_alarm_events(new_codes: set, cleared_codes: set,
                        alarm_dict: dict) -> list[tuple]:
    """
    Convert alarm set changes into events.
    alarm_dict is the current {code: message} mapping.
    """
    events = []
    for code in new_codes:
        events.append(("alarm_active", {
            "code":    code,
            "message": alarm_dict.get(code, ""),
        }))
    for code in cleared_codes:
        events.append(("alarm_cleared", {
            "code": code,
        }))
    return events
