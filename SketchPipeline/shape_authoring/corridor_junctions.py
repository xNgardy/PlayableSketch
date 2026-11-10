import copy
import numpy as np
from .corridor_candidates import wall_ink

POLICY = {
    "version": "observed-corridor-interfaces/1.0",
    "minimum_clear_fraction": 0.92,
    "minimum_clear_run_fraction": 0.85,
    "review_required": True,
}


def add_observed_passages(
    proposals, segments, gray, working_to_evidence, recovered_indices, *, door_evidence=None
):
    result = copy.deepcopy(proposals)
    ink = wall_ink(gray)
    matrix = np.asarray(working_to_evidence, float)
    records = []
    recovered = set(recovered_indices)
    for segment, owners in segments.items():
        if len(owners) != 2 or not recovered.intersection(owners):
            continue
        if any((p["segment"] == segment for p in result)):
            continue
        if door_evidence is not None:
            from .opening_alignment import door_conflicts

            conflicts = door_conflicts(segment, segment[0], segment[1], door_evidence, matrix)
            if conflicts:
                records.append(
                    {
                        "segment": segment,
                        "entity_indices": owners,
                        "status": "needs_attention",
                        "reason": "paired_door_evidence_unresolved",
                        "door_evidence": conflicts,
                        "review_required": True,
                    }
                )
                continue
        points = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        points = points[:, :2] / points[:, 2:]
        axis = int(abs(points[1, 1] - points[0, 1]) > abs(points[1, 0] - points[0, 0]))
        normal = 1 - axis
        lo, hi = sorted(points[:, axis])
        if hi - lo < max(8, max(gray.shape) * 0.012):
            continue
        fixed = float(points[:, normal].mean())
        margin = max(2, int((hi - lo) * 0.12))
        along = np.arange(
            max(0, int(np.ceil(lo)) + margin),
            min(gray.shape[1 - axis], int(np.floor(hi)) - margin + 1),
        )
        across = np.arange(max(0, round(fixed) - 2), min(gray.shape[axis], round(fixed) + 3))
        if len(along) < 5 or len(across) < 3:
            continue
        patch = ink[np.ix_(across, along)] if axis == 0 else ink[np.ix_(along, across)].T
        clear = patch.max(axis=0) == 0
        edges = np.diff(np.r_[False, clear, False].astype(np.int8))
        runs = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
        fraction = float(clear.mean())
        longest = float(runs.max() / len(clear)) if len(runs) else 0.0
        accepted = (
            fraction >= POLICY["minimum_clear_fraction"]
            and longest >= POLICY["minimum_clear_run_fraction"]
        )
        record = {
            "segment": segment,
            "entity_indices": owners,
            "source": "observed_ink",
            "clear_fraction": fraction,
            "clear_run_fraction": longest,
            "status": "proposed" if accepted else "rejected",
            "review_required": True,
        }
        records.append(record)
        if accepted:
            result.append(
                {
                    "segment": segment,
                    "entity_indices": owners,
                    "start": list(segment[0]),
                    "end": list(segment[1]),
                    "type": "open_passage",
                    "evidence": record,
                }
            )
    return (result, {"policy": POLICY, "interfaces": records})


def project_boxes(boxes, matrix):
    result = []
    for box in boxes:
        p = np.c_[np.asarray(box["bounds_px"]).reshape(2, 2), np.ones(2)] @ np.asarray(matrix).T
        p = p[:, :2] / p[:, 2:]
        result.append(
            {k: copy.deepcopy(v) for k, v in box.items() if k != "evidence"}
            | {"bounds_px": np.round(p.ravel(), 6).tolist()}
        )
    return result


def append_manifold_regions(boxes, candidates):
    from .decoder import boundary_graph

    result = list(boxes)
    rejected = []
    for candidate in candidates:
        if any((len(owners) > 2 for owners in boundary_graph(result + [candidate])[0].values())):
            rejected.append(
                {"bounds_px": candidate["bounds_px"], "reason": "more_than_two_boundary_owners"}
            )
        else:
            result.append(candidate)
    return (result, rejected)
