import re


def clean(response):
    if not response:
        return None
    response = (response
                .replace("\x02", "")
                .replace("\x17", "")
                .replace("\r", "")
                .replace("\n", "")
                .replace(">", "")
                .strip())
    if not response or response.upper() == "UNKNOWN":
        return None
    return response


def parse_position(response, axis):
    m = re.search(rf"{axis}[,\s]*([-\d.]+)", response or "", re.I)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, AttributeError):
            return None
    return None


def parse_alarms(raw: dict) -> dict:
    """
    Parse Q400-Q499 responses into {alarm_code: message}.
    HAAS returns "ALARM, <code>, <message>" for each active alarm.
    Returns empty dict when no alarms are active.
    """
    alarms = {}
    for qcode, raw_response in raw.items():
        if not qcode.startswith("Q4"):
            continue
        r = clean(raw_response)
        if not r:
            continue
        m = re.search(r"ALARM,\s*(\d+),\s*(.+)", r, re.I)
        if m:
            code = m.group(1)
            message = m.group(2).strip()
            alarms[code] = message
    return alarms


# Fields treated as discrete (write on any change, no deadband)
DISCRETE_FIELDS = {
    "program_status",
    "program",
    "mode",
    "serial_number",
    "software_ver",
}

# Fields excluded from historian comparison — change every poll by
# design and are not useful for change detection
EXCLUDED_FIELDS = {
    "power_on_time",
    "cycle_start_time",
}


def historian_should_ignore(field: str) -> bool:
    return field in EXCLUDED_FIELDS


def parse_responses(raw: dict) -> dict:
    data = {
        "serial_number":    None,
        "software_ver":     None,
        "mode":             None,
        "tool_changes":     None,
        "current_tool":     None,
        "power_on_time":    None,
        "cycle_start_time": None,
        "program":          None,
        "program_status":   None,
        "parts_count":      None,
        "x_position":       None,
        "y_position":       None,
        "z_position":       None,
        "a_position":       None,
        "b_position":       None,
        "spindle_speed":    None,
        "feed_rate":        None,
    }

    for qcode, raw_response in raw.items():
        r = clean(raw_response)
        if not r:
            continue

        if qcode == "Q100":
            m = re.search(r"S/N,\s*(\d+)", r)
            if m:
                data["serial_number"] = m.group(1)

        elif qcode == "Q101":
            m = re.search(r"SOFTWARE,\s*VER\s*(\S+)", r)
            if m:
                data["software_ver"] = m.group(1)

        elif qcode == "Q104":
            # Handles both MODE, (MEM) and MODE, MEM
            m = re.search(r"MODE,\s*\(?([^)]+)\)?", r)
            if m:
                data["mode"] = m.group(1).strip()

        elif qcode == "Q200":
            m = re.search(r"TOOL CHANGES,\s*(\d+)", r)
            if m:
                data["tool_changes"] = int(m.group(1))

        elif qcode == "Q201":
            m = re.search(r"USING TOOL,\s*(\d+)", r)
            if m:
                data["current_tool"] = int(m.group(1))

        elif qcode == "Q300":
            m = re.search(r"P\.O\. TIME,\s*([\d:]+)", r)
            if m:
                data["power_on_time"] = m.group(1)

        elif qcode == "Q301":
            m = re.search(r"C\.S\. TIME,\s*([\d:]+)", r)
            if m:
                data["cycle_start_time"] = m.group(1)

        elif qcode == "Q500":
            # Full NGC format: PROGRAM, O1234, RUNNING, PARTS, 47
            m = re.search(r"PROGRAM,\s*(\S+),\s*([^,]+),\s*PARTS,\s*(\d+)", r)
            if m:
                data["program"]        = m.group(1)
                data["program_status"] = m.group(2).strip()
                data["parts_count"]    = int(m.group(3))
            else:
                # Older M-series format: STATUS, BUSY  or  STATUS, IDLE
                m = re.search(r"STATUS,\s*(\w+)", r)
                if m:
                    data["program_status"] = m.group(1).strip()

            s = re.search(r"S\s*(\d+)", r)
            f = re.search(r"F\s*([\d.]+)", r)
            if s:
                data["spindle_speed"] = int(s.group(1))
            if f:
                data["feed_rate"] = float(f.group(1))

        elif qcode in ("Q501", "Q502", "Q503", "Q504", "Q505"):
            axis_map = {
                "Q501": "X",
                "Q502": "Y",
                "Q503": "Z",
                "Q504": "A",
                "Q505": "B",
            }
            axis = axis_map[qcode]
            data[f"{axis.lower()}_position"] = parse_position(r, axis)

    return data