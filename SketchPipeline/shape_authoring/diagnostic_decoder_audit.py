import argparse
import copy
import json
from pathlib import Path
import time
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import project
from .decoder import CONFIG, stroke_scale
from .diagnose import decode_masks, sha, ROOT
from .pilot import score, aggregate
from .propose import prepare_image
from .synthetic import write_json


def document_in_frame(document, source_metadata, target_metadata):
    result = copy.deepcopy(document)
    matrix = np.asarray(target_metadata["original_to_working"]) @ np.asarray(
        source_metadata["working_to_original"]
    )
    width, height = target_metadata["working_size_px"]
    for values in result["topology"].values():
        for entity in values:
            points = entity["geometry"]["points_px"]
            if not points:
                continue
            mapped = project(points, matrix)
            entity["geometry"]["points_px"] = mapped.tolist()
            entity["geometry"]["points_normalized"] = (mapped / [width, height]).tolist()
    result["image_evidence"].update(
        working_size_px=[width, height],
        original_to_working=target_metadata["original_to_working"],
        working_to_original=target_metadata["working_to_original"],
        normalization_bounds_px=[0, 0, width, height],
    )
    return result


def reference_gate_probes(gray, masks, reference, metadata):
    side = max(gray.shape)
    stroke = stroke_scale(gray)
    radius = max(2, round(stroke * 0.65))
    rows = []
    for opening in reference["openings"]:
        p, q = np.asarray(opening["points_px"])
        axis = int(abs(q[1] - p[1]) >= abs(q[0] - p[0]))
        fixed = round((p[1 - axis] + q[1 - axis]) / 2)
        lo, hi = sorted([round(p[axis]), round(q[axis])])
        if not (0 <= fixed < gray.shape[axis] and 0 <= lo < hi < gray.shape[1 - axis]):
            continue
        leg_support = []
        tick_scores = []
        for endpoint in (lo, hi):
            for sign in (-1, 1):
                minimum = max(radius + 1, 3)
                maximum = max(minimum + 3, round(stroke * 3))
                cross = np.arange(fixed + sign * minimum, fixed + sign * maximum + sign, sign)
                cross = cross[(cross >= 0) & (cross < gray.shape[axis])]
                nearby = np.arange(
                    max(0, endpoint - radius - 2),
                    min(gray.shape[1 - axis] - 1, endpoint + radius + 2) + 1,
                )
                patch = gray[np.ix_(cross, nearby)] if axis == 0 else gray[np.ix_(nearby, cross)].T
                leg_support.append(float((patch.min(axis=1) < 160).mean()) if patch.size else 0.0)
                prob = (
                    masks[3][np.ix_(cross, nearby)]
                    if axis == 0
                    else masks[3][np.ix_(nearby, cross)].T
                )
                tick_scores.append(float(prob.max()) if prob.size else 0.0)
        positions = np.arange(lo + max(1, (hi - lo) // 5), hi - max(1, (hi - lo) // 5) + 1)
        dark = gray[fixed, positions] if axis == 0 else gray[positions, fixed]
        width = hi - lo
        rows.append(
            {
                "opening_id": opening["id"],
                "type": opening["type"],
                "diagnostic_only": True,
                "reference_position_used": True,
                "gap_width_px": width,
                "stroke_scale_px": stroke,
                "width_pass": side * CONFIG["opening_min_fraction"]
                <= width
                <= side * CONFIG["opening_max_fraction"],
                "gap_dark_fraction": float((dark < 145).mean()) if len(dark) else None,
                "raw_tick_four_leg_support": leg_support,
                "raw_tick_pass": min(leg_support) >= CONFIG["tick_min_raw_support"],
                "model_tick_four_leg_max_response": tick_scores,
                "model_tick_pass": min(tick_scores) >= CONFIG["tick_model_threshold"],
                "warning": "Approximate reference placement only; support/attachment and detector search may still fail.",
            }
        )
    return rows


def native_reference(n, metadata):
    from .pilot import human_reference

    return human_reference(n, metadata)


def audit(study, output):
    study = Path(study).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = json.loads((study / "report.json").read_text())
    protocol = {
        "version": "shape-native-decoder-audit/1.0",
        "study_report_sha256": sha(study / "report.json"),
        "study_protocol_sha256": sha(study / "protocol.json"),
        "source_sha256": sha(__file__),
        "decoder_sha256": sha(Path(__file__).with_name("decoder.py")),
        "scope": "Post-hoc development diagnosis; same persisted masks; no training or model selection.",
        "scoring": "All native predictions map back to the baseline frame for identical matching tolerances.",
        "oracle_policy": "Reference-position raw/model gate probes are privileged diagnostics, never normal detection metrics.",
    }
    write_json(output / "protocol.json", protocol)
    rows = []
    all_probes = []
    for previous in report["rows"]:
        sample, arm = (previous["sample_id"], previous["arm"])
        folder = study / sample / arm
        prediction = json.loads((folder / "prediction.json").read_text())
        source = prediction["authoring"]["image_evidence"]["source"]
        gray = cv2.imread(str(folder / "input.png"), cv2.IMREAD_GRAYSCALE)
        with np.load(folder / "masks.npz") as cache:
            masks = cache["native"]
        metadata = prediction["preprocessing"]
        baseline = prediction["canonical_preprocessing"]
        directory = output / sample / arm
        directory.mkdir(parents=True)
        started = time.perf_counter()
        document, detail = decode_masks(masks, gray, metadata, source)
        canonical = document_in_frame(document, metadata, baseline)
        elapsed = time.perf_counter() - started
        write_json(
            directory / "native-prediction.json",
            {
                "native_authoring": document,
                "canonical_scoring_copy": canonical,
                "canonical_copy_exportable": False,
                "labels_used_as_input": False,
                "decoder": detail,
                "decoder_elapsed_seconds": elapsed,
            },
        )
        n = int(sample.split("_")[1])
        reference = native_reference(n, baseline)
        metrics = score(canonical, reference, baseline["working_size_px"])
        probes = reference_gate_probes(gray, masks, native_reference(n, metadata), metadata)
        for probe in probes:
            probe.update(sample_id=sample, arm=arm)
        row = {
            "sample_id": sample,
            "arm": arm,
            "origin": "human",
            "elapsed_seconds": elapsed,
            "status": "needs_attention" if document["topology"]["regions"] else "manual_required",
            "metrics": metrics,
            "native_size_px": [gray.shape[1], gray.shape[0]],
            "diagnostic_reference_gate_probes": probes,
        }
        rows.append(row)
        all_probes.extend(probes)
        write_json(directory / "metrics.json", row)
    summary = {arm: aggregate([r for r in rows if r["arm"] == arm]) for arm in report["arms"]}
    probes_summary = {}
    for arm in report["arms"]:
        probes = [p for p in all_probes if p["arm"] == arm and p["type"] == "door"]
        probes_summary[arm] = {
            "reference_doors_probed": len(probes),
            "width_pass": sum((p["width_pass"] for p in probes)),
            "raw_tick_pass": sum((p["raw_tick_pass"] for p in probes)),
            "model_tick_pass": sum((p["model_tick_pass"] for p in probes)),
            "both_tick_gates_pass": sum(
                (p["raw_tick_pass"] and p["model_tick_pass"] for p in probes)
            ),
        }
    value = {
        "version": "shape-native-decoder-audit-report/1.0",
        "normal_native_decode": summary,
        "reference_position_probes_diagnostic_only": probes_summary,
        "rows": rows,
        "study_report_sha256": protocol["study_report_sha256"],
    }
    write_json(output / "report.json", value)
    print(json.dumps({"native_summary": summary, "privileged_gate_probe_summary": probes_summary}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Post-hoc native-frame decoder audit of persisted fixed-model predictions."
    )
    parser.add_argument("--study", type=Path, default=ROOT / "Saved/ShapeFirst/diagnostics/v1")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/diagnostics/native-v1"
    )
    args = parser.parse_args()
    audit(args.study, args.output)
