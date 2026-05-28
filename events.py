def detect_events(prev, curr):
    events = []

    if not prev:
        return events

    if prev.get("program_status") != "RUNNING" and curr.get("program_status") == "RUNNING":
        events.append(("cycle_start", {}))

    if prev.get("program_status") == "RUNNING" and curr.get("program_status") != "RUNNING":
        events.append(("cycle_stop", {}))

    if prev.get("current_tool") != curr.get("current_tool"):
        events.append(("tool_change", {
            "from": prev.get("current_tool"),
            "to": curr.get("current_tool")
        }))

    if prev.get("parts_count") != curr.get("parts_count"):
        events.append(("part_complete", {
            "count": curr.get("parts_count")
        }))

    return events