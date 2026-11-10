import copy
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "shape_authoring.schema.json").read_text()
)
POLICY = json.loads(Path(__file__).with_name("sizing_policy.v1.json").read_text())


def validate_authoring(document):
    errors = []

    def finite(value):
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, dict):
            return all((finite(v) for v in value.values()))
        if isinstance(value, list):
            return all((finite(v) for v in value))
        return True

    if not finite(document):
        return ["Non-finite number."]
    errors.extend(
        (f"{e.json_path}: {e.message}" for e in Draft202012Validator(SCHEMA).iter_errors(document))
    )
    if errors:
        return errors
    topology = document["topology"]
    groups = {k: {v["id"]: v for v in values} for k, values in topology.items()}
    evidence = document["image_evidence"]
    all_ids = [e["id"] for values in topology.values() for e in values]
    all_ids += [e["id"] for e in evidence["items"]]
    all_ids += [e["id"] for e in document["physical_design"]["values"]]
    if len(all_ids) != len(set(all_ids)):
        errors.append("IDs must be unique across the document.")
    regions, walls, junctions = (groups[k] for k in ("regions", "walls", "junctions"))
    evidence_ids = {e["id"] for e in evidence["items"]}
    for values in topology.values():
        for entity in values:
            geometry = entity["geometry"]
            if not set(geometry["evidence_ids"]) <= evidence_ids:
                errors.append(f"{entity['id']}: missing image evidence.")
            if len(geometry["points_px"]) != len(geometry["points_normalized"]):
                errors.append(f"{entity['id']}: geometry point counts disagree.")
    for region in regions.values():
        for wall_id in region["wall_ids"]:
            if wall_id not in walls or region["id"] not in walls[wall_id]["entity_ids"]:
                errors.append(f"{region['id']}: missing or inconsistent boundary wall.")
    for wall in walls.values():
        if (
            wall["start_junction_id"] not in junctions
            or wall["end_junction_id"] not in junctions
            or wall["start_junction_id"] == wall["end_junction_id"]
        ):
            errors.append(f"{wall['id']}: invalid junction references.")
        for entity_id in wall["entity_ids"]:
            if entity_id not in regions or wall["id"] not in regions[entity_id]["wall_ids"]:
                errors.append(f"{wall['id']}: inconsistent ownership.")
    for opening in groups["openings"].values():
        wall = walls.get(opening["support_wall_id"])
        placement = opening["placement"]
        if not wall or set(wall["entity_ids"]) != set(opening["entity_ids"]):
            errors.append(f"{opening['id']}: opening requires two supporting wall owners.")
        elif placement["reference_junction_id"] not in (
            wall["start_junction_id"],
            wall["end_junction_id"],
        ):
            errors.append(
                f"{opening['id']}: reference must be a wall endpoint (node T junctions first)."
            )
        elif (placement["direction"] == "toward_end") != (
            placement["reference_junction_id"] == wall["start_junction_id"]
        ):
            errors.append(f"{opening['id']}: reference direction points away from wall.")
        lo, hi = placement["interval_normalized"]
        expected = lo if placement["direction"] == "toward_end" else 1 - hi
        if lo >= hi or not math.isclose(expected, placement["near_edge_normalized"], abs_tol=1e-08):
            errors.append(f"{opening['id']}: inconsistent normalized opening interval.")
    for connection in groups["connections"].values():
        if not set(connection["entity_ids"]) <= regions.keys():
            errors.append(f"{connection['id']}: missing connected region.")
        span = connection["shared_span_normalized"]
        if span is not None and span[0] >= span[1]:
            errors.append(f"{connection['id']}: unordered shared span.")
        for opening_id in connection["opening_ids"]:
            opening = groups["openings"].get(opening_id)
            if not opening or set(opening["entity_ids"]) != set(connection["entity_ids"]):
                errors.append(f"{connection['id']}: inconsistent opening connection.")
    linked = [o for c in groups["connections"].values() for o in c["opening_ids"]]
    if sorted(linked) != sorted(groups["openings"]):
        errors.append("Each opening must belong to exactly one connection.")
    design = document["physical_design"]
    anchor = design["anchor"]["junction_id"]
    if anchor is not None and anchor not in junctions:
        errors.append("Missing physical anchor junction.")
    targets = set(regions) | set(walls) | set(groups["openings"]) | {"global"}
    bindings = set()
    for value in design["values"]:
        binding = (value["entity_id"], value["parameter"])
        if binding in bindings or value["entity_id"] not in targets:
            errors.append(f"{value['id']}: missing or duplicate adjustable target.")
        bindings.add(binding)
        number = value["value"]
        if number is None and value["state"] != "unknown":
            errors.append(f"{value['id']}: only unknown values may be null.")
        if number is not None and (
            number < 0 or (number == 0 and value["parameter"] != "near_edge_offset_cm")
        ):
            errors.append(f"{value['id']}: physical size must be positive; offsets may be zero.")
        if value["state"] == "current" and value["binding_revision_id"] != document["revision_id"]:
            errors.append(f"{value['id']}: current binding targets a different revision.")
    a, b = (evidence["original_to_working"], evidence["working_to_original"])
    product = [[sum((a[i][k] * b[k][j] for k in range(3))) for j in range(3)] for i in range(3)]
    scale = product[2][2]
    if abs(scale) < 1e-12 or any(
        (
            not math.isclose(product[i][j] / scale, float(i == j), abs_tol=1e-07)
            for i in range(3)
            for j in range(3)
        )
    ):
        errors.append("Image transforms must be mutually inverse.")
    x0, y0, x1, y1 = evidence["normalization_bounds_px"]
    if (
        x0 < 0
        or y0 < 0
        or x1 <= x0
        or (y1 <= y0)
        or (x1 > evidence["working_size_px"][0])
        or (y1 > evidence["working_size_px"][1])
    ):
        errors.append("Normalization bounds must be inside the working image.")
    else:
        for values in topology.values():
            for entity in values:
                geometry = entity["geometry"]
                for (x, y), (u, v) in zip(geometry["points_px"], geometry["points_normalized"]):
                    if not (
                        math.isclose((x - x0) / (x1 - x0), u, abs_tol=1e-08)
                        and math.isclose((y - y0) / (y1 - y0), v, abs_tol=1e-08)
                    ):
                        errors.append(f"{entity['id']}: pixel and normalized geometry disagree.")
    acceptance = design["acceptance"]
    if acceptance["status"] == "accepted":
        if (
            acceptance["revision_id"] != document["revision_id"]
            or not (acceptance["reviewer"] or "").strip()
        ):
            errors.append("Acceptance requires a named reviewer and the exact current revision.")
        if any((v["state"] != "current" for v in design["values"])) or any(
            (e["geometry"]["state"] != "confirmed" for values in topology.values() for e in values)
        ):
            errors.append("Unresolved topology or sizing cannot be accepted.")
    elif acceptance["revision_id"] is not None or acceptance["reviewer"] is not None:
        errors.append("Pending acceptance must not retain an accepted revision/reviewer.")
    return errors


def accept_revision(document, reviewer):
    result = copy.deepcopy(document)
    result["physical_design"]["acceptance"] = {
        "status": "accepted",
        "revision_id": result["revision_id"],
        "reviewer": reviewer,
    }
    errors = validate_authoring(result)
    if errors:
        raise ValueError("; ".join(errors))
    return result


def invalidate_bindings(document, new_revision_id, affected_ids):
    if new_revision_id == document["revision_id"]:
        raise ValueError("An edit requires a new revision ID.")
    result = copy.deepcopy(document)
    result.update(parent_revision_id=document["revision_id"], revision_id=new_revision_id)
    result["physical_design"]["acceptance"] = {
        "status": "pending",
        "revision_id": None,
        "reviewer": None,
    }
    affected = set(affected_ids)
    for values in result["topology"].values():
        for entity in values:
            if entity["id"] in affected:
                entity["geometry"]["state"] = "stale"
    for value in result["physical_design"]["values"]:
        if value["entity_id"] in affected:
            value["state"] = "stale"
        else:
            value["binding_revision_id"] = new_revision_id
    return result


def near_edge_to_center(
    wall_length_cm,
    reference_from_start_cm,
    direction,
    near_edge_cm,
    clear_width_cm,
    *,
    tolerance_cm=0,
):
    numbers = (wall_length_cm, reference_from_start_cm, near_edge_cm, clear_width_cm)
    if any(
        (
            isinstance(n, bool) or not isinstance(n, (int, float)) or (not math.isfinite(n))
            for n in numbers
        )
    ):
        raise ValueError("Expected finite physical dimensions.")
    if (
        isinstance(direction, bool)
        or direction not in (-1, 1)
        or wall_length_cm <= 0
        or (clear_width_cm <= 0)
        or (near_edge_cm < 0)
    ):
        raise ValueError("Invalid opening dimensions/direction.")
    if not 0 <= reference_from_start_cm <= wall_length_cm:
        raise ValueError("Reference lies outside supporting wall.")
    center = reference_from_start_cm + direction * (near_edge_cm + clear_width_cm / 2)
    if (
        not isinstance(tolerance_cm, (int, float))
        or isinstance(tolerance_cm, bool)
        or (not math.isfinite(tolerance_cm))
        or (tolerance_cm < 0)
    ):
        raise ValueError("Expected a finite nonnegative conversion tolerance.")
    if (
        center - clear_width_cm / 2 < -tolerance_cm
        or center + clear_width_cm / 2 > wall_length_cm + tolerance_cm
    ):
        raise ValueError("Opening does not fit supporting wall.")
    return (
        max(clear_width_cm / 2, min(wall_length_cm - clear_width_cm / 2, center))
        if tolerance_cm
        else center
    )
