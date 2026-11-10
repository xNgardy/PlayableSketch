import copy
from itertools import combinations
import cv2
import numpy as np
from .corridor_candidates import wall_ink, overlap, touching
from .decoder import iou, boundary_graph, authoring_document
from .corridor_junctions import project_boxes, add_observed_passages
from .passage_refinement import opening_candidates as passages
from .door_geometry import opening_candidates as doors

POLICY = {
    "version": "enclosed-corridor-geometry/0.2",
    "minimum_ink_component_area": 25,
    "minimum_ink_component_span": 15,
    "perimeter_close_sizes": [5, 7, 11, 15, 19],
    "minimum_enclosure_area_fraction": 0.002,
    "room_core_radius_fraction": 0.55,
    "minimum_core_area": 30,
    "minimum_rectangle_coverage": 0.68,
    "minimum_corridor_extent": 5,
    "minimum_corridor_length_fraction": 0.045,
    "maximum_corridor_width_fraction": 0.16,
    "minimum_corridor_coverage": 0.4,
    "review_required": True,
    "production_enabled": True,
}


def enclosed_floor(gray, boxes):
    ink = wall_ink(gray)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    keep = [
        k
        for k in range(1, n)
        if stats[k, 4] >= POLICY["minimum_ink_component_area"]
        and max(stats[k, 2:4]) >= POLICY["minimum_ink_component_span"]
    ]
    clean = np.uint8(np.isin(labels, keep))
    best, best_rank, trials = (None, None, [])
    for size in POLICY["perimeter_close_sizes"]:
        barrier = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, np.ones((size, size), np.uint8))
        count, components, sizes, _ = cv2.connectedComponentsWithStats(1 - barrier)
        floor = np.zeros_like(gray)
        for k in range(1, count):
            x, y, w, h, area = sizes[k]
            if x <= 0 or y <= 0 or x + w >= gray.shape[1] or (y + h >= gray.shape[0]):
                continue
            if area < gray.size * POLICY["minimum_enclosure_area_fraction"]:
                continue
            component = np.uint8(components == k)
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(floor, contours, -1, 1, cv2.FILLED)
        centers = []
        for b in boxes:
            if b["type"] != "room":
                continue
            x, y, X, Y = b["bounds_px"]
            if min(X - x, Y - y) < 20:
                continue
            cx, cy = (
                int(np.clip((x + X) / 2, 0, gray.shape[1] - 1)),
                int(np.clip((y + Y) / 2, 0, gray.shape[0] - 1)),
            )
            centers.append(int(floor[cy, cx]))
        rank = (sum(centers), -size)
        trials.append(
            {
                "close_size": size,
                "floor_area": int(floor.sum()),
                "supported_room_centers": sum(centers),
            }
        )
        if best_rank is None or rank > best_rank:
            best, best_rank = (floor, rank)
    return (best, clean, {"trials": trials, "chosen_rank": list(best_rank)})


def run_at(mask, point, axis):
    x, y = np.rint(point).astype(int)
    if not 0 <= x < mask.shape[1] or not 0 <= y < mask.shape[0] or (not mask[y, x]):
        return None
    line = mask[y, :] if axis == 0 else mask[:, x]
    at = x if axis == 0 else y
    lo = hi = at
    while lo > 0 and line[lo - 1]:
        lo -= 1
    while hi < len(line) - 1 and line[hi + 1]:
        hi += 1
    return (lo, hi)


def room_rectangle(floor, center):
    horizontal, vertical = (run_at(floor, center, 0), run_at(floor, center, 1))
    if horizontal is None or vertical is None:
        return None
    x, X = horizontal
    y, Y = vertical
    for _ in range(2):
        verticals = [
            run_at(floor, [px, center[1]], 1)
            for px in np.linspace(x + (X - x) * 0.15, X - (X - x) * 0.15, 9)
        ]
        verticals = [v for v in verticals if v is not None]
        if verticals:
            y, Y = (
                np.percentile([v[0] for v in verticals], 70),
                np.percentile([v[1] for v in verticals], 30),
            )
        horizontals = [
            run_at(floor, [center[0], py], 0)
            for py in np.linspace(y + (Y - y) * 0.15, Y - (Y - y) * 0.15, 9)
        ]
        horizontals = [v for v in horizontals if v is not None]
        if horizontals:
            x, X = (
                np.percentile([v[0] for v in horizontals], 70),
                np.percentile([v[1] for v in horizontals], 30),
            )
    return [float(x - 1), float(y - 1), float(X + 1), float(Y + 1)]


def coverage(mask, bounds):
    x, y, X, Y = np.rint(bounds).astype(int)
    patch = mask[max(0, y) : min(mask.shape[0], Y + 1), max(0, x) : min(mask.shape[1], X + 1)]
    return float(patch.mean()) if patch.size else 0.0


def infer_regions(gray, base_boxes, *, hybrid=False):
    floor, ink, detail = enclosed_floor(gray, base_boxes)
    if floor.sum() < gray.size * 0.008:
        return (
            copy.deepcopy(base_boxes),
            {**detail, "status": "abstained_no_supported_enclosure"},
            floor,
        )
    distance = cv2.distanceTransform(floor, cv2.DIST_L2, 5)
    radius = float(distance.max() * POLICY["room_core_radius_fraction"])
    count, labels, stats, centers = cv2.connectedComponentsWithStats(np.uint8(distance > radius))
    rooms, records = ([], [])
    for k in range(1, count):
        if stats[k, 4] < POLICY["minimum_core_area"]:
            continue
        region = room_rectangle(floor, centers[k])
        if region is None:
            continue
        w, h = (region[2] - region[0], region[3] - region[1])
        if min(w, h) < max(14, radius * 1.5) or max(w / h, h / w) > 4:
            continue
        fill = coverage(floor, region)
        if fill < POLICY["minimum_rectangle_coverage"] or any(
            (iou(region, r["bounds_px"]) > 0.4 for r in rooms)
        ):
            continue
        rooms.append({"type": "room", "bounds_px": region, "model_score": 0.0})
        records.append(
            {"core_center": centers[k].tolist(), "bounds_px": region, "floor_coverage": fill}
        )
    if not rooms:
        return (copy.deepcopy(base_boxes), {**detail, "status": "abstained_no_room_cores"}, floor)
    from .corridor_candidates import line_support

    for b in base_boxes:
        if b["type"] != "room" or any((iou(b["bounds_px"], r["bounds_px"]) > 0.3 for r in rooms)):
            continue
        x, y, X, Y = b["bounds_px"]
        if min(X - x, Y - y) < radius * 2:
            continue
        supports = [
            line_support(ink, axis, fixed, lo, hi)
            for axis, fixed, lo, hi in [(0, y, x, X), (0, Y, x, X), (1, x, y, Y), (1, X, y, Y)]
        ]
        cx, cy = (round((x + X) / 2), round((y + Y) / 2))
        if (
            not floor[
                int(np.clip(cy, 0, floor.shape[0] - 1)), int(np.clip(cx, 0, floor.shape[1] - 1))
            ]
            and min(supports) < 0.75
        ):
            continue
        if sum((v >= 0.5 for v in supports)) >= 3:
            rooms.append(copy.deepcopy(b))
    residual = floor.copy()
    room_mask = np.zeros_like(floor)
    for r in rooms:
        x, y, X, Y = np.rint(r["bounds_px"]).astype(int)
        room_mask[max(0, y) : Y + 1, max(0, x) : X + 1] = 1
    margin = max(3, round(max(gray.shape) * 0.01))
    residual[cv2.dilate(room_mask, np.ones((margin * 2 + 1, margin * 2 + 1), np.uint8)) > 0] = 0
    corridors = []
    length = max(
        12, round(max(gray.shape) * POLICY["minimum_corridor_length_fraction"]), round(radius * 2)
    )
    for axis in (0, 1):
        mask = cv2.morphologyEx(
            residual, cv2.MORPH_OPEN, np.ones((1, length) if axis == 0 else (length, 1), np.uint8)
        )
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        for k in range(1, count):
            x, y, w, h, area = map(int, stats[k])
            along, normal = (w, h) if axis == 0 else (h, w)
            if (
                normal < POLICY["minimum_corridor_extent"]
                or normal > max(gray.shape) * POLICY["maximum_corridor_width_fraction"]
            ):
                continue
            if along < max(length, normal * 1.4) or area / (w * h) < 0.5:
                continue
            box = [float(x - 1), float(y - 1), float(x + w), float(y + h)]
            alongs = np.linspace(box[axis] + 2, box[axis + 2] - 2, 48)
            fixed = (box[1 - axis] + box[3 - axis]) / 2
            spans = []
            for along_at in alongs:
                point = [along_at, fixed] if axis == 0 else [fixed, along_at]
                span = run_at(residual, point, 1 - axis)
                if (
                    span
                    and span[1] - span[0]
                    <= max(gray.shape) * POLICY["maximum_corridor_width_fraction"]
                ):
                    spans.append(span)
            if len(spans) >= 12:
                box[1 - axis] = float(np.percentile([s[0] for s in spans], 10) - 1)
                box[3 - axis] = float(np.percentile([s[1] for s in spans], 90) + 1)
            if coverage(floor, box) < POLICY["minimum_corridor_coverage"]:
                continue
            corridors.append(
                {"type": "corridor_segment", "bounds_px": box, "model_score": 0.0, "axis": axis}
            )
    merged = True
    while merged:
        merged = False
        for i, j in combinations(range(len(corridors)), 2):
            a, b = (corridors[i], corridors[j])
            if a["axis"] != b["axis"]:
                continue
            axis = a["axis"]
            normal = 1 - axis
            A, B = (a["bounds_px"], b["bounds_px"])
            common = min(A[axis + 2], B[axis + 2]) - max(A[axis], B[axis])
            if common < min(A[axis + 2] - A[axis], B[axis + 2] - B[axis]) * 0.8:
                continue
            gap = max(A[normal], B[normal]) - min(A[normal + 2], B[normal + 2])
            if gap > max(6, min(A[normal + 2] - A[normal], B[normal + 2] - B[normal]) * 0.8):
                continue
            union = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])]
            if coverage(floor, union) < 0.65:
                continue
            mid = (max(A[normal], B[normal]) + min(A[normal + 2], B[normal + 2])) / 2
            if (
                gap > 0
                and line_support(
                    ink, axis, mid, max(A[axis], B[axis]), min(A[axis + 2], B[axis + 2])
                )
                > 0.35
            ):
                continue
            a["bounds_px"] = union
            corridors.pop(j)
            merged = True
            break
    for c in corridors:
        C = c["bounds_px"]
        axis = c["axis"]
        normal = 1 - axis
        width = C[normal + 2] - C[normal]
        for edge in (axis, axis + 2):
            options = []
            for r in rooms:
                B = r["bounds_px"]
                lo = max(C[normal], B[normal])
                hi = min(C[normal + 2], B[normal + 2])
                target = B[axis + 2] if edge == axis else B[axis]
                if hi - lo >= width * 0.45 and abs(C[edge] - target) <= max(
                    margin + 5, width * 0.5
                ):
                    options.append(target)
            if options:
                C[edge] = min(options, key=lambda t: abs(t - C[edge]))
    for a, b in combinations(corridors, 2):
        if a["axis"] == b["axis"] or not overlap(a["bounds_px"], b["bounds_px"]):
            continue
        v, h = (a, b) if a["axis"] == 1 else (b, a)
        V, H = (v["bounds_px"], h["bounds_px"])
        if H[2] > V[2] + 4 and H[0] >= V[0] - 4:
            H[0] = V[2]
        elif H[0] < V[0] - 4 and H[2] <= V[2] + 4:
            H[2] = V[0]
    hybrid_detail = None
    if hybrid:
        from .corridor_candidates import recover

        anchors = rooms + [{k: v for k, v in c.items() if k != "axis"} for c in corridors]
        recovered, hybrid_detail = recover(gray, anchors, bends=True)
        incomplete = any(
            (
                not floor[
                    int(
                        np.clip(
                            round((b["bounds_px"][1] + b["bounds_px"][3]) / 2),
                            0,
                            floor.shape[0] - 1,
                        )
                    ),
                    int(
                        np.clip(
                            round((b["bounds_px"][0] + b["bounds_px"][2]) / 2),
                            0,
                            floor.shape[1] - 1,
                        )
                    ),
                ]
                for b in rooms
            )
        )
        for c in recovered[len(anchors) :]:
            if coverage(floor, c["bounds_px"]) < 0.4 and (not incomplete):
                continue
            B = c["bounds_px"]
            axis = int(B[3] - B[1] > B[2] - B[0])
            corridors.append({**c, "axis": axis})
    candidates = rooms + corridors
    graph = {i: set() for i in range(len(candidates))}
    for i, j in combinations(range(len(candidates)), 2):
        if touching(candidates[i]["bounds_px"], candidates[j]["bounds_px"], 2):
            graph[i].add(j)
            graph[j].add(i)
    active = set(graph)
    while True:
        leaves = {i for i in active if i >= len(rooms) and len(graph[i] & active) < 2}
        if not leaves:
            break
        active -= leaves
    selected = set()
    unseen = set(active)
    while unseen:
        stack = [unseen.pop()]
        component = set(stack)
        while stack:
            for nxt in (graph[stack.pop()] & active) - component:
                component.add(nxt)
                unseen.discard(nxt)
                stack.append(nxt)
        if sum((i < len(rooms) for i in component)) >= 2:
            selected.update(component)
    corridors = [c for i, c in enumerate(corridors, len(rooms)) if i in selected]
    combined = rooms + [{k: v for k, v in c.items() if k != "axis"} for c in corridors]
    kept = []
    rejected = []
    for b in combined:
        B = b["bounds_px"]
        if min(B[2] - B[0], B[3] - B[1]) < 3:
            continue
        conflicts = [v for v in kept if overlap(B, v["bounds_px"]) > 0]
        if conflicts:
            rejected.append({"reason": "overlap", "candidate": b})
        elif any((len(v) > 2 for v in boundary_graph(kept + [b])[0].values())):
            rejected.append({"reason": "nonmanifold", "candidate": b})
        else:
            kept.append(b)
    return (
        kept,
        {
            **detail,
            "status": "proposed",
            "room_core_radius": radius,
            "room_core_records": records,
            "rejections": rejected,
            "hybrid_recovery": hybrid_detail,
        },
        floor,
    )


def decode(
    gray,
    probabilities,
    source,
    metadata,
    *,
    working_metadata,
    evidence_to_working,
    baseline_result,
    hybrid=False,
    preserve_doors=True,
    opening_alignment=False,
):
    baseline, old_detail = baseline_result
    baseline_alignment = None
    if opening_alignment:
        base_boxes = old_detail["region_boxes"]
        base_segments = boundary_graph(base_boxes)[0]
        inverse = np.linalg.inv(evidence_to_working)
        base_proposals, baseline_alignment = passages(
            base_segments,
            gray,
            probabilities,
            inverse,
            region_types=[b["type"] for b in base_boxes],
            align_doors=True,
        )
        recovered_base = [
            i
            for i, b in enumerate(base_boxes)
            if b["type"] == "corridor_segment" and b.get("model_score") == 0.0
        ]
        base_proposals, physical = add_observed_passages(
            base_proposals,
            base_segments,
            gray,
            inverse,
            recovered_base,
            door_evidence=baseline_alignment,
        )
        baseline_alignment["observed_interfaces"] = physical
        base_proposals, observed = doors(base_proposals, base_segments, gray, inverse)
        baseline_alignment["observed_doors"] = observed
        baseline = authoring_document(
            source, working_metadata, base_boxes, base_proposals, evidence_origin="classical"
        )
    native_boxes = project_boxes(old_detail["region_boxes"], np.linalg.inv(evidence_to_working))
    regions, detail, floor = infer_regions(gray, native_boxes, hybrid=hybrid)
    if detail["status"].startswith("abstained"):
        return (
            copy.deepcopy(baseline),
            {
                **detail,
                "baseline_preserved": True,
                "baseline_alignment_evidence": baseline_alignment,
            },
            floor,
        )
    boxes = project_boxes(regions, evidence_to_working)
    segments = boundary_graph(boxes)[0]
    matrix = np.linalg.inv(evidence_to_working)
    proposals, evidence = passages(
        segments,
        gray,
        probabilities,
        matrix,
        region_types=[b["type"] for b in boxes],
        align_doors=opening_alignment,
    )
    recovered = [i for i, b in enumerate(boxes) if b["type"] == "corridor_segment"]
    proposals, physical = add_observed_passages(
        proposals,
        segments,
        gray,
        matrix,
        recovered,
        door_evidence=evidence if opening_alignment else None,
    )
    proposals, observed = doors(proposals, segments, gray, matrix)
    evidence.update(observed_interfaces=physical, observed_doors=observed)
    doc = authoring_document(
        source, working_metadata, boxes, proposals, evidence_origin="classical"
    )
    if preserve_doors:
        from SketchPipeline.evaluation.metrics import pairs, endpoint_error

        old = baseline["topology"]["openings"]
        new = doc["topology"]["openings"]
        matched = pairs(
            old,
            new,
            lambda a, b: (
                endpoint_error(a["geometry"]["points_px"], b["geometry"]["points_px"])
                if a["type"] != "door" or b["type"] == "door"
                else float("inf")
            ),
            max(working_metadata["working_size_px"]) * 0.04,
        )
        if len(matched) < len(old):
            return (
                copy.deepcopy(baseline),
                {
                    **detail,
                    "baseline_preserved": True,
                    "status": "abstained_incumbent_opening_lost",
                    "attempted_region_boxes": boxes,
                    "attempted_opening_evidence": evidence,
                    "baseline_alignment_evidence": baseline_alignment,
                },
                floor,
            )
        from .corridor_candidates import line_support

        _, ink, _ = enclosed_floor(gray, native_boxes)
        for b in native_boxes:
            if b["type"] != "room" or b.get("model_score", 0) < 0.95:
                continue
            x, y, X, Y = b["bounds_px"]
            if min(X - x, Y - y) < max(gray.shape) * 0.08:
                continue
            supports = [
                line_support(ink, axis, fixed, lo, hi)
                for axis, fixed, lo, hi in [(0, y, x, X), (0, Y, x, X), (1, x, y, Y), (1, X, y, Y)]
            ]
            if min(supports) < 0.45:
                continue
            if not any((iou(b["bounds_px"], r["bounds_px"]) >= 0.5 for r in regions)):
                return (
                    copy.deepcopy(baseline),
                    {
                        **detail,
                        "baseline_preserved": True,
                        "status": "abstained_supported_room_lost",
                        "attempted_region_boxes": boxes,
                        "baseline_alignment_evidence": baseline_alignment,
                    },
                    floor,
                )
    return (
        doc,
        {
            **detail,
            "policy": POLICY,
            "region_boxes": boxes,
            "opening_evidence": evidence,
            "opening_policy_unchanged": not opening_alignment,
            "opening_alignment_enabled": opening_alignment,
            "review_required": True,
        },
        floor,
    )
