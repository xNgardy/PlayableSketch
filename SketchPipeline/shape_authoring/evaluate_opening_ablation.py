import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import cv2
import numpy as np
from . import opening_ablation as experiment
from . import decoder_refined as decoder
from .decoder import boundary_graph, authoring_document
from .contract import validate_authoring
from .dino_region_audit import ROOT, sha
from .evaluate_region_recovery import signature, summary
from .human_error_review import reference
from .pilot import score, synthetic_reference, draw_preview
from .synthetic import write_json

ARMS = {
    "control": (False, False),
    "A_endpoints": (True, False),
    "B_tracking": (False, True),
    "AB_combined": (True, True),
}


def evaluate(output, subset):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    study = ROOT / "Saved/ShapeFirst/dinov2/v1"
    baseline = ROOT / "Saved/ShapeFirst/dinov2/decoder_recovery/v2/final"
    protocol = json.loads((study / "protocol.json").read_text())
    protected = {
        p: sha(ROOT / p)
        for p in json.loads((baseline / "freeze.json").read_text())["source_hashes"]
    }
    for p in [
        "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt",
        "SketchPipeline/shape_authoring/models.lock.json",
        "SketchPipeline/shape_authoring/dinov2-candidate.lock.json",
    ]:
        protected[p] = sha(ROOT / p)
    sources = [Path(__file__), Path(experiment.__file__)]
    frozen = {
        "version": "opening-ablation-evaluation/1.0",
        "new_policy": experiment.POLICY,
        "acceptance_policy": copy.deepcopy(decoder.POLICY),
        "arms": ARMS,
        "subset": subset,
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "protected_hashes": protected,
        "selection_policy": "No default promotion. No tuning on full results. Pilot guard: retain previously correct openings and do not increase synthetic false connections. All arms are reported even if guard fails.",
        "scope": "Retrospective development, approximate human labels; no new blind evaluation.",
        "open_passages": "Existing proposals preserved; experimental additions are doors only.",
        "input_hashes": {},
        "labels_used_for_inference": False,
        "model_retrained": False,
        "model_inference_run": False,
    }
    write_json(output / "freeze.json", frozen)
    for p in sources:
        dest = output / "source_snapshot" / p.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(p, dest)
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    cases = []
    baseline_equal = 0
    for folder in folders:
        sample = folder.parent.name
        human = folder.parent.parent.name == "human"
        role = protocol["groups"][sample]["split"] if human else "synthetic_control"
        if subset == "validation" and (
            not (
                role == "validation"
                or (not human and sample in protocol["validation_synthetic_ids"])
            )
        ):
            continue
        for name in [
            "working.png",
            "evidence.png",
            "proposals.json",
            "model-masks.npz",
            "native-auxiliary-masks.npz",
        ]:
            frozen["input_hashes"][str((folder / name).relative_to(ROOT))] = sha(folder / name)
        old = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as f:
            native = f["native_probabilities"]
        with np.load(folder / "native-auxiliary-masks.npz") as f:
            endpoint = f["probabilities"][6]
        matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )
        inverse = np.linalg.inv(matrix)
        source = old["authoring"]["image_evidence"]["source"]
        started = time.perf_counter()
        doc, detail = decoder.decode(
            gray,
            native,
            source,
            old["evidence_preprocessing"],
            working_gray=working,
            working_metadata=old["preprocessing"],
            evidence_to_working=matrix,
        )
        saved = json.loads(
            (
                baseline
                / ("human" if human else "synthetic")
                / sample
                / "supported/prediction.json"
            ).read_text()
        )
        if signature(doc) != signature(saved["authoring"]) or detail != saved["decoder"]:
            raise ValueError("Control changed: " + sample)
        baseline_equal += 1
        boxes = detail["region_boxes"]
        segments = boundary_graph(boxes)[0]
        predictions = []
        for arm, (a, b) in ARMS.items():
            directory = output / ("human" if human else "synthetic") / sample / arm
            directory.mkdir(parents=True)
            start = time.perf_counter()
            if arm == "control":
                proposals, evidence = decoder.opening_candidates(segments, gray, native, inverse)
                prediction = authoring_document(source, old["preprocessing"], boxes, proposals)
                if signature(prediction) != signature(doc):
                    raise ValueError("Control opening replay changed")
            else:
                proposals, evidence = experiment.experiment(
                    segments, gray, native, inverse, endpoint, endpoint_first=a, tracking=b
                )
                prediction = authoring_document(source, old["preprocessing"], boxes, proposals)
            elapsed = time.perf_counter() - start
            if validate_authoring(prediction):
                raise ValueError("Contract invalid: " + sample + " " + arm)
            if prediction["topology"]["regions"] != doc["topology"]["regions"]:
                raise ValueError("Region changed")
            if prediction["physical_design"]["acceptance"]["status"] != "pending":
                raise ValueError("Acceptance changed")
            write_json(
                directory / "prediction.json",
                {
                    "authoring": prediction,
                    "opening_evidence": evidence,
                    "labels_used_as_input": False,
                },
            )
            predictions.append((arm, directory, elapsed))
        cases.append((folder, sample, human, role, old, predictions))
        print(json.dumps({"phase": "predict", "sample": sample}), flush=True)
    rows = []
    figures = []
    retention = []
    for folder, sample, human, role, old, predictions in cases:
        ref = (
            reference(int(sample.split("_")[1]), old["preprocessing"])
            if human
            else synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
        )
        baseline_doc = json.loads((predictions[0][1] / "prediction.json").read_text())["authoring"]
        for arm, directory, elapsed in predictions:
            doc = json.loads((directory / "prediction.json").read_text())["authoring"]
            metrics = score(doc, ref, old["preprocessing"]["working_size_px"])
            row = {
                "sample_id": sample,
                "origin": "human" if human else "synthetic",
                "role": role,
                "arm": arm,
                "status": "needs_attention",
                "elapsed_seconds": elapsed,
                "timing_scope": "Opening decode and authoring assembly only; cached masks and fixed region boxes. No model inference or region decode.",
                "metrics": metrics,
                "has_region_reference": bool(ref["regions"]),
                "owner_reference_count": sum((bool(o["entity_ids"]) for o in ref["openings"])),
            }
            row["unmatched_location_proposals"] = (
                metrics["openings"]["predicted"] - metrics["openings"]["true_positive"]
            )
            row["matched_wrong_owner"] = (
                metrics["attachment_scorable"] - metrics["attachment_correct"]
            )
            baseline_open = baseline_doc["topology"]["openings"]
            current = doc["topology"]["openings"]
            preserved = all(
                (
                    any(
                        (
                            o["type"] == p["type"]
                            and o["entity_ids"] == p["entity_ids"]
                            and (o["geometry"]["points_px"] == p["geometry"]["points_px"])
                            for p in current
                        )
                    )
                    for o in baseline_open
                )
            )
            if not preserved:
                raise ValueError("Baseline opening removed")
            retention.append(
                {"sample_id": sample, "arm": arm, "all_baseline_proposals_retained": preserved}
            )
            write_json(directory / "metrics.json", row)
            rows.append(row)
            if human:
                draw_preview(folder / "working.png", doc, ref, directory / "comparison.png")
                figures.append(
                    "<figure><figcaption>"
                    + sample
                    + " / "
                    + role
                    + " / "
                    + arm
                    + "<br>location "
                    + str(metrics["openings"])
                    + "<br>correct owner "
                    + str(metrics["attachment_correct"])
                    + '</figcaption><img loading="lazy" src="'
                    + str((directory / "comparison.png").relative_to(output))
                    + '"></figure>'
                )
    summaries = {
        arm: {
            role: summary([r for r in rows if r["arm"] == arm and r["role"] == role])
            for role in ["train", "validation", "test", "synthetic_control"]
        }
        for arm in ARMS
    }
    for arm in ARMS:
        for role in summaries[arm]:
            selected = [r for r in rows if r["arm"] == arm and r["role"] == role]
            summaries[arm][role]["unmatched_location_proposals"] = sum(
                (r["unmatched_location_proposals"] for r in selected)
            )
            summaries[arm][role]["matched_wrong_owner"] = sum(
                (r["matched_wrong_owner"] for r in selected)
            )
    guards = {
        arm: {
            "baseline_proposals_retained": True,
            "synthetic_false_connections_not_increased": summaries[arm]["synthetic_control"][
                "false_connections"
            ]
            <= summaries["control"]["synthetic_control"]["false_connections"],
        }
        for arm in ARMS
    }
    changed = [p for p, h in {**protected, **frozen["input_hashes"]}.items() if sha(ROOT / p) != h]
    if changed:
        raise ValueError("Protected files changed")
    write_json(output / "freeze.json", frozen)
    write_json(
        output / "report.json",
        {
            "scope": frozen["scope"],
            "summary": summaries,
            "rows": rows,
            "guards": guards,
            "default_promoted": False,
            "control_replays_equal": baseline_equal,
            "all_baseline_proposals_retained_by_design": True,
            "human_exact_topology": None,
            "human_correction_time": None,
            "model_retrained": False,
            "model_inference_run": False,
        },
    )
    write_json(
        output / "verification.json",
        {
            "cases": len(cases),
            "control_replays_equal": baseline_equal,
            "contract_valid_predictions": len(rows),
            "regions_unchanged_all_arms": True,
            "protected_files_changed": changed,
            "cached_files_checked": len(frozen["input_hashes"]),
            "acceptance_pending_all_arms": True,
            "baseline_retention": retention,
        },
    )
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Opening ablation</title><style>body{font:14px system-ui;margin:20px}main{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}figure{margin:0;border:1px solid #ccc;padding:8px}img{width:100%}figcaption{overflow-wrap:anywhere}</style><h1>Four-arm opening experiment</h1><p>Same masks. No training. Green approximate reference, orange regions, red proposed openings. Human exact topology unknown. Baseline proposals retain precedence in every arm.</p><main>'
        + "".join(figures)
        + "</main>"
    )
    print(json.dumps({"summary": summaries, "guards": guards}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subset", choices=["validation", "all"], default="validation")
    args = parser.parse_args()
    evaluate(args.output, args.subset)
