import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .contract import validate_authoring
from .sizing_qp import solve

POLICY = json.loads(Path(__file__).with_name("sizing_policy.v2.json").read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def topology_key(document):
    return digest(
        {
            k: [
                {a: b for a, b in e.items() if a != "geometry"}
                | {"points": e["geometry"]["points_px"]}
                for e in v
            ]
            for k, v in document["topology"].items()
        }
    )


def number(value, zero=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(value))
        or (not (0 if zero else 1e-06) <= value <= POLICY["maximum_value_cm"])
    ):
        raise ValueError(
            "Use a finite positive size within the supported range (offsets may be zero)."
        )
    return float(value)


def edit_value(value, edit):
    result = copy.deepcopy(value)
    if set(edit) - {"entity_id", "parameter", "action", "value", "unit", "locked"}:
        raise ValueError("Unknown size edit field.")
    action = edit.get("action", "set")
    if action == "reset":
        suggestion = result["previous_suggestion"]
        result.update(value=suggestion["value"], origin=suggestion["origin"], locked=False)
    elif action == "set":
        unit = edit.get("unit", "cm")
        if unit not in ("cm", "m", "mm"):
            raise ValueError("Use cm, m or mm.")
        raw = edit.get("value")
        number(raw, result["parameter"] == "near_edge_offset_cm")
        result.update(
            value=number(
                raw * {"cm": 1, "m": 100, "mm": 0.1}[unit],
                result["parameter"] == "near_edge_offset_cm",
            ),
            origin="user_override",
            locked=edit.get("locked", result["locked"]),
        )
    elif action in ("lock", "unlock"):
        result["locked"] = action == "lock"
    else:
        raise ValueError("Unknown size edit action.")
    if not isinstance(result["locked"], bool):
        raise ValueError("Lock must be true or false.")
    return result


def recompute(document, request=None, previous=None):
    request = copy.deepcopy(request if request is not None else {})
    document = copy.deepcopy(document)
    if not isinstance(request, dict):
        raise ValueError("Sizing request must be an object.")
    if set(request) - {
        "edits",
        "design_scale",
        "aspect_locks",
        "use_suggested_sizes",
        "settings",
        "reset_bindings",
    }:
        raise ValueError("Unknown sizing option.")
    if not isinstance(request.get("reset_bindings", False), bool):
        raise ValueError("Reset bindings must be true or false.")
    if not isinstance(request.get("use_suggested_sizes", False), bool):
        raise ValueError("Use suggested sizes must be true or false.")
    if not isinstance(request.get("settings", {}), dict):
        raise ValueError("Settings must be an object.")
    if (
        not isinstance(request.get("edits", []), list)
        or len(request.get("edits", [])) > 1000
        or any((not isinstance(e, dict) for e in request.get("edits", [])))
    ):
        raise ValueError("Provide a bounded list of size edits.")
    errors = validate_authoring(document)
    if errors:
        raise ValueError("; ".join(errors))
    top = document["topology"]
    design = document["physical_design"]
    key = topology_key(document)
    result = {
        "version": "shape-sizing-result/1.0",
        "policy": POLICY,
        "topology_revision_id": document["revision_id"],
        "topology_key": key,
        "authoring": document,
        "preview": None,
        "last_valid_preview": copy.deepcopy((previous or {}).get("last_valid_preview")),
        "issues": [],
        "changes": [],
        "exportable": False,
        "suggestions_chosen": bool(request.get("use_suggested_sizes", False)),
    }

    def failure(code, message, ids=(), detail=None):
        result["status"] = "needs_attention"
        result["issues"].append(
            {
                "code": code,
                "message": message,
                "entity_ids": list(ids),
                "details": detail,
                "suggestions": [
                    "Review the highlighted geometry and size choices.",
                    "Unlock a size or reset it to the suggestion.",
                ],
            }
        )
        result["preview"] = copy.deepcopy(result["last_valid_preview"])
        result["preview_is_stale"] = result["preview"] is not None
        return result

    if request.get("reset_bindings"):
        result["discarded_bindings"] = copy.deepcopy(
            (previous or {}).get("authoring", document)["physical_design"]["values"]
        )
        previous = None
        design["values"] = []
        design["acceptance"] = {"status": "pending", "revision_id": None, "reviewer": None}
    if previous and previous.get("topology_key") != key:
        oldvalues = copy.deepcopy(previous["authoring"]["physical_design"]["values"])
        targets = {e["id"] for k in ("regions", "walls", "openings") for e in top[k]} | {"global"}
        design["values"] = [v for v in oldvalues if v["entity_id"] in targets]
        result["orphaned_values"] = [v for v in oldvalues if v["entity_id"] not in targets]
        for v in design["values"]:
            v["state"] = "stale"
        design["acceptance"] = {"status": "pending", "revision_id": None, "reviewer": None}
        return failure(
            "topology_changed",
            "The plan changed. Review size bindings before applying previous choices.",
            targets,
        )
    unresolved = [
        e["id"]
        for entities in top.values()
        for e in entities
        if e["geometry"]["state"] in ("unknown", "ambiguous", "stale")
    ]
    unresolved += [v["entity_id"] for v in design["values"] if v["state"] == "stale"]
    if unresolved:
        return failure(
            "topology_unresolved",
            "Resolve the highlighted plan geometry before sizing.",
            unresolved,
        )
    if not top["regions"] or not top["junctions"]:
        return failure("empty_plan", "Add at least one rectangular region before sizing.")
    if len(top["regions"]) > 200 or len(top["openings"]) > 400:
        raise ValueError("Plan exceeds the supported sizing limit.")
    options = copy.deepcopy(
        (previous or {}).get("options", {"design_scale": 1.0, "aspect_locks": []})
    )
    options.update({k: request[k] for k in ("design_scale", "aspect_locks") if k in request})
    scale = number(options["design_scale"])
    if not 0.1 <= scale <= 10:
        raise ValueError("Design scale must be between 0.1 and 10.")
    regions = {e["id"]: e for e in top["regions"]}
    walls = {e["id"]: e for e in top["walls"]}
    opens = {e["id"]: e for e in top["openings"]}
    if (
        not isinstance(options["aspect_locks"], list)
        or not set(options["aspect_locks"]) <= regions.keys()
    ):
        raise ValueError("Unknown region in Keep proportions.")
    result["options"] = options
    result["size_assumptions"] = {
        "scale_source": "Largest interpreted room is assigned the configured reference area; remaining shape spans are soft proportions.",
        "reference_area_cm2": POLICY["room_reference_area_cm2"] * scale**2,
        "corridor_width_source": "Application preset combined with joint geometry constraints.",
        "units": "cm",
        "image_measurements_used": False,
        "topology_accuracy_established": False,
    }
    settings = {
        **POLICY["runtime_settings"],
        **copy.deepcopy((previous or {}).get("settings", {})),
        **request.get("settings", {}),
    }
    if set(settings) != set(POLICY["runtime_settings"]):
        raise ValueError("Unknown physical setting.")
    for v in settings.values():
        number(v)
    points = {
        e["id"]: e["geometry"]["points_px"][0]
        for e in top["junctions"]
        if len(e["geometry"]["points_px"]) == 1
    }
    if len(points) != len(top["junctions"]):
        return failure("invalid_junction", "Each junction needs one point.")
    point_ids = {tuple((round(v, 9) for v in p)): identifier for identifier, p in points.items()}
    if len(point_ids) != len(points):
        return failure("duplicate_junction", "Coincident junctions must share one identity.")
    polygonal = any(len(r["geometry"]["points_px"]) != 4 for r in regions.values())
    parents = [{identifier: identifier for identifier in points} for _ in (0, 1)]

    def root(axis, identifier):
        while parents[axis][identifier] != identifier:
            parents[axis][identifier] = parents[axis][parents[axis][identifier]]
            identifier = parents[axis][identifier]
        return identifier

    for w in walls.values():
        a, b = (w["start_junction_id"], w["end_junction_id"])
        p, q = (points[a], points[b])
        if p == q or (p[0] != q[0] and p[1] != q[1]):
            return failure("invalid_wall", "Walls must be nonzero and orthogonal.", [w["id"]])
        fixed = 1 if p[1] == q[1] else 0
        parents[fixed][root(fixed, b)] = root(fixed, a)
    if polygonal:
        for axis in (0, 1):
            levels = {}
            for identifier, p in points.items():
                if p[axis] in levels:
                    parents[axis][root(axis, identifier)] = root(axis, levels[p[axis]])
                else:
                    levels[p[axis]] = identifier
    coords = [sorted({root(a, identifier) for identifier in points}) for a in (0, 1)]
    groups = [
        {identifier: i + sum(map(len, coords[:a])) for i, identifier in enumerate(coords[a])}
        for a in (0, 1)
    ]
    indices = [
        {identifier: groups[a][root(a, identifier)] for identifier in points} for a in (0, 1)
    ]
    n = sum(map(len, coords)) + len(opens) * 2

    def vector():
        return np.zeros(n)

    def coordinate(p, axis):
        v = vector()
        identifier = point_ids.get(tuple(round(q, 9) for q in p))
        if identifier is None and polygonal:
            identifier = next(k for k, q in points.items() if q[axis] == p[axis])
        v[indices[axis][identifier]] = 1
        return v

    def span(a, b):
        axis = 0 if a[1] == b[1] else 1
        if a[1 - axis] != b[1 - axis] or a == b:
            raise ValueError("Walls must be nonzero and orthogonal.")
        return (coordinate(b, axis) - coordinate(a, axis)) * (1 if b[axis] > a[axis] else -1)

    bounds = {}
    for rid, region in regions.items():
        p = np.asarray(region["geometry"]["points_px"], float)
        from shapely.geometry import Polygon

        polygon = Polygon(p) if p.ndim == 2 and p.shape[1] == 2 and len(p) >= 4 else None
        if (
            polygon is None
            or not polygon.is_valid
            or polygon.area <= 0
            or any(
                a[0] != b[0] and a[1] != b[1] or np.array_equal(a, b)
                for a, b in zip(p, np.roll(p, -1, axis=0))
            )
        ):
            return failure(
                "unsupported_region", "Each room must be a simple orthogonal polygon.", [rid]
            )
        x, y = p.min(axis=0)
        X, Y = p.max(axis=0)
        if any(tuple(round(v, 9) for v in corner) not in point_ids for corner in p):
            return failure(
                "missing_boundary", "Region corners must be noded wall junctions.", [rid]
            )
        bounds[rid] = [x, y, X, Y]
    for wid, w in walls.items():
        a, b = (points[w["start_junction_id"]], points[w["end_junction_id"]])
        if w["geometry"]["points_px"] != [a, b]:
            return failure(
                "wall_geometry_mismatch", "Wall endpoints disagree with their junctions.", [wid]
            )
    rooms = [b for rid, b in bounds.items() if regions[rid]["type"] == "room"] or list(
        bounds.values()
    )
    largest = max(rooms, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    factor = (
        math.sqrt(
            POLICY["room_reference_area_cm2"]
            / ((largest[2] - largest[0]) * (largest[3] - largest[1]))
        )
        * scale
    )
    anchor = design["anchor"]["junction_id"] or min(
        points, key=lambda k: (points[k][0], points[k][1], k)
    )
    anchor_point = points[anchor]
    design["anchor"]["junction_id"] = anchor
    A = []
    b = []
    E = []
    f = []
    G = []
    h = []
    labels = []
    expressions = {}
    suggestions = {}
    origins = {}

    def soft(v, t, weight=1):
        A.append(v * weight)
        b.append(t * weight)

    def equal(v, t):
        E.append(v)
        f.append(t)

    def lower(v, t, ids):
        G.append(v)
        h.append(t)
        labels.append(ids)

    for axis in (0, 1):
        for representative in coords[axis]:
            p = points[representative]
            soft(
                coordinate(p, axis),
                (p[axis] - anchor_point[axis]) * factor,
                POLICY["position_preference_weight"],
            )
        equal(coordinate(anchor_point, axis), 0.0)
    for w in walls.values():
        lower(
            span(points[w["start_junction_id"]], points[w["end_junction_id"]]),
            POLICY["minimum_coordinate_gap_cm"],
            [w["id"]],
        )
    if polygonal:
        from shapely.geometry import Polygon

        shapes = {rid: Polygon(r["geometry"]["points_px"]) for rid, r in regions.items()}
        for axis in (0, 1):
            levels = sorted({p[axis] for p in points.values()})
            for low, high in zip(levels, levels[1:]):
                a, bpoint = [0, 0], [0, 0]
                a[axis], bpoint[axis] = low, high
                lower(
                    coordinate(bpoint, axis) - coordinate(a, axis),
                    POLICY["minimum_coordinate_gap_cm"],
                    list(regions),
                )
    region_list = list(bounds.items())
    for i, (rid, B) in enumerate(region_list):
        for other, C in region_list[i + 1 :]:
            if polygonal:
                if shapes[rid].intersection(shapes[other]).area > 1e-9:
                    return failure("overlapping_topology", "Room interiors overlap.", [rid, other])
                continue
            separation = None
            for axis in (0, 1):
                if B[axis + 2] <= C[axis]:
                    separation = (B, C, axis)
                    break
                if C[axis + 2] <= B[axis]:
                    separation = (C, B, axis)
                    break
            if separation is None:
                return failure(
                    "overlapping_topology",
                    "Region interiors overlap. Correct the plan before sizing.",
                    [rid, other],
                )
            left, right, axis = separation
            a = [left[0], left[1]]
            a[axis] = left[axis + 2]
            bpoint = [right[0], right[1]]
            gap = (
                POLICY["minimum_coordinate_gap_cm"] if right[axis] - left[axis + 2] > 1e-09 else 0.0
            )
            lower(coordinate(bpoint, axis) - coordinate(a, axis), gap, [rid, other])

    def adjustable(entity, param, value, expr=None, origin="proportion_suggestion"):
        suggestions[entity, param] = float(value)
        origins[entity, param] = origin
        if expr is not None:
            expressions[entity, param] = expr

    for rid, B in bounds.items():
        x, y, X, Y = B
        horizontal = span([x, y], [X, y])
        vertical = span([x, y], [x, Y])
        if regions[rid]["type"] == "room":
            adjustable(rid, "width_cm", (X - x) * factor, horizontal)
            adjustable(rid, "depth_cm", (Y - y) * factor, vertical)
        else:
            long_horizontal = X - x >= Y - y
            adjustable(
                rid,
                "length_cm",
                max(X - x, Y - y) * factor,
                horizontal if long_horizontal else vertical,
            )
            adjustable(
                rid,
                "width_cm",
                POLICY["corridor_width_cm"] * scale,
                vertical if long_horizontal else horizontal,
                origin="preset",
            )
        if rid in options["aspect_locks"]:
            equal(horizontal - (X - x) / (Y - y) * vertical, 0)
    for i, (oid, o) in enumerate(opens.items()):
        w = walls[o["support_wall_id"]]
        a, c = (points[w["start_junction_id"]], points[w["end_junction_id"]])
        L = span(a, c)
        width = vector()
        near = vector()
        width[sum(map(len, coords)) + i * 2] = 1
        near[sum(map(len, coords)) + i * 2 + 1] = 1
        length_px = float(np.linalg.norm(np.asarray(c) - a))
        fraction = o["placement"]["near_edge_normalized"]
        adjustable(
            oid,
            "clear_width_cm",
            (
                POLICY["door_clear_width_cm"] * scale
                if o["type"] == "door"
                else max(1, length_px * factor - settings["wall_thickness_cm"])
            ),
            width,
            "preset" if o["type"] == "door" else "proportion_suggestion",
        )
        adjustable(
            oid,
            "near_edge_offset_cm",
            (
                fraction * length_px * factor
                if o["type"] == "door"
                else settings["wall_thickness_cm"] / 2
            ),
            near,
        )
        adjustable(
            oid,
            "height_cm",
            settings["door_height_cm"] if o["type"] == "door" else settings["wall_height_cm"],
            origin="preset",
        )
        lower(width, 1, [oid])
        lower(near, 0, [oid])
        lower(L - near - width, 0, [oid, w["id"]])
    for p, val in settings.items():
        adjustable("global", p, val, origin="preset")
    stored = copy.deepcopy((previous or {}).get("authoring", document)["physical_design"]["values"])
    old = {(v["entity_id"], v["parameter"]): v for v in stored}
    values = {}
    revision = (
        "sizing_"
        + digest(
            {
                "parent": document["revision_id"],
                "request": request,
                "options": options,
                "old": stored,
                "policy": POLICY,
            }
        )[:24]
    )
    for target, suggested in suggestions.items():
        entity, param = target
        item = copy.deepcopy(
            old.get(
                target,
                {
                    "id": "size_" + digest(target)[:20],
                    "entity_id": entity,
                    "parameter": param,
                    "value": suggested,
                    "origin": origins[target],
                    "locked": False,
                    "previous_suggestion": None,
                    "authoring_revision_id": revision,
                    "binding_revision_id": revision,
                    "state": "current",
                },
            )
        )
        if item["origin"] != "user_override" and (not item["locked"]):
            item.update(value=suggested, origin=origins[target])
        item["previous_suggestion"] = {
            "value": suggested,
            "origin": origins[target],
            "revision_id": revision,
        }
        values[target] = item
    for edit in request.get("edits", []):
        target = (edit.get("entity_id"), edit.get("parameter"))
        if target not in values:
            raise ValueError("This size does not belong to a current entity.")
        values[target] = edit_value(values[target], edit)
    for target, item in values.items():
        item.update(authoring_revision_id=revision, binding_revision_id=revision, state="current")
        number(item["value"], item["parameter"] == "near_edge_offset_cm")
        if target[0] == "global":
            settings[target[1]] = item["value"]
    result["settings"] = settings
    for oid, o in opens.items():
        updates = {
            "height_cm": (
                settings["door_height_cm"] if o["type"] == "door" else settings["wall_height_cm"]
            )
        }
        if o["type"] == "open_passage":
            w = walls[o["support_wall_id"]]
            length = float(
                np.linalg.norm(
                    np.asarray(points[w["end_junction_id"]]) - points[w["start_junction_id"]]
                )
            )
            updates.update(
                clear_width_cm=max(1, length * factor - settings["wall_thickness_cm"]),
                near_edge_offset_cm=settings["wall_thickness_cm"] / 2,
            )
        for param, target in updates.items():
            suggestions[oid, param] = target
            values[oid, param]["previous_suggestion"]["value"] = target
            if values[oid, param]["origin"] != "user_override" and (
                not values[oid, param]["locked"]
            ):
                values[oid, param]["value"] = target
    document.update(
        parent_revision_id=document["revision_id"],
        revision_id=revision,
        policy_version=POLICY["policy_version"],
    )
    design["values"] = list(values.values())
    design["acceptance"] = {"status": "pending", "revision_id": None, "reviewer": None}
    if settings["door_height_cm"] > settings["wall_height_cm"]:
        return failure("height_conflict", "Door height exceeds wall height.", ["global"])
    for target, expr in expressions.items():
        item = values[target]
        soft(
            expr,
            suggestions[target],
            (
                POLICY["corridor_preference_weight"]
                if regions.get(target[0], {}).get("type") == "corridor_segment"
                and target[1] == "width_cm"
                else POLICY["span_preference_weight"]
            ),
        )
        if item["locked"] or item["origin"] == "user_override":
            equal(expr, item["value"])
    if polygonal:
        from .room_geometry import rectangular_parts

        for rid, region in regions.items():
            for x, y, X, Y in rectangular_parts(region["geometry"]["points_px"]):
                for expr in [span([x, y], [X, y]), span([x, y], [x, Y])]:
                    lower(
                        expr, settings["wall_thickness_cm"] + POLICY["minimum_interior_cm"], [rid]
                    )
    for rid, B in bounds.items():
        x, y, X, Y = B
        for expr in [span([x, y], [X, y]), span([x, y], [x, Y])]:
            lower(expr, settings["wall_thickness_cm"] + POLICY["minimum_interior_cm"], [rid])
    centers = {}
    for oid, o in opens.items():
        width = expressions[oid, "clear_width_cm"]
        near = expressions[oid, "near_edge_offset_cm"]
        w = walls[o["support_wall_id"]]
        L = span(points[w["start_junction_id"]], points[w["end_junction_id"]])
        centers[oid] = (
            near + width / 2
            if o["placement"]["direction"] == "toward_end"
            else L - near - width / 2
        )
        if o["type"] == "open_passage":
            equal(width - L, -settings["wall_thickness_cm"])
            equal(near, settings["wall_thickness_cm"] / 2)
        elif values[oid, "clear_width_cm"]["origin"] != "user_override" and (
            not values[oid, "clear_width_cm"]["locked"]
        ):
            equal(width, suggestions[oid, "clear_width_cm"])
        height = values[oid, "height_cm"]
        expected = settings["door_height_cm"] if o["type"] == "door" else settings["wall_height_cm"]
        if height["origin"] == "user_override" or height["locked"]:
            if abs(height["value"] - expected) > 1e-06:
                return failure(
                    "height_conflict",
                    "Opening height must match the configured global height.",
                    [oid, "global"],
                )
        else:
            height["value"] = expected
    for wid in walls:
        ordered = sorted(
            [o for o in opens.values() if o["support_wall_id"] == wid],
            key=lambda o: o["placement"]["interval_normalized"][0],
        )
        for first, second in zip(ordered, ordered[1:]):
            a, c = (first["id"], second["id"])
            lower(
                centers[c]
                - expressions[c, "clear_width_cm"] / 2
                - centers[a]
                - expressions[a, "clear_width_cm"] / 2,
                0,
                [a, c],
            )
    x, detail = solve(A, b, E, f, G, h, POLICY["solver_iterations"], POLICY["solver_tolerance_cm"])
    result["solver"] = detail
    if x is None:
        for item in design["values"]:
            if item["locked"] or item["origin"] == "user_override":
                item["state"] = "conflicting"
        return failure(
            "size_conflict",
            "These size choices cannot fit together. Your values and last valid preview are retained.",
            [
                v["entity_id"]
                for v in design["values"]
                if v["locked"] or v["origin"] == "user_override"
            ],
            detail,
        )
    for target, expr in expressions.items():
        value = float(expr @ x)
        if target[1] == "near_edge_offset_cm" and abs(value) < POLICY["solver_tolerance_cm"]:
            value = 0.0
        values[target]["value"] = round(value, 6)
    result["suggestion_adjustments"] = [
        {
            "entity_id": target[0],
            "parameter": target[1],
            "preferred_cm": suggestions[target],
            "resolved_cm": item["value"],
        }
        for target, item in values.items()
        if abs(item["value"] - suggestions[target]) > 1e-05
    ]
    try:
        from .sizing_adapter import canonical_preview

        preview = canonical_preview(document, points, indices, x, centers, settings)
    except ValueError as error:
        return failure(
            "geometry_invalid", "The sized plan needs geometry correction.", detail=str(error)
        )
    for target, item in values.items():
        before = old.get(target, {}).get("value")
        if before is not None and abs(before - item["value"]) > 1e-05:
            result["changes"].append(
                {
                    "entity_id": target[0],
                    "parameter": target[1],
                    "before_cm": before,
                    "after_cm": item["value"],
                }
            )
    errors = validate_authoring(document)
    if errors:
        raise ValueError("Sizing produced an invalid authoring contract: " + "; ".join(errors))
    result.update(
        status="ready",
        preview=preview,
        last_valid_preview=copy.deepcopy(preview),
        preview_is_stale=False,
    )
    return result


def main():
    from SketchPipeline.validation.validate import load_json

    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--request", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    doc = load_json(args.input)
    result = recompute(doc, load_json(args.request) if args.request else {})
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [
        ("result.json", result),
        ("authoring.json", result["authoring"]),
        ("canonical-preview.json", result["preview"]),
    ]:
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False))
    print(json.dumps({"status": result["status"], "issues": result["issues"], "exportable": False}))


if __name__ == "__main__":
    main()
