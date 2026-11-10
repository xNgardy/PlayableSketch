import argparse
import hashlib
import json
from pathlib import Path
from SketchPipeline.validation.validate import load_json, validate_document


def export_legacy(document, observations):
    if observations is None:
        raise ValueError("The linked observation document is required for legacy export.")
    checked = validate_document(document, observations)
    if not checked["exportable"]:
        raise ValueError("A validated metric layout with matching observations is required.")
    layout = document["layout"]
    if len(layout["rooms"]) != 2 or len(layout["corridors"]) != 1:
        raise ValueError(
            "Step 04 supports exactly two rooms and one straight rectangular corridor. Use the Step 05 explicit builder for other layouts."
        )
    if len(layout["openings"]) != 2 or any((o["type"] != "door" for o in layout["openings"])):
        raise ValueError(
            "The legacy connection requires a door at each corridor entrance; open passages are not silently converted to doors."
        )
    if document["start_room_id"] is None or document["goal_room_id"] is None:
        raise ValueError("Choose Start and Goal rooms explicitly before legacy export.")
    points = {v["id"]: v["position_cm"] for v in layout["vertices"]}
    walls = {w["id"]: w for w in layout["walls"]}

    def bounds(region):
        values = [points[v] for v in region["boundary_vertex_ids"]]
        return [
            min((p[0] for p in values)),
            min((p[1] for p in values)),
            max((p[0] for p in values)),
            max((p[1] for p in values)),
        ]

    def integer(value):
        if value <= 0 or not float(value).is_integer():
            raise ValueError(
                "Legacy int32 dimensions require exact positive whole centimeters; no rounding is applied."
            )
        return int(value)

    settings = document["settings"]
    thickness = settings["wall_thickness_cm"]
    half = thickness / 2
    corridor = layout["corridors"][0]
    cb = bounds(corridor)
    rooms, doors = ([], {})
    for region in layout["rooms"]:
        rb = bounds(region)
        room = {
            "id": region["id"],
            "name": region["name"],
            "min_cm": [rb[0] + half, rb[1] + half],
            "width_cm": integer(rb[2] - rb[0] - thickness),
            "depth_cm": integer(rb[3] - rb[1] - thickness),
        }
        rooms.append(room)
        matches = [
            o
            for o in layout["openings"]
            if {e["id"] for e in o["connected_entities"]} == {region["id"], corridor["id"]}
        ]
        if len(matches) != 1:
            raise ValueError("Each room must have exactly one door to the corridor.")
        opening = matches[0]
        wall = walls[opening["wall_id"]]
        center = list(points[wall["start_vertex_id"]])
        axis = 0 if wall["axis"] == "x" else 1
        center[axis] += opening["center_offset_cm"]
        if center[0] == rb[2]:
            side = "east"
        elif center[0] == rb[0]:
            side = "west"
        elif center[1] == rb[3]:
            side = "north"
        elif center[1] == rb[1]:
            side = "south"
        else:
            raise ValueError("Door center is not on the room boundary.")
        along = 0 if side in ("north", "south") else 1
        doors[region["id"]] = {
            "side": side,
            "offset_cm": center[along] - room["min_cm"][along],
            "width_cm": integer(opening["clear_width_cm"]),
            "center": center,
        }
    a, b = rooms
    da, db = (doors[a["id"]], doors[b["id"]])
    if da["width_cm"] != db["width_cm"]:
        raise ValueError(
            "The legacy connection uses one shared door width; unequal door widths require the explicit builder."
        )
    horizontal = {da["side"], db["side"]} == {"east", "west"}
    vertical = {da["side"], db["side"]} == {"north", "south"}
    axis = 0 if horizontal else 1
    if not (horizontal or vertical) or da["center"][1 - axis] != db["center"][1 - axis]:
        raise ValueError("Door centers must face each other on one straight axis.")
    low, high = sorted((da["center"][axis], db["center"][axis]))
    if (cb[axis], cb[axis + 2]) != (low, high) or da["center"][1 - axis] != (
        cb[1 - axis] + cb[3 - axis]
    ) / 2:
        raise ValueError("Corridor bounds must run exactly between the two door centers.")
    for room, door in ((a, da), (b, db)):
        expected_side = (
            ("east" if horizontal else "north")
            if door["center"][axis] == low
            else "west" if horizontal else "south"
        )
        if door["side"] != expected_side:
            raise ValueError("Corridor doors do not face into the corridor.")
    clear_width = integer(cb[3 - axis] - cb[1 - axis] - thickness)
    expected_min, expected_max = (cb[:2], cb[2:])
    expected_min[axis] -= half
    expected_max[axis] += half
    expected_min[1 - axis] += half
    expected_max[1 - axis] -= half
    connection = {
        "id": corridor["id"],
        "room_a_id": a["id"],
        "room_b_id": b["id"],
        "corridor_width_cm": clear_width,
        "door_width_cm": da["width_cm"],
        "door_a": {"side": da["side"], "offset_cm": da["offset_cm"]},
        "door_b": {"side": db["side"], "offset_cm": db["offset_cm"]},
        "expected_corridor_min_cm": expected_min,
        "expected_corridor_max_cm": expected_max,
    }
    return {
        "schema_version": "playablesketch-legacy-import/1.0",
        "units": "cm",
        "dimension_basis": "clear_inside",
        "source_document_id": document["document_id"],
        "source_revision_id": document["revision_id"],
        "source_layout_sha256": hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "start_room_id": document["start_room_id"],
        "goal_room_id": document["goal_room_id"],
        "settings": {k: v for k, v in settings.items() if k != "source"},
        "rooms": rooms,
        "connections": [connection],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export two rooms + one straight corridor + two doors, without approximation."
    )
    parser.add_argument("layout", type=Path)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new path to preserve it.")
    try:
        output = export_legacy(load_json(args.layout), load_json(args.observations))
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
