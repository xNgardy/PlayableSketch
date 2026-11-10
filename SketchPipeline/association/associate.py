from copy import deepcopy
import numpy as np
from SketchPipeline.solver.linear import MetricSystem, solve


def target_key(target, basis):
    import json

    return json.dumps([target, basis], sort_keys=True)


def span_catalog(document, pixels, chain_budget=2048):
    layout = document["layout"]
    vertices, openings = (pixels["vertices"], pixels["openings"])
    walls = {w["id"]: w for w in layout["walls"]}
    catalog = []

    def put(target, basis, a, b, semantic):
        if np.linalg.norm(np.array(b) - a) > 1e-06:
            catalog.append(
                {
                    "target": target,
                    "basis": basis,
                    "start_px_y_up": a,
                    "end_px_y_up": b,
                    "semantic": semantic,
                }
            )

    for rid, corners in pixels["regions"].items():
        for i, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1])):
            put(
                {"type": "region_span", "region_id": rid, "axis": "x" if i % 2 == 0 else "y"},
                "wall_centerline",
                a,
                b,
                "region",
            )
    generated = 0
    truncated = False
    for first in walls.values():
        stack = [[first]]
        while stack:
            chain = stack.pop()
            if generated >= chain_budget:
                truncated = True
                break
            put(
                {"type": "wall_chain", "wall_ids": [w["id"] for w in chain]},
                "wall_centerline",
                vertices[first["start_vertex_id"]],
                vertices[chain[-1]["end_vertex_id"]],
                "wall",
            )
            generated += 1
            for w in walls.values():
                if (
                    w["axis"] == first["axis"]
                    and w["start_vertex_id"] == chain[-1]["end_vertex_id"]
                    and (w not in chain)
                ):
                    stack.append(chain + [w])
        if truncated:
            break
    for o in layout["openings"]:
        p, q = openings[o["id"]]
        put({"type": "opening_width", "opening_id": o["id"]}, "clear_opening", p, q, "opening")
        w = walls[o["wall_id"]]
        axis = 0 if w["axis"] == "x" else 1
        for entity in o["connected_entities"]:
            rid = entity["id"]
            corners = pixels["regions"][rid]
            lo = min((pt[axis] for pt in corners))
            hi = max((pt[axis] for pt in corners))
            normal_lo = min((pt[1 - axis] for pt in corners))
            side = (
                ("south" if abs(p[1] - normal_lo) < 1e-06 else "north")
                if axis == 0
                else "west" if abs(p[0] - normal_lo) < 1e-06 else "east"
            )
            a, b = (list(p), list(q))
            a[axis] = lo
            b[axis] = hi
            for reference, start, end in (("min_corner", a, p), ("max_corner", q, b)):
                put(
                    {
                        "type": "opening_offset",
                        "opening_id": o["id"],
                        "region_id": rid,
                        "side": side,
                        "reference": reference,
                    },
                    "edge_offset",
                    start,
                    end,
                    "offset",
                )
    for w in walls.values():
        axis = 0 if w["axis"] == "x" else 1
        group = sorted(
            [o for o in layout["openings"] if o["wall_id"] == w["id"]],
            key=lambda o: openings[o["id"]][0][axis],
        )
        for a, b in zip(group, group[1:]):
            put(
                {
                    "type": "opening_separation",
                    "from_opening_id": a["id"],
                    "to_opening_id": b["id"],
                },
                "edge_offset",
                openings[a["id"]][1],
                openings[b["id"]][0],
                "separation",
            )
    return (catalog, truncated)


def transform_points(points, matrix):
    a = np.c_[np.asarray(points, dtype=float), np.ones(len(points))] @ matrix.T
    if np.any(np.abs(a[:, 2]) < 1e-12):
        raise ValueError("Invalid homogeneous point")
    result = a[:, :2] / a[:, 2:3]
    result[:, 1] *= -1
    return result


def propose(document, pixels, observations, observation_to_review, *, top_k=3, chain_budget=2048):
    if not 1 <= top_k <= 8:
        raise ValueError("top_k must be 1..8")
    catalog, truncated = span_catalog(document, pixels, chain_budget)
    lines = [
        transform_points([line["start_px"], line["end_px"]], observation_to_review)
        for line in observations["lines"]
    ]
    proposals = []
    for text in observations["texts"]:
        candidates = {}
        if text["polygon_px"] is not None and text["parsed_value_cm"] is not None:
            polygon = transform_points(text["polygon_px"], observation_to_review)
            center = polygon.mean(axis=0)
            spread = np.ptp(polygon, axis=0)
            for entry in catalog:
                a, b = (np.array(entry["start_px_y_up"]), np.array(entry["end_px_y_up"]))
                v = b - a
                length = float(np.linalg.norm(v))
                scale = max(24.0, 0.2 * length)
                t = float(np.dot(center - a, v) / (length * length))
                distance = (
                    abs(float(v[0] * (center - a)[1] - v[1] * (center - a)[0])) / length / scale
                )
                projection = max(-t, t - 1, 0)
                axis = int(abs(v[1]) > abs(v[0]))
                orientation = max(
                    0.0, (spread[1 - axis] - spread[axis]) / max(float(max(spread)), 1.0)
                )
                endpoint = []
                for p in (a, b):
                    scores = []
                    for line in lines:
                        direction = line[1] - line[0]
                        norm = np.linalg.norm(direction)
                        if norm > 0 and abs(float(np.dot(direction / norm, v / length))) < 0.3:
                            scores.append(
                                min(np.linalg.norm(line[0] - p), np.linalg.norm(line[1] - p))
                                / scale
                            )
                    endpoint.append(min(scores, default=1.0))
                extension = float(min(1.0, sum(endpoint) / 2))
                semantic = {
                    "region": 0.0,
                    "wall": 0.05,
                    "opening": 0.05,
                    "offset": 0.1,
                    "separation": 0.1,
                }[entry["semantic"]]
                cost = distance + 2 * projection + 0.25 * orientation + 0.35 * extension + semantic
                row = dict(
                    entry,
                    cost=float(cost),
                    features={
                        "normalized_perpendicular_distance": float(distance),
                        "projection_penalty": projection,
                        "orientation_mismatch": float(orientation),
                        "endpoint_extension_mismatch": extension,
                        "semantic_prior": semantic,
                    },
                )
                key = target_key(entry["target"], entry["basis"])
                if key not in candidates or cost < candidates[key]["cost"]:
                    candidates[key] = row
        ranked = sorted(
            candidates.values(), key=lambda c: (c["cost"], target_key(c["target"], c["basis"]))
        )
        proposals.append(
            {
                "evidence_id": text["id"],
                "raw_text": text["raw_text"],
                "value_cm": text["parsed_value_cm"],
                "candidates": [r for r in ranked[:top_k] if r["cost"] <= 6],
                "accepted": False,
                "requires_review": True,
                "reason": "Heuristic proposals only; confirmation required.",
            }
        )
    return {
        "proposals": proposals,
        "catalog_size": len(catalog),
        "catalog_budget_exhausted": truncated,
        "score_version": "span-cost/1.0",
        "top_k": top_k,
        "note": "Endpoint evidence is optional geometric evidence; semantic_prior is a weak type prior, not an ML semantic classifier.",
    }


def hypotheses(document, proposals, *, relations=(), origin_vertex_id=None, budget=16):
    if not 1 <= budget <= 64:
        raise ValueError("hypothesis budget must be 1..64")
    bound_evidence = {
        e
        for d in document["layout"]["dimensions"]
        if d["state"] == "confirmed"
        for e in d["provenance"]["evidence_ids"]
    }
    pending = [
        p
        for p in proposals
        if p["evidence_id"] not in bound_evidence and p["value_cm"] is not None and p["candidates"]
    ]
    beam = [(0.0, [])]
    pruned = False
    for p in pending:
        choices = [
            (cost + c["cost"], chosen + [(p, c)]) for cost, chosen in beam for c in p["candidates"]
        ]
        choices += [(cost + 4.0, chosen + [(p, None)]) for cost, chosen in beam]
        choices.sort(key=lambda x: x[0])
        pruned |= len(choices) > budget
        beam = choices[:budget]
    results = []
    for cost, chosen in beam:
        dimensions = [
            deepcopy(d) for d in document["layout"]["dimensions"] if d["state"] == "confirmed"
        ]
        assignments = []
        used = {d["id"] for d in dimensions}
        for i, (p, c) in enumerate(chosen):
            assignments.append(
                {
                    "evidence_id": p["evidence_id"],
                    "target": c["target"] if c else {"type": "unassigned"},
                }
            )
            if c:
                identifier = f"hyp{i}"
                while identifier in used:
                    identifier += "x"
                used.add(identifier)
                dimensions.append(
                    {
                        "id": identifier,
                        "target": c["target"],
                        "basis": c["basis"],
                        "value_cm": p["value_cm"],
                        "state": "confirmed",
                        "span_label": "Diagnostic hypothesis only",
                        "provenance": {
                            "method": "ocr",
                            "evidence_ids": [p["evidence_id"]],
                            "note": "Temporary hypothesis; never persisted as confirmed.",
                        },
                    }
                )
        try:
            system = MetricSystem(document).build(dimensions, relations, origin_vertex_id)
            values, report = system.numerical()
            invalid_order = False
            for wid in system.walls:
                terms = system.wall_span(wid)
                if all((values[k] is not None for k in terms)):
                    invalid_order |= sum((values[k] * v for k, v in terms.items())) <= 0
            for oid, opening in system.openings.items():
                center, width = (values[f"{oid}:center"], values[f"{oid}:width"])
                terms = system.wall_span(opening["wall_id"])
                if width is not None:
                    invalid_order |= width <= 0
                if (
                    center is not None
                    and width is not None
                    and all((values[k] is not None for k in terms))
                ):
                    length = sum((values[k] * v for k, v in terms.items()))
                    invalid_order |= (
                        center - width / 2 < -1e-06 or center + width / 2 > length + 1e-06
                    )
            hypothesis_doc = deepcopy(document)
            hypothesis_doc["layout"]["dimensions"] = dimensions
            _, checked = solve(
                hypothesis_doc, relations=relations, origin_vertex_id=origin_vertex_id
            )
            geometric_errors = [
                issue
                for issue in checked["validation"]["issues"]
                if issue["code"]
                not in (
                    "SKETCH_GEOMETRY_INCOMPLETE",
                    "SKETCH_DIMENSION_MISSING",
                    "SKETCH_REVIEW_REQUIRED",
                    "SKETCH_ASSOCIATION_PENDING",
                )
            ]
            penalty = (
                1000
                if report["status"] == "inconsistent" or invalid_order or geometric_errors
                else 0
            )
            results.append(
                {
                    "local_cost": cost,
                    "combined_cost": cost + penalty,
                    "assignments": assignments,
                    "linear_status": report["status"],
                    "invalid_order_or_interval": bool(invalid_order),
                    "rank": report["rank"],
                    "nullity": report["nullity"],
                    "max_residual_cm": report["max_residual_cm"],
                    "equations": report["equations"],
                    "validation": checked["validation"],
                }
            )
        except (ValueError, KeyError) as error:
            results.append(
                {
                    "local_cost": cost,
                    "combined_cost": cost + 1000,
                    "assignments": assignments,
                    "error": str(error),
                }
            )
    results.sort(key=lambda r: r["combined_cost"])
    return {
        "budget": budget,
        "evaluated": len(results),
        "budget_exhausted": pruned,
        "requires_review": bool(pending),
        "auto_confirmed": False,
        "hypotheses": results,
        "note": "Global residual/order checks rank a bounded local beam. This is not exhaustive search or metric acceptance; overlap/ownership are checked where coordinates are resolved; final validation remains required.",
    }
