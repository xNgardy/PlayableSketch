import copy
from itertools import combinations
import cv2
import numpy as np
from .corridor_candidates import wall_ink
from .door_geometry import sample_line, wall_level
from .decoder import boundary_graph, authoring_document
from .decoder_refined import decode as geometry_decode
from .dino_keypoints import endpoint_peaks
from .corridor_junctions import project_boxes

POLICY = {
    "version": "task-ensemble/1.0",
    "endpoint_threshold": 0.5,
    "maximum_axis_offset_fraction": 0.04,
    "maximum_endpoint_search_pixels": 3,
    "minimum_crossing_support": 0.6,
    "minimum_wall_support": 0.65,
    "minimum_gap_clear": 0.85,
    "geometry_foreground_fraction_min": 0.25,
    "review_required": True,
}


def crossing_jamb(ink, axis, fixed, endpoint):
    side = max(ink.shape)
    normal = 1 - axis
    best = None
    for along in range(round(endpoint) - 3, round(endpoint) + 4):
        fractions = []
        for sign in (-1, 1):
            offsets = np.arange(3, max(7, round(side * 0.016)) + 1) * sign
            normals = np.rint(fixed + offsets).astype(int)
            normals = normals[(normals >= 0) & (normals < ink.shape[1 - normal])]
            positions = np.arange(max(0, along - 2), min(ink.shape[1 - axis], along + 3))
            if len(normals) < 4 or not len(positions):
                fractions.append(0.0)
                continue
            patch = (
                ink[np.ix_(normals, positions)] if axis == 0 else ink[np.ix_(positions, normals)].T
            )
            fractions.append(float(patch.max(axis=1).mean()))
        center = sample_line(ink, axis, fixed, along - 1, along + 1, 1)
        support = min(fractions) if len(center) and center.any() else 0.0
        rank = (support, -abs(along - endpoint))
        if best is None or rank > best[0]:
            best = (rank, float(along), fractions)
    return {"position": best[1], "support": best[0][0], "legs": best[2]}


def guided_doors(proposals, boxes, gray, endpoint_probability, working_to_native):
    if endpoint_probability.shape != gray.shape or not np.isfinite(endpoint_probability).all():
        raise ValueError("Endpoint map/image frames differ")
    matrix = np.asarray(working_to_native, float)
    if (
        not np.allclose(matrix[2], [0, 0, 1])
        or abs(matrix[0, 1]) + abs(matrix[1, 0]) > 1e-06
        or min(matrix[0, 0], matrix[1, 1]) <= 0
    ):
        raise ValueError("Aligned positive evidence transform required")
    result = copy.deepcopy(proposals)
    ink = wall_ink(gray)
    side = max(gray.shape)
    peaks = endpoint_peaks(endpoint_probability, POLICY["endpoint_threshold"])
    records = []
    pool = {}
    for segment, owners in boundary_graph(boxes)[0].items():
        if len(owners) != 2:
            continue
        native = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        native = native[:, :2] / native[:, 2:]
        axis = 0 if segment[0][1] == segment[1][1] else 1
        normal = 1 - axis
        lo, hi = sorted(native[:, axis])
        fixed = float(native[:, normal].mean())
        bound = side * 0.04
        near = [p for p in peaks if lo - 4 <= p[axis] <= hi + 4 and abs(p[normal] - fixed) <= bound]
        for first, second in combinations(sorted(near, key=lambda p: p[axis]), 2):
            x, y = (first[axis], second[axis])
            width = y - x
            if not side * 0.012 <= width <= side * 0.15 or abs(
                first[normal] - second[normal]
            ) > max(3, width * 0.4):
                continue
            seed = (first[normal] + second[normal]) / 2
            best = None
            for at in range(round(seed) - 5, round(seed) + 6):
                if abs(at - fixed) > bound:
                    continue
                flank = max(9, width * 0.7)
                levels = [
                    wall_level(ink, axis, at, x - flank, x - 3),
                    wall_level(ink, axis, at, y + 3, y + flank),
                ]
                jambs = [crossing_jamb(ink, axis, level, p) for level, p in zip(levels, (x, y))]
                a, b = [q["position"] for q in jambs]
                if b - a < side * 0.012:
                    continue
                supports = [
                    sample_line(ink, axis, level, left, right, 3)
                    for level, left, right in [
                        (levels[0], a - flank, a - 3),
                        (levels[1], b + 3, b + flank),
                    ]
                ]
                supports = [float(q.mean()) if len(q) else 0.0 for q in supports]
                gap = sample_line(ink, axis, float(np.mean(levels)), a + 3, b - 3, 1)
                clear = float(1 - gap.mean()) if len(gap) >= 3 else 0.0
                physical = min((q["support"] for q in jambs))
                passed = physical >= 0.6 and min(supports) >= 0.65 and (clear >= 0.85)
                rank = (passed, physical, min(supports), clear, -abs(np.mean(levels) - fixed))
                if best is None or rank > best[0]:
                    best = (rank, a, b, levels, jambs, supports, clear)
            if best is None:
                continue
            rank, a, b, levels, jambs, supports, clear = best
            record = {
                "segment": segment,
                "owners": owners,
                "endpoint_peaks": [first, second],
                "refined_interval": [a, b],
                "observed_levels": levels,
                "jambs": jambs,
                "wall_support": supports,
                "gap_clear": clear,
                "status": "candidate" if rank[0] else "rejected",
            }
            records.append(record)
            if (
                not rank[0]
                or a < lo - 4
                or b > hi + 4
                or (min(hi, b) - max(lo, a) < (b - a) * 0.85)
            ):
                continue
            key = (axis, tuple(first), tuple(second))
            distance = abs(np.mean(levels) - fixed)
            pool.setdefault(key, []).append(
                (distance, segment, owners, [max(lo, a), min(hi, b)], record, axis)
            )
    chosen = []
    for options in pool.values():
        options.sort(key=lambda o: o[0])
        best = options[0]
        if len(options) > 1 and options[1][2] != best[2] and (options[1][0] - best[0] <= 2):
            best[4].update(status="rejected", reason="ambiguous_owners")
            continue
        chosen.append(best)
    for distance, segment, owners, interval, record, axis in sorted(chosen, key=lambda o: o[0]):
        a, b = [float((p - matrix[axis, 2]) / matrix[axis, axis]) for p in interval]
        overlaps = lambda p: p["segment"] == segment and min(p["end"][axis], b) > max(
            p["start"][axis], a
        )
        if any((p["type"] == "door" and overlaps(p) for p in result)):
            record.update(status="suppressed", reason="existing_door")
            continue
        result = [p for p in result if not (p["type"] == "open_passage" and overlaps(p))]
        start = list(segment[0])
        end = list(segment[1])
        start[axis] = a
        end[axis] = b
        record.update(status="proposed", type="door", review_required=True)
        result.append(
            {
                "segment": segment,
                "entity_indices": owners,
                "start": start,
                "end": end,
                "type": "door",
                "evidence": record,
            }
        )
    return (result, {"policy": POLICY, "endpoint_peaks": peaks, "candidates": records})


def document_proposals(document):
    walls = {
        w["id"]: tuple((tuple(p) for p in w["geometry"]["points_px"]))
        for w in document["topology"]["walls"]
    }
    indices = {r["id"]: i for i, r in enumerate(document["topology"]["regions"])}
    return [
        {
            "segment": walls[o["support_wall_id"]],
            "entity_indices": [indices[r] for r in o["entity_ids"]],
            "start": o["geometry"]["points_px"][0],
            "end": o["geometry"]["points_px"][1],
            "type": o["type"],
        }
        for o in document["topology"]["openings"]
    ]


def decode(
    gray,
    geometry_probabilities,
    endpoint_probability,
    source,
    metadata,
    *,
    working_gray,
    working_metadata,
    evidence_to_working,
    consensus_probabilities=None,
    geometry_result=None,
):
    if geometry_result is None:
        baseline, detail = geometry_decode(
            gray,
            geometry_probabilities,
            source,
            metadata,
            working_gray=working_gray,
            working_metadata=working_metadata,
            evidence_to_working=evidence_to_working,
            region_policy="supported-corridors",
            opening_policy="corridor-passages",
            door_policy="observed-jambs",
        )
    else:
        baseline, detail = geometry_result
    boxes = detail["region_boxes"]
    rejected = []
    if consensus_probabilities is not None:
        native_boxes = project_boxes(boxes, np.linalg.inv(evidence_to_working))
        recovery = (
            detail["region_reconstruction"].get("observed_corridor_recovery", {}).get("kept", [])
        )
        filtered = []
        for box, native_box in zip(boxes, native_boxes):
            bounds = native_box["bounds_px"]
            is_recovered = any(
                (max((abs(a - b) for a, b in zip(bounds, c["bounds_px"]))) < 0.01 for c in recovery)
            )
            if is_recovered:
                x, y, X, Y = map(round, bounds)
                margin = 2
                foreground = np.maximum(consensus_probabilities[1], consensus_probabilities[2])[
                    y + margin : Y - margin, x + margin : X - margin
                ]
                fraction = float((foreground > 0.5).mean()) if foreground.size else 0.0
                if fraction < POLICY["geometry_foreground_fraction_min"]:
                    rejected.append(
                        {"bounds_px": box["bounds_px"], "foreground_fraction": fraction}
                    )
                    continue
            filtered.append(box)
        if len(filtered) != len(boxes):
            from .passage_refinement import opening_candidates
            from .door_geometry import opening_candidates as raw_doors

            boxes = filtered
            segments = boundary_graph(boxes)[0]
            proposals, _ = opening_candidates(
                segments,
                gray,
                geometry_probabilities,
                np.linalg.inv(evidence_to_working),
                region_types=[b["type"] for b in boxes],
            )
            proposals, _ = raw_doors(proposals, segments, gray, np.linalg.inv(evidence_to_working))
        else:
            proposals = document_proposals(baseline)
    else:
        proposals = document_proposals(baseline)
    proposals, door_detail = guided_doors(
        proposals, boxes, gray, endpoint_probability, np.linalg.inv(evidence_to_working)
    )
    document = authoring_document(
        source, working_metadata, boxes, proposals, evidence_origin="classical"
    )
    return (
        document,
        {
            "version": POLICY["version"],
            "region_boxes": boxes,
            "geometry_decoder": detail,
            "endpoint_detector": door_detail,
            "geometry_consensus_rejections": rejected,
            "region_source_and_endpoint_source_separate": True,
            "review_required": True,
        },
    )


def endpoint_tiles(
    geometry, gray, cleaned, detector, global_probability, working_to_native, max_tiles=8
):
    matrix = np.asarray(working_to_native, float)
    choices = []
    height, width = gray.shape
    for segment, owners in boundary_graph(geometry)[0].items():
        if len(owners) != 2:
            continue
        p = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        p = p[:, :2] / p[:, 2:]
        axis = 0 if segment[0][1] == segment[1][1] else 1
        normal = 1 - axis
        lo, hi = sorted(p[:, axis])
        fixed = float(p[:, normal].mean())
        peaks = endpoint_peaks(global_probability, 0.5)
        near = [
            q
            for q in peaks
            if lo <= q[axis] <= hi and abs(q[normal] - fixed) <= max(gray.shape) * 0.04
        ]
        center = (
            max(near, key=lambda q: global_probability[q[1], q[0]]) if near else np.mean(p, axis=0)
        )
        confidence = max((float(global_probability[q[1], q[0]]) for q in near), default=0.0)
        x = int(np.clip(round(center[0]) - 128, 0, max(0, width - 256)))
        y = int(np.clip(round(center[1]) - 128, 0, max(0, height - 256)))
        choices.append((confidence, x, y))
    chosen = []
    seen = set()
    for confidence, x, y in sorted(choices, reverse=True):
        if (x, y) in seen:
            continue
        seen.add((x, y))
        chosen.append((x, y))
        if len(chosen) >= max_tiles:
            break
    fused = global_probability.copy()
    records = []
    from .contrast import normalize_ink

    for x, y in chosen:
        X = min(width, x + 256)
        Y = min(height, y + 256)
        a, _ = normalize_ink(gray[y:Y, x:X])
        b, _ = normalize_ink(cleaned[y:Y, x:X])
        detector.predict(a, b)
        probability = detector.last_auxiliary[6]
        fused[y:Y, x:X] = np.maximum(fused[y:Y, x:X], probability)
        records.append(
            {
                "bounds_native": [x, y, X, Y],
                "source": "predicted_shared_wall_and_model_endpoint",
                "ground_truth_used": False,
            }
        )
    return (fused, records)
