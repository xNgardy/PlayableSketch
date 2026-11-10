import cv2
import numpy as np
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from .room_geometry import orthogonal_contour
from .decoder import boundary_graph, authoring_document

POLICY = {
    "version": "hybrid-authoring/1.0",
    "minimum_shape_overlap": 0.78,
    "snap_fraction": 0.012,
    "door_axis_tolerance_fraction": 0.03,
    "review_required": True,
}


def align_door_boundaries(regions, boxes, side, masks):
    snaps = []
    for bounds in boxes:
        x, y, X, Y = bounds
        axis = 0 if X - x >= Y - y else 1
        normal = 1 - axis
        center = np.array([(x + X) / 2, (y + Y) / 2])
        candidates = []
        for index, region in enumerate(regions):
            polygon = Polygon(region["points_px"])
            points = region["points_px"]
            if not polygon.is_valid:
                continue
            for p, q in zip(points, points[1:] + points[:1]):
                if p[normal] != q[normal] or not min(p[axis], q[axis]) < center[axis] < max(
                    p[axis], q[axis]
                ):
                    continue
                fixed = p[normal]
                if abs(fixed - center[normal]) > side * 0.04:
                    continue
                probe = center.copy()
                probe[normal] = fixed - 1
                left = polygon.contains(Point(probe))
                probe[normal] = fixed + 1
                right = polygon.contains(Point(probe))
                if left == right:
                    continue
                candidates.append((index, fixed, -1 if left else 1))
        pairs = []
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 :]:
                if a[0] == b[0] or a[2] == b[2] or abs(a[1] - b[1]) > side * 0.04:
                    continue
                pairs.append((abs(a[1] - center[normal]) + abs(b[1] - center[normal]), a, b))
        if not pairs:
            continue
        _, a, b = min(pairs)
        if a[1] == b[1]:
            continue
        options = []
        for fixed in {a[1], b[1], round((a[1] + b[1]) / 2, 3), round(float(center[normal]), 3)}:
            overlaps = []
            for index, old, _ in (a, b):
                points = [
                    [
                        fixed if axis_index == normal and value == old else value
                        for axis_index, value in enumerate(point)
                    ]
                    for point in regions[index]["points_px"]
                ]
                polygon = Polygon(points)
                if not polygon.is_valid or polygon.area <= 0:
                    break
                fitted = np.zeros_like(masks[index])
                cv2.fillPoly(fitted, [np.rint(points).astype(np.int32)], 1)
                overlaps.append(
                    np.count_nonzero((fitted > 0) & (masks[index] > 0))
                    / max(1, np.count_nonzero((fitted > 0) | (masks[index] > 0)))
                )
            if len(overlaps) == 2:
                options.append((min(overlaps), sum(overlaps), -abs(fixed - center[normal]), fixed))
        if not options:
            continue
        fixed = max(options)[3]
        for index, old, _ in (a, b):
            for point in regions[index]["points_px"]:
                if point[normal] == old:
                    point[normal] = fixed
        snaps.append(
            {
                "region_indices": [a[0], b[0]],
                "axis": normal,
                "coordinate_px": fixed,
                "previous_coordinates_px": [a[1], b[1]],
            }
        )
    return snaps


def partition_regions(regions, masks):
    levels = [sorted({p[a] for r in regions for p in r["points_px"]}) for a in (0, 1)]
    integrals = [cv2.integral(mask) for mask in masks]
    cells = [[] for _ in regions]
    for x, X in zip(levels[0], levels[0][1:]):
        for y, Y in zip(levels[1], levels[1][1:]):
            a, b, c, d = np.rint([x, y, X, Y]).astype(int)
            if c <= a or d <= b:
                continue
            support = [
                (v[d, c] - v[b, c] - v[d, a] + v[b, a]) / ((c - a) * (d - b)) for v in integrals
            ]
            owner = int(np.argmax(support))
            if support[owner] >= 0.5:
                cells[owner].append(box(x, y, X, Y))
    for region, parts in zip(regions, cells):
        polygon = unary_union(parts).simplify(0)
        if polygon.geom_type != "Polygon" or polygon.interiors or not polygon.is_valid:
            raise ValueError("Room grid partition requires manual boundary correction")
        region["points_px"] = [list(p) for p in polygon.exterior.coords[:-1]]


def regularize_regions(regions, size, door_boxes=()):
    result = []
    records = []
    side = max(size)
    for index, parts in enumerate(regions):
        if len(parts) != 1:
            raise ValueError("A room has unsupported disconnected floor parts")
        mask = np.zeros(size, np.uint8)
        cv2.fillPoly(mask, [np.rint(parts[0]).astype(np.int32)], 1)
        points = orthogonal_contour(mask, side)
        if points is None:
            raise ValueError(f"Room {index+1} needs manual boundary correction")
        result.append({"type": "room", "points_px": points})
        records.append({"model_region_index": index, "mask": mask})
    tolerance = side * POLICY["snap_fraction"]
    for axis in (0, 1):
        owners = {}
        for index, room in enumerate(result):
            for point in room["points_px"]:
                owners.setdefault(point[axis], set()).add(index)
        values = sorted(owners)
        clusters = []
        for value in values:
            if (
                clusters
                and value - clusters[-1][0] <= tolerance
                and not owners[value].intersection(set().union(*(owners[v] for v in clusters[-1])))
            ):
                clusters[-1].append(value)
            else:
                clusters.append([value])
        mapping = {v: round(float(np.mean(c)), 3) for c in clusters for v in c}
        for room in result:
            for point in room["points_px"]:
                point[axis] = mapping[point[axis]]
    door_snaps = align_door_boundaries(result, door_boxes, side, [r["mask"] for r in records])
    fitted_polygons = [Polygon(r["points_px"]) for r in result]
    overlaps = any(
        a.intersection(b).area > 0
        for i, a in enumerate(fitted_polygons)
        for b in fitted_polygons[i + 1 :]
    )
    low_overlap = False
    for room, record in zip(result, records):
        fitted = np.zeros(size, np.uint8)
        cv2.fillPoly(fitted, [np.rint(room["points_px"]).astype(np.int32)], 1)
        overlap = np.count_nonzero((fitted > 0) & (record["mask"] > 0)) / max(
            1, np.count_nonzero((fitted > 0) | (record["mask"] > 0))
        )
        low_overlap |= overlap < POLICY["minimum_shape_overlap"]
    if overlaps or low_overlap:
        partition_regions(result, [r["mask"] for r in records])
    polygons = []
    diagnostics = []
    for room, record in zip(result, records):
        polygon = Polygon(room["points_px"])
        if polygon.is_valid:
            polygon = polygon.simplify(0)
            room["points_px"] = [list(p) for p in polygon.exterior.coords[:-1]]
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError("Regularized room boundary is invalid")
        fitted = np.zeros(size, np.uint8)
        cv2.fillPoly(fitted, [np.rint(room["points_px"]).astype(np.int32)], 1)
        overlap = np.count_nonzero((fitted > 0) & (record["mask"] > 0)) / max(
            1, np.count_nonzero((fitted > 0) | (record["mask"] > 0))
        )
        if overlap < POLICY["minimum_shape_overlap"]:
            raise ValueError("Room boundary regularization would change the detected floor shape")
        room["bounds_px"] = list(polygon.bounds)
        polygons.append(polygon)
        diagnostics.append(
            {"model_region_index": record["model_region_index"], "shape_overlap": float(overlap)}
        )
    if any(a.intersection(b).area > 0 for i, a in enumerate(polygons) for b in polygons[i + 1 :]):
        raise ValueError("Regularized room interiors overlap")
    return result, {"regions": diagnostics, "door_supported_snaps": door_snaps}


def authoring_from_prediction(prediction, source, preprocessing):
    gray = prediction["gray"]
    regions, region_detail = regularize_regions(
        prediction["regions"], gray.shape, prediction["door_boxes"]
    )
    segments, _ = boundary_graph(regions)
    proposals = []
    unattached = []
    for index, box in enumerate(prediction["door_boxes"]):
        x, y, X, Y = box
        axis = 0 if X - x >= Y - y else 1
        normal = 1 - axis
        center = np.array([(x + X) / 2, (y + Y) / 2])
        lo, hi = (x + 4, X - 4) if axis == 0 else (y + 4, Y - 4)
        candidates = []
        for segment, owners in segments.items():
            if len(owners) != 2 or segment[0][normal] != segment[1][normal]:
                continue
            delta = abs(segment[0][normal] - center[normal])
            a = max(lo, segment[0][axis])
            b = min(hi, segment[1][axis])
            if (
                delta > max(gray.shape) * POLICY["door_axis_tolerance_fraction"]
                or b - a <= 2
                or not segment[0][axis] <= center[axis] <= segment[1][axis]
            ):
                continue
            candidates.append((delta, segment, owners, a, b))
        if not candidates:
            unattached.append(
                {"model_door_index": index, "box_px": box, "reason": "no_shared_room_boundary"}
            )
            continue
        _, segment, owners, a, b = min(candidates)
        p, q = list(segment[0]), list(segment[0])
        p[axis], q[axis] = a, b
        if any(
            old["segment"] == segment and min(old["end"][axis], b) > max(old["start"][axis], a)
            for old in proposals
        ):
            unattached.append(
                {"model_door_index": index, "box_px": box, "reason": "overlapping_door_interval"}
            )
            continue
        proposals.append(
            {"segment": segment, "entity_indices": owners, "start": p, "end": q, "type": "door"}
        )
    matrix = np.asarray(preprocessing["original_to_working"]) @ np.asarray(
        prediction["preprocessing"]["working_to_original"]
    )
    if abs(matrix[0, 1]) + abs(matrix[1, 0]) > 1e-8:
        raise ValueError("Hybrid authoring requires aligned working axes")

    def mapped(points):
        p = np.c_[np.asarray(points), np.ones(len(points))] @ matrix.T
        return np.round(p[:, :2] / p[:, 2:], 6).tolist()

    for region in regions:
        region["points_px"] = mapped(region["points_px"])
    for proposal in proposals:
        proposal["segment"] = tuple(tuple(p) for p in mapped(proposal["segment"]))
        proposal["start"], proposal["end"] = mapped([proposal["start"], proposal["end"]])
    document = authoring_document(source, preprocessing, regions, proposals)
    return document, {
        "policy": POLICY,
        "model_room_count": len(prediction["regions"]),
        "model_door_count": len(prediction["door_boxes"]),
        "authoring_room_count": len(regions),
        "authoring_door_count": len(proposals),
        "region_regularization": region_detail,
        "unattached_doors": unattached,
        "model_wall_attachment": prediction["door_attached"],
    }
