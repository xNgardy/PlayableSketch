import itertools
import math
import cv2
import numpy as np
from .geometry import length, segment_distance, angle_delta

CONFIG = {
    "version": "contextual-openings/3.0",
    "support_min_fraction": 0.018,
    "gap_min_fraction": 0.012,
    "candidate_min_gap_fraction": 0.023,
    "gap_max_fraction": 0.35,
    "context_radius_fraction": 0.02,
    "alignment_base_fraction": 0.009,
    "alignment_gap_fraction": 0.12,
    "alignment_cap_fraction": 0.03,
    "direction_tolerance_degrees": 20,
    "continuous_ink_fraction": 0.75,
    "context_segment_extension_fraction": 0.1,
}


def direction(line):
    v = np.asarray(line["end"], float) - line["start"]
    return v / max(np.linalg.norm(v), 1e-09)


def endpoint_context(endpoint, axis, lines, radius):
    result = []
    for line in lines:
        if line["axis"] == axis:
            continue
        distance = float(segment_distance([endpoint], line["start"], line["end"])[0])
        if distance <= radius:
            result.append((distance, line))
    return sorted(result, key=lambda pair: pair[0])


def anchor(endpoint, other_line, axis_vector):
    a = np.asarray(other_line["start"], float)
    v = direction(other_line)
    system = np.column_stack((axis_vector, -v))
    if abs(np.linalg.det(system)) < 0.2:
        return np.asarray(endpoint, float)
    t, _ = np.linalg.solve(system, a - endpoint)
    return np.asarray(endpoint) + axis_vector * t


def blocked_by_ink(p, q, ink):
    if ink is None:
        return (False, 0.0)
    points = np.linspace(p, q, max(5, round(np.linalg.norm(q - p))))
    points = points[max(1, len(points) // 5) : -max(1, len(points) // 5)]
    coords = np.rint(points).astype(int)
    coords[:, 0] = np.clip(coords[:, 0], 0, ink.shape[1] - 1)
    coords[:, 1] = np.clip(coords[:, 1], 0, ink.shape[0] - 1)
    fraction = float((ink[coords[:, 1], coords[:, 0]] > 0).mean())
    return (fraction >= CONFIG["continuous_ink_fraction"], fraction)


def same_proposal(a, b, side):
    if a["axis"] != b["axis"]:
        return False
    p, q = (np.asarray(a["start"]), np.asarray(a["end"]))
    v = (q - p) / max(np.linalg.norm(q - p), 1e-09)
    normal = np.array([-v[1], v[0]])
    r, s = (np.asarray(b["start"]), np.asarray(b["end"]))
    if abs((r + s - p - q) / 2 @ normal) > max(5, side * 0.009):
        return False
    ia = sorted([p @ v, q @ v])
    ib = sorted([r @ v, s @ v])
    overlap = max(0, min(ia[1], ib[1]) - max(ia[0], ib[0]))
    return overlap / max(1, min(ia[1] - ia[0], ib[1] - ib[0])) >= 0.65


def plausible_pairs(support, side):
    if not support:
        return
    starts = np.asarray([l["start"] for l in support], float)
    ends = np.asarray([l["end"] for l in support], float)
    vectors = ends - starts
    units = vectors / np.maximum(np.linalg.norm(vectors, axis=1)[:, None], 1e-09)
    angles = np.degrees(np.arctan2(units[:, 1], units[:, 0]))
    axes = np.asarray([l["axis"] for l in support])
    for i, a in enumerate(support):
        js = np.flatnonzero(
            (np.arange(len(support)) > i)
            & (axes == axes[i])
            & (
                np.abs((angles - angles[i] + 90) % 180 - 90)
                <= CONFIG["direction_tolerance_degrees"] + 1
            )
        )
        if not len(js):
            continue
        other = units[js].copy()
        other[other @ units[i] < 0] *= -1
        v = other + units[i]
        v /= np.maximum(np.linalg.norm(v, axis=1)[:, None], 1e-09)
        a0 = v @ starts[i]
        a1 = v @ ends[i]
        b0 = np.sum(v * starts[js], axis=1)
        b1 = np.sum(v * ends[js], axis=1)
        disjoint = (
            np.minimum(np.maximum(a0, a1), np.maximum(b0, b1))
            <= np.maximum(np.minimum(a0, a1), np.minimum(b0, b1)) + 1
        )
        delta = np.stack(
            [
                starts[js] - starts[i],
                ends[js] - starts[i],
                starts[js] - ends[i],
                ends[js] - ends[i],
            ],
            axis=1,
        )
        selected = np.argmin(np.linalg.norm(delta, axis=2), axis=1)
        d = delta[np.arange(len(js)), selected]
        span = np.abs(np.sum(d * v, axis=1))
        offset = np.abs(np.sum(d * np.c_[-v[:, 1], v[:, 0]], axis=1))
        keep = (
            disjoint
            & (span > max(1, side * 0.004) - 1)
            & (span < side * CONFIG["gap_max_fraction"] + 1)
            & (offset <= max(8, side * 0.04) + 1)
        )
        for j in js[keep]:
            yield (a, support[j])


def gap_evidence(lines, texts, shape, *, recovery_lines=(), ink=None, diagnostics=True):
    side = max(shape)
    radius = max(10, side * CONFIG["context_radius_fraction"])
    pool = list(lines) + list(recovery_lines)
    support = [l for l in pool if length(l) >= max(8, side * CONFIG["support_min_fraction"])]
    trusted = [l for l in lines if l["role"] == "wall_candidate"]
    proposals = []
    context_cache = {}
    credibility_cache = {}
    axes = {line["axis"] for line in pool}

    def arrays(items):
        start = np.asarray([l["start"] for l in items], float).reshape(-1, 2)
        end = np.asarray([l["end"] for l in items], float).reshape(-1, 2)
        vector = end - start
        return (items, start, vector, np.maximum(np.sum(vector * vector, axis=1), 1e-12))

    perpendicular = {axis: arrays([l for l in pool if l["axis"] != axis]) for axis in axes}
    structural = {axis: arrays([l for l in trusted if l["axis"] == axis]) for axis in axes}

    def distances(point, data):
        _, start, vector, norm = data
        t = np.clip(np.sum((np.asarray(point) - start) * vector, axis=1) / norm, 0, 1)
        return np.linalg.norm(np.asarray(point) - (start + t[:, None] * vector), axis=1)

    def context(endpoint, axis):
        key = (tuple(endpoint), axis)
        if key not in context_cache:
            data = perpendicular[axis]
            context_cache[key] = sorted(
                (
                    (float(d), line)
                    for d, line in zip(distances(endpoint, data), data[0])
                    if d <= radius
                ),
                key=lambda pair: pair[0],
            )
        return context_cache[key]

    def credible(line):
        key = line["id"]
        if key not in credibility_cache:
            data = structural[line["axis"]]
            credibility_cache[key] = line["role"] == "wall_candidate" or bool(
                np.any(
                    np.minimum(distances(line["start"], data), distances(line["end"], data))
                    <= max(5, side * 0.006)
                )
            )
        return credibility_cache[key]

    for a, b in plausible_pairs(support, side):
        if a["axis"] != b["axis"]:
            continue
        axis = a["axis"]
        v = direction(a)
        bv = direction(b)
        if v @ bv < 0:
            bv = -bv
        v = v + bv
        v /= max(np.linalg.norm(v), 1e-09)
        if (
            angle_delta(
                math.degrees(math.atan2(*direction(a)[::-1])),
                math.degrees(math.atan2(*direction(b)[::-1])),
            )
            > CONFIG["direction_tolerance_degrees"]
        ):
            continue
        normal = np.array([-v[1], v[0]])
        ia = sorted(np.asarray([a["start"], a["end"]]) @ v)
        ib = sorted(np.asarray([b["start"], b["end"]]) @ v)
        if min(ia[1], ib[1]) > max(ia[0], ib[0]):
            continue
        p, q = min(
            (
                (np.asarray(p, float), np.asarray(q, float))
                for p in [a["start"], a["end"]]
                for q in [b["start"], b["end"]]
            ),
            key=lambda pair: np.linalg.norm(pair[0] - pair[1]),
        )
        delta = q - p
        span = abs(float(delta @ v))
        offset = abs(float(delta @ normal))
        if not max(1, side * 0.004) < span < side * CONFIG["gap_max_fraction"] or offset > max(
            8, side * 0.04
        ):
            continue
        limit = min(
            side * CONFIG["alignment_cap_fraction"],
            max(5, side * CONFIG["alignment_base_fraction"])
            + span * CONFIG["alignment_gap_fraction"],
        )
        reasons = []
        if offset > limit:
            reasons.append("alignment")
        if span < side * CONFIG["gap_min_fraction"]:
            reasons.append("small_stroke_break")
        if all((l.get("text_overlap_fraction", 0) > 0.8 for l in [a, b])):
            reasons.append("text_only_support")
        if reasons and (not diagnostics):
            continue
        credibility = [credible(a), credible(b)]
        if not any(credibility):
            reasons.append("no_structural_support")
        midpoint = (p + q) / 2
        blockers = [
            c["id"]
            for d, c in zip(distances(midpoint, structural[axis]), structural[axis][0])
            if c["id"] not in (a["id"], b["id"]) and d < max(5, side * 0.006)
        ]
        if blockers:
            reasons.append("wall_across_gap")
        if reasons and (not diagnostics):
            continue
        cp = context(p, axis)
        cq = context(q, axis)
        context_pairs = []
        ordered_context = sorted(
            itertools.product(cp[:12], cq[:12]), key=lambda pair: pair[0][0] + pair[1][0]
        )
        for (dp, lp), (dq, lq) in ordered_context:
            if lp["id"] == lq["id"]:
                continue
            ap = anchor(p, lp, v)
            aq = anchor(q, lq, v)
            if abs(float((aq - ap) @ v)) < 0.5 * span:
                continue
            context_pairs.append((dp + dq, lp, lq, ap, aq))
            break
        tick_ids = []
        context_ids = [[], []]
        context_parameters = [None, None]
        endpoint_cost = 2 * radius
        if not context_pairs:
            reasons.append("missing_distinct_endpoint_context")
        else:
            endpoint_cost, lp, lq, ap, aq = min(context_pairs, key=lambda pair: pair[0])
            context_ids = [[lp["id"]], [lq["id"]]]

            def segment_parameter(point, line):
                start = np.asarray(line["start"], float)
                vector = np.asarray(line["end"], float) - start
                return float(
                    np.dot(np.asarray(point, float) - start, vector)
                    / max(float(np.dot(vector, vector)), 1e-09)
                )

            context_parameters = [segment_parameter(p, lp), segment_parameter(q, lq)]
            extension = CONFIG["context_segment_extension_fraction"]
            if any((t < -extension or t > 1 + extension for t in context_parameters)):
                reasons.append("context_on_extension_only")
            tick_ids = [c["id"] for c in [lp, lq] if length(c) < side * 0.1]
            if (
                len(tick_ids) == 2
                and np.linalg.norm(ap - p) <= radius
                and (np.linalg.norm(aq - q) <= radius)
            ):
                p, q = (ap, aq)
        final_span = float(np.linalg.norm(q - p))
        if (
            final_span < side * CONFIG["candidate_min_gap_fraction"]
            and "small_stroke_break" not in reasons
        ):
            reasons.append("small_gap_needs_review")
        blocked, ink_fraction = blocked_by_ink(p, q, ink)
        if blocked:
            reasons.append("continuous_wall_ink")
        if reasons and (not diagnostics):
            continue
        nearby = [
            t["id"]
            for t in texts
            if np.linalg.norm(np.mean(t["polygon_working"], axis=0) - (p + q) / 2)
            <= max(100, 2 * span)
        ]
        numeric = [
            t["id"]
            for t in texts
            if t["id"] in nearby
            and t.get("chosen", {}).get("parsed", {}).get("value_cm") is not None
        ]
        markers = [
            t["id"]
            for t in texts
            if t["id"] in nearby and t.get("chosen", {}).get("parsed", {}).get("door_marker", False)
        ]
        points = np.float32([a["start"], a["end"], b["start"], b["end"]])
        fit = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        residual = float(np.mean(np.abs((points - fit[2:]) @ np.array([-fit[1], fit[0]]))))
        proposals.append(
            {
                "id": "pending",
                "axis": axis,
                "start": p.tolist(),
                "end": q.tolist(),
                "supporting_line_ids": [a["id"], b["id"]],
                "support_roles": [a["role"], b["role"]],
                "sources": [a.get("source", "masked"), b.get("source", "masked")],
                "perpendicular_line_ids": context_ids,
                "context_segment_parameters": context_parameters,
                "nearby_text_ids": nearby,
                "nearby_numeric_text_ids": numeric,
                "door_marker_text_ids": markers,
                "role": "unresolved_gap" if reasons else "opening_candidate",
                "interpretation": (
                    "unknown"
                    if reasons
                    else "door_like" if len(tick_ids) == 2 and numeric else "passage_like"
                ),
                "rejection_reasons": reasons,
                "review_required": True,
                "width_cm": None,
                "score": None,
                "alignment_offset_px": offset,
                "alignment_limit_px": limit,
                "gap_ink_fraction": ink_fraction,
                "midpoint_blockers": blockers,
                "support_line": {
                    "direction": fit[:2].astype(float).tolist(),
                    "point": fit[2:].astype(float).tolist(),
                    "mean_residual_px": residual,
                    "method": "cv2.fitLine/DIST_HUBER",
                },
                "rank_cost": endpoint_cost
                + offset
                + sum((not c for c in credibility)) * radius * 0.2,
            }
        )
    accepted = []
    for proposal in sorted(
        (p for p in proposals if p["role"] == "opening_candidate"), key=lambda p: p["rank_cost"]
    ):
        duplicate = next((p for p in accepted if same_proposal(p, proposal, side)), None)
        if duplicate is None:
            accepted.append(proposal)
        else:
            proposal["role"] = "unresolved_gap"
            proposal["rejection_reasons"].append("duplicate_proposal")
    if not diagnostics:
        proposals = [p for p in proposals if p["role"] == "opening_candidate"]
    proposals.sort(
        key=lambda p: (p["role"] != "opening_candidate", p["axis"], p["start"][1], p["start"][0])
    )
    for i, p in enumerate(proposals, 1):
        p["id"] = f"g{i:03d}"
    return proposals
