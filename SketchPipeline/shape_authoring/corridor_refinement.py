import copy
import numpy as np
from . import region_recovery as r
from .decoder import iou

POLICY = {
    "version": "corridor-refinement/1.1",
    "fit_search_fraction": 0.045,
    "minimum_corridor_score": 0.9,
    "minimum_retained_room_fraction": 0.65,
    "maximum_trim_fraction": 0.35,
    "review_required": True,
}


def refine(boxes, rejected, probabilities, gray, axis_masks):
    result = copy.deepcopy(boxes)
    records = []
    for candidate in rejected:
        if (
            candidate.get("code") != "UNSUPPORTED_RECOVERY"
            or candidate.get("type") != "corridor_segment"
        ):
            continue
        if candidate["area_px"] < max(
            r.POLICY["minimum_supported_area_px"],
            max(gray.shape) ** 2 * r.POLICY["minimum_supported_area_fraction"],
        ):
            continue
        if (
            candidate["fill"] < r.POLICY["minimum_supported_fill"]
            or candidate["model_mean"] < POLICY["minimum_corridor_score"]
        ):
            continue
        old = candidate["bounds_px"]
        new = r.fit_box(old, gray, probabilities, max(gray.shape) * POLICY["fit_search_fraction"])
        edges = r.box_support(new, probabilities, axis_masks)
        opposite = (
            (edges[1], edges[3]) if new[2] - new[0] >= new[3] - new[1] else (edges[0], edges[2])
        )
        if min(opposite) < r.POLICY["support_opposite_wall_threshold"]:
            continue
        if min(new[2] - new[0], new[3] - new[1]) < 8:
            continue
        if any((iou(new, b["bounds_px"]) > 0.05 for b in result)):
            continue
        result.append(
            {"type": "corridor_segment", "bounds_px": new, "model_score": candidate["model_mean"]}
        )
        records.append(
            {"action": "parallel_wall_refit", "before": old, "after": new, "edge_support": edges}
        )
    for corridor in result:
        if (
            corridor["type"] != "corridor_segment"
            or corridor["model_score"] < POLICY["minimum_corridor_score"]
        ):
            continue
        C = corridor["bounds_px"]
        long = 0 if C[2] - C[0] >= C[3] - C[1] else 1
        normal = 1 - long
        edges = r.box_support(C, probabilities, axis_masks)
        opposing = (edges[1], edges[3]) if long == 0 else (edges[0], edges[2])
        if min(opposing) < r.POLICY["support_opposite_wall_threshold"]:
            continue
        for room in result:
            if room["type"] != "room" or iou(C, room["bounds_px"]) <= 0:
                continue
            B = room["bounds_px"]
            lo = max(C[long], B[long])
            hi = min(C[long + 2], B[long + 2])
            if hi - lo < min(B[long + 2] - B[long], C[long + 2] - C[long]) * 0.8:
                continue
            edge = normal if B[normal] + B[normal + 2] > C[normal] + C[normal + 2] else normal + 2
            target = C[normal + 2] if edge == normal else C[normal]
            distance = abs(B[edge] - target)
            extent = B[normal + 2] - B[normal]
            if distance > extent * POLICY["maximum_trim_fraction"]:
                continue
            new = list(B)
            new[edge] = target
            if min(new[2] - new[0], new[3] - new[1]) < 8:
                continue
            retained = (new[2] - new[0]) * (new[3] - new[1]) / ((B[2] - B[0]) * (B[3] - B[1]))
            if not POLICY["minimum_retained_room_fraction"] <= retained <= 1:
                continue
            records.append(
                {"action": "room_spill_trim", "before": list(B), "after": new, "corridor": list(C)}
            )
            room["bounds_px"] = new
    return (result, records)
