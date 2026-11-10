import copy
import cv2
import numpy as np
from shapely.geometry import Polygon, Point, box as rectangle
from .corridor_candidates import wall_ink
from .door_geometry import sample_line, wall_level
from .decoder import authoring_document, boundary_graph
from SketchPipeline.preprocessing.prepare import prepare

POLICY = {
    "version": "observed-room-geometry/1.1",
    "evidence_max_side": 1024,
    "minimum_region_area_fraction": 0.001,
    "minimum_boundary_support": 0.6,
    "minimum_shape_overlap": 0.78,
    "maximum_corners": 64,
    "maximum_hand_drawn_slope": 0.65,
    "maximum_boundary_deviation_fraction": 0.03,
    "maximum_line_repair_fraction": 0.008,
    "room_definition": "Connected interior; only observed walls and doors separate rooms.",
    "review_required": True,
}


def polygon_points(region):
    if "points_px" in region:
        return [tuple(p) for p in region["points_px"]]
    x, y, X, Y = region["bounds_px"]
    return [(x, y), (X, y), (X, Y), (x, Y)]


def rectangular_parts(points):
    polygon = Polygon(points)
    xs = sorted({p[0] for p in points})
    ys = sorted({p[1] for p in points})
    parts = []
    for y, Y in zip(ys, ys[1:]):
        runs = []
        for x, X in zip(xs, xs[1:]):
            if polygon.covers(rectangle(x, y, X, Y).centroid):
                if runs and runs[-1][2] == x:
                    runs[-1][2] = X
                else:
                    runs.append([x, y, X, Y])
        for run in runs:
            previous = next(
                (p for p in parts if p[0] == run[0] and p[2] == run[2] and p[3] == y), None
            )
            if previous:
                previous[3] = Y
            else:
                parts.append(run)
    return sorted(parts, key=lambda p: (-(p[2] - p[0]) * (p[3] - p[1]), p))


def as_rooms(document):
    result = copy.deepcopy(document)
    for index, region in enumerate(result["topology"]["regions"], 1):
        region["type"] = "room"
        if region["name"].startswith(("Room ", "Corridor ")):
            region["name"] = f"Room {index}"
    return result


def room_ink(gray):
    side = max(gray.shape)
    strong = wall_ink(gray)
    block = max(15, round(side * 0.04) | 1)
    weak = np.uint8(
        cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 5
        )
        > 0
    )
    count, labels, stats, _ = cv2.connectedComponentsWithStats(weak)
    support = cv2.dilate(strong, np.ones((3, 3), np.uint8))
    kept = np.unique(labels[(support > 0) & (weak > 0)])
    kept = [k for k in kept if k and stats[k, 4] >= max(8, round(side * 0.015))]
    ink = np.maximum(strong, np.uint8(np.isin(labels, kept)))
    count, frame_labels, frame_stats, _ = cv2.connectedComponentsWithStats(ink)
    frame_components = [
        k
        for k in range(1, count)
        if (frame_stats[k, 0] == 0 and frame_stats[k, 0] + frame_stats[k, 2] == gray.shape[1])
        or (frame_stats[k, 1] == 0 and frame_stats[k, 1] + frame_stats[k, 3] == gray.shape[0])
    ]
    frame = np.isin(frame_labels, frame_components)
    ink[frame] = 0
    gap = max(3, round(side * POLICY["maximum_line_repair_fraction"]) | 1)
    repaired = ink.copy()
    for axis in (0, 1):
        kernel = np.ones((1, gap) if axis == 0 else (gap, 1), np.uint8)
        closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)
        additions = np.uint8((closed > 0) & (ink == 0))
        count, labels, stats, centers = cv2.connectedComponentsWithStats(additions)
        for k in range(1, count):
            x, y, w, h, _ = stats[k]
            along, normal = (w, h) if axis == 0 else (h, w)
            if along > gap or normal > max(3, round(side * 0.006)):
                continue
            lo = x if axis == 0 else y
            hi = lo + along
            fixed = centers[k][1 - axis]
            flank = max(10, gap * 2)
            support = [
                sample_line(ink, axis, fixed, l, h, 2)
                for l, h in ((lo - flank, lo - 1), (hi, hi + flank))
            ]
            if all(len(line) and line.mean() >= 0.7 for line in support):
                repaired[labels == k] = 1
    return (
        repaired,
        strong,
        {
            "adaptive_block_px": block,
            "maximum_axis_repair_px": gap,
            "frame_ink_pixels_ignored": int(np.count_nonzero(frame)),
            "recovered_ink_pixels": int(np.count_nonzero(ink & (1 - strong))),
            "repaired_gap_pixels": int(np.count_nonzero(repaired & (1 - ink))),
        },
    )


def paired_jambs(ink):
    from itertools import combinations

    side = max(ink.shape)
    scale = side / 1024
    lines = cv2.createLineSegmentDetector().detect(255 - ink * 255)[0]
    groups = {0: [], 1: []}
    for x, y, X, Y in [] if lines is None else lines[:, 0]:
        dx, dy = abs(X - x), abs(Y - y)
        axis = 0 if dy > dx else 1
        if max(dx, dy) < 6 * scale or min(dx, dy) > max(dx, dy) * 0.45:
            continue
        p, q = np.array([x, y]), np.array([X, Y])
        lo, hi = sorted([p[1 - axis], q[1 - axis]])
        groups[axis].append(
            {"at": float((p[axis] + q[axis]) / 2), "lo": float(lo), "hi": float(hi)}
        )
    if sum(map(len, groups.values())) > 400:
        return []
    found = []
    for axis in (0, 1):
        for a, b in combinations(sorted(groups[axis], key=lambda t: t["at"]), 2):
            x, y = a["at"], b["at"]
            width = y - x
            if not 6 * scale < width < side * 0.075:
                continue
            low = max(a["lo"], b["lo"]) + scale
            high = min(a["hi"], b["hi"]) - scale
            best = None
            for at in np.arange(np.ceil(low), np.floor(high) + 1):
                margin, flank = max(2, 3 * scale), max(10 * scale, width * 0.7)
                intervals = [(x - flank, x - margin), (y + margin, y + flank)]
                levels = [
                    wall_level(ink, axis, at, l, h, max(3, round(8 * scale))) for l, h in intervals
                ]
                legs = [min(v - t["lo"], t["hi"] - v) for v, t in zip(levels, (a, b))]
                if min(legs) < scale or max(legs) > 20 * scale:
                    continue
                if abs(levels[0] - levels[1]) > max(10 * scale, width * 0.4):
                    continue
                support = [
                    sample_line(ink, axis, v, l, h, max(2, round(4 * scale)))
                    for v, (l, h) in zip(levels, intervals)
                ]
                if any(not len(s) for s in support) or min(s.mean() for s in support) < 0.65:
                    continue
                fixed = float(np.mean(levels))
                gap = sample_line(ink, axis, fixed, x + margin, y - margin, max(1, round(scale)))
                clear = float(1 - gap.mean()) if len(gap) >= 3 else 0.0
                if clear < 0.85:
                    continue
                score = (min(s.mean() for s in support), clear, min(legs), -abs(at - fixed))
                if best is None or score > best[0]:
                    best = (score, levels)
            if best:
                points = [[x, best[1][0]], [y, best[1][1]]]
                if axis == 1:
                    points = [p[::-1] for p in points]
                found.append({"axis": axis, "start": points[0], "end": points[1], "width": width})
    from .door_geometry import detect_pairs

    existing, _ = detect_pairs(255 - ink * 255)
    kept = []
    for pair in existing:
        axis = pair["axis"]
        a, b = pair["native_interval"]
        at = pair["observed_wall_axis"]
        points = [[a, at], [b, at]] if axis == 0 else [[at, a], [at, b]]
        kept.append({"axis": axis, "start": points[0], "end": points[1], "width": b - a})
    for record in sorted(found, key=lambda r: r["width"]):
        center = np.mean([record["start"], record["end"]], axis=0)
        if any(
            r["axis"] == record["axis"]
            and np.linalg.norm(center - np.mean([r["start"], r["end"]], axis=0))
            < (record["width"] + r["width"]) * 0.4
            for r in kept
        ):
            continue
        kept.append(record)
    return kept


def orthogonal_contour(mask, side):
    smooth = max(3, round(side * 0.02) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((smooth, smooth), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    candidates = []
    for fraction in (0.006, 0.009, 0.012, 0.016):
        points = (
            cv2.approxPolyDP(contour, max(2, side * fraction), True)[:, 0].astype(float).tolist()
        )
        changed = True
        while changed and len(points) >= 4:
            changed = False
            for i in range(len(points)):
                a, b, c = (
                    np.asarray(points[i - 1]),
                    np.asarray(points[i]),
                    np.asarray(points[(i + 1) % len(points)]),
                )
                first, second = b - a, c - b
                axis = int(abs(first[1]) > abs(first[0]))
                other = int(abs(second[1]) > abs(second[0]))
                if axis == other and first[axis] * second[axis] >= 0:
                    points.pop(i)
                    changed = True
                    break
        if not 4 <= len(points) <= POLICY["maximum_corners"] or len(points) % 2:
            continue
        edges = []
        for p, q in zip(np.asarray(points), np.roll(points, -1, axis=0)):
            axis = int(abs(q[1] - p[1]) > abs(q[0] - p[0]))
            if (
                abs(q[1 - axis] - p[1 - axis])
                > abs(q[axis] - p[axis]) * POLICY["maximum_hand_drawn_slope"]
            ):
                break
            edges.append((axis, float((p[1 - axis] + q[1 - axis]) / 2)))
        if len(edges) != len(points) or any(e[0] == edges[i - 1][0] for i, e in enumerate(edges)):
            continue
        result = [
            [edge[1], edges[i - 1][1]] if edge[0] == 1 else [edges[i - 1][1], edge[1]]
            for i, edge in enumerate(edges)
        ]
        polygon = Polygon(result)
        if not polygon.is_valid or polygon.area <= 0:
            continue
        fitted = np.zeros_like(mask)
        cv2.fillPoly(fitted, [np.rint(result).astype(np.int32)], 1)
        overlap = np.count_nonzero((mask > 0) & (fitted > 0)) / max(
            1, np.count_nonzero((mask > 0) | (fitted > 0))
        )
        candidates.append((overlap, -len(result), result))
    return max(candidates)[2] if candidates else None


def observe(gray):
    side = max(gray.shape)
    ink, strong, ink_detail = room_ink(gray)
    pairs = paired_jambs(strong)
    for pair in paired_jambs(ink):
        center = np.mean([pair["start"], pair["end"]], axis=0)
        if not any(
            p["axis"] == pair["axis"]
            and np.linalg.norm(center - np.mean([p["start"], p["end"]], axis=0))
            < (p["width"] + pair["width"]) * 0.4
            for p in pairs
        ):
            pairs.append(pair)
    barrier = ink.copy()
    for pair in pairs:
        cv2.line(
            barrier,
            tuple(np.rint(pair["start"]).astype(int)),
            tuple(np.rint(pair["end"]).astype(int)),
            1,
            max(2, round(side * 0.003)),
        )
    close = max(3, round(side * 0.003) | 1)
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(1 - barrier)
    regions = []
    rejected = []
    for k in range(1, count):
        x, y, w, h, area = stats[k]
        if (
            x <= 0
            or y <= 0
            or x + w >= gray.shape[1]
            or y + h >= gray.shape[0]
            or area < gray.size * POLICY["minimum_region_area_fraction"]
        ):
            continue
        points = orthogonal_contour(np.uint8(labels == k), side)
        if points is None:
            rejected.append(
                {
                    "bounds_px": [int(x), int(y), int(x + w), int(y + h)],
                    "reason": "unsupported_contour",
                }
            )
            continue
        regions.append({"type": "room", "points_px": points, "component_label": k})
    tolerance = side * 0.012
    for axis in (0, 1):
        values = sorted({p[axis] for r in regions for p in r["points_px"]})
        clusters = []
        for value in values:
            if clusters and value - clusters[-1][0] <= tolerance:
                clusters[-1].append(value)
            else:
                clusters.append([value])
        mapped = {v: round(float(np.mean(c)), 3) for c in clusters for v in c}
        for region in regions:
            for p in region["points_px"]:
                p[axis] = mapped[p[axis]]
    support_records = []
    for region in regions:
        points = region["points_px"]
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= 0:
            return None, {"status": "abstained_invalid_polygon"}
        fitted = np.zeros_like(ink)
        cv2.fillPoly(fitted, [np.rint(points).astype(np.int32)], 1)
        observed = labels == region.pop("component_label")
        overlap = np.count_nonzero(observed & (fitted > 0)) / max(
            1, np.count_nonzero(observed | (fitted > 0))
        )
        if overlap < POLICY["minimum_shape_overlap"]:
            return None, {"status": "abstained_shape_mismatch", "shape_overlap": overlap}
        support = []
        for p, q in zip(points, points[1:] + points[:1]):
            axis = 0 if p[1] == q[1] else 1
            lo, hi = sorted([p[axis], q[axis]])
            occupied = sample_line(
                ink,
                axis,
                p[1 - axis],
                lo,
                hi,
                max(3, round(side * POLICY["maximum_boundary_deviation_fraction"])),
            )
            support.append(float(occupied.mean()) if len(occupied) else 0.0)
        if min(support) < POLICY["minimum_boundary_support"]:
            return None, {"status": "abstained_weak_boundary", "support": support}
        support_records.append(support)
        bounds = polygon.bounds
        region["bounds_px"] = list(bounds)
    polygons = [Polygon(r["points_px"]) for r in regions]
    if any(a.intersection(b).area > 0 for i, a in enumerate(polygons) for b in polygons[i + 1 :]):
        return None, {"status": "abstained_overlapping_polygons"}
    if rejected or not regions:
        return None, {"status": "abstained_incomplete_enclosures", "rejected": rejected}
    segments, _ = boundary_graph(regions)
    proposals = []
    discarded_pairs = []
    for pair in pairs:
        axis = pair["axis"]
        center = np.mean([pair["start"], pair["end"]], axis=0)
        candidates = []
        for segment, owners in segments.items():
            if len(owners) != 2 or segment[0][1 - axis] != segment[1][1 - axis]:
                continue
            lo, hi = pair["start"][axis], pair["end"][axis]
            if not segment[0][axis] <= lo < hi <= segment[1][axis]:
                continue
            delta = abs(segment[0][1 - axis] - center[1 - axis])
            if delta <= tolerance:
                candidates.append((delta, segment, owners))
        if not candidates:
            if all(polygon.distance(Point(center)) > tolerance for polygon in polygons):
                discarded_pairs.append({**pair, "reason": "outside_supported_rooms"})
                continue
            return None, {"status": "abstained_unattached_jambs", "pair": pair}
        _, segment, owners = min(candidates)
        p, q = [list(pair[k]) for k in ("start", "end")]
        p[1 - axis] = q[1 - axis] = segment[0][1 - axis]
        proposals.append(
            {"segment": segment, "entity_indices": owners, "start": p, "end": q, "type": "door"}
        )
    return (regions, proposals), {
        "status": "proposed",
        "policy": POLICY,
        "boundary_support": support_records,
        "ink_recovery": ink_detail,
        "jambs": pairs,
        "discarded_jambs": discarded_pairs,
        "region_count": len(regions),
        "door_count": len(proposals),
    }


def decode_image(image, source, preprocessing):
    images, metadata = prepare(
        image,
        max_side=POLICY["evidence_max_side"],
        deskew_degrees=preprocessing.get("automatic_deskew_degrees", 0),
    )
    result, detail = observe(images["gray"])
    if result is None:
        return None, detail
    regions, openings = result
    matrix = np.asarray(preprocessing["original_to_working"]) @ np.asarray(
        metadata["working_to_original"]
    )

    def mapped(points):
        p = np.c_[np.asarray(points), np.ones(len(points))] @ matrix.T
        return np.round(p[:, :2] / p[:, 2:], 6).tolist()

    for region in regions:
        region["points_px"] = mapped(region["points_px"])
    for opening in openings:
        opening["segment"] = tuple(tuple(p) for p in mapped(opening["segment"]))
        opening["start"], opening["end"] = mapped([opening["start"], opening["end"]])
    return (
        authoring_document(source, preprocessing, regions, openings, evidence_origin="classical"),
        detail,
    )
