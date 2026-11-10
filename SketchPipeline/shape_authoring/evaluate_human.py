import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from SketchPipeline.evaluation.metrics import pairs, endpoint_error
from .human_supervision import ROOT, freeze, source_image, sha
from .human_error_review import reference
from .propose import run
from .pilot import score, aggregate, synthetic_reference
from .diagnose import panel
from .decoder_refined import decode
from .synthetic import write_json


def saved_probabilities(directory, gray):
    cache_path = directory / "model-masks.npz"
    if not cache_path.exists():
        return np.zeros((6, *gray.shape), dtype=np.float32)
    with np.load(cache_path) as cache:
        return cache["probabilities"]


def evaluate(output):
    output = Path(output).resolve()
    protocol = freeze(output)
    training = json.loads((output / "training_report.json").read_text())
    selected = training["selected"]
    if training["selection_used_test"]:
        raise ValueError("Selection leaked test outcomes")
    checkpoint = ROOT / selected["path"]
    if sha(checkpoint) != selected["sha256"]:
        raise ValueError("Selected checkpoint changed")
    root = output / "evaluation"
    root.mkdir(exist_ok=False)
    frozen = {
        "version": "human-adaptation-evaluation/1.0",
        "selected": selected,
        "training_report_sha256": sha(output / "training_report.json"),
        "protocol_sha256": sha(output / "protocol.json"),
        "reserved_evaluation_ids": protocol["reserved_development_evaluation_ids"],
        "diagnostic_seen_ids": protocol["previously_inspected_diagnostic_ids"],
        "source_hashes": {
            str(p.relative_to(ROOT)): sha(p)
            for p in [
                Path(__file__),
                Path(__file__).with_name("human_supervision.py"),
                Path(__file__).with_name("human_error_review.py"),
                Path(__file__).with_name("propose.py"),
                Path(__file__).with_name("contrast.py"),
                Path(__file__).with_name("pilot.py"),
                Path(__file__).with_name("decoder_refined.py"),
            ]
        },
        "evaluation_policy": "No further checkpoint or threshold selection from these outcomes. Reserved plans are same-collection development, not new writers.",
        "reference_policy_version": "structural-openings/2.0",
    }
    write_json(root / "freeze.json", frozen)
    baseline = ROOT / protocol["base_model_lock"]["checkpoint_path"]
    arms = [
        ("old_raw", baseline, False),
        ("old_photo_stretch", baseline, True),
        ("adapted", checkpoint, protocol["training"].get("normalize_ink", False)),
    ]
    ids = sorted(
        set(protocol["previously_inspected_diagnostic_ids"])
        | set(protocol["reserved_development_evaluation_ids"])
    )
    rows = []
    figures = []
    for n in ids:
        print(f"evaluate Data_{n}", flush=True)
        for arm, model, normalize in arms:
            directory = root / "human" / f"Data_{n}" / arm
            result = run(
                source_image(n),
                directory,
                checkpoint=model,
                expected_sha256=sha(model),
                profile="refined-full",
                normalize_ink=normalize,
            )
            ref = reference(n, result["preprocessing"])
            metrics = score(result["authoring"], ref, result["preprocessing"]["working_size_px"])
            predictions = result["authoring"]["topology"]["openings"]
            matched = pairs(
                predictions,
                ref["openings"],
                lambda a, b: (
                    endpoint_error(a["geometry"]["points_px"], b["points_px"])
                    if a["type"] == b["type"]
                    else float("inf")
                ),
                max(result["preprocessing"]["working_size_px"]) * 0.04,
            )
            row = {
                "sample_id": f"Data_{n}",
                "origin": "human",
                "arm": arm,
                "parent_group": protocol["groups"][f"Data_{n}"]["base_plan_id"],
                "original_split": protocol["groups"][f"Data_{n}"]["split"],
                "cohort": (
                    "reserved_development"
                    if n in protocol["reserved_development_evaluation_ids"]
                    else "previously_inspected_mixed_diagnostic"
                ),
                "status": result["status"],
                "failure": result["failure"],
                "elapsed_seconds": result["elapsed_seconds"],
                "metrics": metrics,
                "reference_opening_ids_detected": [ref["openings"][j]["id"] for i, j, c in matched],
                "reference_openings": ref["openings"],
                "excluded_incidental_gaps": ref["excluded_non_opening_gaps"],
            }
            rows.append(row)
            write_json(directory / "metrics.json", row)
            gray = cv2.imread(str(directory / "working.png"), 0)
            probabilities = saved_probabilities(directory, gray)
            panel(gray, probabilities, result["authoring"], ref, directory / "comparison.png")
            figures.append(
                f"""<figure><figcaption>Data {n} · {row['cohort']} · {arm} · openings {metrics['openings']['true_positive']}/{metrics['openings']['predicted']} proposed, {metrics['openings']['reference']} reference</figcaption><img loading="lazy" src="human/Data_{n}/{arm}/comparison.png"></figure>"""
            )
    synthetic_rows = []
    for seed in range(2000, 2012):
        for style in ["clean", "wavy", "grid", "stray", "broken"]:
            sample = f"{seed}_{style}"
            folder = ROOT / "Saved/ShapeFirst/v1/development" / sample
            for arm, model, normalize in [arms[0], arms[2]]:
                directory = root / "synthetic" / sample / arm
                result = run(
                    folder / "source.png",
                    directory,
                    checkpoint=model,
                    expected_sha256=sha(model),
                    profile="baseline",
                )
                gray = cv2.imread(str(directory / "working.png"), 0)
                probabilities = saved_probabilities(directory, gray)
                refined, detail = decode(
                    gray,
                    probabilities,
                    result["authoring"]["image_evidence"]["source"],
                    result["preprocessing"],
                    working_gray=gray,
                    working_metadata=result["preprocessing"],
                    evidence_to_working=np.eye(3),
                )
                write_json(
                    directory / "refined-prediction.json",
                    {"authoring": refined, "decoder": detail, "labels_used_as_input": False},
                )
                ref = synthetic_reference(folder / "reference.json")
                row = {
                    "sample_id": sample,
                    "origin": "synthetic",
                    "arm": arm,
                    "status": result["status"],
                    "elapsed_seconds": result["elapsed_seconds"],
                    "metrics": score(refined, ref, result["preprocessing"]["working_size_px"]),
                }
                synthetic_rows.append(row)
                write_json(directory / "refined-metrics.json", row)
    summary = {
        arm: {
            cohort: aggregate([r for r in rows if r["arm"] == arm and r["cohort"] == cohort])
            for cohort in ["reserved_development", "previously_inspected_mixed_diagnostic"]
        }
        for arm, _, _ in arms
    }
    syn_summary = {
        arm: aggregate([r for r in synthetic_rows if r["arm"] == arm])
        for arm in ["old_raw", "adapted"]
    }
    old_review = json.loads(
        (
            ROOT / "Saved/ShapeFirst/human_adaptation/v1/error_review_corrected/review.json"
        ).read_text()
    )
    detected = {
        (r["sample_id"], g)
        for r in rows
        if r["arm"] == "adapted"
        for g in r["reference_opening_ids_detected"]
    }
    resolved = [
        {
            "image_id": r["image_id"],
            "opening_id": r["opening_id"],
            "prior_reason": r["reason"],
            "now_detected": (r["image_id"], r["opening_id"]) in detected,
        }
        for r in old_review["rows"]
        if not r["detected"]
    ]
    changed = [
        path
        for path, expected in protocol["protected_data"].items()
        if sha(ROOT / path) != expected
    ]
    if changed:
        raise ValueError("Protected source/annotation changed")
    h = summary["adapted"]["reserved_development"]
    s = syn_summary["adapted"]
    before = syn_summary["old_raw"]
    gates = {
        "reserved_opening_precision": (h["openings"]["precision"] or 0)
        >= protocol["targets"]["reserved_opening_precision"],
        "reserved_opening_recall": (h["openings"]["recall"] or 0)
        >= protocol["targets"]["reserved_opening_recall"],
        "synthetic_precision_preserved": (s["openings"]["precision"] or 0)
        >= (before["openings"]["precision"] or 0),
        "synthetic_recall_preserved": (s["openings"]["recall"] or 0)
        >= (before["openings"]["recall"] or 0),
        "validation_synthetic_guard_passed": training["synthetic_guard_passed"],
    }
    report = {
        "version": "human-shape-adaptation-report/1.0",
        "selected": selected,
        "reference_policy_version": "structural-openings/2.0",
        "human_summary": summary,
        "synthetic_summary": syn_summary,
        "rows": rows,
        "synthetic_rows": synthetic_rows,
        "old_missed_opening_outcomes": resolved,
        "old_missed_openings_recovered": sum((r["now_detected"] for r in resolved)),
        "gates": gates,
        "all_gates_passed": all(gates.values()),
        "writer_holdout": False,
        "writer_overlap": protocol["leakage_audit"]["writer_train_test_overlap"],
        "scope": protocol["scope"],
        "protected_data_files_checked": len(protocol["protected_data"]),
        "protected_data_files_changed": changed,
        "human_correction_time_seconds": None,
        "model_promoted_to_default": False,
    }
    write_json(output / "report.json", report)
    (root / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Human adaptation comparison</title><style>body{font:14px system-ui;background:#f8f8f8;margin:24px}figure{padding:12px;border:1px solid #ddd;background:white;margin:12px 0}img{max-width:100%}</style><h1>Human geometry adaptation</h1><p>Reserved plan groups are from the existing development collection. Known writer overlap; no unseen-writer claim. Green: approximate reference regions; orange: predictions; red: proposed openings. Incidental breaks are not opening references.</p>'
        + "".join(figures)
    )
    print(
        json.dumps(
            {
                "human_summary": summary,
                "synthetic_summary": syn_summary,
                "gates": gates,
                "old_missed_recovered": report["old_missed_openings_recovered"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/human_adaptation/v4"
    )
    args = parser.parse_args()
    evaluate(args.output)
