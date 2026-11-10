import copy
import cv2
import numpy as np
from . import decoder_refined as d
from .dino_keypoints import endpoint_peaks
from SketchPipeline.perception.structural import suppress_grid

POLICY = {
    "version": "opening-ablation/1.0",
    "endpoint_threshold": 0.5,
    "normal_search_side_fraction": 0.025,
    "normal_search_strokes": 6,
    "path_median_window": 7,
    "path_max_slope": 1.0,
    "candidate_pairing": "adjacent sorted peaks within each shared span",
    "baseline_precedence": True,
    "new_open_passages": False,
}


def wall_path(structural, axis, fixed, lo, hi, bound):
    along = np.arange(lo, hi + 1)
    observed = []
    indices = []
    for i, t in enumerate(along):
        normal = np.arange(
            max(0, int(np.ceil(fixed - bound))),
            min(structural.shape[axis], int(np.floor(fixed + bound)) + 1),
        )
        values = structural[normal, t] if axis == 0 else structural[t, normal]
        groups = d.runs(values > 0)
        centers = [float(normal[a:b].mean()) for a, b in groups]
        if centers:
            observed.append(min(centers, key=lambda x: abs(x - fixed)))
            indices.append(i)
    if len(indices) < 8:
        return np.full(len(along), fixed)
    observations = np.asarray(observed)
    half = POLICY["path_median_window"] // 2
    smooth = np.array(
        [np.median(observations[max(0, i - half) : i + half + 1]) for i in range(len(observations))]
    )
    path = np.interp(np.arange(len(along)), indices, smooth)
    for sweep in (range(1, len(path)), range(len(path) - 2, -1, -1)):
        direction = 1 if sweep.start == 1 else -1
        for i in sweep:
            path[i] = np.clip(
                path[i],
                path[i - direction] - POLICY["path_max_slope"],
                path[i - direction] + POLICY["path_max_slope"],
            )
    return np.clip(path, fixed - bound, fixed + bound)


def experiment(
    segments, gray, probabilities, matrix, endpoint_map, *, endpoint_first=False, tracking=False
):
    baseline, evidence = d.opening_candidates(segments, gray, probabilities, matrix)
    proposals = copy.deepcopy(baseline)
    records = []
    cleaned, _, _ = suppress_grid(gray)
    ink, stroke, _ = d.ink_evidence(cleaned)
    peaks = endpoint_peaks(endpoint_map, POLICY["endpoint_threshold"])
    matrix = np.asarray(matrix, float)
    for segment, owners in segments.items():
        if len(owners) != 2:
            continue
        p = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        p = p[:, :2] / p[:, 2:]
        axis = 0 if segment[0][1] == segment[1][1] else 1
        lo, hi = sorted(p[:, axis])
        start = max(0, int(np.ceil(lo)))
        stop = min(gray.shape[1 - axis] - 1, int(np.floor(hi)))
        if stop <= start:
            continue
        scale = matrix[axis, axis]
        fixed = d.fit_axis(ink, axis, float(p[:, 1 - axis].mean()), lo, hi, stroke, scale)
        radius = max(1, round(max(stroke * 2, scale * 2)))
        length = max(3, round(max(stroke * 4, scale * d.POLICY["axis_support_length_units"]))) | 1
        nw = max(1, round(stroke)) | 1
        structural = cv2.morphologyEx(
            cv2.dilate(ink, np.ones((nw, 1) if axis == 0 else (1, nw), np.uint8)),
            cv2.MORPH_OPEN,
            np.ones((1, length) if axis == 0 else (length, 1), np.uint8),
        )
        bound = max(
            max(gray.shape) * POLICY["normal_search_side_fraction"],
            stroke * POLICY["normal_search_strokes"],
        )
        path = (
            wall_path(structural, axis, fixed, start, stop, bound)
            if tracking
            else np.full(stop - start + 1, fixed)
        )

        def at(t):
            return float(path[int(np.clip(round(t) - start, 0, len(path) - 1))])

        def occupied(t):
            if not start <= t <= stop:
                return False
            patch = d.ribbon(structural, axis, at(t), [t], radius)
            return bool(patch.size and patch.max())

        occupancy = np.array([occupied(t) for t in range(start, stop + 1)])
        candidates = []
        if tracking:
            candidates += [(start + a, start + b - 1, "tracked_gap") for a, b in d.runs(~occupancy)]
        if endpoint_first:
            eligible = sorted(
                [p for p in peaks if lo <= p[axis] <= hi and abs(p[1 - axis] - fixed) <= bound],
                key=lambda p: p[axis],
            )
            candidates += [
                (a[axis], b[axis], "endpoint_pair") for a, b in zip(eligible, eligible[1:])
            ]
        for a, b, source in candidates:
            width = b - a
            minimum = max(
                stroke * d.POLICY["minimum_gap_strokes"],
                max(gray.shape) * d.POLICY["minimum_gap_side_fraction"],
            )
            record = {
                "segment": segment,
                "source": source,
                "native_interval": [a, b],
                "tracking": tracking,
                "axis": axis,
                "fixed": fixed,
                "path_px": path.tolist(),
            }
            if width < minimum or width > max(gray.shape) * d.POLICY["maximum_gap_side_fraction"]:
                records.append(dict(record, status="rejected", reason="gap_width"))
                continue
            first = d.tick_evidence(ink, probabilities[3], axis, at(a), a, stroke, scale)
            second = d.tick_evidence(ink, probabilities[3], axis, at(b), b, stroke, scale)
            x, y = (first["position_px"], second["position_px"])
            support_len = max(4, round(max(stroke * 6, scale * 8)))
            margin = max(1, round(stroke)) if source == "endpoint_pair" else 0
            supports = [
                np.mean(
                    [occupied(t) for t in range(round(a) - margin - support_len, round(a) - margin)]
                ),
                np.mean(
                    [
                        occupied(t)
                        for t in range(round(b) + margin + 1, round(b) + margin + support_len + 1)
                    ]
                ),
            ]
            interior = range(round(a) + margin, round(b) - margin + 1)
            clear = float(1 - np.mean([occupied(t) for t in interior])) if len(interior) else 0.0
            raw = min(first["raw_support"], second["raw_support"])
            semantic = min(first["model_center_response"], second["model_center_response"])
            model_supported = (
                raw >= d.POLICY["raw_tick_min_support"]
                and semantic >= d.POLICY["model_tick_center_min"]
            )
            strong_raw = (
                raw >= d.POLICY["strong_tick_min_support"]
                and min(supports) >= d.POLICY["strong_wall_support_min"]
                and (clear >= d.POLICY["strong_gap_clear_min"])
                and (a - lo >= stroke * 4)
                and (hi - b >= stroke * 4)
                and (width >= stroke * 5)
            )
            tests = {
                "paired_ticks": model_supported or strong_raw,
                "wall_support": min(supports) >= d.POLICY["wall_support_min"],
                "gap_clear": clear >= d.POLICY["gap_clear_min"],
                "span": y - x >= stroke * d.POLICY["minimum_clear_span_strokes"],
            }
            record.update(
                ticks=[first, second],
                wall_support=supports,
                gap_clear_fraction=clear,
                tests=tests,
                model_supported=model_supported,
                strong_raw=strong_raw,
            )
            if not all(tests.values()):
                records.append(dict(record, status="rejected", reason="physical_evidence"))
                continue
            ca, cb = [(v - matrix[axis, 2]) / matrix[axis, axis] for v in (x, y)]
            if not segment[0][axis] <= ca < cb <= segment[1][axis]:
                records.append(dict(record, status="rejected", reason="outside_support"))
                continue
            begin = list(segment[0])
            end = list(segment[1])
            begin[axis] = ca
            end[axis] = cb
            if any(
                (
                    q["segment"] == segment and min(q["end"][axis], cb) > max(q["start"][axis], ca)
                    for q in proposals
                )
            ):
                records.append(
                    dict(record, status="suppressed", reason="overlap_baseline_or_earlier")
                )
                continue
            record.update(status="proposed", type="door")
            proposals.append(
                {
                    "segment": segment,
                    "entity_indices": owners,
                    "start": begin,
                    "end": end,
                    "type": "door",
                    "evidence": record,
                }
            )
            records.append(record)
    return (proposals, {"baseline": evidence, "experimental_candidates": records, "policy": POLICY})
