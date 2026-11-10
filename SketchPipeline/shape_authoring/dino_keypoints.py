import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from SketchPipeline.evaluation.metrics import counts, pairs
from .human_error_review import reference
from .synthetic import write_json

POLICY = {
    "version": "dino-endpoint-evaluation/1.0",
    "threshold": 0.5,
    "matching_tolerance_side_fraction": 0.04,
    "peak_policy": "One maximum per connected threshold component; no reference-guided search.",
    "scope": "Diagnostic only; approximate existing human annotations, not a fresh test.",
}


def endpoint_peaks(probability, threshold=0.5):
    if probability.ndim != 2 or not np.isfinite(probability).all():
        raise ValueError("Finite endpoint map required")
    count, labels, stats, centers = cv2.connectedComponentsWithStats(
        (probability >= threshold).astype(np.uint8), 8
    )
    points = []
    for label in range(1, count):
        y, x = np.where(labels == label)
        index = np.argmax(probability[y, x])
        points.append([int(x[index]), int(y[index])])
    return points


def evaluate(output):
    output = Path(output).resolve()
    report = output / "keypoint-report.json"
    if report.exists():
        raise ValueError("Endpoint report already exists")
    protocol = json.loads((output / "protocol.json").read_text())
    rows = []
    write_json(output / "keypoint-policy.json", POLICY)
    for n in protocol["evaluation_ids"]:
        folder = output / "evaluation/human" / f"Data_{n}" / "dino"
        result = json.loads((folder / "proposals.json").read_text())
        with np.load(folder / "native-auxiliary-masks.npz") as cache:
            probability = cache["probabilities"][6]
        native = endpoint_peaks(probability, POLICY["threshold"])
        transform = np.asarray(result["preprocessing"]["original_to_working"]) @ np.asarray(
            result["evidence_preprocessing"]["working_to_original"]
        )
        prediction = []
        for point in native:
            projected = transform @ np.r_[point, 1.0]
            prediction.append((projected[:2] / projected[2]).tolist())
        ref = reference(n, result["preprocessing"])
        truth = [
            point
            for opening in ref["openings"]
            if opening["type"] == "door"
            for point in opening["points_px"]
        ]
        tolerance = (
            max(result["preprocessing"]["working_size_px"])
            * POLICY["matching_tolerance_side_fraction"]
        )
        matches = pairs(
            prediction, truth, lambda a, b: float(np.linalg.norm(np.asarray(a) - b)), tolerance
        )
        geometry = json.loads((folder / "metrics.json").read_text())["metrics"]["region_id_mapping"]
        types = {r["id"]: r["type"] for r in ref["regions"]}
        predicted_types = {r["id"]: r["type"] for r in result["authoring"]["topology"]["regions"]}
        type_correct = sum(
            (
                predicted_types[identifier] == types[expected]
                for identifier, expected in geometry.items()
            )
        )
        row = {
            "sample_id": f"Data_{n}",
            "role": protocol["groups"][f"Data_{n}"]["split"],
            "counts": counts(len(matches), len(prediction), len(truth)),
            "region_type_correct": type_correct,
            "region_type_matched": len(geometry),
            "prediction_points_px": prediction,
            "reference_points_px": truth,
            "tolerance_px": tolerance,
        }
        rows.append(row)
        write_json(folder / "keypoint-metrics.json", row)
    summary = {}
    for role in ["train", "validation", "test"]:
        selected = [r["counts"] for r in rows if r["role"] == role]
        summary[role] = counts(
            sum((r["true_positive"] for r in selected)),
            sum((r["predicted"] for r in selected)),
            sum((r["reference"] for r in selected)),
        )
    region_types = {}
    for role in ["train", "validation", "test"]:
        correct = sum((r["region_type_correct"] for r in rows if r["role"] == role))
        matched = sum((r["region_type_matched"] for r in rows if r["role"] == role))
        region_types[role] = {
            "correct": correct,
            "geometry_matched": matched,
            "accuracy": correct / matched if matched else None,
        }
    value = {
        "policy": POLICY,
        "summary": summary,
        "region_types": region_types,
        "rows": rows,
        "model_selection_used_these_results": False,
    }
    write_json(report, value)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.output)
