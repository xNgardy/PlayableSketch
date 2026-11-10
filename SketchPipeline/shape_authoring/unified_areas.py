import copy
import cv2
import numpy as np
from .decoder import boundary_graph, authoring_document, iou, stroke_scale
from .decoder_refined import canonical_frame
from .region_recovery import fit_box, box_support, supported_barrier, structural_ink
from .door_geometry import detect_pairs, opening_candidates as observed_doors
from .local_wall_tracking import opening_candidates as tracked_doors
from .corridor_candidates import wall_ink

POLICY = {
    "version": "unified-area-experiment/1.0",
    "probability_threshold": 0.5,
    "minimum_interior_area_fraction": 0.0015,
    "minimum_mean_response": 0.65,
    "minimum_mask_extent": 4,
    "minimum_supported_sides": 2,
    "edge_support_min": 0.45,
    "maximum_parts_per_component": 12,
    "shared_snap_units": 6,
    "open_interface_clear_min": 0.92,
    "review_required": True,
}


def largest_rectangle(binary):
    heights = np.zeros(binary.shape[1], int)
    best = (0, None)
    for y, row in enumerate(binary):
        heights = np.where(row, heights + 1, 0)
        stack = []
        for x, height in enumerate(np.r_[heights, 0]):
            start = x
            while stack and stack[-1][1] > height:
                left, h = stack.pop()
                area = (x - left) * h
                start = left
                if area > best[0]:
                    best = (int(area), [int(left), int(y - h + 1), int(x), int(y + 1)])
            if height and (not stack or stack[-1][1] < height):
                stack.append((start, int(height)))
    return best


def partition(binary, min_area, min_extent, max_parts=12):
    remaining = binary.copy().astype(bool)
    rectangles = []
    for _ in range(max_parts):
        area, bounds = largest_rectangle(remaining)
        if area < min_area or bounds is None:
            break
        x, y, X, Y = bounds
        remaining[y:Y, x:X] = False
        if min(X - x, Y - y) >= min_extent:
            rectangles.append(bounds)
    return rectangles


def _ribbon(ink, normal, fixed, lo, hi, radius=2):
    along = 1 - normal
    positions = np.arange(max(0, int(lo) + 2), min(ink.shape[1 - along], int(hi) - 1))
    normals = np.arange(
        max(0, round(fixed) - radius), min(ink.shape[1 - normal], round(fixed) + radius + 1)
    )
    if not len(positions) or not len(normals):
        return np.zeros(0, bool)
    patch = ink[np.ix_(normals, positions)] if along == 0 else ink[np.ix_(positions, normals)].T
    return patch.max(axis=0) > 0


def snap_rectangles(boxes, gray):
    result = copy.deepcopy(boxes)
    ink = wall_ink(gray)
    joins = []
    for i, a in enumerate(result):
        for j, b in enumerate(result[:i]):
            A, B = (a["bounds_px"], b["bounds_px"])
            for normal in (0, 1):
                along = 1 - normal
                lo = max(A[along], B[along])
                hi = min(A[along + 2], B[along + 2])
                if hi - lo < 4:
                    continue
                ea, eb = (
                    (normal, normal + 2)
                    if A[normal] + A[normal + 2] > B[normal] + B[normal + 2]
                    else (normal + 2, normal)
                )
                delta = abs(A[ea] - B[eb])
                extent = min(A[normal + 2] - A[normal], B[normal + 2] - B[normal])
                if delta > min(POLICY["shared_snap_units"], extent * 0.25) or iou(A, B) > 0.2:
                    continue
                midpoint = (A[ea] + B[eb]) / 2
                values = _ribbon(ink, normal, midpoint, lo, hi, 3)
                if not len(values):
                    continue
                occupancy = float(values.mean())
                if 0.15 < occupancy < 0.4:
                    continue
                candidates = []
                for at in np.arange(
                    np.ceil(min(A[ea], B[eb]) - 2), np.floor(max(A[ea], B[eb]) + 2) + 1
                ):
                    wall = _ribbon(ink, normal, at, lo, hi, 0)
                    if len(wall):
                        candidates.append((float(wall.mean()), -abs(at - midpoint), float(at)))
                at = max(candidates)[2] if candidates and max(candidates)[0] > 0.4 else midpoint
                proposedA = A.copy()
                proposedB = B.copy()
                proposedA[ea] = at
                proposedB[eb] = at
                if (
                    min(
                        proposedA[2] - proposedA[0],
                        proposedA[3] - proposedA[1],
                        proposedB[2] - proposedB[0],
                        proposedB[3] - proposedB[1],
                    )
                    < 4
                ):
                    continue
                A[ea] = at
                B[eb] = at
                joins.append(
                    {
                        "regions": [j, i],
                        "axis": normal,
                        "coordinate": at,
                        "source_ink_occupancy": occupancy,
                    }
                )
    kept = []
    rejected = []
    for box in sorted(
        result,
        key=lambda b: (
            -b["model_score"],
            -(b["bounds_px"][2] - b["bounds_px"][0]) * (b["bounds_px"][3] - b["bounds_px"][1]),
        ),
    ):
        if any((iou(box["bounds_px"], old["bounds_px"]) > 0 for old in kept)):
            rejected.append({"bounds_px": box["bounds_px"], "reason": "overlap_after_fitting"})
            continue
        if any((len(owners) > 2 for owners in boundary_graph(kept + [box])[0].values())):
            rejected.append(
                {"bounds_px": box["bounds_px"], "reason": "ambiguous_boundary_ownership"}
            )
            continue
        kept.append(box)
    return (
        sorted(kept, key=lambda b: (b["bounds_px"][1], b["bounds_px"][0])),
        {"joins": joins, "rejected": rejected},
    )


def classify_interfaces(boxes, gray, probabilities, working_to_native):
    segments = boundary_graph(boxes)[0]
    doors, tracked = tracked_doors(segments, gray, probabilities, working_to_native)
    doors, paired = observed_doors(doors, segments, gray, working_to_native)
    proposals = [p for p in doors if p["type"] == "door"]
    records = []
    ink = wall_ink(gray)
    matrix = np.asarray(working_to_native, float)
    for segment, owners in segments.items():
        if len(owners) != 2:
            continue
        if any((p["segment"] == segment for p in proposals)):
            continue
        native = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        native = native[:, :2] / native[:, 2:]
        normal = 0 if segment[0][0] == segment[1][0] else 1
        along = 1 - normal
        lo, hi = sorted(native[:, along])
        fixed = float(native[:, normal].mean())
        radius = max(3, round(max(gray.shape) * 0.01))
        occupied = _ribbon(ink, normal, fixed, lo, hi, radius)
        clear = float(1 - occupied.mean()) if len(occupied) >= 5 else 0.0
        accepted = clear >= POLICY["open_interface_clear_min"]
        records.append(
            {
                "segment": segment,
                "owners": owners,
                "clear_fraction": clear,
                "status": "proposed" if accepted else "closed_or_unresolved",
            }
        )
        if accepted:
            proposals.append(
                {
                    "segment": segment,
                    "entity_indices": owners,
                    "start": list(segment[0]),
                    "end": list(segment[1]),
                    "type": "open_passage",
                }
            )
    return (
        proposals,
        {"tracked_doors": tracked, "paired_doors": paired, "generic_interfaces": records},
    )


def decode(
    gray,
    probabilities,
    source,
    metadata,
    *,
    working_gray,
    working_metadata,
    evidence_to_working,
    fusion="max",
):
    working, masks, matrix = canonical_frame(
        gray,
        probabilities,
        working_gray,
        evidence_to_working,
        metadata.get("diagnostic_content_bounds_px"),
    )
    side = max(working.shape)
    ink, axis_masks = structural_ink(working)
    barrier, closures = supported_barrier(masks, working, ink, axis_masks, stroke_scale(working))
    pairs, _ = detect_pairs(gray)
    for pair in pairs:
        axis = pair["axis"]
        normal = 1 - axis
        native = []
        for at in pair["native_interval"]:
            p = [0.0, 0.0, 1.0]
            p[axis] = at
            p[normal] = pair["observed_wall_axis"]
            q = matrix @ p
            native.append(tuple(np.rint(q[:2] / q[2]).astype(int)))
        cv2.line(barrier, native[0], native[1], 255, 2)
    if fusion not in ("max", "sum"):
        raise ValueError("Unknown semantic fusion")
    interior = (
        np.maximum(masks[1], masks[2]) if fusion == "max" else np.clip(masks[1] + masks[2], 0, 1)
    )
    binary = np.uint8(interior > POLICY["probability_threshold"])
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    binary[barrier > 0] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    boxes = []
    rejected = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        minimum = max(48, side * side * POLICY["minimum_interior_area_fraction"])
        if area < minimum:
            continue
        local = labels[y : y + h, x : x + w] == label
        for box in partition(
            local, minimum, POLICY["minimum_mask_extent"], POLICY["maximum_parts_per_component"]
        ):
            a, b, A, B = box
            confidence = float(interior[y + b : y + B, x + a : x + A].mean())
            bound = np.clip(
                [x + a - 4, y + b - 4, x + A + 3, y + B + 3],
                [0] * 4,
                [working.shape[1] - 1, working.shape[0] - 1] * 2,
            )
            fitted = fit_box(bound, working, masks, max(3, side * 0.025))
            support = box_support(fitted, masks, axis_masks)
            if (
                confidence < POLICY["minimum_mean_response"]
                or sum((v >= POLICY["edge_support_min"] for v in support))
                < POLICY["minimum_supported_sides"]
            ):
                rejected.append(
                    {"bounds_px": fitted, "support": support, "mean_response": confidence}
                )
                continue
            boxes.append({"type": "room", "bounds_px": fitted, "model_score": confidence})
    boxes, joints = snap_rectangles(boxes, working)
    openings, opening_detail = classify_interfaces(
        boxes, gray, probabilities, np.linalg.inv(matrix)
    )
    doc = authoring_document(source, working_metadata, boxes, openings, evidence_origin="classical")
    return (
        doc,
        {
            "version": POLICY["version"],
            "policy": POLICY,
            "semantic_fusion": fusion,
            "region_boxes": boxes,
            "region_rejections": rejected,
            "partition_fitting": joints,
            "logical_gap_closures": closures,
            "opening_evidence": opening_detail,
            "review_required": True,
            "training_run": False,
        },
    )


def fill_small_holes(binary, maximum_area):
    result = binary.copy()
    count, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(binary == 0))
    for i in range(1, count):
        x, y, w, h, area = map(int, stats[i])
        if (
            x > 0
            and y > 0
            and (x + w < binary.shape[1])
            and (y + h < binary.shape[0])
            and (area <= maximum_area)
        ):
            result[labels == i] = 1
    return result


def decode_observed(
    gray, probabilities, source, metadata, *, working_gray, working_metadata, evidence_to_working
):
    from .contrast import normalize_ink
    from .corridor_junctions import project_boxes

    raw = wall_ink(gray)
    side = max(gray.shape)
    content = metadata.get("diagnostic_content_bounds_px", [0, 0, gray.shape[1], gray.shape[0]])
    count, labels, stats, _ = cv2.connectedComponentsWithStats(raw)
    filtered = np.zeros_like(raw)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= max(8, round(side * 0.02)):
            filtered[labels == i] = 1
    closed = cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    observed_pairs, _ = detect_pairs(gray)
    for pair in observed_pairs:
        axis = pair["axis"]
        normal = 1 - axis
        p = []
        for at in pair["native_interval"]:
            q = [0.0, 0.0]
            q[axis] = at
            q[normal] = pair["observed_wall_axis"]
            p.append(tuple(np.rint(q).astype(int)))
        cv2.line(closed, p[0], p[1], 1, 3)
    free = 1 - closed
    count, labels, stats, _ = cv2.connectedComponentsWithStats(free)
    normalized, _ = normalize_ink(gray, content)
    dummy = np.ones_like(probabilities)
    length = max(7, round(side * 0.025))
    axis_masks = {
        0: cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((1, length), np.uint8)),
        1: cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((length, 1), np.uint8)),
    }
    boxes = []
    rejected = []
    minimum = max(80, side * side * 0.0015)
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        if x == 0 or y == 0 or x + w >= gray.shape[1] or (y + h >= gray.shape[0]):
            continue
        touches = sum(
            [
                x <= content[0] + 5,
                y <= content[1] + 5,
                x + w >= content[2] - 5,
                y + h >= content[3] - 5,
            ]
        )
        if area < minimum or area > side * side * 0.5 or touches >= 2:
            continue
        local = np.uint8(labels[y : y + h, x : x + w] == label)
        local = fill_small_holes(local, max(16, round(side * side * 0.0002)))
        fill = float(local.mean())
        parts = [[0, 0, w, h]] if fill >= 0.82 else partition(local, minimum, 6)
        for a, b, A, B in parts:
            bound = [
                max(0, x + a - 2),
                max(0, y + b - 2),
                min(gray.shape[1] - 1, x + A + 1),
                min(gray.shape[0] - 1, y + B + 1),
            ]
            fitted = fit_box(bound, normalized, dummy, max(4, side * 0.015))
            support = box_support(fitted, dummy, axis_masks)
            if sum((v >= 0.5 for v in support)) < 2:
                rejected.append({"bounds_px": fitted, "support": support})
                continue
            boxes.append(
                {
                    "type": "room",
                    "bounds_px": fitted,
                    "model_score": 0.0,
                    "observed_edge_support": support,
                }
            )
    boxes, joints = snap_rectangles(boxes, gray)
    boxes = project_boxes(boxes, np.asarray(evidence_to_working))
    proposals, evidence = classify_interfaces(
        boxes, gray, probabilities, np.linalg.inv(evidence_to_working)
    )
    doc = authoring_document(
        source, working_metadata, boxes, proposals, evidence_origin="classical"
    )
    return (
        doc,
        {
            "version": "unified-observed-areas/1.0",
            "region_boxes": boxes,
            "rejected": rejected,
            "partition_fitting": joints,
            "opening_evidence": evidence,
            "model_semantic_heads_used_for_regions": False,
            "review_required": True,
        },
    )
