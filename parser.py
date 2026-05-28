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
    return response if response else None


def parse_position(response, axis):
    m = re.search(rf"{axis}[,\s]*([-\d.]+)", response or "", re.I)
    if m:
        try:
            return float(m.group(1))
        except:
            return None
    return None


def parse_responses(raw):
    data = {}

    for qcode, raw_response in raw.items():
        r = clean(raw_response)
        if not r:
            continue

        if qcode == "Q100":
            m = re.search(r"S/N,\s*(\d+)", r)
            if m:
                data["serial_number"] = m.group(1)

        elif qcode == "Q104":
            m = re.search(r"MODE,\s*\((.+?)\)", r)
            if m:
                data["mode"] = m.group(1)

        elif qcode == "Q200":
            m = re.search(r"TOOL CHANGES,\s*(\d+)", r)
            if m:
                data["tool_changes"] = int(m.group(1))

        elif qcode == "Q201":
            m = re.search(r"USING TOOL,\s*(\d+)", r)
            if m:
                data["current_tool"] = int(m.group(1))

        elif qcode == "Q301":
            m = re.search(r"C\.S\. TIME,\s*([\d:]+)", r)
            if m:
                data["cycle_start_time"] = m.group(1)

        elif qcode == "Q500":
            m = re.search(
                r"PROGRAM,\s*(\S+),\s*(\w+),\s*PARTS,\s*(\d+)", r
            )
            if m:
                data["program"] = m.group(1)
                data["program_status"] = m.group(2)
                data["parts_count"] = int(m.group(3))

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

    return data