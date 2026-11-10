import copy
import heapq
from itertools import combinations
import cv2
import numpy as np

POLICY = {
    "version": "parallel-corridor-experiment/1.0",
    "minimum_length_fraction": 0.045,
    "width_range_fraction": [0.018, 0.16],
    "maximum_slope": 0.18,
    "minimum_wall_support": 0.55,
    "maximum_interior_ink": 0.16,
    "review_required": True,
}


def wall_ink(gray):
    side = max(gray.shape)
    background = cv2.GaussianBlur(gray, (0, 0), max(1.5, side * 0.006))
    contrast = cv2.subtract(background, gray)
    values = contrast[contrast > 3]
    threshold = max(6.0, float(np.percentile(values, 85)) * 0.55) if values.size else 255.0
    return np.uint8(contrast >= threshold)


def lines_from_image(gray):
    ink = wall_ink(gray)
    side = max(gray.shape)
    lines = cv2.HoughLinesP(
        ink * 255,
        1,
        np.pi / 360,
        max(10, round(side * 0.025)),
        minLineLength=side * POLICY["minimum_length_fraction"],
        maxLineGap=side * 0.025,
    )
    groups = {0: [], 1: []}
    for x, y, X, Y in [] if lines is None else lines[:, 0]:
        axis = int(abs(Y - y) > abs(X - x))
        a, b = (x, X) if axis == 0 else (y, Y)
        c, d = (y, Y) if axis == 0 else (x, X)
        if abs(b - a) < 1 or abs(d - c) / abs(b - a) > POLICY["maximum_slope"]:
            continue
        lo, hi = sorted([float(a), float(b)])
        fixed = float(c + d) / 2
        nearby = next(
            (
                g
                for g in groups[axis]
                if abs(g["fixed"] - fixed) < side * 0.012
                and min(g["hi"], hi) - max(g["lo"], lo) > -side * 0.025
            ),
            None,
        )
        if nearby:
            nearby.update(
                fixed=(nearby["fixed"] + fixed) / 2,
                lo=min(lo, nearby["lo"]),
                hi=max(hi, nearby["hi"]),
            )
        else:
            groups[axis].append({"fixed": fixed, "lo": lo, "hi": hi})
    return (ink, groups)


def line_support(ink, axis, fixed, lo, hi):
    along = np.arange(max(0, int(lo) + 2), min(ink.shape[1 - axis], int(hi) - 1))
    normal = np.arange(
        max(0, round(fixed) - max(3, round(max(ink.shape) * 0.015))),
        min(ink.shape[axis], round(fixed) + max(3, round(max(ink.shape) * 0.015)) + 1),
    )
    if not len(along) or not len(normal):
        return 0.0
    patch = ink[np.ix_(normal, along)] if axis == 0 else ink[np.ix_(along, normal)].T
    return float(patch.max(axis=0).mean())


def overlap(a, b):
    w, h = (max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1])))
    return w * h


def touching(a, b, tolerance=1.5):
    for normal in (0, 1):
        axis = 1 - normal
        if min(abs(a[normal + 2] - b[normal]), abs(b[normal + 2] - a[normal])) > tolerance:
            continue
        if min(a[axis + 2], b[axis + 2]) - max(a[axis], b[axis]) >= 3:
            return True
    return False


def recover(gray, boxes, *, bends=False):
    ink, groups = lines_from_image(gray)
    side = max(gray.shape)
    candidates = []
    for axis, lines in groups.items():
        for left, right in combinations(sorted(lines, key=lambda g: g["fixed"]), 2):
            low, high = (left["fixed"], right["fixed"])
            width = high - low
            if (
                not side * POLICY["width_range_fraction"][0]
                <= width
                <= side * POLICY["width_range_fraction"][1]
            ):
                continue
            lo, hi = (max(left["lo"], right["lo"]), min(left["hi"], right["hi"]))
            if hi - lo < max(side * 0.035, width * 0.75):
                continue
            if (
                bends
                and abs(left["lo"] - right["lo"]) <= width * 1.4
                and (abs(left["hi"] - right["hi"]) <= width * 1.4)
            ):
                lo, hi = (min(left["lo"], right["lo"]), max(left["hi"], right["hi"]))
            bound = [lo, low, hi, high] if axis == 0 else [low, lo, high, hi]
            for edge in (axis, axis + 2):
                targets = []
                for region in boxes:
                    b = region["bounds_px"]
                    if (
                        min(bound[3 - axis], b[3 - axis]) - max(bound[1 - axis], b[1 - axis])
                        < width * 0.6
                    ):
                        continue
                    target = b[axis + 2] if edge == axis else b[axis]
                    if abs(bound[edge] - target) <= max(5, width * 0.4):
                        targets.append(target)
                if targets:
                    bound[edge] = min(targets, key=lambda v: abs(bound[edge] - v))
            if bound[axis + 2] - bound[axis] < width * 0.75:
                continue
            supports = [
                line_support(ink, axis, c, bound[axis], bound[axis + 2]) for c in (low, high)
            ]
            if min(supports) < POLICY["minimum_wall_support"]:
                continue
            x, y, X, Y = map(round, bound)
            margin = max(2, round(width * 0.2))
            interior = ink[y + margin : Y - margin, x + margin : X - margin]
            if not interior.size or float(interior.mean()) > POLICY["maximum_interior_ink"]:
                continue
            area = (X - x) * (Y - y)
            if any(
                (
                    overlap(bound, b["bounds_px"])
                    > min(
                        area,
                        (b["bounds_px"][2] - b["bounds_px"][0])
                        * (b["bounds_px"][3] - b["bounds_px"][1]),
                    )
                    * 0.08
                    for b in boxes
                )
            ):
                continue
            if any(
                (max((abs(a - b) for a, b in zip(bound, c["bounds_px"]))) < 3 for c in candidates)
            ):
                continue
            candidates.append(
                {
                    "type": "corridor_segment",
                    "bounds_px": [float(v) for v in bound],
                    "model_score": 0.0,
                    "evidence": {
                        "parallel_wall_support": supports,
                        "source": "observed_ink",
                        "axis": axis,
                    },
                }
            )
    candidates.sort(
        key=lambda c: min(
            c["bounds_px"][2] - c["bounds_px"][0], c["bounds_px"][3] - c["bounds_px"][1]
        )
    )
    if bends:
        for a, b in combinations(candidates, 2):
            if a["evidence"]["axis"] == b["evidence"]["axis"]:
                continue
            vertical, horizontal = (a, b) if a["evidence"]["axis"] == 1 else (b, a)
            V, H = (vertical["bounds_px"], horizontal["bounds_px"])
            if overlap(V, H) <= 0:
                continue
            if H[2] > V[2] + 4 and H[0] >= V[0] - 4:
                H[0] = V[2]
            elif H[0] < V[0] - 4 and H[2] <= V[2] + 4:
                H[2] = V[0]
            else:
                continue
            if V[1] < H[1] and abs(V[3] - H[3]) <= (H[3] - H[1]) * 0.6:
                V[3] = H[3]
            elif V[3] > H[3] and abs(V[1] - H[1]) <= (H[3] - H[1]) * 0.6:
                V[1] = H[1]
    for candidate in candidates:
        bound = candidate["bounds_px"]
        axis = candidate["evidence"]["axis"]
        for edge in (axis, axis + 2):
            for region in boxes:
                b = region["bounds_px"]
                span = min(bound[3 - axis], b[3 - axis]) - max(bound[1 - axis], b[1 - axis])
                target = b[axis + 2] if edge == axis else b[axis]
                if span > 3 and abs(bound[edge] - target) < 2:
                    bound[edge] = target

    def interface(a, b, axis=None):
        for normal in (0, 1) if axis is None else (axis,):
            along = 1 - normal
            faces = [(a[normal + 2], b[normal]), (a[normal], b[normal + 2])]
            for first, second in faces:
                if abs(first - second) > 2:
                    continue
                lo = max(a[along], b[along])
                hi = min(a[along + 2], b[along + 2])
                if hi - lo < 6:
                    continue
                fixed = round((first + second) / 2)
                positions = np.arange(max(0, int(lo) + 1), min(ink.shape[normal] - 1, int(hi)))
                normals = np.arange(max(0, fixed - 2), min(ink.shape[along], fixed + 3))
                patch = (
                    ink[np.ix_(normals, positions)]
                    if along == 0
                    else ink[np.ix_(positions, normals)].T
                )
                if not patch.size:
                    continue
                clear = patch.max(axis=0) == 0
                edges = np.diff(np.r_[False, clear, False].astype(np.int8))
                lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
                if len(lengths) and lengths.max() >= max(5, max(ink.shape) * 0.01):
                    return True
        return False

    count = len(candidates)
    graph = {i: set() for i in range(count + len(boxes))}
    for i, a in enumerate(candidates):
        for j, b in enumerate(candidates[:i]):
            if overlap(a["bounds_px"], b["bounds_px"]) == 0 and interface(
                a["bounds_px"], b["bounds_px"]
            ):
                graph[i].add(j)
                graph[j].add(i)
        for j, b in enumerate(boxes):
            if interface(a["bounds_px"], b["bounds_px"], a["evidence"]["axis"]):
                graph[i].add(count + j)
                graph[count + j].add(i)
    selected = set()
    for start, goal in combinations(range(count, count + len(boxes)), 2):
        queue = [(0.0, start, ())]
        seen = set()
        while queue:
            cost, node, path = heapq.heappop(queue)
            if node in seen:
                continue
            seen.add(node)
            if node == goal:
                selected.update((p for p in path if p < count))
                break
            if node >= count and node != start:
                continue
            for nxt in graph[node] - seen:
                c = candidates[nxt]["bounds_px"] if nxt < count else None
                extra = (c[2] - c[0]) * (c[3] - c[1]) if c else 0
                heapq.heappush(queue, (cost + extra, nxt, path + (nxt,)))
    result = copy.deepcopy(boxes)
    kept = []
    for i in sorted(selected):
        c = candidates[i]
        B = c["bounds_px"]
        area = (B[2] - B[0]) * (B[3] - B[1])
        if min(B[2] - B[0], B[3] - B[1]) <= 0:
            continue
        if any((overlap(B, b["bounds_px"]) > 0.03 * area for b in result)):
            continue
        kept.append(c)
        result.append({k: v for k, v in c.items() if k != "evidence"})
    return (
        result,
        {
            "policy": POLICY,
            "bends": bends,
            "lines": groups,
            "raw_candidates": candidates,
            "kept": kept,
        },
    )
