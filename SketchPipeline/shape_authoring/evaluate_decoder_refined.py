import argparse
import hashlib
import html
import json
from pathlib import Path
import time
import cv2
import numpy as np
from .contract import validate_authoring
from .decoder_refined import decode, POLICY
from .diagnose import decode_masks, panel, ROOT
from .pilot import score, aggregate, human_reference, synthetic_reference
from .synthetic import write_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(output):
    output = Path(output).resolve()
    protocol = json.loads((output / "protocol.json").read_text())
    freeze = output / "candidate-freeze.json"
    if freeze.exists():
        raise ValueError(
            "Candidate comparison already exists; preserve it and choose a new version"
        )
    sources = [
        "decoder_refined.py",
        "decoder_refined.config.json",
        "evaluate_decoder_refined.py",
        "propose.py",
        "jobs.py",
        "server.py",
    ]
    inputs = {}
    for n in protocol["human_ids"]:
        for profile in protocol["input_profiles"]:
            folder = ROOT / "Saved/ShapeFirst/diagnostics/v2" / f"Data_{n}" / profile
            for name in ("prediction.json", "masks.npz", "input.png"):
                path = folder / name
                inputs[str(path.relative_to(ROOT))] = sha(path)
    for sample in protocol["synthetic_samples"]:
        folder = ROOT / "Saved/ShapeFirst/v1/comparison" / sample / "candidate_12"
        for name in ("proposals.json", "model-masks.npz", "working.png"):
            path = folder / name
            inputs[str(path.relative_to(ROOT))] = sha(path)
    value = {
        "sources": {name: sha(Path(__file__).with_name(name)) for name in sources},
        "persisted_inputs": inputs,
        "diagnostic_masks": "Saved/ShapeFirst/diagnostics/v2",
        "policy": POLICY,
        "development_note": "Previously inspected human development drawings; no new-writer or holdout claim.",
    }
    write_json(freeze, value)
    rows = []
    gallery = []
    modes = [("refined_model_center", "model_center"), ("refined_paired_raw", "paired_raw")]
    for n in protocol["human_ids"]:
        for profile in protocol["input_profiles"]:
            directory = ROOT / "Saved/ShapeFirst/diagnostics/v2" / f"Data_{n}" / profile
            cached = json.loads((directory / "prediction.json").read_text())
            if (
                cached["model"]["checkpoint_sha256"]
                != json.loads((output.parent / "v1/baseline/models.lock.json").read_text())[
                    "checkpoint_sha256"
                ]
            ):
                raise ValueError("Cached model identity changed")
            native = cv2.imread(str(directory / "input.png"), cv2.IMREAD_GRAYSCALE)
            working = cv2.imread(
                str(directory.parent / "baseline_256/input.png"), cv2.IMREAD_GRAYSCALE
            )
            base_meta = cached["canonical_preprocessing"]
            native_meta = cached["preprocessing"]
            transform = np.asarray(base_meta["original_to_working"]) @ np.asarray(
                native_meta["working_to_original"]
            )
            source = cached["authoring"]["image_evidence"]["source"]
            with np.load(directory / "masks.npz") as data:
                raw = data["native"]
                canonical = data["canonical"]
            predictions = []
            for arm, mode in [("baseline_canonical", None)] + modes:
                started = time.perf_counter()
                if mode is None:
                    document, detail = decode_masks(canonical, working, base_meta, source)
                else:
                    document, detail = decode(
                        native,
                        raw,
                        source,
                        native_meta,
                        working_gray=working,
                        working_metadata=base_meta,
                        evidence_to_working=transform,
                        mode=mode,
                    )
                errors = validate_authoring(document)
                if errors:
                    raise ValueError(str(errors))
                folder = output / "human" / f"Data_{n}" / profile / arm
                folder.mkdir(parents=True)
                prediction = {
                    "authoring": document,
                    "decoder": detail,
                    "decoder_elapsed_seconds": time.perf_counter() - started,
                    "labels_used_as_input": False,
                    "model_inference_performed": False,
                }
                write_json(folder / "prediction.json", prediction)
                predictions.append((arm, document, prediction, folder))
            reference = human_reference(n, base_meta)
            for arm, document, prediction, folder in predictions:
                metrics = score(document, reference, base_meta["working_size_px"])
                row = {
                    "sample_id": f"Data_{n}",
                    "origin": "human",
                    "input_profile": profile,
                    "arm": arm,
                    "status": (
                        "needs_attention" if document["topology"]["regions"] else "manual_required"
                    ),
                    "elapsed_seconds": prediction["decoder_elapsed_seconds"],
                    "metrics": metrics,
                }
                rows.append(row)
                write_json(folder / "metrics.json", row)
                panel(working, canonical, document, reference, folder / "comparison.png")
                gallery.append(
                    f"""<figure><figcaption>Data {n} · {profile} · {arm} · openings {metrics['openings']['true_positive']}/{metrics['openings']['predicted']} proposed; {metrics['openings']['reference']} reference</figcaption><img loading="lazy" src="{folder.relative_to(output).as_posix()}/comparison.png"></figure>"""
                )
            print(f"Data_{n} {profile}", flush=True)
    for sample in protocol["synthetic_samples"]:
        folder = ROOT / "Saved/ShapeFirst/v1/comparison" / sample / "candidate_12"
        cached = json.loads((folder / "proposals.json").read_text())
        metadata = cached["preprocessing"]
        gray = cv2.imread(str(folder / "working.png"), cv2.IMREAD_GRAYSCALE)
        with np.load(folder / "model-masks.npz") as data:
            masks = data["probabilities"]
        source = cached["authoring"]["image_evidence"]["source"]
        predictions = []
        for arm, mode in [("baseline_canonical", None)] + modes:
            started = time.perf_counter()
            if mode is None:
                document, detail = decode_masks(masks, gray, metadata, source)
            else:
                document, detail = decode(
                    gray,
                    masks,
                    source,
                    metadata,
                    working_gray=gray,
                    working_metadata=metadata,
                    evidence_to_working=np.eye(3),
                    mode=mode,
                )
            destination = output / "synthetic" / sample / arm
            destination.mkdir(parents=True)
            elapsed = time.perf_counter() - started
            write_json(
                destination / "prediction.json",
                {"authoring": document, "decoder": detail, "labels_used_as_input": False},
            )
            predictions.append((arm, document, elapsed, destination))
        reference = synthetic_reference(
            ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
        )
        for arm, document, elapsed, destination in predictions:
            row = {
                "sample_id": sample,
                "origin": "synthetic",
                "arm": arm,
                "input_profile": "baseline_256",
                "status": (
                    "needs_attention" if document["topology"]["regions"] else "manual_required"
                ),
                "elapsed_seconds": elapsed,
                "metrics": score(document, reference, metadata["working_size_px"]),
            }
            rows.append(row)
            write_json(destination / "metrics.json", row)
    arms = protocol["decoder_arms"]
    summary = {
        arm: {
            "synthetic": aggregate(
                [r for r in rows if r["arm"] == arm and r["origin"] == "synthetic"]
            ),
            "human": {
                profile: aggregate(
                    [
                        r
                        for r in rows
                        if r["arm"] == arm
                        and r["origin"] == "human"
                        and (r["input_profile"] == profile)
                    ]
                )
                for profile in protocol["input_profiles"]
            },
        }
        for arm in arms
    }
    gate_results = {}
    for arm in arms[1:]:
        s = summary[arm]["synthetic"]
        h = summary[arm]["human"]["crop_square_512"]
        t = protocol["targets"]
        gate_results[arm] = {
            "human_region_precision": (h["regions"]["precision"] or 0)
            >= t["human_region_precision_min"],
            "human_region_recall": (h["regions"]["recall"] or 0) >= t["human_region_recall_min"],
            "human_opening_precision": (h["openings"]["precision"] or 0)
            >= t["human_opening_precision_min"],
            "human_opening_recall": (h["openings"]["recall"] or 0) >= t["human_opening_recall_min"],
            "synthetic_opening_precision": (s["openings"]["precision"] or 0)
            >= t["synthetic_opening_precision_min"],
            "synthetic_opening_recall": (s["openings"]["recall"] or 0)
            >= t["synthetic_opening_recall_min"],
            "synthetic_exact_topology": (s["exact_topology_fraction"] or 0)
            >= t["synthetic_exact_topology_min"],
        }
    changed = [p for p, expected in protocol["protected_data"].items() if sha(ROOT / p) != expected]
    cache_changes = [p for p, expected in inputs.items() if sha(ROOT / p) != expected]
    if changed or cache_changes:
        raise ValueError("Input artifacts changed during comparison")
    result = {
        "version": "shape-refined-decoder-report/1.0",
        "summary": summary,
        "targets": protocol["targets"],
        "target_checks": gate_results,
        "protected_data_files": len(protocol["protected_data"]),
        "protected_files_changed": changed,
        "rows": rows,
        "human_correction_time_seconds": None,
        "unseen_writer_generalization": "unknown",
        "cached_input_files_checked": len(inputs),
        "cached_input_files_changed": cache_changes,
        "scope": "Development-only deterministic decoder comparison; same existing model masks; no training.",
    }
    write_json(output / "report.json", result)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Refined decoder comparison</title><style>body{font:14px system-ui;background:#f6f7f8;margin:24px}figure{background:white;border:1px solid #ddd;padding:12px;margin:12px 0}img{max-width:100%}figcaption{margin-bottom:10px}</style><h1>Fixed-model decoder comparison</h1><p>Same saved model masks; no retraining. Green: approximate reference regions; orange: proposed regions; red: proposed openings. All results require review. No human exact-topology or unseen-writer claim.</p>'
        + "".join(gallery)
    )
    print(json.dumps({"summary": summary, "gates": gate_results, "protected_changes": changed}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare versioned deterministic decoders with the same persisted model masks."
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/decoder_refinement/v1"
    )
    args = parser.parse_args()
    evaluate(args.output)
