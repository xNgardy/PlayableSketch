from collections import defaultdict
import math
import cv2
import numpy as np
from shapely import LineString, Point, unary_union
from shapely.ops import polygonize_full

CONFIG = {
    "version": "pixel-topology/1.1",
    "snap_tolerance_fraction": 0.025,
    "minimum_region_area_fraction": 0.0001,
    "rectangle_area_ratio_min": 0.97,
    "rectangle_axis_tolerance_degrees": 8.0,
    "bridge_max_gap_fraction": 0.05,
    "bridge_ink_fraction_min": 0.75,
    "bridge_ribbon_radius_fraction": 0.003,
    "bridge_axis_tolerance_degrees": 15.0,
    "opening_end_adjustment_max_fraction": 0.25,
}


def _rotate(point, center, degrees):
    angle = math.radians(-degrees)
    x, y = np.asarray(point, float) - center
    return np.asarray(
        [
            center[0] + math.cos(angle) * x - math.sin(angle) * y,
            center[1] + math.sin(angle) * x + math.cos(angle) * y,
        ]
    )


def _normalized_wall(line, center, rotation):
    a = _rotate(line["start"], center, rotation)
    b = _rotate(line["end"], center, rotation)
    evidence = [a.copy(), b.copy()]
    if line.get("axis") == "horizontal":
        y = float((a[1] + b[1]) / 2)
        a[1] = b[1] = y
    elif line.get("axis") == "vertical":
        x = float((a[0] + b[0]) / 2)
        a[0] = b[0] = x
    else:
        return None
    along = 0 if line["axis"] == "horizontal" else 1
    if a[along] > b[along]:
        a, b = (b, a)
    return {
        "id": line["id"],
        "axis": line["axis"],
        "a": a,
        "b": b,
        "source_line_ids": [line["id"]],
        "evidence_segments": [evidence],
    }


def _snap_endpoints(
    walls,
    tolerance,
    protected_pairs,
    *,
    ink=None,
    center=None,
    rotation=0.0,
    locked_ends=frozenset(),
):
    spans = [
        sorted(
            (
                float(wall["a"][0 if wall["axis"] == "horizontal" else 1]),
                float(wall["b"][0 if wall["axis"] == "horizontal" else 1]),
            )
        )
        for wall in walls
    ]
    extensions = [span.copy() for span in spans]
    adjustments = []
    for i, wall in enumerate(walls):
        for j in range(i + 1, len(walls)):
            other = walls[j]
            if wall["axis"] == other["axis"] or _protected(wall, other, protected_pairs):
                continue
            horizontal, vertical = (wall, other) if wall["axis"] == "horizontal" else (other, wall)
            hi, vi = (i, j) if wall["axis"] == "horizontal" else (j, i)
            x, y = (float(vertical["a"][0]), float(horizontal["a"][1]))
            hx0, hx1 = spans[hi]
            vy0, vy1 = spans[vi]
            dx = max(hx0 - x, 0.0, x - hx1)
            dy = max(vy0 - y, 0.0, y - vy1)
            if (
                x < hx0
                and (hi, "a") in locked_ends
                or (x > hx1 and (hi, "b") in locked_ends)
                or (y < vy0 and (vi, "a") in locked_ends)
                or (y > vy1 and (vi, "b") in locked_ends)
            ):
                continue
            evidence = None
            if dx > tolerance or dy > tolerance:
                if dx > tolerance * 2 or dy > tolerance * 2:
                    continue
                evidence = _junction_evidence(horizontal, vertical, ink, center, rotation)
                if evidence is None:
                    continue
            extensions[hi] = [min(extensions[hi][0], x), max(extensions[hi][1], x)]
            extensions[vi] = [min(extensions[vi][0], y), max(extensions[vi][1], y)]
            if dx > 0 or dy > 0:
                adjustments.append(
                    {
                        "line_ids": [wall["id"], other["id"]],
                        "junction_px_rotated": [x, y],
                        "extension_px": [dx, dy],
                        "ink_evidence": evidence,
                    }
                )
    for wall, (lo, hi) in zip(walls, extensions):
        along = 0 if wall["axis"] == "horizontal" else 1
        wall["a"][along], wall["b"][along] = (lo, hi)
    return adjustments


def _protected(wall, other, protected_pairs):
    return any(
        (
            frozenset((left, right)) in protected_pairs
            for left in wall["source_line_ids"]
            for right in other["source_line_ids"]
        )
    )


def _sample_ink(a, b, ink, center, rotation):
    distance = float(np.linalg.norm(b - a))
    points = np.linspace(a, b, max(2, math.ceil(distance) + 1))
    points = np.asarray([_rotate(point, center, -rotation) for point in points])
    coords = np.rint(points).astype(int)
    inside = (
        (coords[:, 0] >= 0)
        & (coords[:, 0] < ink.shape[1])
        & (coords[:, 1] >= 0)
        & (coords[:, 1] < ink.shape[0])
    )
    if not inside.all():
        return 0.0
    return float((ink[coords[:, 1], coords[:, 0]] > 0).mean())


def _bridge_evidence(left, right, ink, center, rotation):
    if ink is None:
        return None
    choices = [
        (float(np.linalg.norm(a - b)), a, b)
        for segment_a in left["evidence_segments"]
        for segment_b in right["evidence_segments"]
        for a in segment_a
        for b in segment_b
    ]
    along = 0 if left["axis"] == "horizontal" else 1
    for distance, a, b in sorted(choices, key=lambda item: item[0]):
        if distance > max(ink.shape) * CONFIG["bridge_max_gap_fraction"]:
            break
        delta = abs(b - a)
        if distance > max(4.0, max(ink.shape) * CONFIG["bridge_ribbon_radius_fraction"] * 2):
            if delta[1 - along] > max(1.0, delta[along]) * math.tan(
                math.radians(CONFIG["bridge_axis_tolerance_degrees"])
            ):
                continue
        fraction = _sample_ink(a, b, ink, center, rotation)
        if fraction >= CONFIG["bridge_ink_fraction_min"]:
            return {
                "observed_endpoints_px_rotated": [a.tolist(), b.tolist()],
                "ink_fraction": fraction,
                "distance_px": distance,
            }
    return None


def _junction_evidence(horizontal, vertical, ink, center, rotation):
    if ink is None:
        return None
    candidates = []
    for a, b in horizontal["evidence_segments"]:
        u = b - a
        for c, d in vertical["evidence_segments"]:
            v = d - c
            denominator = u[0] * v[1] - u[1] * v[0]
            if abs(denominator) < 1e-09:
                continue
            delta = c - a
            t = (delta[0] * v[1] - delta[1] * v[0]) / denominator
            s = (delta[0] * u[1] - delta[1] * u[0]) / denominator
            intersection = a + t * u
            ha, va = (a + np.clip(t, 0, 1) * u, c + np.clip(s, 0, 1) * v)
            lengths = [float(np.linalg.norm(intersection - endpoint)) for endpoint in (ha, va)]
            if max(lengths) > max(ink.shape) * CONFIG["bridge_max_gap_fraction"]:
                continue
            fractions = [
                _sample_ink(endpoint, intersection, ink, center, rotation) if distance > 1 else 1.0
                for endpoint, distance in zip((ha, va), lengths)
            ]
            if min(fractions) >= CONFIG["bridge_ink_fraction_min"]:
                candidates.append(
                    (
                        sum(lengths),
                        {
                            "ink_fractions": fractions,
                            "observed_intersection_px_rotated": intersection.tolist(),
                        },
                    )
                )
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _merge_duplicate_walls(
    walls,
    tolerance,
    *,
    protected_pairs=(),
    bridge_tolerance=None,
    ink=None,
    center=None,
    rotation=0.0,
    repairs=None,
):
    merged = []
    for item in sorted(walls, key=lambda wall: (wall["axis"], wall["a"][1], wall["a"][0])):
        current = {**item, "a": item["a"].copy(), "b": item["b"].copy()}
        current["source_line_ids"] = list(item.get("source_line_ids", [item["id"]]))
        while True:
            match_index = None
            for index, other in enumerate(merged):
                if current["axis"] != other["axis"]:
                    continue
                if _protected(current, other, protected_pairs):
                    continue
                normal_index, along_index = (1, 0) if current["axis"] == "horizontal" else (0, 1)
                normal_distance = abs(current["a"][normal_index] - other["a"][normal_index])
                if normal_distance > (bridge_tolerance or tolerance):
                    continue
                a0, a1 = sorted((current["a"][along_index], current["b"][along_index]))
                b0, b1 = sorted((other["a"][along_index], other["b"][along_index]))
                overlap = max(0.0, min(a1, b1) - max(a0, b0))
                shorter = max(1.0, min(a1 - a0, b1 - b0))
                separation = max(0.0, max(a0, b0) - min(a1, b1))
                duplicate = normal_distance <= tolerance and (
                    overlap / shorter >= 0.15 or separation < 1e-06
                )
                evidence = None
                if not duplicate and separation <= (bridge_tolerance or tolerance) * 2:
                    evidence = _bridge_evidence(current, other, ink, center, rotation)
                if duplicate or (
                    evidence and evidence["ink_fraction"] >= CONFIG["bridge_ink_fraction_min"]
                ):
                    if not duplicate and repairs is not None:
                        repairs.append(
                            {
                                "source_line_ids": sorted(
                                    set(current["source_line_ids"] + other["source_line_ids"])
                                ),
                                **evidence,
                            }
                        )
                    match_index = index
                    break
            if match_index is None:
                break
            other = merged.pop(match_index)
            normal_index, along_index = (1, 0) if current["axis"] == "horizontal" else (0, 1)
            weights = [
                max(1.0, np.linalg.norm(current["b"] - current["a"])),
                max(1.0, np.linalg.norm(other["b"] - other["a"])),
            ]
            normal = (
                current["a"][normal_index] * weights[0] + other["a"][normal_index] * weights[1]
            ) / sum(weights)
            lo = min(
                current["a"][along_index],
                current["b"][along_index],
                other["a"][along_index],
                other["b"][along_index],
            )
            hi = max(
                current["a"][along_index],
                current["b"][along_index],
                other["a"][along_index],
                other["b"][along_index],
            )
            if current["axis"] == "horizontal":
                current["a"], current["b"] = (np.asarray([lo, normal]), np.asarray([hi, normal]))
            else:
                current["a"], current["b"] = (np.asarray([normal, lo]), np.asarray([normal, hi]))
            current["source_line_ids"] = sorted(
                set(current["source_line_ids"] + other["source_line_ids"])
            )
            current["evidence_segments"] = current["evidence_segments"] + other["evidence_segments"]
        current["id"] = "wall-" + "-".join(current["source_line_ids"])
        merged.append(current)
    return merged


def _align_opening_supports(walls, openings, center, rotation, tolerance):
    parent = list(range(len(walls)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    attachments, boundaries = ({}, [])
    for gap in openings:
        ids = set(gap.get("supporting_line_ids", []))
        supports = [i for i, wall in enumerate(walls) if ids.intersection(wall["source_line_ids"])]
        reason = None
        points = [_rotate(gap[key], center, rotation) for key in ("start", "end")]
        choices = []
        if len(supports) != 2 or walls[supports[0]]["axis"] != walls[supports[1]]["axis"]:
            reason = "missing_distinct_collinear_supports"
        else:
            normal = 1 if walls[supports[0]]["axis"] == "horizontal" else 0
            if abs(walls[supports[0]]["a"][normal] - walls[supports[1]]["a"][normal]) > tolerance:
                reason = "support_axis_mismatch"
            for first, second in (supports, list(reversed(supports))):
                match = []
                distances = []
                for point, index in zip(points, (first, second)):
                    endpoint = min(
                        ("a", "b"), key=lambda key: np.linalg.norm(point - walls[index][key])
                    )
                    match.append((index, endpoint))
                    distances.append(float(np.linalg.norm(point - walls[index][endpoint])))
                if max(distances) <= tolerance:
                    choices.append((sum(distances), match))
            if not choices:
                reason = "opening_endpoint_not_attached"
        if reason:
            boundaries.append(
                {"opening_id": gap["id"], "status": "unresolved_boundary", "reason": reason}
            )
            continue
        match = min(choices, key=lambda item: item[0])[1]
        attachments[gap["id"]] = match
        parent[root(supports[1])] = root(supports[0])
        boundaries.append(
            {"opening_id": gap["id"], "status": "virtual_boundary_candidate", "reason": None}
        )
    components = defaultdict(list)
    for index in range(len(walls)):
        components[root(index)].append(index)
    for indices in components.values():
        if len(indices) < 2:
            continue
        normal = 1 if walls[indices[0]]["axis"] == "horizontal" else 0
        values = [float(walls[index]["a"][normal]) for index in indices]
        if max(values) - min(values) > tolerance:
            for gap_id, match in list(attachments.items()):
                if match[0][0] in indices:
                    del attachments[gap_id]
                    record = next((item for item in boundaries if item["opening_id"] == gap_id))
                    record.update(
                        status="unresolved_boundary", reason="support_alignment_chain_drift"
                    )
            continue
        weights = [
            float(np.linalg.norm(walls[index]["b"] - walls[index]["a"])) for index in indices
        ]
        coordinate = float(np.average(values, weights=weights))
        for index in indices:
            walls[index]["a"][normal] = walls[index]["b"][normal] = coordinate
    return (attachments, boundaries)


def _snap_opening_ends(walls, attachments, tolerance):
    updates, adjustments = ({}, [])
    for opening_id, match in attachments.items():
        first, second = [walls[index][endpoint].copy() for index, endpoint in match]
        axis = walls[match[0][0]]["axis"]
        along, normal = (0, 1) if axis == "horizontal" else (1, 0)
        lo, hi = sorted((float(first[along]), float(second[along])))
        maximum = min(tolerance, (hi - lo) * CONFIG["opening_end_adjustment_max_fraction"])
        for (index, endpoint), point in zip(match, (first, second)):
            choices = []
            for other in walls:
                if other["axis"] == axis:
                    continue
                start, end = sorted((other["a"][normal], other["b"][normal]))
                if not start - 1e-06 <= point[normal] <= end + 1e-06:
                    continue
                coordinate = float(other["a"][along])
                distance = abs(coordinate - point[along])
                if lo <= coordinate <= hi and 1e-06 < distance <= maximum:
                    choices.append((distance, coordinate))
            if choices:
                _, coordinate = min(choices)
                updates[index, endpoint, along] = coordinate
                adjustments.append(
                    {
                        "opening_id": opening_id,
                        "wall_id": walls[index]["id"],
                        "endpoint": endpoint,
                        "from_px": float(point[along]),
                        "to_px": coordinate,
                    }
                )
    for (index, endpoint, along), coordinate in updates.items():
        walls[index][endpoint][along] = coordinate
    return adjustments


def _flatten_lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [line for part in geometry.geoms for line in _flatten_lines(part)]
    return []


def _edge_key(a, b):
    pair = sorted((tuple((round(float(v), 2) for v in a)), tuple((round(float(v), 2) for v in b))))
    return tuple(pair)


def _polygon_corners(polygon):
    points = list(polygon.exterior.coords)[:-1]
    if len(points) < 4:
        return points
    kept = []
    for index, point in enumerate(points):
        previous = np.asarray(points[index - 1], float)
        current = np.asarray(point, float)
        following = np.asarray(points[(index + 1) % len(points)], float)
        a, b = (current - previous, following - current)
        cross_2d = a[0] * b[1] - a[1] * b[0]
        sine = abs(float(cross_2d)) / max(float(np.linalg.norm(a) * np.linalg.norm(b)), 1e-09)
        if sine > math.sin(math.radians(3)):
            kept.append([float(current[0]), float(current[1])])
    return kept


def build_topology(lines, gaps, shape, rotation_degrees=0.0, *, ink=None, review_exact=False):
    height, width = shape[:2]
    side = max(height, width)
    center = np.asarray([width / 2, height / 2], float)
    tolerance = 1e-05 if review_exact else max(3.0, side * CONFIG["snap_tolerance_fraction"])
    openings = [gap for gap in gaps if gap.get("role") == "opening_candidate"]
    opening_support_ids = {
        identifier for gap in openings for identifier in gap.get("supporting_line_ids", [])
    }
    protected_pairs = {
        frozenset(gap.get("supporting_line_ids", []))
        for gap in openings
        if len(gap.get("supporting_line_ids", [])) == 2
    }
    walls = []
    local_support_ids = []
    border_line_ids = []
    for line in lines:
        local_support = line["id"] in opening_support_ids
        if line.get("role") != "wall_candidate" and (not local_support):
            continue
        a, b = (np.asarray(line["start"]), np.asarray(line["end"]))
        border = max(3.0, side * 0.005)
        if not review_exact and (
            max(a[0], b[0]) < border
            or min(a[0], b[0]) > width - border
            or max(a[1], b[1]) < border
            or (min(a[1], b[1]) > height - border)
        ):
            border_line_ids.append(line["id"])
            continue
        normalized = _normalized_wall(line, center, rotation_degrees)
        min_length = 1e-05 if review_exact else max(3.0, side * (0.005 if local_support else 0.02))
        if normalized and np.linalg.norm(normalized["b"] - normalized["a"]) >= min_length:
            walls.append(normalized)
            if local_support and line.get("role") != "wall_candidate":
                local_support_ids.append(line["id"])
    if review_exact:
        stroke_repairs, recovered_short_ids = ([], [])
        snap_adjustments, opening_endpoint_adjustments = ([], [])
        attachments, opening_boundaries = _align_opening_supports(
            walls, openings, center, rotation_degrees, tolerance
        )
    else:
        bridge_ink = None
        if ink is not None:
            radius = max(2, round(side * CONFIG["bridge_ribbon_radius_fraction"]))
            bridge_ink = cv2.dilate(
                np.uint8(ink > 0), np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)
            )
        stroke_repairs = []
        walls = _merge_duplicate_walls(
            walls,
            max(3.0, side * 0.01),
            protected_pairs=protected_pairs,
            bridge_tolerance=tolerance,
            ink=bridge_ink,
            center=center,
            rotation=rotation_degrees,
            repairs=stroke_repairs,
        )
        short_fragments = []
        for line in lines:
            if (
                line.get("role") != "unknown"
                or line["id"] in opening_support_ids
                or line.get("text_overlap_fraction", 0) > 0.2
            ):
                continue
            candidate = _normalized_wall(line, center, rotation_degrees)
            if candidate is None:
                continue
            if (
                not max(8.0, side * 0.008)
                <= np.linalg.norm(candidate["b"] - candidate["a"])
                < side * 0.04
            ):
                continue
            normal = 1 if candidate["axis"] == "horizontal" else 0
            for wall in walls:
                if wall["axis"] != candidate["axis"] or _protected(
                    candidate, wall, protected_pairs
                ):
                    continue
                if abs(wall["a"][normal] - candidate["a"][normal]) > tolerance:
                    continue
                evidence = _bridge_evidence(candidate, wall, bridge_ink, center, rotation_degrees)
                if evidence:
                    short_fragments.append(candidate)
                    break
        recovered_short_ids = [wall["id"] for wall in short_fragments]
        if short_fragments:
            walls = _merge_duplicate_walls(
                walls + short_fragments,
                max(3.0, side * 0.01),
                protected_pairs=protected_pairs,
                bridge_tolerance=tolerance,
                ink=bridge_ink,
                center=center,
                rotation=rotation_degrees,
                repairs=stroke_repairs,
            )
        attachments, opening_boundaries = _align_opening_supports(
            walls, openings, center, rotation_degrees, tolerance
        )
        snap_adjustments = _snap_endpoints(
            walls,
            tolerance,
            protected_pairs,
            ink=bridge_ink,
            center=center,
            rotation=rotation_degrees,
            locked_ends={endpoint for match in attachments.values() for endpoint in match},
        )
        opening_endpoint_adjustments = _snap_opening_ends(walls, attachments, tolerance)
    physical = [LineString([wall["a"], wall["b"]]) for wall in walls]
    virtual = []
    for gap in openings:
        match = attachments.get(gap["id"])
        if match is None:
            continue
        a, b = [walls[index][endpoint].copy() for index, endpoint in match]
        boundary = LineString([a, b])
        record = next((item for item in opening_boundaries if item["opening_id"] == gap["id"]))
        reason = None
        if boundary.length <= 1:
            reason = "collapsed_opening_boundary"
        elif any((boundary.intersection(raw).length > 1 for raw in physical)):
            reason = "physical_wall_overlaps_opening"
        if reason:
            record.update(status="unresolved_boundary", reason=reason)
        else:
            record["endpoints_px_rotated"] = [a.tolist(), b.tolist()]
            virtual.append((gap["id"], boundary))
    raw_linework = physical + [line for _, line in virtual]
    noded = unary_union(raw_linework) if raw_linework else LineString()
    noded_lines = _flatten_lines(noded)
    edge_map = {}
    node_set = set()
    for part in noded_lines:
        coordinates = list(part.coords)
        for a, b in zip(coordinates, coordinates[1:]):
            if np.linalg.norm(np.asarray(b) - a) < (1e-05 if review_exact else 1):
                continue
            key = _edge_key(a, b)
            if key[0] == key[1]:
                continue
            midpoint = Point((np.asarray(a) + b) / 2)
            physical_ids = [
                source_id
                for wall, raw in zip(walls, physical)
                if raw.distance(midpoint) <= 1e-06
                for source_id in wall["source_line_ids"]
            ]
            virtual_ids = [gap_id for gap_id, raw in virtual if raw.distance(midpoint) <= 1e-06]
            edge_map[key] = {
                "a": list(key[0]),
                "b": list(key[1]),
                "physical_line_ids": sorted(set(physical_ids)),
                "virtual_opening_ids": sorted(set(virtual_ids)),
                "kind": "physical_wall" if physical_ids else "virtual_boundary",
            }
            node_set.update(key)
    polygons, cuts, dangles, invalid = polygonize_full(noded)
    minimum_area = max(25.0, side * side * CONFIG["minimum_region_area_fraction"])
    faces = [polygon for polygon in polygons.geoms if polygon.area >= minimum_area]
    faces.sort(
        key=lambda polygon: (
            round(polygon.bounds[1], 2),
            round(polygon.bounds[0], 2),
            -round(polygon.area, 2),
        )
    )
    regions = []
    for index, polygon in enumerate(faces, 1):
        min_x, min_y, max_x, max_y = polygon.bounds
        box_area = max((max_x - min_x) * (max_y - min_y), 1e-09)
        corners = _polygon_corners(polygon)
        axis_aligned = all(
            (
                min(abs(end[0] - start[0]), abs(end[1] - start[1]))
                <= np.linalg.norm(np.asarray(end) - start)
                * math.sin(math.radians(CONFIG["rectangle_axis_tolerance_degrees"]))
                for start, end in zip(corners, corners[1:] + corners[:1])
            )
        )
        rectangle = (
            len(corners) == 4
            and axis_aligned
            and (not polygon.interiors)
            and (polygon.area / box_area >= CONFIG["rectangle_area_ratio_min"])
        )
        regions.append(
            {
                "id": f"r{index:03d}",
                "kind": "rectangular_region_candidate" if rectangle else "unsupported_region",
                "rectangle_candidate": rectangle,
                "hole_count": len(polygon.interiors),
                "corners_px_rotated": corners,
                "bounds_px_rotated": [min_x, min_y, max_x, max_y],
                "area_px2": float(polygon.area),
                "perimeter_px": float(polygon.length),
                "_geometry": polygon,
            }
        )
    connectivity_nodes = [{"id": region["id"], "kind": region["kind"]} for region in regions]
    connectivity_edges = []
    issues = []
    if not regions:
        issues.append(
            {"code": "TOPOLOGY_NO_BOUNDED_REGION", "severity": "warning", "element_ids": []}
        )
    for region in regions:
        if not region["rectangle_candidate"]:
            issues.append(
                {
                    "code": "TOPOLOGY_NON_RECTANGULAR_FACE",
                    "severity": "warning",
                    "element_ids": [region["id"]],
                }
            )
    region_openings = defaultdict(list)
    virtual_map = dict(virtual)
    for gap in openings:
        boundary = virtual_map.get(gap["id"])
        record = next((item for item in opening_boundaries if item["opening_id"] == gap["id"]))
        if boundary is None:
            a = _rotate(gap["start"], center, rotation_degrees)
            b = _rotate(gap["end"], center, rotation_degrees)
        else:
            a, b = np.asarray(boundary.coords, float)
        midpoint = (a + b) / 2
        direction = b - a
        normal = np.asarray([-direction[1], direction[0]]) / max(np.linalg.norm(direction), 1e-09)
        offset = max(0.1, min(2.0, tolerance * 0.1, np.linalg.norm(direction) * 0.05))
        boundary_regions = [
            region
            for region in regions
            if boundary is not None
            and region["_geometry"].boundary.intersection(boundary).length >= boundary.length * 0.95
        ]
        sides = []
        for sign in (-1, 1):
            point = Point(midpoint + sign * offset * normal)
            matches = [
                region["id"] for region in boundary_regions if region["_geometry"].covers(point)
            ]
            sides.append(matches[0] if len(matches) == 1 else None)
        adjacent = sorted(set((region for region in sides if region is not None)))
        supported = len(adjacent) == 2 and all(
            (region["rectangle_candidate"] for region in boundary_regions)
        )
        relation = {
            "opening_id": gap["id"],
            "interpretation": gap.get("interpretation", "unknown"),
            "region_ids_by_side": sides,
            "adjacent_region_ids": adjacent,
            "status": "two_region_connection" if supported else "unresolved_region_relation",
            "boundary_status": record["status"],
            "reason": (
                record["reason"]
                if boundary is None
                else (
                    None
                    if supported
                    else (
                        "unsupported_adjacent_region"
                        if len(adjacent) == 2
                        else "boundary_has_no_two_region_sides"
                    )
                )
            ),
            "review_required": True,
        }
        if supported:
            connectivity_edges.append(relation)
            for region_id in adjacent:
                region_openings[region_id].append((gap["id"], midpoint))
        else:
            issues.append(
                {
                    "code": "TOPOLOGY_OPENING_REGION_RELATION_UNRESOLVED",
                    "severity": "warning",
                    "element_ids": [gap["id"]],
                }
            )
            for region in regions:
                if (
                    boundary is None
                    or region["_geometry"].boundary.intersection(boundary).length <= 1e-06
                ):
                    continue
                region.setdefault("unresolved_opening_ids", []).append(gap["id"])
        gap["topology_relation"] = relation
    for region in regions:
        region["topology_status"] = (
            "unsupported_region"
            if not region["rectangle_candidate"]
            else (
                "ambiguous_boundary" if region.get("unresolved_opening_ids") else "region_candidate"
            )
        )
        if region.get("unresolved_opening_ids"):
            issues.append(
                {
                    "code": "TOPOLOGY_REGION_USES_UNRESOLVED_BOUNDARY",
                    "severity": "warning",
                    "element_ids": [region["id"]] + region["unresolved_opening_ids"],
                }
            )
    corridor_hypotheses = []
    for region in regions:
        if not region["rectangle_candidate"] or region.get("unresolved_opening_ids"):
            continue
        links = region_openings[region["id"]]
        if len(links) < 2:
            continue
        center_point = np.asarray(region["_geometry"].centroid.coords[0])
        directions = [point - center_point for _, point in links]
        has_opposed = any(
            (
                float(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-09)) < -0.35
                for i, a in enumerate(directions)
                for b in directions[i + 1 :]
            )
        )
        if has_opposed:
            corridor_hypotheses.append(
                {
                    "region_id": region["id"],
                    "opening_ids": sorted({opening_id for opening_id, _ in links}),
                    "status": "corridor_hypothesis",
                    "reason": "rectangular region has openings on opposed sides; semantic review required",
                }
            )
    for region in regions:
        region.pop("_geometry")
    return {
        "schema_version": CONFIG["version"],
        "coordinate_frame": "working_rotated_pixel",
        "units": "px",
        "rotation_degrees_removed": float(rotation_degrees),
        "snap_tolerance_px": tolerance,
        "snap_adjustments": snap_adjustments,
        "stroke_repairs": stroke_repairs,
        "opening_boundaries": opening_boundaries,
        "opening_endpoint_adjustments": opening_endpoint_adjustments,
        "recovered_short_line_ids": sorted(recovered_short_ids),
        "local_opening_support_line_ids": sorted(local_support_ids),
        "excluded_border_line_ids": sorted(border_line_ids),
        "config": dict(CONFIG),
        "geometry_mode": "review_exact" if review_exact else "perception_hypothesis",
        "wall_graph": {
            "nodes": [
                {"id": f"n{i:04d}", "point_px_rotated": list(point)}
                for i, point in enumerate(sorted(node_set), 1)
            ],
            "edges": [edge_map[key] for key in sorted(edge_map)],
        },
        "regions": regions,
        "region_connectivity_graph": {"nodes": connectivity_nodes, "edges": connectivity_edges},
        "corridor_hypotheses": corridor_hypotheses,
        "polygonization": {
            "bounded_faces": len(faces),
            "cut_edge_count": len(_flatten_lines(cuts)),
            "dangle_count": len(_flatten_lines(dangles)),
            "invalid_ring_count": len(_flatten_lines(invalid)),
            "dangles_px_rotated": [
                [list(point) for point in line.coords] for line in _flatten_lines(dangles)
            ],
            "cut_edges_px_rotated": [
                [list(point) for point in line.coords] for line in _flatten_lines(cuts)
            ],
        },
        "issues": issues,
        "review_required": True,
        "metric_layout_created": False,
    }
