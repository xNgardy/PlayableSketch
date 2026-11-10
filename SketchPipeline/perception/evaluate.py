import math
import cv2
import numpy as np
from .geometry import segment_distance, angle_delta

POLICY = {
    "text_iou_threshold": 0.3,
    "wall_distance_px_at_1600": 12.0,
    "wall_angle_tolerance_degrees": 15.0,
    "wall_sample_spacing_px": 4.0,
    "gap_endpoint_tolerance_fraction": 0.02,
}


def ratio(a, b):
    return a / b if b else None


def polygon_iou(a, b):
    a = cv2.convexHull(np.asarray(a, np.float32))
    b = cv2.convexHull(np.asarray(b, np.float32))
    intersection, _ = cv2.intersectConvexConvex(a, b)
    union = cv2.contourArea(a) + cv2.contourArea(b) - intersection
    return float(intersection / union) if union > 0 else 0.0


def greedy_pairs(predicted, truth, similarity, threshold):
    options = sorted(
        ((similarity(p, t), i, j) for i, p in enumerate(predicted) for j, t in enumerate(truth)),
        reverse=True,
    )
    used_p = set()
    used_t = set()
    pairs = []
    for score, i, j in options:
        if score < threshold:
            break
        if i not in used_p and j not in used_t:
            pairs.append((i, j, float(score)))
            used_p.add(i)
            used_t.add(j)
    return pairs


def object_counts(predicted, truth, pairs):
    return {
        "true_positive": len(pairs),
        "predicted": len(predicted),
        "reference": len(truth),
        "precision": ratio(len(pairs), len(predicted)),
        "recall": ratio(len(pairs), len(truth)),
    }


def line_angle(line):
    dx, dy = np.asarray(line["end"]) - line["start"]
    return math.degrees(math.atan2(dy, dx))


def covered_length(source, target, tolerance):
    total = covered = 0.0
    for line in source:
        a, b = (np.asarray(line["start"]), np.asarray(line["end"]))
        length = float(np.linalg.norm(b - a))
        if length == 0:
            continue
        count = max(1, math.ceil(length / POLICY["wall_sample_spacing_px"]))
        points = a + ((np.arange(count) + 0.5) / count)[:, None] * (b - a)
        hit = np.zeros(count, dtype=bool)
        for other in target:
            if (
                angle_delta(line_angle(line), line_angle(other))
                <= POLICY["wall_angle_tolerance_degrees"]
            ):
                hit |= segment_distance(points, other["start"], other["end"]) <= tolerance
        covered += float(hit.mean()) * length
        total += length
    return {
        "covered_length_px": covered,
        "total_length_px": total,
        "coverage": ratio(covered, total),
    }


def evaluate(observations, working, reference, sidecar):
    side = max(reference["frame"]["width_px"], reference["frame"]["height_px"])
    pred = observations["texts"]
    truth = reference["texts"]
    pairs = greedy_pairs(
        pred,
        truth,
        lambda p, t: polygon_iou(p["polygon_px"], t["polygon_px"]),
        POLICY["text_iou_threshold"],
    )
    text = object_counts(pred, truth, pairs)
    text["unmatched_reference_ids"] = [
        t["id"] for j, t in enumerate(truth) if j not in {b for a, b, s in pairs}
    ]
    text["unmatched_prediction_ids"] = [
        p["id"] for i, p in enumerate(pred) if i not in {a for a, b, s in pairs}
    ]
    correct = sum(
        (
            pred[i]["parsed_value_cm"] is not None
            and pred[i]["parsed_value_cm"] == truth[j]["parsed_value_cm"]
            for i, j, _ in pairs
        )
    )
    text.update(
        numeric_exact_correct=correct,
        numeric_exact_on_matched=ratio(correct, len(pairs)),
        numeric_end_to_end_recall=ratio(correct, len(truth)),
        matched_pairs=[
            {
                "prediction_id": pred[i]["id"],
                "reference_id": truth[j]["id"],
                "iou": s,
                "predicted_raw": pred[i]["raw_text"],
                "expected_raw": truth[j]["raw_text"],
                "predicted_cm": pred[i]["parsed_value_cm"],
                "expected_cm": truth[j]["parsed_value_cm"],
            }
            for i, j, s in pairs
        ],
    )
    classes = {lid: s["kind"] for s in sidecar["strokes"] for lid in s["line_ids"]}
    truth_lines = [
        {"start": segment["start_px"], "end": segment["end_px"]}
        for segment in reference["lines"]
        if classes[segment["id"]] == "wall"
    ]
    walls = {}
    for method, lines in working["line_detectors"].items():
        predicted = [
            {"start": segment["start_original"], "end": segment["end_original"]}
            for segment in lines
            if segment["role"] == "wall_candidate"
        ]
        tolerance = max(6.0, POLICY["wall_distance_px_at_1600"] * side / 1600)
        walls[method] = {
            "precision": covered_length(predicted, truth_lines, tolerance),
            "recall": covered_length(truth_lines, predicted, tolerance),
            "distance_tolerance_px": tolerance,
        }
    gt_gaps = [g for g in sidecar["gaps"] if g["kind"] != "incidental"]
    pred_gaps = [g for g in working["gaps"] if g["role"] == "opening_candidate"]
    tolerance = max(12.0, side * POLICY["gap_endpoint_tolerance_fraction"])

    def gap_similarity(p, t):
        a = np.asarray([p["start_original"], p["end_original"]])
        b = np.asarray([t["start_px"], t["end_px"]])
        error = min(np.linalg.norm(a - b, axis=1).max(), np.linalg.norm(a - b[::-1], axis=1).max())
        return 1 - float(error) / tolerance

    gp = greedy_pairs(pred_gaps, gt_gaps, gap_similarity, 0.0)
    gap = object_counts(pred_gaps, gt_gaps, gp)
    gap["unmatched_reference_ids"] = [
        g["id"] for j, g in enumerate(gt_gaps) if j not in {b for a, b, s in gp}
    ]
    gap["unmatched_prediction_ids"] = [
        g["id"] for i, g in enumerate(pred_gaps) if i not in {a for a, b, s in gp}
    ]
    gap.update(
        endpoint_tolerance_px=tolerance,
        matched_pairs=[
            {"prediction_id": pred_gaps[i]["id"], "reference_id": gt_gaps[j]["id"]}
            for i, j, _ in gp
        ],
    )
    return {
        "text": text,
        "walls": walls,
        "openings": gap,
        "policy": POLICY,
        "scope": "development only; wall metrics are sampled length coverage, not one-to-one segment matches",
    }


def aggregate(samples):
    result = {}
    for key in ("text", "openings"):
        totals = {
            name: sum((s["metrics"][key][name] for s in samples))
            for name in ("true_positive", "predicted", "reference")
        }
        totals.update(
            precision=ratio(totals["true_positive"], totals["predicted"]),
            recall=ratio(totals["true_positive"], totals["reference"]),
        )
        result[key] = totals
    correct = sum((s["metrics"]["text"]["numeric_exact_correct"] for s in samples))
    result["text"].update(
        numeric_exact_correct=correct,
        numeric_exact_on_matched=ratio(correct, result["text"]["true_positive"]),
        numeric_end_to_end_recall=ratio(correct, result["text"]["reference"]),
    )
    result["walls"] = {}
    for method in ("hough", "lsd"):
        result["walls"][method] = {}
        for key in ("precision", "recall"):
            covered = sum(
                (s["metrics"]["walls"][method][key]["covered_length_px"] for s in samples)
            )
            total = sum((s["metrics"]["walls"][method][key]["total_length_px"] for s in samples))
            result["walls"][method][key] = {
                "covered_length_px": covered,
                "total_length_px": total,
                "coverage": ratio(covered, total),
            }
    return result
