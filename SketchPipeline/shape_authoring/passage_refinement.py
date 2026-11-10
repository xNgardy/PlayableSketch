import copy
import cv2
import numpy as np
from . import decoder_refined as d
from . import local_wall_tracking as tracking
from SketchPipeline.perception.structural import suppress_grid

POLICY = {
    "version": "passage-refinement/1.0",
    "maximum_normal_search_strokes": 2,
    "coherent_wall_barrier_fraction": 0.8,
    "model_interface_min": 0.45,
    "minimum_clear_fraction": 0.8,
    "review_required": True,
}


def opening_candidates(
    segments,
    gray,
    probabilities,
    matrix,
    mode="paired_raw",
    region_types=None,
    *,
    align_doors=False,
):
    proposals, evidence = tracking.opening_candidates(
        segments, gray, probabilities, matrix, mode, align_doors=align_doors
    )
    records = []
    clean, _, _ = suppress_grid(gray)
    ink, stroke, _ = d.ink_evidence(clean)
    matrix = np.asarray(matrix, float)
    for segment, owners in segments.items():
        if len(owners) != 2:
            continue
        if region_types is None or not any((region_types[i] == "corridor_segment" for i in owners)):
            continue
        p = np.c_[np.asarray(segment), np.ones(2)] @ matrix.T
        p = p[:, :2] / p[:, 2:]
        axis = 0 if segment[0][1] == segment[1][1] else 1
        fixed = float(p[:, 1 - axis].mean())
        lo, hi = sorted(p[:, axis])
        scale = matrix[axis, axis]
        if hi - lo < max(stroke * 2, max(gray.shape) * d.POLICY["minimum_gap_side_fraction"]):
            continue
        positions = np.arange(
            max(0, int(np.ceil(lo)) + 2), min(gray.shape[1 - axis], int(np.floor(hi)) - 1)
        )
        if not len(positions):
            continue
        radius = max(2, round(stroke * POLICY["maximum_normal_search_strokes"]))
        length = max(3, round(max(stroke * 4, scale * d.POLICY["axis_support_length_units"]))) | 1
        structural = cv2.morphologyEx(
            ink, cv2.MORPH_OPEN, np.ones((1, length) if axis == 0 else (length, 1), np.uint8)
        )
        barriers = [
            float(d.ribbon(structural, axis, fixed + offset, positions, 0).mean())
            for offset in range(-radius, radius + 1)
        ]
        coherent = max(barriers)
        options = []
        for offset in range(-radius, radius + 1):
            line = fixed + offset
            learned = d.ribbon(probabilities[5], axis, line, positions, max(1, round(stroke)))
            raw = d.ribbon(ink, axis, line, positions, 0)
            semantic = float(learned.max(axis=0).mean()) if learned.size else 0
            clear = float(1 - raw.mean()) if raw.size else 0
            options.append(
                (
                    semantic >= POLICY["model_interface_min"]
                    and clear >= POLICY["minimum_clear_fraction"],
                    semantic,
                    clear,
                    -abs(offset),
                    line,
                )
            )
        accepted, semantic, clear, _, line = max(options)
        record = {
            "segment": segment,
            "native_axis": line,
            "model_interface_response": semantic,
            "raw_clear_fraction": clear,
            "coherent_crossing_wall": coherent,
        }
        if not accepted or coherent >= POLICY["coherent_wall_barrier_fraction"]:
            records.append(dict(record, status="rejected", reason="interface_or_physical_barrier"))
            continue
        a, b = (list(segment[0]), list(segment[1]))
        if align_doors:
            from .opening_alignment import door_conflicts

            conflicts = door_conflicts(segment, a, b, evidence, matrix)
            if conflicts:
                records.append(
                    dict(
                        record,
                        status="needs_attention",
                        reason="paired_door_evidence_unresolved",
                        door_evidence=conflicts,
                    )
                )
                continue
        if any(
            (
                q["segment"] == segment
                and min(q["end"][axis], b[axis]) > max(q["start"][axis], a[axis])
                for q in proposals
            )
        ):
            records.append(dict(record, status="suppressed", reason="existing_opening"))
            continue
        record.update(status="proposed", type="open_passage")
        proposals.append(
            {
                "segment": segment,
                "entity_indices": owners,
                "start": a,
                "end": b,
                "type": "open_passage",
                "evidence": record,
            }
        )
        records.append(record)
    return (proposals, {"tracked": evidence, "passage_candidates": records, "policy": POLICY})
