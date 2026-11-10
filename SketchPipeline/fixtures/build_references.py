import argparse
import json
import struct
from pathlib import Path
from SketchPipeline.validation.validate import as_validated, validate_document

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Data" / "ground_truth"
OUTPUT = SOURCE / "v1"


def provenance(method="derived", evidence=(), note=""):
    return {"method": method, "evidence_ids": list(evidence), "note": note}


def jpeg_size(path):
    data = path.read_bytes()
    cursor = 2
    while cursor < len(data):
        if data[cursor] != 255:
            raise ValueError("Invalid JPEG marker")
        while data[cursor] == 255:
            cursor += 1
        marker = data[cursor]
        cursor += 1
        size = struct.unpack(">H", data[cursor : cursor + 2])[0]
        if marker in (192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207):
            height, width = struct.unpack(">HH", data[cursor + 3 : cursor + 7])
            return (width, height)
        cursor += size
    raise ValueError("JPEG dimensions not found")


def build_case(n):
    old_path = SOURCE / f"Data_{n}.draft.json"
    old = json.loads(old_path.read_text())
    metric = old["metric_reference"]
    source = {
        "image_path": f"../../Data_{n}.jpeg",
        "image_sha256": old["source_image"]["sha256"],
        "legacy_draft_path": f"../Data_{n}.draft.json",
    }
    width, height = jpeg_size(ROOT / "Data" / f"Data_{n}.jpeg")
    obs = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": f"data_{n:02d}_observations",
        "revision_id": "manual-edge-2",
        "source": source,
        "units": "px",
        "coordinate_system": "u_right_v_down",
        "frame": {
            "id": "original",
            "width_px": width,
            "height_px": height,
            "original_to_frame": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },
        "region_annotation_status": "not_started",
        "texts": [],
        "lines": [],
        "opening_candidates": [],
        "issues": [],
        "notes": [
            "Manual numeric transcriptions only; pixel regions and strokes are not annotated.",
            "Whitespace is normalized in raw_text; numbers are not OCR predictions.",
        ],
    }
    settings = {k: v for k, v in old["settings"].items() if k != "source"}
    settings["source"] = "configured"
    layout = {
        key: []
        for key in ("vertices", "walls", "rooms", "corridors", "openings", "passages", "dimensions")
    }
    doc = {
        "schema_version": "playablesketch-layout/1.0",
        "kind": "draft_layout",
        "document_id": f"data_{n:02d}_layout",
        "revision_id": "manual-edge-2",
        "parent_revision_id": "manual-1",
        "algorithm_version": "manual-fixture-conversion/1.1",
        "observation_document_id": obs["document_id"],
        "source": source,
        "units": "cm",
        "coordinate_system": "local_x_right_y_up_z_up",
        "dimension_basis": "wall_centerline",
        "validation_mode": "geometry_only",
        "start_room_id": None,
        "goal_room_id": None,
        "settings": settings,
        "review": {"status": "pending", "reviewer": None},
        "layout": layout,
        "status": "conflicting" if n == 9 else "needs_review" if n == 10 else "draft",
        "issues": [],
        "validation": {
            "metric": "not_run",
            "validator_version": None,
            "tolerance_cm": 0.001,
            "engine_geometry": "not_run",
            "navigation": "not_run",
        },
        "notes": [
            note for note in old["notes"] if not note.startswith("This draft does not contain")
        ]
        + [
            "Author corrected paper offsets to corner-to-near-opening-edge on 2026-10-16; derived centers add half the clear width.",
            "Canonical boundary walls include logical interfaces at open corridor entrances.",
        ],
    }
    rectangles = {}
    for r in metric["rooms"]:
        x, y = r["min_cm"]
        rectangles[r["id"]] = [
            x,
            y,
            None if r["width_cm"] is None else x + r["width_cm"],
            None if r["depth_cm"] is None else y + r["depth_cm"],
        ]
    for c in metric["corridors"]:
        a, b = c["centerline_points_cm"]
        half = None if c["centerline_width_cm"] is None else c["centerline_width_cm"] / 2
        if a[1] == b[1]:
            rectangles[c["id"]] = [
                min(a[0], b[0]),
                None if half is None else a[1] - half,
                max(a[0], b[0]),
                None if half is None else a[1] + half,
            ]
        else:
            rectangles[c["id"]] = [
                None if half is None else a[0] - half,
                min(a[1], b[1]),
                None if half is None else a[0] + half,
                max(a[1], b[1]),
            ]
    corners = {
        key: [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]
        for key, b in rectangles.items()
    }
    all_corners = sorted({p for values in corners.values() for p in values if None not in p})
    point_ids, wall_ids = ({}, {})

    def vertex(point, identity):
        lookup = point if None not in point else identity
        if lookup not in point_ids:
            id = f"v{len(point_ids) + 1:03d}"
            point_ids[lookup] = id
            layout["vertices"].append(
                {
                    "id": id,
                    "position_cm": list(point),
                    "state": "derived" if None not in point else "missing",
                    "provenance": provenance(
                        note="Normalized reference coordinate from manual dimensions."
                    ),
                }
            )
        return point_ids[lookup]

    for region_id, polygon in corners.items():
        expanded = []
        for i, (a, b) in enumerate(zip(polygon, polygon[1:] + polygon[:1])):
            candidates = [a]
            if None not in a + b:
                axis = 0 if i % 2 == 0 else 1
                candidates = [
                    p
                    for p in all_corners
                    if p[1 - axis] == a[1 - axis]
                    and min(a[axis], b[axis]) <= p[axis] <= max(a[axis], b[axis])
                ]
                candidates.sort(key=lambda p: p[axis], reverse=b[axis] < a[axis])
                candidates = candidates[:-1]
            expanded += [(p, (region_id, i)) for p in candidates]
        boundary = [vertex(p, identity) for p, identity in expanded]
        ids = []
        for i, (a_id, b_id) in enumerate(zip(boundary, boundary[1:] + boundary[:1])):
            pair = tuple(sorted((a_id, b_id)))
            if pair not in wall_ids:
                a = next((v["position_cm"] for v in layout["vertices"] if v["id"] == a_id))
                b = next((v["position_cm"] for v in layout["vertices"] if v["id"] == b_id))
                axis = (
                    "x"
                    if a[1] is not None and a[1] == b[1]
                    else "y" if a[0] is not None and a[0] == b[0] else "x" if i % 2 == 0 else "y"
                )
                start, end = (a_id, b_id) if None in a + b or tuple(a) < tuple(b) else (b_id, a_id)
                id = f"w{len(wall_ids) + 1:03d}"
                wall = {
                    "id": id,
                    "start_vertex_id": start,
                    "end_vertex_id": end,
                    "axis": axis,
                    "thickness_cm": settings["wall_thickness_cm"],
                    "height_cm": settings["wall_height_cm"],
                    "region_ids": [],
                    "provenance": provenance(
                        note="Unique noded region boundary; centerline basis."
                    ),
                }
                wall_ids[pair] = wall
                layout["walls"].append(wall)
            wall_ids[pair]["region_ids"].append(region_id)
            ids.append(wall_ids[pair]["id"])
        kind = "corridors" if region_id.startswith("c") else "rooms"
        layout[kind].append(
            {
                "id": region_id,
                "name": region_id,
                "boundary_vertex_ids": boundary,
                "boundary_wall_ids": ids,
                "role": "none",
                "provenance": provenance(
                    "manual_annotation", note="Topology from photograph and prior fixture intent."
                ),
            }
        )
    points = {v["id"]: v["position_cm"] for v in layout["vertices"]}

    def add_opening(id, entities, center, clear_width, type, note):
        ids = {e["id"] for e in entities}
        matches = []
        for wall in layout["walls"]:
            a, b = (points[wall["start_vertex_id"]], points[wall["end_vertex_id"]])
            axis = 0 if wall["axis"] == "x" else 1
            if (
                set(wall["region_ids"]) == ids
                and None not in a + b
                and (center[1 - axis] == a[1 - axis])
                and (a[axis] <= center[axis] <= b[axis])
            ):
                matches.append((wall, center[axis] - a[axis]))
        if len(matches) != 1:
            raise ValueError(f"Data_{n}: opening {id} has {len(matches)} supporting walls")
        wall, offset = matches[0]
        opening = {
            "id": id,
            "wall_id": wall["id"],
            "type": type,
            "center_offset_cm": offset,
            "clear_width_cm": clear_width,
            "clear_height_cm": (
                settings["door_height_cm"] if type == "door" else settings["wall_height_cm"]
            ),
            "connected_entities": entities,
            "state": "confirmed" if type == "door" else "derived",
            "provenance": provenance(
                "manual_annotation" if type == "door" else "derived", note=note
            ),
        }
        layout["openings"].append(opening)
        layout["passages"].append(
            {
                "id": "p-" + id,
                "opening_id": id,
                "connected_entities": entities,
                "type": type,
                "provenance": provenance(
                    note="Passage through its opening; adjacency alone is not a passage."
                ),
            }
        )
        return id

    for opening in metric["doors"]:
        add_opening(
            opening["id"],
            opening["connected_entities"],
            opening["center_cm"],
            opening["clear_width_cm"],
            "door",
            "Photographed width; center is derived from the author-confirmed near-edge offset plus half the clear width.",
        )
    entrances = {}
    for c in metric["corridors"]:
        if c["centerline_width_cm"] is None:
            continue
        for region_id in c["room_ids"]:
            existing = next(
                (
                    o
                    for o in layout["openings"]
                    if {e["id"] for e in o["connected_entities"]} == {region_id, c["id"]}
                ),
                None,
            )
            if existing:
                entrances[region_id] = existing["id"]
                continue
            bound = rectangles[region_id]
            center = next(
                (
                    p
                    for p in c["centerline_points_cm"]
                    if bound[0] <= p[0] <= bound[2] and bound[1] <= p[1] <= bound[3]
                )
            )
            entities = [{"type": "room", "id": region_id}, {"type": "corridor", "id": c["id"]}]
            id = "o-" + c["id"] + "-" + region_id
            entrances[region_id] = add_opening(
                id,
                entities,
                center,
                c["centerline_width_cm"] - settings["wall_thickness_cm"],
                "open_passage",
                "Open entrance from prior fixture intent; clear width derived from centerline width minus equal boundary-wall thickness.",
            )

    def dimension(value, target, label, basis="wall_centerline", state="confirmed"):
        evidence = []
        if value is not None:
            id = f"t{len(obs['texts']) + 1:03d}"
            obs["texts"].append(
                {
                    "id": id,
                    "raw_text": f"{value} cm",
                    "polygon_px": None,
                    "parsed_value_cm": value,
                    "score": None,
                    "method": "manual_transcription",
                }
            )
            evidence = [id]
        layout["dimensions"].append(
            {
                "id": f"m{len(layout['dimensions']) + 1:03d}",
                "value_cm": value,
                "basis": basis,
                "target": target,
                "state": "missing" if value is None else state,
                "span_label": label,
                "provenance": provenance(
                    "manual_annotation",
                    evidence,
                    "Manual label-to-span annotation; no pixel region yet.",
                ),
            }
        )

    def size(region, axis, value, label):
        dimension(value, {"type": "region_span", "region_id": region, "axis": axis}, label)

    if n == 9:
        for span in metric["observed_spans"]:
            side = span["target"].split(".")[1]
            size("rA", "x" if side.startswith(("top", "bottom")) else "y", span["value_cm"], side)
    else:
        for r in metric["rooms"]:
            size(r["id"], "x", r["width_cm"], r["id"] + ".width")
            size(r["id"], "y", r["depth_cm"], r["id"] + ".depth")
        for c in metric["corridors"]:
            horizontal = c["centerline_points_cm"][0][1] == c["centerline_points_cm"][1][1]
            size(c["id"], "x" if horizontal else "y", c["length_cm"], c["id"] + ".length")
            size(c["id"], "y" if horizontal else "x", c["centerline_width_cm"], c["id"] + ".width")
        for opening in metric["doors"]:
            dimension(
                opening["clear_width_cm"],
                {"type": "opening_width", "opening_id": opening["id"]},
                opening["id"] + ".clear_width",
                "clear_opening",
            )
            room_id = next((e["id"] for e in opening["connected_entities"] if e["type"] == "room"))
            bound = rectangles[room_id]
            center = opening["center_cm"]
            side = (
                "north"
                if opening["supporting_wall_axis"] == "x" and center[1] == bound[3]
                else (
                    "south"
                    if opening["supporting_wall_axis"] == "x"
                    else "east" if center[0] == bound[2] else "west"
                )
            )
            dimension(
                opening["edge_offset_cm"],
                {
                    "type": "opening_offset",
                    "opening_id": opening["id"],
                    "region_id": room_id,
                    "side": side,
                    "reference": "min_corner",
                },
                opening["id"] + ".room_corner_offset",
                "edge_offset",
            )
        for c in metric["corridors"]:
            for region_id, offset in c["entrance_edge_offsets_cm"].items():
                if any(
                    (
                        region_id in {e["id"] for e in d["connected_entities"]}
                        for d in metric["doors"]
                    )
                ):
                    continue
                if region_id not in entrances:
                    dimension(
                        offset,
                        {"type": "unassigned"},
                        region_id + ".entrance_edge_offset",
                        "edge_offset",
                    )
                    continue
                opening_id = entrances[region_id]
                opening = next((o for o in layout["openings"] if o["id"] == opening_id))
                wall = next((w for w in layout["walls"] if w["id"] == opening["wall_id"]))
                bound = rectangles[region_id]
                a = points[wall["start_vertex_id"]]
                side = (
                    ("east" if a[0] == bound[2] else "west")
                    if horizontal
                    else "north" if a[1] == bound[3] else "south"
                )
                dimension(
                    offset,
                    {
                        "type": "opening_offset",
                        "opening_id": opening_id,
                        "region_id": region_id,
                        "side": side,
                        "reference": "min_corner",
                    },
                    region_id + ".entrance_edge_offset",
                    "edge_offset",
                )
    checked = validate_document(doc, obs)
    if not checked["schema_valid"]:
        raise ValueError(json.dumps(checked["issues"]))
    if n <= 8 and (not checked["metric_valid"]):
        raise ValueError(f"Data_{n}: " + json.dumps(checked["issues"]))
    if n >= 9:
        doc["issues"] = checked["issues"]
    return (obs, doc)


def main():
    parser = argparse.ArgumentParser(
        description="Convert the ten preserved manual drafts to v1 reference fixtures."
    )
    parser.add_argument(
        "--check", action="store_true", help="Compare generated fixtures without writing."
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Explicitly replace generated v1 fixtures."
    )
    args = parser.parse_args()
    artifacts = {}
    for n in range(1, 11):
        obs, draft = build_case(n)
        for suffix, document in [("observations", obs), ("draft", draft)]:
            artifacts[OUTPUT / f"Data_{n}.{suffix}.json"] = document
        if n <= 8:
            accepted = as_validated(draft, "manual-reference-annotation", obs)
            accepted["notes"].append(
                "Accepted metric reference fixture only; not evidence of OCR, Unreal geometry or navigation success."
            )
            artifacts[OUTPUT / f"Data_{n}.validated.json"] = accepted
    if args.check:
        mismatches = [
            str(path)
            for path, document in artifacts.items()
            if not path.exists() or json.loads(path.read_text()) != document
        ]
        if mismatches:
            raise SystemExit("Fixture differences: " + ", ".join(mismatches))
        print("All 28 fixtures match the preserved source drafts.")
        return
    if not args.overwrite and any((path.exists() for path in artifacts)):
        raise SystemExit(
            "Existing fixtures are preserved. Use --check, or explicitly --overwrite generated references."
        )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path, document in artifacts.items():
        path.write_text(json.dumps(document, indent=2) + "\n")
    print(
        "Wrote 10 observation documents, 10 drafts and 8 accepted metric references. Original drafts/images are unchanged."
    )


if __name__ == "__main__":
    main()
