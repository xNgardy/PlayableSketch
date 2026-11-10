import numpy as np

POLICY = {
    "version": "opening-alignment/1.0",
    "maximum_endpoint_overshoot_evidence_px": 2.0,
    "minimum_retained_interval_fraction": 0.85,
    "review_required": True,
}


def align_interval(segment, owners, endpoints, matrix, segments):
    matrix = np.asarray(matrix, float)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or (not np.allclose(matrix[2], [0, 0, 1]))
        or (abs(matrix[0, 1]) + abs(matrix[1, 0]) > 1e-06)
        or (min(matrix[0, 0], matrix[1, 1]) <= 0)
    ):
        raise ValueError("Aligned positive evidence transform required")
    axis = 0 if segment[0][1] == segment[1][1] else 1
    scale = matrix[axis, axis]
    lo, hi = sorted((float(float(p[axis]) * scale + matrix[axis, 2]) for p in segment))
    a, b = sorted((float(float(v) * scale + matrix[axis, 2]) for v in endpoints))
    clipped = [max(lo, a), min(hi, b)]
    overshoot = max(0.0, lo - a, b - hi)
    detail = {
        "observed_interval_evidence_px": [a, b],
        "support_interval_evidence_px": [lo, hi],
        "endpoint_overshoot_evidence_px": overshoot,
        "policy": POLICY,
    }
    if b <= a or clipped[1] <= clipped[0] or len(set(owners)) != 2:
        return (None, {**detail, "reason": "invalid_interval_or_owners"})
    if overshoot > POLICY["maximum_endpoint_overshoot_evidence_px"]:
        return (None, {**detail, "reason": "overshoot_exceeds_tolerance"})
    if (clipped[1] - clipped[0]) / (b - a) < POLICY["minimum_retained_interval_fraction"]:
        return (None, {**detail, "reason": "insufficient_retained_width"})
    if overshoot > 0:
        for other, other_owners in segments.items():
            if len(set(other_owners)) != 2 or set(other_owners) == set(owners):
                continue
            other_axis = 0 if other[0][1] == other[1][1] else 1
            if (
                other_axis != axis
                or abs(other[0][1 - axis] - segment[0][1 - axis]) * matrix[1 - axis, 1 - axis]
                > 0.01
            ):
                continue
            L, H = sorted((float(p[axis]) * scale + matrix[axis, 2] for p in other))
            if min(b, H) > max(a, L):
                return (None, {**detail, "reason": "competing_shared_boundary_owners"})
    result = [float((v - matrix[axis, 2]) / scale) for v in clipped]
    return (
        result,
        {
            **detail,
            "attached_interval_evidence_px": clipped,
            "adjusted": overshoot > 0,
            "reason": "bounded_endpoint_alignment" if overshoot else "already_inside_support",
        },
    )


def door_conflicts(segment, start, end, evidence, matrix):
    axis = 0 if segment[0][1] == segment[1][1] else 1
    lo, hi = sorted([start[axis], end[axis]])
    matrix = np.asarray(matrix, float)
    records = []

    def visit(value):
        if isinstance(value, dict):
            support = value.get("segment")
            if (
                value.get("paired_door_evidence")
                and support is not None
                and np.allclose(np.asarray(support, float), np.asarray(segment, float), atol=1e-08)
            ):
                ticks = value.get("ticks", [])
                interval = (
                    [t["position_px"] for t in ticks]
                    if len(ticks) == 2
                    else value.get("native_interval", value.get("native_gap_px", []))
                )
                if len(interval) == 2:
                    a, b = sorted(
                        ((float(v) - matrix[axis, 2]) / matrix[axis, axis] for v in interval)
                    )
                    if min(hi, b) > max(lo, a):
                        records.append(
                            {
                                "segment": support,
                                "interval_working_px": [a, b],
                                "status": value.get("status"),
                                "reason": value.get("reason"),
                                "raw_tick_support": value.get("raw_tick_support"),
                                "model_center_response": value.get("model_center_response"),
                            }
                        )
            for key, v in value.items():
                if key not in ("path_px", "ticks", "policy", "alignment"):
                    visit(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                visit(v)

    visit(evidence)
    return records


def suppress_ambiguous_passages(proposals, evidence, matrix):
    result = []
    records = []
    for p in proposals:
        conflicts = (
            door_conflicts(p["segment"], p["start"], p["end"], evidence, matrix)
            if p["type"] == "open_passage"
            else []
        )
        if conflicts:
            records.append(
                {
                    "segment": p["segment"],
                    "status": "needs_attention",
                    "reason": "paired_door_evidence_unresolved",
                    "door_evidence": conflicts,
                    "review_required": True,
                }
            )
        else:
            result.append(p)
    return (result, records)
