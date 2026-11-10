import math
import re

NUMBER = "(?:\\d+(?:[.,]\\d+)?|[.,]\\d+)"
LABEL = re.compile(f"^\\s*(D\\s*)?({NUMBER})\\s*cm\\s*$", re.I)
ALTERNATIVES = re.compile(f"^\\s*(D\\s*)?({NUMBER})\\s*/\\s*({NUMBER})\\s*cm\\s*$", re.I)
BARE = re.compile(f"^\\s*(D\\s*)?({NUMBER})\\s*$", re.I)


def parse_numeric(raw):
    result = {"value_cm": None, "alternatives_cm": [], "door_marker": False, "issue": None}
    match = LABEL.fullmatch(raw)
    if match:
        number = float(match[2].replace(",", "."))
        result["door_marker"] = bool(match[1])
        if not math.isfinite(number) or not 0 < number <= 1000000000.0:
            result["issue"] = "SKETCH_NUMBER_OUT_OF_RANGE"
        else:
            result["value_cm"] = number
            result["alternatives_cm"] = [number]
        return result
    alt = ALTERNATIVES.fullmatch(raw)
    if alt:
        result["door_marker"] = bool(alt[1])
        result["alternatives_cm"] = [float(v.replace(",", ".")) for v in alt.group(2, 3)]
        if any((not 0 < v <= 1000000000.0 for v in result["alternatives_cm"])):
            result["alternatives_cm"] = []
            result["issue"] = "SKETCH_NUMBER_OUT_OF_RANGE"
        else:
            result["issue"] = "SKETCH_NUMBER_AMBIGUOUS"
    elif BARE.fullmatch(raw):
        result["issue"] = "SKETCH_UNIT_MISSING"
    elif re.search("\\d", raw):
        result["issue"] = (
            "SKETCH_UNIT_UNSUPPORTED"
            if re.search("(?:\\d\\s*(?:m|mm|ft|feet|inch|inches|in)\\b|[\\'\\\"])", raw, re.I)
            else "SKETCH_NUMBER_UNREADABLE"
        )
    else:
        result["issue"] = "SKETCH_TEXT_NON_DIMENSION"
    return result
