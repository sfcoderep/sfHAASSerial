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
        # Format: ALARM, 1234, SERVO ERROR X AXIS
        m = re.search(r"ALARM,\s*(\d+),\s*(.+)", r, re.I)
        if m:
            code = m.group(1)
            message = m.group(2).strip()
            alarms[code] = message
    return alarms


def parse_responses(raw: dict) -> dict:
    data = {
        "serial_number":   None,
        "software_ver":    None,
        "mode":            None,
        "tool_changes":    None,
        "current_tool":    None,
        "power_on_time":   None,
        "cycle_start_time": None,
        "program":         None,
        "program_status":  None,
        "parts_count":     None,
        "x_position":      None,
        "y_position":      None,
        "z_position":      None,
        "a_position":      None,
        "b_position":      None,
        "spindle_speed":   None,
        "feed_rate":       None,
    }

    for qcode, raw_response in raw.items():
        r = clean(raw_response)
        if not r:
            continue

        if qcode == "Q100":
            # S/N, 12345678
            m = re.search(r"S/N,\s*(\d+)", r)
            if m:
                data["serial_number"] = m.group(1)

        elif qcode == "Q101":
            # SOFTWARE, VER 100.20.000.1150
            m = re.search(r"SOFTWARE,\s*VER\s*(\S+)", r)
            if m:
                data["software_ver"] = m.group(1)

        elif qcode == "Q104":
            # MODE, (MEM)
            m = re.search(r"MODE,\s*\((.+?)\)", r)
            if m:
                data["mode"] = m.group(1)

        elif qcode == "Q200":
            # TOOL CHANGES, 42
            m = re.search(r"TOOL CHANGES,\s*(\d+)", r)
            if m:
                data["tool_changes"] = int(m.group(1))

        elif qcode == "Q201":
            # USING TOOL, 5
            m = re.search(r"USING TOOL,\s*(\d+)", r)
            if m:
                data["current_tool"] = int(m.group(1))

        elif qcode == "Q300":
            # P.O. TIME, 12345:30
            m = re.search(r"P\.O\. TIME,\s*([\d:]+)", r)
            if m:
                data["power_on_time"] = m.group(1)

        elif qcode == "Q301":
            # C.S. TIME, 5678:15
            m = re.search(r"C\.S\. TIME,\s*([\d:]+)", r)
            if m:
                data["cycle_start_time"] = m.group(1)

        elif qcode == "Q500":
            # PROGRAM, O1234, RUNNING, PARTS, 47, S1200, F25.0
            m = re.search(
                r"PROGRAM,\s*(\S+),\s*([^,]+),\s*PARTS,\s*(\d+)", r
            )
            if m:
                data["program"]        = m.group(1)
                data["program_status"] = m.group(2).strip()
                data["parts_count"]    = int(m.group(3))

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
