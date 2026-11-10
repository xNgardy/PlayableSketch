import re


def region_names(regions):
    counts = {"room": 0, "corridor_segment": 0}
    names = {}
    for region in regions:
        kind = region["type"]
        counts[kind] += 1
        name = region["name"]
        if re.fullmatch("(?:Room|Corridor) \\d+", name):
            name = ("Room " if kind == "room" else "Corridor ") + str(counts[kind])
        names[region["id"]] = name
    return names
