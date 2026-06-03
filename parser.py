import re


def clean(response):
    if not response:
        return None

    # Strip leading Q-code echo (some serial converters echo the command back)
    response = re.sub(r"^Q\d+[^\r\n]*\r?\n?", "", response)

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


def parse_macro(response):
    """
    Parse a Q600 macro response: 'MACRO, <var_num>, <value>'
    Returns float value or None if invalid/uninitialized.
    -16777215.0 is HAAS's sentinel for an unset macro variable.
    """
    if not response:
        return None

    r = clean(response)
    if not r:
        return None

    if "INVALID" in r:
        return None

    m = re.search(r"MACRO,\s*\d+,\s*([-\d.]+)", r)
    if m:
        try:
            val = float(m.group(1))
            # -16777215 = uninitialized HAAS macro variable, discard
            if val <= -16777214 or abs(val) > 1000000:
                return None
            return val
        except ValueError:
            return None

    return None


def parse_alarms(raw: dict) -> dict:
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
                # Strip any trailing > that bleeds in from socket framing
                data["software_ver"] = m.group(1).rstrip(">")

        elif qcode == "Q104":
            # Handles MODE, MEM  and  MODE, (ZERO RET)  and  MODE, ZERORET
            m = re.search(r"MODE,\s*\(?([^)]+?)\)?$", r)
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
            m = re.search(
                r"PROGRAM,\s*(\S+),\s*([^,]+),\s*PARTS,\s*(\d+)", r
            )
            if m:
                data["program"]        = m.group(1)
                data["program_status"] = m.group(2).strip()
                data["parts_count"]    = int(m.group(3))
            else:
                # Older M-series: STATUS, BUSY  or  STATUS, IDLE
                m = re.search(r"STATUS,\s*(\w+)", r)
                if m:
                    data["program_status"] = m.group(1).strip()

            s = re.search(r"S\s*(\d+)", r)
            f = re.search(r"F\s*([\d.]+)", r)
            if s:
                data["spindle_speed"] = int(s.group(1))
            if f:
                data["feed_rate"] = float(f.group(1))

        elif qcode.startswith("Q50"):
            axis_map = {
                "Q501": "X",
                "Q502": "Y",
                "Q503": "Z",
                "Q504": "A",
                "Q505": "B",
            }
            axis = axis_map.get(qcode)
            if axis:
                data[f"{axis.lower()}_position"] = parse_position(r, axis)

    # Macro fallback — fills in positions/spindle/feed for controls that
    # don't support Q501-Q505 natively (older NGC, lathes, etc.)
    macro_map = {
        "x_position_macro":     "x_position",
        "y_position_macro":     "y_position",
        "z_position_macro":     "z_position",
        "spindle_speed_macro":  "spindle_speed",
        "feed_rate_macro":      "feed_rate",
    }

    for raw_key, data_key in macro_map.items():
        val = parse_macro(raw.get(raw_key))
        if val is not None:
            data[data_key] = val

    return data
