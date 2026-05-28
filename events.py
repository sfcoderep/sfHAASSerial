
def detect_events(prev, curr):
    events = []

    if not prev:
        return events

    prev_status = prev.get("program_status")
    curr_status = curr.get("program_status")

    prev_tool = prev.get("current_tool")
    curr_tool = curr.get("current_tool")

    prev_parts = prev.get("parts_count")
    curr_parts = curr.get("parts_count")

    # Status change
    if prev_status != curr_status:
        events.append(("status_change", {
            "from": prev_status,
            "to": curr_status
        }))

    # Cycle start
    if prev_status != "RUNNING" and curr_status == "RUNNING":
        events.append(("cycle_start", {}))

    # Cycle stop
    if prev_status == "RUNNING" and curr_status != "RUNNING":
        events.append(("cycle_stop", {}))

    # Tool change
    if prev_tool != curr_tool:
        events.append(("tool_change", {
            "from": prev_tool,
            "to": curr_tool
        }))

    # Part complete
    if prev_parts is not None and curr_parts is not None:
        if curr_parts > prev_parts:
            events.append(("part_complete", {
                "count": curr_parts
            }))

    # Idle
    if curr_status and curr_status != "RUNNING":
        events.append(("machine_idle", {
            "status": curr_status
        }))

    return events
