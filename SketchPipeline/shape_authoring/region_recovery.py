from collections import defaultdict
import copy
import json
from pathlib import Path
import cv2
import numpy as np
from .decoder import CONFIG, stroke_scale, logical_boundary_mask, iou
from SketchPipeline.perception.structural import suppress_grid

POLICY = json.loads(Path(__file__).with_name("region_recovery.v1.json").read_text())


def structural_ink(gray):
    from .decoder_refined import ink_evidence

    clean, _, _ = suppress_grid(gray)
    ink, stroke, _ = ink_evidence(clean)
    length = max(5, round(max(gray.shape) * 0.035))
    masks = {
        0: cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, length), np.uint8)),
        1: cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((length, 1), np.uint8)),
    }
    return (ink, masks)


def line_support(mask, probabilities, axis, fixed, lo, hi, radius=3):
    positions = np.arange(
        max(0, int(np.ceil(lo)) + 2), min(mask.shape[1 - axis], int(np.floor(hi)) - 1)
    )
    normals = np.arange(
        max(0, round(fixed) - radius), min(mask.shape[axis], round(fixed) + radius + 1)
    )
    if not len(positions) or not len(normals):
        return 0.0
    raw = mask[np.ix_(normals, positions)] if axis == 0 else mask[np.ix_(positions, normals)].T
    semantic = (
        probabilities[0][np.ix_(normals, positions)]
        if axis == 0
        else probabilities[0][np.ix_(positions, normals)].T
    )
    return float(((raw > 0) & (semantic > 0.2)).max(axis=0).mean())


def box_support(box, probabilities, axis_masks):
    x, y, X, Y = box
    edges = []
    for axis, fixed, lo, hi in [(1, x, y, Y), (0, y, x, X), (1, X, y, Y), (0, Y, x, X)]:
        edges.append(line_support(axis_masks[axis], probabilities, axis, fixed, lo, hi))
    return edges


def supported_barrier(probabilities, gray, ink, axis_masks, stroke):
    from .decoder_refined import tick_evidence

    barrier = logical_boundary_mask(probabilities, gray)
    side = max(gray.shape)
    closures = []
    count, labels, stats, centers = cv2.connectedComponentsWithStats(
        np.uint8(probabilities[3] > CONFIG["tick_model_threshold"])
    )
    points = [
        centers[i]
        for i in range(1, count)
        if stats[i, 4] >= 3 and max(stats[i, 2:4]) <= side * 0.12
    ]
    for i, p in enumerate(points):
        for q in points[i + 1 :]:
            axis = int(abs(p[1] - q[1]) > abs(p[0] - q[0]))
            if abs(p[1 - axis] - q[1 - axis]) > max(3, side * 0.015):
                continue
            lo, hi = sorted([p[axis], q[axis]])
            fixed = float((p[1 - axis] + q[1 - axis]) / 2)
            if (
                not side * CONFIG["opening_min_fraction"]
                < hi - lo
                < side * CONFIG["opening_max_fraction"]
            ):
                continue
            start = max(0, round(lo) + 3)
            stop = min(gray.shape[1 - axis], round(hi) - 2)
            if stop <= start:
                continue
            ribbon = (
                ink[max(0, round(fixed) - 1) : min(gray.shape[0], round(fixed) + 2), start:stop]
                if axis == 0
                else ink[
                    start:stop, max(0, round(fixed) - 1) : min(gray.shape[1], round(fixed) + 2)
                ].T
            )
            if not ribbon.size or ribbon.max(axis=0).mean() > CONFIG["gap_ink_max_fraction"]:
                continue
            supports = [
                line_support(axis_masks[axis], probabilities, axis, fixed, lo - 14, lo),
                line_support(axis_masks[axis], probabilities, axis, fixed, hi, hi + 14),
            ]
            if min(supports) < 0.5:
                continue
            ends = [
                tick_evidence(ink, probabilities[3], axis, fixed, t, stroke, 1) for t in (lo, hi)
            ]
            if min((end["raw_support"] for end in ends)) < 0.6:
                continue
            if min((end["model_center_response"] for end in ends)) < 0.25:
                continue
            a, b = sorted([end["position_px"] for end in ends])
            first = (a, round(fixed)) if axis == 0 else (round(fixed), a)
            second = (b, round(fixed)) if axis == 0 else (round(fixed), b)
            cv2.line(barrier, first, second, 255, 3)
            closures.append(
                {
                    "points_px": [list(first), list(second)],
                    "basis": "paired_endpoint_and_raw_tick_wall_evidence",
                }
            )
    return (barrier, closures)


def fit_box(box, gray, probabilities, radius):
    result = np.asarray(box, float).copy()
    for edge in range(4):
        axis = edge % 2
        coordinate = result[edge]
        lo = result[1 - axis] + 3
        hi = result[3 - axis] - 3
        if hi <= lo:
            continue
        observations = []
        for along in np.linspace(lo, hi, 32):
            candidates = np.arange(
                max(0, int(coordinate - radius)),
                min(gray.shape[1 - axis] - 1, int(coordinate + radius)) + 1,
            )
            if not len(candidates):
                continue
            xs = candidates if axis == 0 else np.full_like(candidates, int(along))
            ys = np.full_like(candidates, int(along)) if axis == 0 else candidates
            good = (gray[ys, xs] < 150) & (probabilities[0, ys, xs] > 0.2)
            if good.any():
                coordinates = candidates[good]
                observations.append(float(coordinates[np.argmin(abs(coordinates - coordinate))]))
        if len(observations) >= 8:
            result[edge] = float(np.median(observations))
    return np.round(result, 3).tolist()


def fit_shared_axis(ink, axis, coordinates, spans):
    center = float(np.median(coordinates))
    radius = max(3, int(np.ceil(max(abs(np.asarray(coordinates) - center)))) + 2)
    observations = []
    for lo, hi in spans:
        for along in np.linspace(lo + 2, hi - 2, 32):
            values = np.arange(
                max(0, int(center - radius)), min(ink.shape[axis], int(center + radius) + 1)
            )
            if not len(values):
                continue
            along = int(np.clip(round(along), 0, ink.shape[1 - axis] - 1))
            occupied = ink[values, along] if axis == 0 else ink[along, values]
            if occupied.any():
                candidates = values[occupied > 0]
                observations.append(float(candidates[np.argmin(abs(candidates - center))]))
    return float(np.median(observations)) if len(observations) >= 8 else center


def joint_regularize(boxes, shape, probabilities, ink, axis_masks):
    result = copy.deepcopy(boxes)
    side = max(shape)
    parent = {}
    members = {}
    spans = defaultdict(list)
    joins = []
    for i, box in enumerate(result):
        for edge in range(4):
            parent[i, edge] = (i, edge)
            members[i, edge] = {(i, edge)}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    candidates = []
    for i, a in enumerate(result):
        for j in range(i + 1, len(result)):
            b = result[j]
            A, B = (a["bounds_px"], b["bounds_px"])
            for coordinate_axis in (0, 1):
                along = 1 - coordinate_axis
                lo = max(A[along], B[along])
                hi = min(A[along + 2], B[along + 2])
                corridor_pair = a["type"] == b["type"] == "corridor_segment"
                minimum_span = 3 if corridor_pair else POLICY["minimum_shared_span_px"]
                if hi - lo < minimum_span:
                    continue
                if (
                    A[coordinate_axis] + A[coordinate_axis + 2]
                    < B[coordinate_axis] + B[coordinate_axis + 2]
                ):
                    ea, eb = (coordinate_axis + 2, coordinate_axis)
                else:
                    ea, eb = (coordinate_axis, coordinate_axis + 2)
                delta = abs(A[ea] - B[eb])
                extent = min(
                    A[coordinate_axis + 2] - A[coordinate_axis],
                    B[coordinate_axis + 2] - B[coordinate_axis],
                )
                tolerance = min(
                    side * POLICY["maximum_joint_snap_fraction"],
                    extent * POLICY["maximum_joint_snap_region_fraction"],
                )
                if delta > tolerance:
                    continue
                if iou(A, B) > 0.2:
                    continue
                wall_axis = 1 - coordinate_axis
                fixed = (A[ea] + B[eb]) / 2
                support = line_support(
                    axis_masks[wall_axis],
                    probabilities,
                    wall_axis,
                    fixed,
                    lo,
                    hi,
                    radius=max(3, round(delta / 2) + 2),
                )
                interface = probabilities[5]
                interface_support = (
                    float(
                        interface[
                            max(0, int(lo)) : min(shape[0], int(hi)),
                            max(0, round(fixed) - 2) : min(shape[1], round(fixed) + 3),
                        ].max()
                    )
                    if coordinate_axis == 0
                    else float(
                        interface[
                            max(0, round(fixed) - 2) : min(shape[0], round(fixed) + 3),
                            max(0, int(lo)) : min(shape[1], int(hi)),
                        ].max()
                    )
                )
                corridor_supported = False
                if corridor_pair and delta <= 4:
                    corridor_supported = True
                    for bounds in (A, B):
                        edges = box_support(bounds, probabilities, axis_masks)
                        opposing = (
                            (edges[1], edges[3])
                            if bounds[2] - bounds[0] >= bounds[3] - bounds[1]
                            else (edges[0], edges[2])
                        )
                        corridor_supported &= (
                            min(opposing) >= POLICY["support_opposite_wall_threshold"]
                        )
                basis = (
                    "observed_wall"
                    if support >= POLICY["minimum_wall_snap_support"]
                    else (
                        "learned_interface"
                        if "corridor_segment" in (a["type"], b["type"]) and interface_support > 0.45
                        else "paired_supported_corridor_ends" if corridor_supported else None
                    )
                )
                if basis is None:
                    continue
                candidates.append((delta, (i, ea), (j, eb), (lo, hi), support, basis))
    for delta, left, right, span, support, basis in sorted(candidates):
        a, b = (find(left), find(right))
        if a == b:
            continue
        merged = members[a] | members[b]
        values = [result[i]["bounds_px"][edge] for i, edge in merged]
        if max(values) - min(values) > side * POLICY["maximum_joint_snap_fraction"]:
            continue
        if any(((i, (edge + 2) % 4) in merged for i, edge in merged)):
            continue
        parent[b] = a
        members[a] = merged
        spans[a] = spans[a] + spans[b] + [span]
        joins.append(
            {
                "edges": [list(left), list(right)],
                "original_delta_px": delta,
                "wall_support": support,
                "basis": basis,
            }
        )
    for root, group in members.items():
        if find(root) != root or len(group) < 2:
            continue
        coordinate_axis = root[1] % 2
        wall_axis = 1 - coordinate_axis
        values = [result[i]["bounds_px"][edge] for i, edge in group]
        value = round(fit_shared_axis(ink, wall_axis, values, spans[root]), 3)
        if value < min(values) - 2 or value > max(values) + 2:
            continue
        proposed = copy.deepcopy(result)
        for i, edge in group:
            proposed[i]["bounds_px"][edge] = value
        if any(
            (
                min(
                    box["bounds_px"][2] - box["bounds_px"][0],
                    box["bounds_px"][3] - box["bounds_px"][1],
                )
                < POLICY["minimum_box_extent_px"]
                for box in proposed
            )
        ):
            continue
        result = proposed
    kept = []
    rejected = []
    for box in result:
        overlaps = [old for old in kept if iou(box["bounds_px"], old["bounds_px"]) > 0]
        if overlaps:
            rejected.append({"code": "UNRESOLVED_OVERLAP", "box": box, "conflicts": overlaps})
        else:
            kept.append(box)
    return (
        sorted(kept, key=lambda b: (b["bounds_px"][1], b["bounds_px"][0])),
        {"joint_boundary_pairs": joins, "unresolved_overlaps": rejected},
    )


def region_boxes(probabilities, gray, threshold=0.5, *, corridor_refinement=False):
    side = max(gray.shape)
    stroke = stroke_scale(gray)
    radius = max(3, min(side * 0.025, stroke * 2))
    ink, axis_masks = structural_ink(gray)
    barrier, closures = supported_barrier(probabilities, gray, ink, axis_masks, stroke)
    boxes = []
    rejected = []
    recovered = []
    for channel, kind in [(1, "room"), (2, "corridor_segment")]:
        binary = ((probabilities[channel] > threshold) & (barrier == 0)).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        for label in range(1, count):
            x, y, w, h, area = map(int, stats[label])
            fill = area / (w * h)
            aspect = max(w / h, h / w)
            old_small = area < side * side * CONFIG["region_min_area_fraction"]
            old_irregular = fill < CONFIG["region_min_rectangular_fill"]
            if aspect > CONFIG["region_max_aspect_ratio"]:
                rejected.append(
                    {"code": "NON_RECTANGULAR_REGION", "bounds_px": [x, y, x + w, y + h]}
                )
                continue
            box = np.clip(
                [x - 4, y - 4, x + w + 3, y + h + 3],
                [0] * 4,
                [gray.shape[1] - 1, gray.shape[0] - 1] * 2,
            )
            fitted = fit_box(box, gray, probabilities, radius)
            mean = float(probabilities[channel][labels == label].mean())
            if old_small or old_irregular:
                minimum = max(
                    POLICY["minimum_supported_area_px"],
                    side * side * POLICY["minimum_supported_area_fraction"],
                )
                support = box_support(fitted, probabilities, axis_masks)
                if kind == "corridor_segment":
                    opposing = (
                        (support[1], support[3])
                        if fitted[2] - fitted[0] >= fitted[3] - fitted[1]
                        else (support[0], support[2])
                    )
                    supported = min(opposing) >= POLICY["support_opposite_wall_threshold"]
                else:
                    supported = (
                        sum((v >= POLICY["support_edge_threshold"] for v in support))
                        >= POLICY["support_room_min_edges"]
                        and min(support) >= POLICY["support_room_min_edge"]
                    )
                allowed = (
                    area >= minimum
                    and min(w, h) >= POLICY["minimum_component_extent_px"]
                    and (fill >= POLICY["minimum_supported_fill"])
                    and (mean >= POLICY["minimum_supported_model_mean"])
                    and supported
                )
                record = {
                    "type": kind,
                    "bounds_px": fitted,
                    "area_px": area,
                    "fill": fill,
                    "model_mean": mean,
                    "edge_support": support,
                    "was_small": old_small,
                    "was_irregular": old_irregular,
                }
                if not allowed:
                    rejected.append({"code": "UNSUPPORTED_RECOVERY", **record})
                    continue
                recovered.append(record)
            if min(fitted[2] - fitted[0], fitted[3] - fitted[1]) < 8:
                continue
            boxes.append({"type": kind, "bounds_px": fitted, "model_score": mean})
    boxes.sort(key=lambda b: (-b["model_score"], b["bounds_px"]))
    kept = []
    for box in boxes:
        if not any((iou(box["bounds_px"], old["bounds_px"]) > 0.8 for old in kept)):
            kept.append(box)
    repairs = []
    if corridor_refinement:
        from .corridor_refinement import refine

        kept, repairs = refine(kept, rejected, probabilities, gray, axis_masks)
    result, joint = joint_regularize(kept, gray.shape, probabilities, ink, axis_masks)
    if corridor_refinement:
        joint["corridor_repairs"] = repairs
    return (
        result,
        rejected,
        {
            "version": POLICY["version"],
            "supported_components": recovered,
            "logical_gap_closures": closures,
            **joint,
        },
    )
