from collections import defaultdict
import copy
import json
from pathlib import Path
import cv2
import numpy as np

CONFIG = json.loads(Path(__file__).with_name("proposals.config.json").read_text())


def stroke_scale(gray):
    ink = (gray < 140).astype(np.uint8)
    distance = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    values = distance[distance > 0]
    return float(np.clip(np.percentile(values, 65) * 2 if len(values) else 2, 1, 8))


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0


def region_boxes(probabilities, gray, threshold=0.5):
    side = max(gray.shape)
    stroke = stroke_scale(gray)
    radius = max(3, min(side * 0.025, stroke * 2))
    boxes = []
    rejected = []
    barrier = logical_boundary_mask(probabilities, gray)
    for channel, kind in [(1, "room"), (2, "corridor_segment")]:
        binary = (probabilities[channel] > threshold).astype(np.uint8)
        binary[barrier > 0] = 0
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        for label in range(1, count):
            x, y, w, h, area = stats[label]
            if area < side * side * CONFIG["region_min_area_fraction"]:
                continue
            if (
                area / (w * h) < CONFIG["region_min_rectangular_fill"]
                or max(w / h, h / w) > CONFIG["region_max_aspect_ratio"]
            ):
                rejected.append(
                    {
                        "code": "NON_RECTANGULAR_REGION",
                        "bounds_px": [int(x), int(y), int(x + w), int(y + h)],
                    }
                )
                continue
            box = np.array([x - 4, y - 4, x + w + 3, y + h + 3], float)
            box = np.clip(box, [0, 0, 0, 0], [gray.shape[1] - 1, gray.shape[0] - 1] * 2)
            for edge in range(4):
                axis = edge % 2
                normal = axis
                coordinate = box[edge]
                lo = box[1 - axis] + 3
                hi = box[3 - axis] - 3
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
                    xs = candidates if normal == 0 else np.full_like(candidates, int(along))
                    ys = np.full_like(candidates, int(along)) if normal == 0 else candidates
                    good = (gray[ys, xs] < 150) & (probabilities[0, ys, xs] > 0.2)
                    if good.any():
                        good_coordinates = candidates[good]
                        observations.append(
                            float(good_coordinates[np.argmin(abs(good_coordinates - coordinate))])
                        )
                if len(observations) >= 8:
                    box[edge] = float(np.median(observations))
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                continue
            boxes.append(
                {
                    "type": kind,
                    "bounds_px": np.round(box, 3).tolist(),
                    "model_score": float(probabilities[channel][labels == label].mean()),
                }
            )
    boxes.sort(key=lambda r: (-r["model_score"], r["bounds_px"]))
    kept = []
    for box in boxes:
        if any((iou(box["bounds_px"], b["bounds_px"]) > 0.8 for b in kept)):
            continue
        kept.append(box)
    return (regularize_boxes(kept, gray.shape, stroke), rejected)


def logical_boundary_mask(probabilities, gray):
    barrier = np.uint8(probabilities[0] > 0.45) * 255
    ticks = np.uint8(probabilities[3] > CONFIG["tick_model_threshold"])
    count, labels, stats, centers = cv2.connectedComponentsWithStats(ticks)
    candidates = []
    side = max(gray.shape)
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < 3 or max(w, h) > side * 0.12:
            continue
        candidates.append((centers[index], 0 if h >= w else 1))
    for i, (p, axis) in enumerate(candidates):
        for q, other_axis in candidates[i + 1 :]:
            if axis != other_axis or abs(p[1 - axis] - q[1 - axis]) > max(3, side * 0.015):
                continue
            lo, hi = sorted([p[axis], q[axis]])
            fixed = round((p[1 - axis] + q[1 - axis]) / 2)
            if (
                not side * CONFIG["opening_min_fraction"]
                < hi - lo
                < side * CONFIG["opening_max_fraction"]
            ):
                continue
            samples = np.arange(round(lo) + 3, round(hi) - 2)
            if not len(samples):
                continue
            ink = gray[fixed, samples] if axis == 0 else gray[samples, fixed]
            if (ink < 145).mean() > CONFIG["gap_ink_max_fraction"]:
                continue
            supports = []
            for end, direction in [(lo, -1), (hi, 1)]:
                samples = np.arange(
                    round(end) + direction * 3, round(end) + direction * 10, direction
                )
                samples = samples[(samples >= 0) & (samples < gray.shape[1 - axis])]
                normals = np.arange(max(0, fixed - 3), min(gray.shape[axis], fixed + 4))
                patch = (
                    probabilities[0][np.ix_(normals, samples)]
                    if axis == 0
                    else probabilities[0][np.ix_(samples, normals)].T
                )
                supports.append(float(patch.max(axis=0).mean()) if patch.size else 0)
            if min(supports) < 0.35:
                continue
            a = (round(lo), fixed) if axis == 0 else (fixed, round(lo))
            b = (round(hi), fixed) if axis == 0 else (fixed, round(hi))
            cv2.line(barrier, a, b, 255, 3)
    interface = np.uint8(probabilities[5] > CONFIG["interface_model_threshold"]) * 255
    barrier = cv2.bitwise_or(barrier, interface)
    return cv2.dilate(barrier, np.ones((3, 3), np.uint8))


def regularize_boxes(boxes, shape, stroke=None):
    result = copy.deepcopy(boxes)
    side = max(shape)
    tolerance = min(side * CONFIG["snap_max_fraction"], max(2, (stroke or 2) * 2))
    for i, a in enumerate(result):
        for b in result[i + 1 :]:
            A, B = (a["bounds_px"], b["bounds_px"])
            for axis in (0, 1):
                overlap = min(A[3 - axis], B[3 - axis]) - max(A[1 - axis], B[1 - axis])
                if overlap < 8:
                    continue
                for ea, eb in [(axis + 2, axis), (axis, axis + 2)]:
                    if abs(A[ea] - B[eb]) <= tolerance:
                        value = round((A[ea] + B[eb]) / 2, 3)
                        A[ea] = B[eb] = value
    kept = []
    for box in result:
        if any((iou(box["bounds_px"], b["bounds_px"]) > 0 for b in kept)):
            continue
        kept.append(box)
    return sorted(kept, key=lambda b: (b["bounds_px"][1], b["bounds_px"][0]))


def boundary_graph(boxes):
    from .room_geometry import polygon_points

    corners = [p for box in boxes for p in polygon_points(box)]
    segments = {}
    region_edges = []
    for index, box in enumerate(boxes):
        points = polygon_points(box)
        edge_keys = []
        for a, b in zip(points, points[1:] + points[:1]):
            axis = 0 if a[1] == b[1] else 1
            fixed = a[1 - axis]
            lo, hi = sorted((a[axis], b[axis]))
            cuts = sorted(
                {lo, hi} | {p[axis] for p in corners if p[1 - axis] == fixed and lo < p[axis] < hi}
            )
            pieces = []
            for low, high in zip(cuts, cuts[1:]):
                p = (low, fixed) if axis == 0 else (fixed, low)
                q = (high, fixed) if axis == 0 else (fixed, high)
                key = (p, q)
                segments.setdefault(key, []).append(index)
                pieces.append(key)
            edge_keys.extend(pieces if a[axis] < b[axis] else reversed(pieces))
        region_edges.append(edge_keys)
    return (segments, region_edges)


def _runs(binary):
    values = np.r_[False, binary, False].astype(np.int8)
    changes = np.diff(values)
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def opening_candidates(segments, gray, probabilities=None):
    side = max(gray.shape)
    stroke = stroke_scale(gray)
    radius = max(2, round(stroke * 0.65))
    proposals = []
    unresolved = []
    for (a, b), owners in segments.items():
        if len(owners) != 2:
            continue
        axis = 0 if a[1] == b[1] else 1
        fixed = round(a[1 - axis])
        lo, hi = (round(a[axis]), round(b[axis]))
        if hi - lo < side * 0.06:
            continue
        along = np.arange(lo, hi + 1)
        normal = np.arange(max(0, fixed - radius), min(gray.shape[axis] - 1, fixed + radius) + 1)
        ribbon = gray[np.ix_(normal, along)] if axis == 0 else gray[np.ix_(along, normal)].T
        ink = (ribbon < 145).mean(axis=0)
        ink = np.convolve(ink, np.ones(3) / 3, mode="same")
        for start, end in _runs(ink < CONFIG["gap_ink_max_fraction"]):
            start += lo
            end += lo - 1
            width = end - start
            if (
                width < side * CONFIG["opening_min_fraction"]
                or width > side * CONFIG["opening_max_fraction"]
            ):
                continue
            if start - lo < 2 or hi - end < 2:
                continue

            def tick(t):
                minimum = max(radius + 1, 3)
                maximum = max(minimum + 3, round(stroke * 3))
                supports = []
                scores = []
                for sign in (-1, 1):
                    cross = np.arange(fixed + sign * minimum, fixed + sign * maximum + sign, sign)
                    cross = cross[(cross >= 0) & (cross < gray.shape[axis])]
                    nearby = np.arange(
                        max(0, t - radius - 2), min(gray.shape[1 - axis] - 1, t + radius + 2) + 1
                    )
                    patch = (
                        gray[np.ix_(cross, nearby)] if axis == 0 else gray[np.ix_(nearby, cross)].T
                    )
                    supports.append(float((patch.min(axis=1) < 160).mean()) if patch.size else 0)
                    if probabilities is not None:
                        patch = (
                            probabilities[3][np.ix_(cross, nearby)]
                            if axis == 0
                            else probabilities[3][np.ix_(nearby, cross)].T
                        )
                        scores.append(float(patch.max()) if patch.size else 0)
                return (min(supports), min(scores) if scores else 1)

            tick_a, tick_b = (tick(start), tick(end))
            raw = min(tick_a[0], tick_b[0])
            model_score = min(tick_a[1], tick_b[1])
            interface = 0.0
            if probabilities is not None:
                idx = np.arange(start, end + 1)
                interface = float(
                    probabilities[5, fixed, idx].mean()
                    if axis == 0
                    else probabilities[5, idx, fixed].mean()
                )
            if (
                raw >= CONFIG["tick_min_raw_support"]
                and model_score >= CONFIG["tick_model_threshold"]
            ):
                kind = "door"
            elif probabilities is not None and interface >= CONFIG["interface_model_threshold"]:
                kind = "open_passage"
            else:
                unresolved.append(
                    {
                        "code": "GAP_WITHOUT_PAIRED_TICKS_OR_INTERFACE",
                        "wall_segment": [list(a), list(b)],
                        "interval_px": [start, end],
                    }
                )
                continue
            p = [start, fixed] if axis == 0 else [fixed, start]
            q = [end, fixed] if axis == 0 else [fixed, end]
            proposals.append(
                {
                    "segment": (a, b),
                    "entity_indices": owners,
                    "start": p,
                    "end": q,
                    "type": kind,
                    "raw_tick_support": raw,
                    "model_tick_score": model_score,
                    "model_interface_score": interface,
                }
            )
    return (proposals, unresolved)


def authoring_document(
    source, preprocessing, boxes, opening_proposals, origin="regularized", evidence_origin="model"
):
    width, height = preprocessing["working_size_px"]
    segments, region_edges = boundary_graph(boxes)
    points = sorted({p for key in segments for p in key})
    junction_ids = {p: f"junction_{i + 1:04d}" for i, p in enumerate(points)}
    wall_ids = {key: f"wall_{i + 1:04d}" for i, key in enumerate(sorted(segments))}
    region_ids = [f"region_{i + 1:04d}" for i in range(len(boxes))]

    def geometry(points):
        return {
            "origin": origin,
            "state": "proposed",
            "evidence_ids": [],
            "points_px": [list(map(float, p)) for p in points],
            "points_normalized": [[float(x) / width, float(y) / height] for x, y in points],
        }

    degree = defaultdict(int)
    for a, b in segments:
        degree[a] += 1
        degree[b] += 1
    topology = {"regions": [], "junctions": [], "walls": [], "openings": [], "connections": []}
    for p in points:
        topology["junctions"].append(
            {
                "id": junction_ids[p],
                "type": {1: "endpoint", 2: "corner", 3: "t", 4: "cross"}.get(degree[p], "unknown"),
                "geometry": geometry([p]),
            }
        )
    from .room_geometry import polygon_points

    region_counts = {"room": 0, "corridor_segment": 0}
    for i, box in enumerate(boxes):
        region_counts[box["type"]] += 1
        topology["regions"].append(
            {
                "id": region_ids[i],
                "name": ("Corridor" if box["type"] == "corridor_segment" else "Room")
                + f" {region_counts[box['type']]}",
                "type": box["type"],
                "wall_ids": [wall_ids[key] for key in region_edges[i]],
                "geometry": geometry(polygon_points(box)),
            }
        )
    interface_keys = {p["segment"] for p in opening_proposals if p["type"] == "open_passage"}
    for key, owners in sorted(segments.items()):
        topology["walls"].append(
            {
                "id": wall_ids[key],
                "type": "interface" if key in interface_keys else "wall",
                "start_junction_id": junction_ids[key[0]],
                "end_junction_id": junction_ids[key[1]],
                "entity_ids": [region_ids[i] for i in owners],
                "geometry": geometry(key),
            }
        )
    connections = {}
    for proposal in opening_proposals:
        key = proposal["segment"]
        if key not in wall_ids or len(segments[key]) != 2:
            continue
        owner_ids = [region_ids[i] for i in segments[key]]
        p, q = (proposal["start"], proposal["end"])
        axis = 0 if key[0][1] == key[1][1] else 1
        length = key[1][axis] - key[0][axis]
        lo, hi = [float(np.clip((t[axis] - key[0][axis]) / length, 0, 1)) for t in (p, q)]
        if hi <= lo:
            continue
        oid = f"opening_{len(topology['openings']) + 1:04d}"
        topology["openings"].append(
            {
                "id": oid,
                "type": proposal["type"],
                "support_wall_id": wall_ids[key],
                "entity_ids": owner_ids,
                "placement": {
                    "reference_junction_id": junction_ids[key[0]],
                    "direction": "toward_end",
                    "near_edge_normalized": lo,
                    "interval_normalized": [lo, hi],
                },
                "geometry": geometry([p, q]),
            }
        )
        pair = tuple(sorted(owner_ids))
        if pair not in connections:
            connections[pair] = {
                "id": f"connection_{len(connections) + 1:04d}",
                "entity_ids": owner_ids,
                "opening_ids": [],
                "shared_span_normalized": [0, 1],
                "geometry": geometry([]),
            }
        connections[pair]["opening_ids"].append(oid)
    topology["connections"] = list(connections.values())
    return {
        "schema_version": "playablesketch-shape-authoring/2.0",
        "document_id": "shape_" + source["image_sha256"][:20],
        "revision_id": "proposal_1",
        "parent_revision_id": None,
        "policy_version": "shape-sizing/1.0",
        "image_evidence": {
            "source": source,
            "working_size_px": [width, height],
            "original_to_working": preprocessing["original_to_working"],
            "working_to_original": preprocessing["working_to_original"],
            "normalization_bounds_px": [0, 0, width, height],
            "items": [],
        },
        "topology": topology,
        "physical_design": {
            "units": "cm",
            "anchor": {"junction_id": None, "position_cm": [0, 0]},
            "orientation_degrees": 0,
            "values": [],
            "acceptance": {"status": "pending", "revision_id": None, "reviewer": None},
        },
    }
