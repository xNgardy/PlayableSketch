import argparse
import copy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.evaluation.metrics import counts, pairs, endpoint_error, distribution
from SketchPipeline.shape_authoring.propose import run
from SketchPipeline.shape_authoring.model import LocalSegmenter
from SketchPipeline.shape_authoring.human_error_review import reference as human_reference
from SketchPipeline.shape_authoring.pilot import score
from SketchPipeline.shape_authoring.contract import validate_authoring

DATA = ROOT / "Data/augmented/v1"
METRICS = ["regions", "doors", "openings", "connections"]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=lambda x: x.item() if isinstance(x, np.generic) else x,
        )
        + "\n"
    )


def inventory():
    samples = read(DATA / "manifest.json")["samples"]
    parents = {}
    for e in samples:
        if e["source_id"] in parents:
            continue
        t = read(DATA / e["transform_path"])
        image = (DATA / t["source_files"]["image_path"]["path"]).resolve()
        parents[e["source_id"]] = {
            "id": e["source_id"],
            "source_id": e["source_id"],
            "source_origin": e["source_origin"],
            "base_plan_id": e["base_plan_id"],
            "profile": "original",
            "image_path": str(image),
            "image_sha256": t["source_files"]["image_path"]["sha256"],
            "source_files": t["source_files"],
        }
    return (list(parents.values()) + samples, parents)


def transform_reference(reference, matrix):
    result = copy.deepcopy(reference)
    for region in result["regions"]:
        polygon = project(region["polygon"], matrix)
        region.update(
            polygon=polygon.tolist(), bounds_px=np.r_[polygon.min(0), polygon.max(0)].tolist()
        )
    for opening in result["openings"]:
        opening["points_px"] = project(opening["points_px"], matrix).tolist()
    return result


def source_reference(parent):
    if parent["source_origin"] == "human":
        size = __import__("PIL.Image", fromlist=["Image"]).open(parent["image_path"]).size
        return human_reference(
            int(parent["source_id"].split("_")[1]),
            {"original_to_working": np.eye(3).tolist(), "working_size_px": list(size)},
        )
    files = parent["source_files"]
    annotation = read(DATA / files["side_path"]["path"])
    metric = read(DATA / files["metric_path"]["path"])
    owners = {
        o["id"]: [v["id"] for v in o["connected_entities"]] for o in metric["layout"]["openings"]
    }
    regions = []
    for r in annotation["regions"]:
        p = np.asarray(r["polygon_px"], float)
        regions.append(
            {
                "id": r["region_id"],
                "type": "corridor_segment" if r["kind"] == "corridor" else "room",
                "polygon": p.tolist(),
                "bounds_px": np.r_[p.min(0), p.max(0)].tolist(),
            }
        )
    openings = [
        {
            "id": g["id"],
            "type": g["kind"],
            "points_px": [g["start_px"], g["end_px"]],
            "entity_ids": owners[g["opening_candidate_id"]],
        }
        for g in annotation["gaps"]
        if g["kind"] in ("door", "open_passage")
    ]
    return {"regions": regions, "openings": openings, "approximate_human_labels": False}


def scored(document, reference, size):
    result = score(document, reference, size)
    result["connections"] = counts(
        result["attachment_correct"],
        len(document["topology"]["openings"]),
        sum((bool(o["entity_ids"]) for o in reference["openings"])),
    )
    result["connection_unit"] = (
        "opening-level correctly typed, localized and attached to mapped source owners"
    )
    mapping = result["region_id_mapping"]
    pd = [o for o in document["topology"]["openings"] if o["type"] == "door"]
    rd = [o for o in reference["openings"] if o["type"] == "door" and o["entity_ids"]]
    matches = pairs(
        pd,
        rd,
        lambda a, b: (
            endpoint_error(a["geometry"]["points_px"], b["points_px"])
            if set((mapping.get(v, "unmatched:" + v) for v in a["entity_ids"]))
            == set(b["entity_ids"])
            else float("inf")
        ),
        max(size) * 0.04,
    )
    result["attached_doors"] = counts(len(matches), len(pd), len(rd))
    return result


def aggregate(rows):
    result = {
        "samples": len(rows),
        "parent_drawings": len({r["source_id"] for r in rows}),
        "base_plan_groups": len({r["base_plan_id"] for r in rows}),
    }
    for key in METRICS + ["attached_doors"]:
        values = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        result[key] = counts(
            *(sum((v[k] for v in values)) for k in ["true_positive", "predicted", "reference"])
        )
        result[key].update(
            scorable_samples=len(values),
            unmatched_predictions=result[key]["predicted"] - result[key]["true_positive"],
            missed_references=result[key]["reference"] - result[key]["true_positive"],
        )
    exact = [
        r["metrics"]["exact_topology"] for r in rows if r["metrics"]["exact_topology"] is not None
    ]
    result["exact_topology"] = {
        "correct": sum(exact),
        "scorable": len(exact),
        "fraction": sum(exact) / len(exact) if exact else None,
    }
    result["failure_count"] = sum((r["failure"] is not None for r in rows))
    result["manual_required"] = sum((r["status"] == "manual_required" for r in rows))
    result["elapsed_seconds"] = distribution([r["elapsed_seconds"] for r in rows])
    return result


def main(output):
    import torch

    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    entries, parents = inventory()
    lock = read(ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json")
    checkpoint = ROOT / lock["checkpoint_path"]
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "protocol.json"
    source_files = (
        list((ROOT / "SketchPipeline/shape_authoring").glob("*.py"))
        + list((ROOT / "SketchPipeline/shape_authoring").glob("*.json"))
        + [Path(__file__).resolve()]
    )
    protected = list((ROOT / "Data").rglob("*"))
    protected = [p for p in protected if p.is_file() and "__pycache__" not in p.parts] + [
        checkpoint
    ]
    if not protocol_path.exists():
        protocol = {
            "version": "augmented-shape-robustness/1.0",
            "date": "2026-11-07",
            "inference_samples": len(entries),
            "originals": len(parents),
            "augmented": len(entries) - len(parents),
            "model_sha256": sha(checkpoint),
            "profile": "refined-full",
            "normalize_ink": True,
            "model_training": False,
            "parameter_selection": False,
            "reference_inference_inputs": False,
            "production_entrypoint": "shape_authoring.propose.run, all three alternatives",
            "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in source_files},
            "protected_hashes": {str(p.relative_to(ROOT)): sha(p) for p in protected},
            "policy": "Compare each transformation with the same original parent; aggregate human and synthetic separately. Not independent holdout.",
            "scoring": "Bounding IoU >= .5; correct opening type and endpoint error <= .04 working maximum side; mapped source owners for connections.",
            "limitations": [
                "Human region and owner references approximate; missing region labels excluded from region metrics.",
                "Synthetic masks represent renderer walls/ticks/text, not full six-channel structural GT; no pixel Dice claimed.",
                "50 old human sources only; Data_51..70 have no variants in this manifest.",
                "Transform-label transfer validated computationally; no new manual label review.",
                "Parent and plan dependence retained; no pooling with old 130 to inflate independent sample count.",
            ],
        }
        save(protocol_path, protocol)
        for p in source_files:
            dest = output / "source_snapshot" / p.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
    protocol = read(protocol_path)
    assert all(
        (sha(ROOT / p) == h for p, h in protocol["source_hashes"].items())
    ), "Source changed during/resuming audit"
    assert sha(checkpoint) == lock["checkpoint_sha256"] == protocol["model_sha256"]
    model = LocalSegmenter(checkpoint, lock["checkpoint_sha256"])
    started = time.perf_counter()
    with patch("SketchPipeline.shape_authoring.model.LocalSegmenter", return_value=model):
        for i, e in enumerate(entries):
            target = output / "predictions" / e["id"]
            archive = target / "proposals.json.gz"
            if not archive.exists():
                image = (
                    Path(e["image_path"]) if e["profile"] == "original" else DATA / e["image_path"]
                )
                assert sha(image) == e["image_sha256"], e["id"]
                if (target / "proposals.json").exists():
                    result = read(target / "proposals.json")
                else:
                    result = run(
                        image,
                        target,
                        checkpoint=checkpoint,
                        expected_sha256=lock["checkpoint_sha256"],
                        profile="refined-full",
                        normalize_ink=True,
                    )
                assert result["model"]["checkpoint_sha256"] == lock["checkpoint_sha256"]
                assert result["review_required"]
                assert all(
                    (
                        not validate_authoring(d)
                        for d in [result["authoring"]] + result["alternatives"]
                    )
                )
                temporary = target / "proposals.json.gz.tmp"
                with gzip.open(temporary, "wt", encoding="utf8") as f:
                    json.dump(
                        result,
                        f,
                        ensure_ascii=False,
                        default=lambda v: v.item() if isinstance(v, np.generic) else v,
                    )
                temporary.replace(archive)
            for p in target.iterdir():
                if p.name not in [
                    "proposals.json.gz",
                    "authoring.json",
                    "working.png",
                    "evidence.png",
                ]:
                    p.unlink()
            if i % 10 == 0 or i == len(entries) - 1:
                print(
                    json.dumps(
                        {
                            "completed": i + 1,
                            "total": len(entries),
                            "sample": e["id"],
                            "elapsed_seconds": round(time.perf_counter() - started, 1),
                        }
                    ),
                    flush=True,
                )
    print("All predictions persisted; reference scoring starts now.", flush=True)
    source_refs = {k: source_reference(p) for k, p in parents.items()}
    parent_splits = read(ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json")["groups"]
    rows = []
    for e in entries:
        archive = output / "predictions" / e["id"] / "proposals.json.gz"
        with gzip.open(archive, "rt", encoding="utf8") as f:
            result = json.load(f)
        transform = (
            np.eye(3)
            if e["profile"] == "original"
            else np.asarray(read(DATA / e["transform_path"])["source_to_augmented"])
        )
        matrix = np.asarray(result["preprocessing"]["original_to_working"]) @ transform
        reference = transform_reference(source_refs[e["source_id"]], matrix)
        metric = scored(result["authoring"], reference, result["preprocessing"]["working_size_px"])
        row = {k: e[k] for k in ["source_id", "source_origin", "base_plan_id", "profile"]}
        row.update(
            sample_id=e["id"],
            split=(
                parent_splits[e["source_id"]]["split"]
                if e["source_origin"] == "human"
                else "development"
            ),
            metrics=metric,
            status=result["status"],
            failure=result["failure"],
            elapsed_seconds=result["elapsed_seconds"],
            prediction_sha256=sha(archive),
        )
        save(output / "metrics" / f"{e['id']}.json", row)
        rows.append(row)
    summary = {
        origin: {
            profile: aggregate(
                [
                    r
                    for r in rows
                    if r["source_origin"] == origin
                    and (
                        r["profile"] == profile
                        if profile != "augmented_all"
                        else r["profile"] != "original"
                    )
                ]
            )
            for profile in [
                "original",
                "rotate",
                "perspective",
                "lighting",
                "capture",
                "combined",
                "augmented_all",
            ]
        }
        for origin in ["human", "synthetic"]
    }
    split_summary = {
        split: {
            profile: aggregate(
                [
                    r
                    for r in rows
                    if r["source_origin"] == "human"
                    and r["split"] == split
                    and (
                        r["profile"] == profile
                        if profile != "augmented_all"
                        else r["profile"] != "original"
                    )
                ]
            )
            for profile in [
                "original",
                "rotate",
                "perspective",
                "lighting",
                "capture",
                "combined",
                "augmented_all",
            ]
        }
        for split in ["train", "validation", "test"]
    }
    originals = {r["source_id"]: r for r in rows if r["profile"] == "original"}
    paired = []
    for r in rows:
        if r["profile"] == "original":
            continue
        for key in METRICS:
            a = originals[r["source_id"]]["metrics"][key]
            b = r["metrics"][key]
            paired.append(
                {
                    "sample_id": r["sample_id"],
                    "source_id": r["source_id"],
                    "origin": r["source_origin"],
                    "base_plan_id": r["base_plan_id"],
                    "profile": r["profile"],
                    "metric": key,
                    "original_f1": a["f1"] if a else None,
                    "augmented_f1": b["f1"] if b else None,
                    "delta_f1": (
                        b["f1"] - a["f1"]
                        if a and b and (a["f1"] is not None) and (b["f1"] is not None)
                        else None
                    ),
                }
            )
    assert all((sha(ROOT / p) == h for p, h in protocol["source_hashes"].items()))
    changed = [p for p, h in protocol["protected_hashes"].items() if sha(ROOT / p) != h]
    assert not changed, changed
    save(
        output / "report.json",
        {
            "summary": summary,
            "human_parent_split_summary": split_summary,
            "rows": rows,
            "paired": paired,
            "training": False,
            "source_and_data_unchanged": True,
        },
    )
    with (output / "metrics.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "origin",
                "profile",
                "samples",
                "metric",
                "TP",
                "predicted",
                "reference",
                "precision",
                "recall",
                "f1",
            ]
        )
        for origin, profiles in summary.items():
            for profile, m in profiles.items():
                for key in METRICS + ["attached_doors"]:
                    v = m[key]
                    w.writerow(
                        [origin, profile, m["samples"], key]
                        + [
                            v[k]
                            for k in [
                                "true_positive",
                                "predicted",
                                "reference",
                                "precision",
                                "recall",
                                "f1",
                            ]
                        ]
                    )
    with (output / "paired.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(paired[0]))
        w.writeheader()
        w.writerows(paired)
    save(
        output / "verification.json",
        {
            "fresh_predictions": len(entries),
            "augmented": 600,
            "originals": 120,
            "valid_documents": len(entries) * 3,
            "protected_files_checked": len(protocol["protected_hashes"]),
            "protected_changed": changed,
            "model_training": False,
        },
    )
    print("Complete: " + str(output), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/augmented_robustness/v1"
    )
    main(parser.parse_args().output.resolve())
