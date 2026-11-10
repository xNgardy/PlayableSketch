import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import time
import cv2
import numpy as np
from .decoder_refined import decode, POLICY
from .region_recovery import POLICY as REGION_POLICY
from .contract import validate_authoring
from .dino_region_audit import sha, ROOT
from .human_error_review import reference
from .pilot import score, aggregate, synthetic_reference, draw_preview
from .synthetic import write_json
from SketchPipeline.evaluation.metrics import counts


def summary(rows):
    result = aggregate(rows)
    scorable = [r for r in rows if r["has_region_reference"]]
    result["attached_openings"] = counts(
        sum((r["metrics"]["attachment_correct"] for r in scorable)),
        sum((r["metrics"]["openings"]["predicted"] for r in scorable)),
        sum((r["owner_reference_count"] for r in scorable)),
    )
    return result


def signature(doc):
    top = doc["topology"]
    return {
        "regions": [(r["type"], r["geometry"]["points_px"]) for r in top["regions"]],
        "openings": [
            (o["type"], o["entity_ids"], o["geometry"]["points_px"]) for o in top["openings"]
        ],
    }


def evaluate(study, output, subset="all"):
    study = Path(study).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((study / "protocol.json").read_text())
    paths = [
        Path(__file__),
        Path(__file__).with_name("region_recovery.py"),
        Path(__file__).with_name("region_recovery.v1.json"),
        Path(__file__).with_name("decoder_refined.py"),
        Path(__file__).with_name("decoder_refined.config.json"),
        Path(__file__).with_name("decoder.py"),
    ]
    frozen = {
        "version": "supported-region-comparison/1.0",
        "region_policy": REGION_POLICY,
        "decoder_policy": POLICY,
        "study_report_sha256": sha(study / "report.json"),
        "subset": subset,
        "model_retrained": False,
        "model_inference_run": False,
        "labels_used_for_inference": False,
        "scope": "Same cached masks from previously inspected development plans; no new blind or writer-disjoint claim.",
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in paths},
        "input_hashes": {},
    }
    for source in paths:
        target = output / "source_snapshot" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_json(output / "freeze.json", frozen)
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    rows = []
    figures = []
    for folder in folders:
        is_human = folder.parent.parent.name == "human"
        sample = folder.parent.name
        if is_human:
            n = int(sample.split("_")[1])
            role = protocol["groups"][sample]["split"]
        else:
            role = "synthetic_control"
        if subset == "validation" and (
            not (
                role == "validation"
                or (not is_human and sample in protocol["validation_synthetic_ids"])
            )
        ):
            continue
        result = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "working.png"), 0)
        evidence = cv2.imread(str(folder / "evidence.png"), 0)
        with np.load(folder / "model-masks.npz") as cache:
            native = cache["native_probabilities"]
        for name in ["proposals.json", "working.png", "evidence.png", "model-masks.npz"]:
            frozen["input_hashes"][str((folder / name).relative_to(ROOT))] = sha(folder / name)
        matrix = np.asarray(result["preprocessing"]["original_to_working"]) @ np.asarray(
            result["evidence_preprocessing"]["working_to_original"]
        )
        source = result["authoring"]["image_evidence"]["source"]
        predictions = []
        for arm in ["legacy", "supported"]:
            directory = output / ("human" if is_human else "synthetic") / sample / arm
            directory.mkdir(parents=True)
            started = time.perf_counter()
            document, detail = decode(
                evidence,
                native,
                source,
                result["evidence_preprocessing"],
                working_gray=gray,
                working_metadata=result["preprocessing"],
                evidence_to_working=matrix,
                region_policy=arm,
            )
            elapsed = time.perf_counter() - started
            if validate_authoring(document):
                raise ValueError("Invalid decoded contract: " + sample)
            if arm == "legacy" and signature(document) != signature(result["authoring"]):
                raise ValueError("Legacy replay changed: " + sample)
            write_json(
                directory / "prediction.json",
                {"authoring": document, "decoder": detail, "labels_used_as_input": False},
            )
            predictions.append((arm, directory, document, detail, elapsed))
        ref = (
            reference(n, result["preprocessing"])
            if is_human
            else synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
        )
        for arm, directory, document, detail, elapsed in predictions:
            metrics = score(document, ref, result["preprocessing"]["working_size_px"])
            row = {
                "sample_id": sample,
                "origin": "human" if is_human else "synthetic",
                "role": role,
                "arm": arm,
                "status": (
                    "needs_attention" if document["topology"]["regions"] else "manual_required"
                ),
                "elapsed_seconds": elapsed,
                "timing_scope": "Decoder only, cached masks; no model inference",
                "metrics": metrics,
                "has_region_reference": bool(ref["regions"]),
                "owner_reference_count": sum((bool(o["entity_ids"]) for o in ref["openings"])),
                "recovery_detail": detail.get("region_reconstruction"),
            }
            rows.append(row)
            write_json(directory / "metrics.json", row)
            if is_human:
                draw_preview(folder / "working.png", document, ref, directory / "comparison.png")
                figures.append(
                    f"""<figure><figcaption>{sample} · {role} · {arm} · regions {metrics['regions']} · openings {metrics['openings']} · correct attachment {metrics['attachment_correct']}/{metrics['attachment_scorable']}</figcaption><img loading="lazy" src="human/{sample}/{arm}/comparison.png"></figure>"""
                )
        print(
            json.dumps(
                {
                    "sample": sample,
                    "role": role,
                    "supported_regions": rows[-1]["metrics"]["regions"],
                    "supported_openings": rows[-1]["metrics"]["openings"],
                }
            ),
            flush=True,
        )
    summaries = {
        arm: {
            role: summary([r for r in rows if r["arm"] == arm and r["role"] == role])
            for role in ["train", "validation", "test", "synthetic_control"]
        }
        for arm in ["legacy", "supported"]
    }
    changed = [
        path for path, digest in frozen["input_hashes"].items() if sha(ROOT / path) != digest
    ]
    if changed:
        raise ValueError("Cached inputs changed")
    write_json(output / "freeze.json", frozen)
    report = {
        "version": frozen["version"],
        "summary": summaries,
        "rows": rows,
        "cached_case_count": len(rows) // 2,
        "cached_input_files_checked": len(frozen["input_hashes"]),
        "cached_inputs_changed": changed,
        "model_inference_run": False,
        "model_retrained": False,
        "legacy_replay_exact": True,
        "scope": frozen["scope"],
    }
    write_json(output / "report.json", report)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Supported region decoder comparison</title><style>body{font:14px system-ui;margin:24px}figure{border:1px solid #ddd;padding:12px;display:inline-block;max-width:47%;vertical-align:top}img{max-width:100%}figcaption{overflow-wrap:anywhere}</style><h1>Region decoder comparison</h1><p>Same saved DINO masks; no training or new inference. Green: approximate reference; orange: decoded regions; red: opening proposals. Retrospective development comparison.</p>'
        + "".join(figures)
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subset", choices=["all", "validation"], default="all")
    args = parser.parse_args()
    evaluate(args.study, args.output, args.subset)
