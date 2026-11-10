import copy
from itertools import combinations
import cv2
import numpy as np
from .corridor_candidates import wall_ink

POLICY = {
    "version": "observed-door-jambs/1.5",
    "maximum_axis_offset_fraction": 0.04,
    "tick_length_range_fraction": [0.012, 0.8],
    "gap_width_range_fraction": [0.012, 0.15],
    "minimum_crossing_leg_fraction": 0.004,
    "minimum_crossing_leg_widths": 2.0,
    "minimum_wall_support": 0.65,
    "minimum_gap_clear": 0.85,
    "review_required": True,
}


def ticks(ink, axis):
    side = max(ink.shape)
    length = max(5, round(side * 0.012))
    kernel = np.ones((length, 1) if axis == 0 else (1, length), np.uint8)
    mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    result = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        along = w if axis == 0 else h
        normal = h if axis == 0 else w
        if not length <= normal <= side * 0.8 or along > max(8, side * 0.035):
            continue
        center = centers[i]
        result.append(
            {
                "at": float(center[axis]),
                "lo": float(y if axis == 0 else x),
                "hi": float(y + h - 1 if axis == 0 else x + w - 1),
                "width": int(along),
            }
        )
    return result


def sample_line(ink, axis, fixed, lo, hi, radius=2):
    positions = np.arange(max(0, int(np.ceil(lo))), min(ink.shape[1 - axis], int(np.floor(hi)) + 1))
    normal = np.arange(
        max(0, round(fixed) - radius), min(ink.shape[axis], round(fixed) + radius + 1)
    )
    if not len(positions) or not len(normal):
        return np.zeros(0, bool)
    patch = ink[np.ix_(normal, positions)] if axis == 0 else ink[np.ix_(positions, normal)].T
    return patch.max(axis=0) > 0


def wall_level(ink, axis, fixed, lo, hi, radius=3):
    along = np.arange(max(0, int(np.ceil(lo))), min(ink.shape[1 - axis], int(np.floor(hi)) + 1))
    normal = np.arange(
        max(0, round(fixed) - radius), min(ink.shape[axis], round(fixed) + radius + 1)
    )
    if not len(along) or not len(normal):
        return fixed
    patch = ink[np.ix_(normal, along)] if axis == 0 else ink[np.ix_(along, normal)].T
    observations = [
        float(np.median(normal[patch[:, i] > 0])) for i in range(len(along)) if patch[:, i].any()
    ]
    return float(np.median(observations)) if observations else fixed


def detect_pairs(gray):
    ink = wall_ink(gray)
    side = max(gray.shape)
    groups = {a: ticks(ink, a) for a in (0, 1)}
    records = []
    found = []
    for axis in (0, 1):
        for a, b in combinations(sorted(groups[axis], key=lambda t: t["at"]), 2):
            x, y = (a["at"], b["at"])
            width = y - x
            if not side * 0.012 <= width <= side * 0.15:
                continue
            required = max(2, int(np.ceil(side * POLICY["minimum_crossing_leg_fraction"])))
            requireds = [
                max(required, t["width"] * POLICY["minimum_crossing_leg_widths"]) for t in (a, b)
            ]
            low = max((t["lo"] + q for t, q in zip((a, b), requireds)))
            high = min((t["hi"] - q for t, q in zip((a, b), requireds)))
            if high < low:
                continue
            best = None
            for at in np.arange(np.ceil(low), np.floor(high) + 1):
                legs = [min(at - t["lo"], t["hi"] - at) for t in (a, b)]
                if max(legs) > side * 0.06:
                    continue
                margin = max(2, a["width"], b["width"])
                flank = max(9, width * 0.7)
                support = []
                for lo, hi in [(x - flank, x - margin), (y + margin, y + flank)]:
                    occupied = sample_line(ink, axis, at, lo, hi, 3)
                    support.append(float(occupied.mean()) if len(occupied) else 0.0)
                gap = sample_line(ink, axis, at, x + margin, y - margin, 1)
                clear = float(1 - gap.mean()) if len(gap) >= 3 else 0.0
                levels = [
                    wall_level(ink, axis, at, x - flank, x - margin),
                    wall_level(ink, axis, at, y + margin, y + flank),
                ]
                actual_legs = [
                    min(level - t["lo"], t["hi"] - level) for level, t in zip(levels, (a, b))
                ]
                passed = (
                    min(support) >= POLICY["minimum_wall_support"]
                    and clear >= POLICY["minimum_gap_clear"]
                    and all((leg >= need for leg, need in zip(actual_legs, requireds)))
                    and (abs(levels[0] - levels[1]) <= max(3, width * 0.4))
                )
                ranking = (
                    passed,
                    min(support),
                    clear,
                    -abs(levels[0] - levels[1]),
                    -abs(at - np.mean(levels)),
                )
                if best is None or ranking > best[0]:
                    best = (ranking, float(np.mean(levels)), support, clear)
            if best is None:
                continue
            rank, at, support, clear = best
            record = {
                "axis": axis,
                "native_interval": [x, y],
                "observed_wall_axis": float(at),
                "wall_support": support,
                "gap_clear_fraction": clear,
                "jambs": [a, b],
                "status": "candidate" if rank[0] else "rejected",
                "source": "observed_ink",
            }
            records.append(record)
            if rank[0]:
                found.append(record)
    return (found, {"policy": POLICY, "pair_tests": records, "ticks": groups})


def opening_candidates(proposals, segments, gray, matrix):
    result = copy.deepcopy(proposals)
    matrix = np.asarray(matrix, float)
    side = max(gray.shape)
    if (
        matrix.shape != (3, 3)
        or abs(matrix[0, 1]) + abs(matrix[1, 0]) > 1e-06
        or min(matrix[0, 0], matrix[1, 1]) <= 0
    ):
        raise ValueError("Door evidence requires aligned positive image axes")
    found, detail = detect_pairs(gray)
    attached = []
    for record in found:
        axis = record["axis"]
        normal = 1 - axis
        x, y = record["native_interval"]
        at = record["observed_wall_axis"]
        width = y - x
        options = []
        for segment, owners in segments.items():
            if len(owners) != 2:
                continue
            native = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
            native = native[:, :2] / native[:, 2:]
            segment_axis = int(abs(native[1, 1] - native[0, 1]) > abs(native[1, 0] - native[0, 0]))
            if segment_axis != axis:
                continue
            lo, hi = sorted(native[:, axis])
            fixed = float(native[:, normal].mean())
            if abs(at - fixed) > side * POLICY["maximum_axis_offset_fraction"]:
                continue
            if x < lo - side * 0.01 or y > hi + side * 0.01:
                continue
            clipped = [max(lo, x), min(hi, y)]
            if clipped[1] - clipped[0] < width * 0.85:
                continue
            options.append((abs(at - fixed), segment, owners, clipped))
        if not options:
            record.update(status="unattached", reason="no_compatible_shared_boundary")
            continue
        options.sort(key=lambda q: q[0])
        distance, segment, owners, interval = options[0]
        if len(options) > 1 and options[1][2] != owners and (options[1][0] - distance <= 2):
            record.update(status="unattached", reason="ambiguous_owners")
            continue
        attached.append((distance, width, segment, owners, interval, record))
    for distance, width, segment, owners, interval, record in sorted(
        attached, key=lambda q: (q[0], q[1])
    ):
        axis = record["axis"]
        a, b = [(t - matrix[axis, 2]) / matrix[axis, axis] for t in interval]
        start = list(segment[0])
        end = list(segment[1])
        start[axis] = a
        end[axis] = b
        overlaps = lambda p: p["segment"] == segment and min(p["end"][axis], b) > max(
            p["start"][axis], a
        )
        if any((p["type"] == "door" and overlaps(p) for p in result)):
            record.update(status="suppressed", reason="existing_door")
            continue
        result = [p for p in result if not (p["type"] == "open_passage" and overlaps(p))]
        record.update(
            status="proposed",
            type="door",
            segment=segment,
            entity_indices=owners,
            axis_offset=distance,
            review_required=True,
        )
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
    detail["candidates"] = found
    return (result, detail)
