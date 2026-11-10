import math
import cv2
import numpy as np

CONFIG = {
    "canny_low": 30,
    "canny_high": 90,
    "axis_tolerance_degrees": 15,
    "merge_angle_degrees": 7,
    "merge_distance_fraction": 0.006,
    "merge_gap_fraction": 0.003,
    "wall_min_length_fraction": 0.04,
    "gap_min_fraction": 0.012,
    "gap_max_fraction": 0.35,
    "endpoint_context_fraction": 0.02,
}


def length(line):
    return float(np.linalg.norm(np.asarray(line["end"]) - line["start"]))


def angle_delta(a, b):
    return abs((a - b + 90) % 180 - 90)


def segment_distance(points, start, end):
    points = np.asarray(points, dtype=float)
    a = np.asarray(start, dtype=float)
    v = np.asarray(end, dtype=float) - a
    t = np.clip((points - a) @ v / max(float(v @ v), 1e-12), 0, 1)
    return np.linalg.norm(points - (a + t[:, None] * v), axis=1)


def detect_raw(gray, method, side):
    if method == "hough":
        edges = cv2.Canny(gray, CONFIG["canny_low"], CONFIG["canny_high"])
        detected = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 720,
            threshold=20,
            minLineLength=max(16, side * 0.012),
            maxLineGap=max(2, side * 0.002),
        )
    elif method == "lsd":
        detected = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    else:
        raise ValueError("Detector must be hough or lsd.")
    if detected is None:
        return []
    lines = []
    for x, y, u, v in detected.reshape(-1, 4):
        item = {"start": [float(x), float(y)], "end": [float(u), float(v)]}
        if length(item) >= max(12, side * 0.008):
            lines.append(item)
    return lines


def dominant_rotation(lines, side):
    values = []
    for item in lines:
        if length(item) < side * 0.12:
            continue
        dx, dy = np.asarray(item["end"]) - item["start"]
        angle = math.degrees(math.atan2(dy, dx))
        residual = (angle + 45) % 90 - 45
        if abs(residual) <= CONFIG["axis_tolerance_degrees"]:
            values.append((residual, length(item)))
    if not values:
        return 0.0
    values.sort()
    half = sum((w for a, w in values)) / 2
    weight = 0.0
    for value, w in values:
        weight += w
        if weight >= half:
            return value
    return 0.0


def classify_axis(item, rotation):
    dx, dy = np.asarray(item["end"]) - item["start"]
    angle = math.degrees(math.atan2(dy, dx))
    h = angle_delta(angle, rotation)
    v = angle_delta(angle, rotation + 90)
    return (
        ("horizontal" if h < v else "vertical")
        if min(h, v) <= CONFIG["axis_tolerance_degrees"]
        else None
    )


def merge_centerlines(lines, rotation, side):
    distance = max(2.5, side * CONFIG["merge_distance_fraction"])
    max_gap = max(2.0, side * CONFIG["merge_gap_fraction"])
    items = []
    for item in sorted(lines, key=length, reverse=True):
        item = dict(item)
        item["axis"] = classify_axis(item, rotation)
        item["raw_count"] = 1
        if item["axis"] is None:
            continue
        direction = np.asarray([math.cos(math.radians(rotation)), math.sin(math.radians(rotation))])
        if item["axis"] == "vertical":
            direction = np.array([-direction[1], direction[0]])
        if np.dot(np.asarray(item["end"]) - item["start"], direction) < 0:
            item["start"], item["end"] = (item["end"], item["start"])
        items.append(item)
    merged = []
    starts = np.empty((len(items), 2), float)
    ends = np.empty_like(starts)
    directions = np.empty_like(starts)
    normals = np.empty_like(starts)
    norms = np.empty(len(items), float)
    angles = np.empty(len(items), float)

    def cache(index, segment):
        starts[index] = segment["start"]
        ends[index] = segment["end"]
        vector = ends[index] - starts[index]
        norms[index] = np.linalg.norm(vector)
        directions[index] = vector / max(norms[index], 1e-12)
        normals[index] = [-directions[index, 1], directions[index, 0]]
        angles[index] = math.degrees(math.atan2(*vector[::-1]))

    for item in items:
        combined = False
        possible = []
        if merged:
            n = len(merged)
            c = np.asarray(item["start"])
            d = np.asarray(item["end"])
            pc = np.sum((c - starts[:n]) * directions[:n], axis=1)
            pd = np.sum((d - starts[:n]) * directions[:n], axis=1)
            angle = math.degrees(math.atan2(*(d - c)[::-1]))
            angular = np.abs((angles[:n] - angle + 90) % 180 - 90)
            offset = np.maximum(
                np.abs(np.sum((c - starts[:n]) * normals[:n], axis=1)),
                np.abs(np.sum((d - starts[:n]) * normals[:n], axis=1)),
            )
            gap = np.maximum(0, np.maximum(np.minimum(pc, pd) - norms[:n], -np.maximum(pc, pd)))
            keep = (
                (angular <= CONFIG["merge_angle_degrees"] + 1e-06)
                & (offset <= distance + 1e-06)
                & (gap <= max_gap + 1e-06)
            )
            possible = np.flatnonzero(keep)
        for other_index in possible:
            other = merged[other_index]
            if other["axis"] != item["axis"]:
                continue
            a = np.asarray(other["start"])
            b = np.asarray(other["end"])
            v = b - a
            norm = np.linalg.norm(v)
            direction = v / norm
            normal = np.array([-direction[1], direction[0]])
            c = np.asarray(item["start"])
            d = np.asarray(item["end"])
            newdir = d - c
            delta = angle_delta(
                math.degrees(math.atan2(*v[::-1])), math.degrees(math.atan2(*newdir[::-1]))
            )
            projections = np.array([(c - a) @ direction, (d - a) @ direction])
            lo, hi = sorted(projections)
            if (
                delta > CONFIG["merge_angle_degrees"]
                or max(abs((c - a) @ normal), abs((d - a) @ normal)) > distance
            ):
                continue
            if max(0, lo - norm, -hi) > max_gap:
                continue
            offset = ((c + d) / 2 - (a + b) / 2) @ normal
            weight = length(item) / (length(item) + length(other))
            origin = a + normal * offset * weight
            other["start"] = (origin + direction * min(0, lo)).tolist()
            other["end"] = (origin + direction * max(norm, hi)).tolist()
            other["raw_count"] += item["raw_count"]
            cache(other_index, other)
            combined = True
            break
        if not combined:
            merged.append(item)
            cache(len(merged) - 1, item)
    return sorted(
        merged, key=lambda segment: (segment["axis"], segment["start"][1], segment["start"][0])
    )


def text_mask(gray, polygons, raw, side):
    text = np.zeros(gray.shape, np.uint8)
    protect = np.zeros(gray.shape, np.uint8)
    for polygon in polygons:
        cv2.fillPoly(text, [np.rint(polygon).astype(np.int32)], 255)
    for item in raw:
        if length(item) >= side * 0.1:
            cv2.line(
                protect,
                tuple(np.rint(item["start"]).astype(int)),
                tuple(np.rint(item["end"]).astype(int)),
                255,
                max(3, round(side * 0.004)),
            )
    removable = (text > 0) & (protect == 0)
    background = cv2.medianBlur(gray, 31)
    masked = gray.copy()
    masked[removable] = background[removable]
    return (masked, text, protect)


def line_evidence(gray, text_polygons):
    side = max(gray.shape)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    enhanced = cv2.GaussianBlur(contrast, (3, 3), 0.7)
    raw = {name: detect_raw(enhanced, name, side) for name in ("hough", "lsd")}
    rotation = dominant_rotation(raw["hough"] + raw["lsd"], side)
    masked, text, protect = text_mask(enhanced, text_polygons, raw["hough"] + raw["lsd"], side)
    outputs = {}
    recovery = {}
    for method in ("hough", "lsd"):
        candidates = merge_centerlines(detect_raw(masked, method, side), rotation, side)
        for i, item in enumerate(candidates, 1):
            a = np.asarray(item["start"])
            b = np.asarray(item["end"])
            points = np.linspace(a, b, max(2, round(length(item))))
            coords = np.rint(points).astype(int)
            coords[:, 0] = np.clip(coords[:, 0], 0, gray.shape[1] - 1)
            coords[:, 1] = np.clip(coords[:, 1], 0, gray.shape[0] - 1)
            overlap = float((text[coords[:, 1], coords[:, 0]] > 0).mean())
            item.update(
                id=f"{method}-l{i:03d}",
                role=(
                    "wall_candidate"
                    if length(item) >= side * CONFIG["wall_min_length_fraction"]
                    else "unknown"
                ),
                text_overlap_fraction=overlap,
                score=None,
            )
            if overlap > 0.85:
                item["role"] = "unknown"
            x1, y1 = item["start"]
            x2, y2 = item["end"]
            if (
                max(x1, x2) < 3
                or min(x1, x2) > gray.shape[1] - 4
                or max(y1, y2) < 3
                or (min(y1, y2) > gray.shape[0] - 4)
            ):
                item["role"] = "unknown"
        outputs[method] = candidates
        recovered = merge_centerlines(raw[method], rotation, side)
        for i, item in enumerate(recovered, 1):
            coords = np.rint(
                np.linspace(item["start"], item["end"], max(2, round(length(item))))
            ).astype(int)
            coords[:, 0] = np.clip(coords[:, 0], 0, gray.shape[1] - 1)
            coords[:, 1] = np.clip(coords[:, 1], 0, gray.shape[0] - 1)
            overlap = float((text[coords[:, 1], coords[:, 0]] > 0).mean())
            item.update(
                id=f"{method}-u{i:03d}",
                source="unmasked",
                score=None,
                text_overlap_fraction=overlap,
                role=(
                    "wall_candidate"
                    if length(item) >= side * CONFIG["wall_min_length_fraction"] and overlap <= 0.85
                    else "unknown"
                ),
            )
            x1, y1 = item["start"]
            x2, y2 = item["end"]
            if (
                max(x1, x2) < 3
                or min(x1, x2) > gray.shape[1] - 4
                or max(y1, y2) < 3
                or (min(y1, y2) > gray.shape[0] - 4)
            ):
                item["role"] = "unknown"
        recovery[method] = recovered
    return (
        outputs,
        {
            "dominant_rotation_degrees": rotation,
            "config": CONFIG,
            "recovery_lines": recovery,
            "raw_counts": {k: len(v) for k, v in raw.items()},
        },
        {
            "wall_input": masked,
            "text_mask": text,
            "protected_strokes": protect,
            "unmasked_line_input": enhanced,
            "wall_ink": np.uint8(cv2.subtract(cv2.medianBlur(masked, 31), masked) > 12) * 255,
            "unmasked_wall_ink": np.uint8(cv2.subtract(cv2.medianBlur(enhanced, 31), enhanced) > 12)
            * 255,
        },
    )


def gap_evidence(lines, texts, shape, *, recovery_lines=(), ink=None, diagnostics=True):
    from .openings import gap_evidence as contextual_gaps

    return contextual_gaps(
        lines, texts, shape, recovery_lines=recovery_lines, ink=ink, diagnostics=diagnostics
    )
