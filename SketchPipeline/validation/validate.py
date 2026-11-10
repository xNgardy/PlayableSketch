import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
VERSION = "metric-validator/1.0"
TOLERANCE_CM = 0.001
SCHEMAS = {}
for _path in sorted(SCHEMA_DIR.glob("*.schema.json")):
    _schema = json.loads(_path.read_text())
    Draft202012Validator.check_schema(_schema)
    SCHEMAS[_schema["$id"]] = _schema
REGISTRY = Registry().with_resources(
    ((key, Resource.from_contents(value)) for key, value in SCHEMAS.items())
)
KINDS = {
    "observations": "urn:playablesketch:observations:1",
    "draft_layout": "urn:playablesketch:draft-layout:1",
    "validated_layout": "urn:playablesketch:validated-layout:1",
}


def load_json(path):

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Non-finite JSON constant: {value}")

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=constant)


def validate_document(document, observations=None):
    issues = []

    def issue(code, message, ids=()):
        value = {"code": code, "severity": "error", "element_ids": list(ids), "message": message}
        if value not in issues:
            issues.append(value)

    def result(schema_valid, metric_valid=False):
        return {
            "schema_valid": schema_valid,
            "metric_valid": metric_valid,
            "exportable": bool(
                schema_valid and metric_valid and (document.get("kind") == "validated_layout")
            ),
            "issues": issues,
        }

    def finite(value):
        if isinstance(value, float) and (not math.isfinite(value)):
            return False
        if isinstance(value, dict):
            return all((finite(v) for v in value.values()))
        if isinstance(value, list):
            return all((finite(v) for v in value))
        return True

    if not isinstance(document, dict) or not finite(document):
        issue("SKETCH_SCHEMA_INVALID", "Expected a finite JSON object.")
        return result(False)
    schema_id = KINDS.get(document.get("kind"))
    if schema_id is None:
        issue("SKETCH_SCHEMA_INVALID", "Unsupported document kind.")
        return result(False)
    validator = Draft202012Validator(SCHEMAS[schema_id], registry=REGISTRY)
    for error in validator.iter_errors(document):
        issue(
            "SKETCH_SCHEMA_INVALID", f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    if issues:
        return result(False)

    def index(items):
        indexed = {}
        for item in items:
            if item["id"] in indexed:
                issue("SKETCH_ID_DUPLICATE", "IDs must be unique.", [item["id"]])
            indexed[item["id"]] = item
        return indexed

    if document["kind"] == "observations":
        index(document["texts"] + document["lines"] + document["opening_candidates"])
        matrix = document["frame"]["original_to_frame"]
        determinant = sum(
            (
                matrix[0][i]
                * (
                    matrix[1][(i + 1) % 3] * matrix[2][(i + 2) % 3]
                    - matrix[1][(i + 2) % 3] * matrix[2][(i + 1) % 3]
                )
                for i in range(3)
            )
        )
        if determinant == 0:
            issue("SKETCH_FRAME_INVALID", "Image transform must be invertible.")
        width, height = (document["frame"]["width_px"], document["frame"]["height_px"])
        for text in document["texts"]:
            if document["region_annotation_status"] == "complete" and text["polygon_px"] is None:
                issue(
                    "SKETCH_EVIDENCE_MISSING",
                    "Complete text annotations require pixel polygons.",
                    [text["id"]],
                )
        polygons = [t["polygon_px"] for t in document["texts"] if t["polygon_px"]]
        polygons += [o["polygon_px"] for o in document["opening_candidates"]]
        points = [p for polygon in polygons for p in polygon]
        points += [p for line in document["lines"] for p in (line["start_px"], line["end_px"])]
        if any(
            (
                width is not None and x > width or (height is not None and y > height)
                for x, y in points
            )
        ):
            issue("SKETCH_EVIDENCE_OUT_OF_BOUNDS", "Pixel coordinates exceed the declared frame.")
        return result(True)
    layout = document["layout"]
    all_entities = [entity for values in layout.values() for entity in values]
    index(all_entities)
    vertices, walls = (index(layout["vertices"]), index(layout["walls"]))
    regions = index(layout["rooms"] + layout["corridors"])
    openings = index(layout["openings"])
    room_ids, corridor_ids = ({r["id"] for r in layout[key]} for key in ("rooms", "corridors"))
    if any((r["role"] != "none" for r in layout["corridors"])):
        issue("SKETCH_ROLE_INVALID", "Start/Goal roles belong to rooms, not corridors.")
    if not room_ids:
        issue("SKETCH_GEOMETRY_INCOMPLETE", "A layout must contain at least one room.")
    settings = document["settings"]
    if settings["door_height_cm"] > settings["wall_height_cm"]:
        issue("SKETCH_OPENING_OUT_OF_BOUNDS", "Default door height exceeds wall height.")
    if observations is not None:
        checked = validate_document(observations)
        if (
            observations.get("kind") != "observations"
            or not checked["schema_valid"]
            or checked["issues"]
        ):
            issue("SKETCH_EVIDENCE_INVALID", "The observation document is invalid.")
        elif (
            observations["document_id"] != document["observation_document_id"]
            or observations["source"]["image_sha256"] != document["source"]["image_sha256"]
        ):
            issue("SKETCH_EVIDENCE_INVALID", "Observation identity/image hash mismatch.")
        else:
            evidence_ids = {
                v["id"]
                for key in ("texts", "lines", "opening_candidates")
                for v in observations[key]
            }
            for entity in all_entities:
                if any((e not in evidence_ids for e in entity["provenance"]["evidence_ids"])):
                    issue(
                        "SKETCH_REFERENCE_MISSING",
                        "Unknown observation evidence ID.",
                        [entity["id"]],
                    )

    def known(point):
        return all((v is not None for v in point))

    points = {key: v["position_cm"] for key, v in vertices.items()}
    known_points = {}
    for key, vertex in vertices.items():
        point = points[key]
        if not known(point):
            issue("SKETCH_GEOMETRY_INCOMPLETE", "Vertex position is unresolved.", [key])
        else:
            if tuple(point) in known_points:
                issue(
                    "SKETCH_VERTEX_DUPLICATE",
                    "Coincident junctions must share one vertex ID.",
                    [known_points[tuple(point)], key],
                )
            known_points[tuple(point)] = key
        if vertex["state"] not in ("confirmed", "derived", "missing", "conflicting"):
            issue("SKETCH_REVIEW_REQUIRED", "Inferred coordinates require review.", [key])
    wall_points = {}
    wall_keys = set()
    for key, wall in walls.items():
        if (
            wall["thickness_cm"] != settings["wall_thickness_cm"]
            or wall["height_cm"] != settings["wall_height_cm"]
        ):
            issue(
                "SKETCH_SETTINGS_CONFLICT",
                "Resolved walls must match the v1 global settings.",
                [key],
            )
        a_id, b_id = (wall["start_vertex_id"], wall["end_vertex_id"])
        if a_id not in vertices or b_id not in vertices:
            issue("SKETCH_REFERENCE_MISSING", "Wall endpoint does not exist.", [key])
            continue
        pair = tuple(sorted((a_id, b_id)))
        if pair in wall_keys:
            issue("SKETCH_WALL_DUPLICATE", "A boundary must be represented by one wall.", [key])
        wall_keys.add(pair)
        if any((r not in regions for r in wall["region_ids"])):
            issue("SKETCH_REFERENCE_MISSING", "Wall owner region does not exist.", [key])
        a, b = (points[a_id], points[b_id])
        if not known(a) or not known(b):
            continue
        axis = 0 if wall["axis"] == "x" else 1
        if a[1 - axis] != b[1 - axis] or b[axis] - a[axis] <= TOLERANCE_CM:
            issue(
                "SKETCH_WALL_INVALID",
                "Wall must be nonzero, orthogonal and oriented in its positive axis.",
                [key],
            )
            continue
        wall_points[key] = (a, b, axis)
    bounds = {}
    owners = {key: set() for key in walls}
    for key, region in regions.items():
        ids, edges = (region["boundary_vertex_ids"], region["boundary_wall_ids"])
        if (
            len(ids) != len(edges)
            or any((v not in points for v in ids))
            or any((w not in walls for w in edges))
        ):
            issue(
                "SKETCH_BOUNDARY_INVALID",
                "Boundary requires matching cyclic vertex/wall references.",
                [key],
            )
            continue
        for i, edge in enumerate(edges):
            owners[edge].add(key)
            wall = walls[edge]
            if {wall["start_vertex_id"], wall["end_vertex_id"]} != {
                ids[i],
                ids[(i + 1) % len(ids)],
            }:
                issue(
                    "SKETCH_BOUNDARY_INVALID",
                    "Wall does not connect the corresponding boundary vertices.",
                    [key, edge],
                )
        polygon = [points[v] for v in ids]
        if not all((known(p) for p in polygon)):
            continue
        xmin, ymin = map(min, zip(*polygon))
        xmax, ymax = map(max, zip(*polygon))
        area = (
            sum((a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2
        )
        rectangular = (
            xmax > xmin
            and ymax > ymin
            and (abs(area - (xmax - xmin) * (ymax - ymin)) <= TOLERANCE_CM)
            and all((x in (xmin, xmax) or y in (ymin, ymax) for x, y in polygon))
        )
        for a, b, c in zip(polygon, polygon[1:] + polygon[:1], polygon[2:] + polygon[:2]):
            ab, bc = ((b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1]))
            if (
                ab[0]
                and ab[1]
                or (bc[0] and bc[1])
                or ab[0] * bc[1] - ab[1] * bc[0] < 0
                or (ab[0] * bc[0] + ab[1] * bc[1] < 0)
            ):
                rectangular = False
        if not rectangular:
            issue(
                "SKETCH_UNSUPPORTED_GEOMETRY",
                "Region must be a counterclockwise rectangle with optional collinear junctions.",
                [key],
            )
        else:
            bounds[key] = (xmin, ymin, xmax, ymax)
    for key, wall in walls.items():
        if set(wall["region_ids"]) != owners[key]:
            issue(
                "SKETCH_WALL_OWNERSHIP", "Wall owners must match region boundary references.", [key]
            )
    for i, (a, ba) in enumerate(bounds.items()):
        for b, bb in list(bounds.items())[i + 1 :]:
            if (
                min(ba[2], bb[2]) - max(ba[0], bb[0]) > TOLERANCE_CM
                and min(ba[3], bb[3]) - max(ba[1], bb[1]) > TOLERANCE_CM
            ):
                issue("SKETCH_REGION_OVERLAP", "Room/corridor interiors overlap.", [a, b])
    entries = list(wall_points.items())
    for i, (aid, (a, b, axis)) in enumerate(entries):
        for bid, (c, d, other_axis) in entries[i + 1 :]:
            shared = {walls[aid]["start_vertex_id"], walls[aid]["end_vertex_id"]} & {
                walls[bid]["start_vertex_id"],
                walls[bid]["end_vertex_id"],
            }
            if axis == other_axis:
                if (
                    a[1 - axis] == c[1 - axis]
                    and min(b[axis], d[axis]) - max(a[axis], c[axis]) > TOLERANCE_CM
                ):
                    issue("SKETCH_WALL_DUPLICATE", "Collinear walls overlap.", [aid, bid])
            else:
                intersection = [c[0], a[1]] if axis == 0 else [a[0], c[1]]
                if all(
                    (
                        min(p[j], q[j]) <= intersection[j] <= max(p[j], q[j])
                        for p, q in ((a, b), (c, d))
                        for j in (0, 1)
                    )
                ) and (not shared):
                    issue(
                        "SKETCH_TOPOLOGY_UNNODED",
                        "Intersecting walls must share an endpoint vertex.",
                        [aid, bid],
                    )
    centers, intervals = ({}, {})

    def check_entities(values, owner):
        for e in values:
            valid = room_ids if e["type"] == "room" else corridor_ids
            if e["id"] not in valid:
                issue(
                    "SKETCH_REFERENCE_MISSING",
                    "Connected entity type/ID does not exist.",
                    [owner, e["id"]],
                )

    for key, opening in openings.items():
        wall = walls.get(opening["wall_id"])
        check_entities(opening["connected_entities"], key)
        if wall is None:
            issue("SKETCH_REFERENCE_MISSING", "Opening wall does not exist.", [key])
            continue
        if {e["id"] for e in opening["connected_entities"]} != set(wall["region_ids"]) or len(
            wall["region_ids"]
        ) != 2:
            issue(
                "SKETCH_OPENING_CONNECTION",
                "An interior opening must connect exactly the two wall-owner regions.",
                [key],
            )
        if opening["clear_height_cm"] > wall["height_cm"]:
            issue("SKETCH_OPENING_OUT_OF_BOUNDS", "Opening height exceeds its wall.", [key])
        expected_height = (
            settings["door_height_cm"] if opening["type"] == "door" else settings["wall_height_cm"]
        )
        if opening["clear_height_cm"] != expected_height:
            issue(
                "SKETCH_SETTINGS_CONFLICT", "Opening height does not match its v1 settings.", [key]
            )
        offset, width = (opening["center_offset_cm"], opening["clear_width_cm"])
        if offset is None or width is None:
            issue("SKETCH_DIMENSION_MISSING", "Opening offset/width is unresolved.", [key])
            continue
        if opening["state"] not in ("confirmed", "derived"):
            issue("SKETCH_REVIEW_REQUIRED", "Opening measurements require review.", [key])
        if opening["wall_id"] not in wall_points:
            continue
        a, b, axis = wall_points[opening["wall_id"]]
        length = b[axis] - a[axis]
        corridor = next(
            (e["id"] for e in opening["connected_entities"] if e["type"] == "corridor"), None
        )
        if (
            opening["type"] == "open_passage"
            and opening["state"] == "derived"
            and (corridor in bounds)
        ):
            expected_width = length - settings["wall_thickness_cm"]
            if abs(width - expected_width) > TOLERANCE_CM:
                issue(
                    "SKETCH_SETTINGS_CONFLICT",
                    "Derived entrance width must be recomputed from shared interface span and wall thickness.",
                    [key],
                )
        lo, hi = (offset - width / 2, offset + width / 2)
        if lo < -TOLERANCE_CM or hi > length + TOLERANCE_CM:
            issue(
                "SKETCH_OPENING_OUT_OF_BOUNDS",
                "Opening interval lies outside its supporting wall.",
                [key],
            )
        for other, old_lo, old_hi in intervals.setdefault(opening["wall_id"], []):
            if min(hi, old_hi) - max(lo, old_lo) > TOLERANCE_CM:
                issue("SKETCH_OPENING_OVERLAP", "Openings overlap on the same wall.", [other, key])
        intervals[opening["wall_id"]].append((key, lo, hi))
        center = list(a)
        center[axis] += offset
        centers[key] = center
    passage_counts = {key: 0 for key in openings}
    for passage in layout["passages"]:
        key = passage["id"]
        check_entities(passage["connected_entities"], key)
        opening = openings.get(passage["opening_id"])
        if opening is None:
            issue("SKETCH_REFERENCE_MISSING", "Passage opening does not exist.", [key])
        else:
            passage_counts[opening["id"]] += 1
            if passage["type"] != opening["type"] or sorted(
                ((v["type"], v["id"]) for v in passage["connected_entities"])
            ) != sorted(((v["type"], v["id"]) for v in opening["connected_entities"])):
                issue(
                    "SKETCH_PASSAGE_INVALID",
                    "Passage must match its opening type and connected regions.",
                    [key],
                )
    for key, count in passage_counts.items():
        if count != 1:
            issue("SKETCH_PASSAGE_INVALID", "Each opening requires exactly one passage.", [key])
    measured_targets = {}
    for dimension in layout["dimensions"]:
        key, value, target = (dimension["id"], dimension["value_cm"], dimension["target"])
        signature = json.dumps({"target": target, "basis": dimension["basis"]}, sort_keys=True)
        if value is None:
            issue("SKETCH_DIMENSION_MISSING", "Dimension is unresolved.", [key])
        elif dimension["state"] in ("confirmed", "derived"):
            old = measured_targets.get(signature)
            if old and abs(old[1] - value) > TOLERANCE_CM:
                issue(
                    "SKETCH_DIMENSION_CONFLICT",
                    "Confirmed dimensions of the same span disagree.",
                    [old[0], key],
                )
            measured_targets[signature] = (key, value)
        if (value is None) != (dimension["state"] == "missing"):
            issue("SKETCH_DIMENSION_STATE", "Only missing dimensions may have null values.", [key])
        if dimension["state"] in ("inferred", "conflicting"):
            issue("SKETCH_REVIEW_REQUIRED", "Dimension requires correction or confirmation.", [key])
        measured = None
        kind = target["type"]
        expected_bases = (
            ("clear_opening",)
            if kind == "opening_width"
            else (
                ("center_offset", "edge_offset")
                if kind == "opening_offset"
                else ("edge_offset",) if kind == "opening_separation" else ("wall_centerline",)
            )
        )
        if kind != "unassigned" and dimension["basis"] not in expected_bases:
            issue("SKETCH_DIMENSION_BASIS", "Measurement basis does not match its target.", [key])
        if kind == "unassigned":
            issue("SKETCH_ASSOCIATION_PENDING", "Dimension target is unresolved.", [key])
        elif kind == "region_span":
            if target["region_id"] not in regions:
                issue("SKETCH_REFERENCE_MISSING", "Dimension region does not exist.", [key])
            elif target["region_id"] in bounds:
                bound = bounds[target["region_id"]]
                axis = 0 if target["axis"] == "x" else 1
                measured = bound[axis + 2] - bound[axis]
        elif kind == "opening_separation":
            first, second = (
                openings.get(target["from_opening_id"]),
                openings.get(target["to_opening_id"]),
            )
            if first is None or second is None:
                issue(
                    "SKETCH_REFERENCE_MISSING",
                    "Opening separation references an unknown opening.",
                    [key],
                )
            elif first["id"] == second["id"] or first["wall_id"] != second["wall_id"]:
                issue(
                    "SKETCH_DIMENSION_TARGET",
                    "Opening separation requires two distinct openings on the same wall.",
                    [key],
                )
            elif first["id"] in centers and second["id"] in centers:
                measured = (
                    second["center_offset_cm"]
                    - second["clear_width_cm"] / 2
                    - first["center_offset_cm"]
                    - first["clear_width_cm"] / 2
                )
                if measured < 0:
                    issue(
                        "SKETCH_DIMENSION_TARGET",
                        "Opening separation must follow the positive wall direction.",
                        [key],
                    )
        elif kind == "wall_chain":
            chain = target["wall_ids"]
            if any((w not in walls for w in chain)):
                issue(
                    "SKETCH_REFERENCE_MISSING",
                    "Dimension wall chain references an unknown wall.",
                    [key],
                )
            elif all((w in wall_points for w in chain)):
                lines = [wall_points[w] for w in chain]
                if any((a[2] != b[2] or a[1] != b[0] for a, b in zip(lines, lines[1:]))):
                    issue(
                        "SKETCH_DIMENSION_TARGET",
                        "Wall chain must be ordered, contiguous and collinear.",
                        [key],
                    )
                else:
                    measured = sum((b[axis] - a[axis] for a, b, axis in lines))
        else:
            opening = openings.get(target["opening_id"])
            if opening is None:
                issue("SKETCH_REFERENCE_MISSING", "Dimension opening does not exist.", [key])
            elif kind == "opening_width":
                measured = opening["clear_width_cm"]
            else:
                region_id = target["region_id"]
                if region_id not in regions:
                    issue("SKETCH_REFERENCE_MISSING", "Offset region does not exist.", [key])
                elif region_id not in {v["id"] for v in opening["connected_entities"]}:
                    issue(
                        "SKETCH_DIMENSION_TARGET",
                        "Offset region is not connected to the opening.",
                        [key],
                    )
                elif region_id in bounds and opening["id"] in centers:
                    bound, center = (bounds[region_id], centers[opening["id"]])
                    side = target["side"]
                    axis = 0 if side in ("north", "south") else 1
                    fixed_axis = 1 - axis
                    boundary = bound[fixed_axis + (2 if side in ("north", "east") else 0)]
                    if abs(center[fixed_axis] - boundary) > TOLERANCE_CM:
                        issue(
                            "SKETCH_DIMENSION_TARGET",
                            "Opening is not on the specified region side.",
                            [key],
                        )
                    measured = (
                        bound[axis + 2] - center[axis]
                        if target["reference"] == "max_corner"
                        else center[axis] - bound[axis]
                    )
                    if dimension["basis"] == "edge_offset":
                        measured -= opening["clear_width_cm"] / 2
        if value is not None and measured is not None and (abs(value - measured) > TOLERANCE_CM):
            issue(
                "SKETCH_DIMENSION_CONFLICT",
                "Dimension disagrees with reconstructed geometry.",
                [key],
            )
    for role in ("start", "goal"):
        reference = document[f"{role}_room_id"]
        tagged = {r["id"] for r in layout["rooms"] if r["role"] == role}
        if (
            reference is not None
            and reference not in room_ids
            or tagged != ({reference} if reference else set())
        ):
            issue("SKETCH_ROLE_INVALID", "Room roles and Start/Goal references must agree.")
    if (
        document["start_room_id"] is not None
        and document["start_room_id"] == document["goal_room_id"]
    ):
        issue("SKETCH_ROLE_INVALID", "Start and Goal must be different rooms.")
    if document["validation_mode"] == "gameplay":
        if document["start_room_id"] is None or document["goal_room_id"] is None:
            issue("SKETCH_ROLE_INVALID", "Gameplay mode requires Start and Goal.")
        else:
            reachable = {document["start_room_id"]}
            while True:
                expanded = reachable | {
                    e["id"]
                    for p in layout["passages"]
                    if any((e["id"] in reachable for e in p["connected_entities"]))
                    for e in p["connected_entities"]
                }
                if expanded == reachable:
                    break
                reachable = expanded
            if not room_ids <= reachable:
                issue(
                    "SKETCH_CONNECTIVITY_INVALID",
                    "All gameplay rooms must be connected to Start through passages.",
                )
    for cached in document["issues"]:
        if cached["severity"] == "error" and cached not in issues:
            issues.append(cached)
    return result(True, not issues)


def as_validated(draft, reviewer, observations=None):
    if not reviewer or not reviewer.strip():
        raise ValueError("A named reviewer is required.")
    if draft.get("kind") != "draft_layout":
        raise ValueError("Expected a draft layout.")
    if observations is None and any(
        (
            e.get("provenance", {}).get("evidence_ids")
            for values in draft.get("layout", {}).values()
            for e in values
        )
    ):
        raise ValueError("The observation document is required to accept linked evidence.")
    report = validate_document(draft, observations)
    if not report["schema_valid"] or not report["metric_valid"]:
        raise ValueError("Layout is incomplete, conflicting, or invalid.")
    output = copy.deepcopy(draft)
    output.update(
        kind="validated_layout",
        status="validated",
        parent_revision_id=draft["revision_id"],
        revision_id=draft["revision_id"] + "-accepted",
    )
    output["review"] = {"status": "accepted", "reviewer": reviewer}
    output["validation"] = {
        "metric": "passed",
        "validator_version": VERSION,
        "tolerance_cm": TOLERANCE_CM,
        "engine_geometry": "not_run",
        "navigation": "not_run",
    }
    checked = validate_document(output, observations)
    if not checked["exportable"]:
        raise ValueError("Validated export rejected: " + json.dumps(checked["issues"]))
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Offline schema/reference/orthogonal metric validation, not Unreal validation."
    )
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        try:
            document = load_json(path)
            observation_path = path.with_name(
                path.name.replace(".draft.json", ".observations.json").replace(
                    ".validated.json", ".observations.json"
                )
            )
            observations = (
                load_json(observation_path)
                if isinstance(document, dict)
                and document.get("kind") != "observations"
                and observation_path.exists()
                else None
            )
            report = validate_document(document, observations)
            if report["schema_valid"] and (
                not (path.parent / document["source"]["image_path"]).is_file()
                or hashlib.sha256(
                    (path.parent / document["source"]["image_path"]).read_bytes()
                ).hexdigest()
                != document["source"]["image_sha256"]
            ):
                report["issues"].append(
                    {
                        "code": "SKETCH_SOURCE_MISMATCH",
                        "severity": "error",
                        "element_ids": [],
                        "message": "Source image is missing or changed.",
                    }
                )
                report.update(metric_valid=False, exportable=False)
            failed |= bool(report["issues"])
        except (ValueError, KeyError, OSError) as error:
            report = {
                "schema_valid": False,
                "metric_valid": False,
                "exportable": False,
                "issues": [
                    {
                        "code": "SKETCH_INPUT_INVALID",
                        "severity": "error",
                        "element_ids": [],
                        "message": str(error),
                    }
                ],
            }
            failed = True
        print(json.dumps({"path": str(path), **report}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
