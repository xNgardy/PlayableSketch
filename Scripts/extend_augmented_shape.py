import copy
import csv
import gzip
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.synthetic.augment import parameters, augment_pixels, PROFILES
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.shape_authoring.diagnose_new20 import (
    reference as reference_new20,
    evaluate as evaluate_new20,
)
from SketchPipeline.shape_authoring.propose import run
from SketchPipeline.shape_authoring.model import LocalSegmenter
from SketchPipeline.shape_authoring.contract import validate_authoring
from Scripts.evaluate_augmented_shape import read, save, sha, transform_reference, scored, aggregate
from Scripts.report_augmented_shape import paired_intervals

DATA = ROOT / "Data/augmented/new20_v1"
PREVIOUS = ROOT / "Saved/ShapeFirst/augmented_robustness/v1"
OUT = ROOT / "Saved/ShapeFirst/augmented_robustness/v2"
OVERRIDES = ROOT / "Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json"
KEYS = ["regions", "doors", "openings", "connections", "attached_doors"]


def transfer_structural(raw, matrix, image_sha):
    result = copy.deepcopy(raw)
    for r in result["regions"]:
        r["polygon_px"] = project(r["polygon_px"], matrix).tolist()
    for g in result["openings"]:
        g["start_px"], g["end_px"] = project([g["start_px"], g["end_px"]], matrix).tolist()
    result.update(image_sha256=image_sha, coordinate_frame="original", augmentation_transfer=True)
    result["notes"] = result.get("notes", []) + [
        "Automatic source-label transfer; no new manual review or metric acceptance."
    ]
    return result


def generate():
    if (DATA / "verification.json").exists():
        return read(DATA / "manifest.json")["samples"]
    DATA.mkdir(parents=True, exist_ok=True)
    parents = [
        s
        for s in read(ROOT / "Data/synthetic/corridor_addon_v1/manifest.json")["samples"]
        if s["origin"] == "human"
    ]
    assert {s["id"] for s in parents} == {f"Data_{n}" for n in range(51, 71)}
    sources = []
    entries = []
    for source in parents:
        sid = source["id"]
        image = ROOT / "Data" / f"{sid}.png"
        raw_path = ROOT / f"Data/ground_truth/structural_v1/{sid}.structural.json"
        assert sha(image) == source["image_sha256"]
        sources.extend([image, raw_path])
        with Image.open(image) as im:
            assert im.getexif().get(274, 1) == 1
            pixels = np.asarray(im.convert("RGB"))
        h, w = pixels.shape[:2]
        raw = read(raw_path)
        assert raw["image_sha256"] == source["image_sha256"]
        for profile in PROFILES:
            eid = f"AUG_{sid}_{profile}"
            matrix, settings = parameters(sid, profile, w, h)
            path = DATA / "images" / f"{eid}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(augment_pixels(pixels, matrix, settings)).save(path, compress_level=3)
            digest = sha(path)
            transferred = transfer_structural(raw, matrix, digest)
            points = [p for r in transferred["regions"] for p in r["polygon_px"]] + [
                g[k] for g in transferred["openings"] for k in ["start_px", "end_px"]
            ]
            assert all((0 <= x < w and 0 <= y < h for x, y in points)), (eid, "out of bounds")
            restored = transfer_structural(
                transferred, np.linalg.inv(matrix), source["image_sha256"]
            )
            for a, b in zip(raw["regions"], restored["regions"]):
                np.testing.assert_allclose(a["polygon_px"], b["polygon_px"], atol=1e-06)
            for a, b in zip(raw["openings"], restored["openings"]):
                assert a["entity_ids"] == b["entity_ids"] and a["kind"] == b["kind"]
                np.testing.assert_allclose(
                    [a["start_px"], a["end_px"]], [b["start_px"], b["end_px"]], atol=1e-06
                )
            label = DATA / "structural" / f"{eid}.structural.json"
            save(label, transferred)
            meta = {
                "source_to_augmented": matrix.tolist(),
                "augmented_to_source": np.linalg.inv(matrix).tolist(),
                "parameters": settings,
                "source_image": str(image.relative_to(ROOT)),
                "source_sha256": source["image_sha256"],
                "source_structural_reference": str(raw_path.relative_to(ROOT)),
                "source_reference_sha256": sha(raw_path),
                "masks": {},
                "human_dense_masks_fabricated": False,
                "review_required": True,
            }
            save(DATA / "transforms" / f"{eid}.json", meta)
            entries.append(
                {
                    "id": eid,
                    "source_id": sid,
                    "source_origin": "human",
                    "base_plan_id": source["base_plan_id"],
                    "writer_id": source["writer_id"],
                    "split": source["split"],
                    "profile": profile,
                    "image_path": str(path.relative_to(DATA)),
                    "image_sha256": digest,
                    "transform_path": f"transforms/{eid}.json",
                    "structural_reference_path": str(label.relative_to(DATA)),
                    "review_status": "pending",
                }
            )
        print(f"Generated {sid}: five views", flush=True)
    save(
        DATA / "manifest.json",
        {
            "version": "new20-augmentation/1.0",
            "generator": "annotation-transfer-augmentation/1.0",
            "profiles": list(PROFILES),
            "split_policy": "Inherit source parent split; not independent holdout.",
            "samples": entries,
        },
    )
    save(
        DATA / "verification.json",
        {
            "source_images": 20,
            "new_images": 100,
            "profiles_per_source": 5,
            "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in sources},
            "coordinate_round_trips_passed": True,
            "annotations_in_bounds": True,
            "owners_and_types_preserved": True,
            "human_dense_masks_fabricated": False,
            "training": False,
            "review_required": True,
        },
    )
    return entries


def check_previous():
    protocol = read(PREVIOUS / "protocol.json")
    assert all(
        (sha(ROOT / p) == h for p, h in protocol["source_hashes"].items())
    ), "Previous inference source changed"
    assert all(
        (sha(ROOT / p) == h for p, h in protocol["protected_hashes"].items())
    ), "Previous data/model changed"
    report = read(PREVIOUS / "report.json")
    for r in report["rows"]:
        assert (
            sha(PREVIOUS / "predictions" / r["sample_id"] / "proposals.json.gz")
            == r["prediction_sha256"]
        )
    return report


def main():
    import torch

    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    previous = check_previous()
    entries = generate()
    parent_map = {}
    for e in entries:
        parent_map[e["source_id"]] = {
            **e,
            "id": e["source_id"],
            "profile": "original",
            "image_path": str(ROOT / "Data" / f"{e['source_id']}.png"),
            "image_sha256": sha(ROOT / "Data" / f"{e['source_id']}.png"),
        }
    todo = list(parent_map.values()) + entries
    OUT.mkdir(parents=True, exist_ok=True)
    lock = read(ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json")
    checkpoint = ROOT / lock["checkpoint_path"]
    protocol_path = OUT / "protocol.json"
    if not protocol_path.exists():
        files = [
            p for p in (ROOT / "Data").rglob("*") if p.is_file() and "__pycache__" not in p.parts
        ] + [checkpoint, OVERRIDES]
        source_files = list((ROOT / "SketchPipeline/shape_authoring").glob("*.py")) + list(
            (ROOT / "SketchPipeline/shape_authoring").glob("*.json")
        )
        source_files += [
            Path(__file__).resolve(),
            ROOT / "Scripts/evaluate_augmented_shape.py",
            ROOT / "Scripts/report_augmented_shape.py",
            ROOT / "SketchPipeline/synthetic/augment.py",
        ]
        protocol = {
            "version": "complete-augmentation-audit/2.0",
            "date": "2026-11-07",
            "old_predictions_reused": 720,
            "fresh_predictions": 120,
            "total_originals": 140,
            "total_augmented": 700,
            "total_predictions": 840,
            "model_sha256": lock["checkpoint_sha256"],
            "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in source_files},
            "protected_hashes": {str(p.relative_to(ROOT)): sha(p) for p in files},
            "previous_report_sha256": sha(PREVIOUS / "report.json"),
            "previous_protocol_sha256": sha(PREVIOUS / "protocol.json"),
            "model_training": False,
            "parameter_selection": False,
            "reference_inference_inputs": False,
            "scope": "70 human sources and 70 synthetic sources with five views each; previously inspected development corpus.",
            "reference_notes": "Old human owners approximate by proximity; new20 owners explicit structural IDs, approximate trace coordinates. Existing Data_63 endpoint override applied only when scoring. All combined connections use the same opening-level matching rule.",
        }
        save(protocol_path, protocol)
        for p in source_files:
            target = OUT / "source_snapshot" / p.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    protocol = read(protocol_path)
    assert all((sha(ROOT / p) == h for p, h in protocol["source_hashes"].items()))
    model = LocalSegmenter(checkpoint, lock["checkpoint_sha256"])
    started = time.perf_counter()
    with patch("SketchPipeline.shape_authoring.model.LocalSegmenter", return_value=model):
        for i, e in enumerate(todo):
            target = OUT / "predictions" / e["id"]
            archive = target / "proposals.json.gz"
            if not archive.exists():
                image = (
                    Path(e["image_path"]) if e["profile"] == "original" else DATA / e["image_path"]
                )
                assert sha(image) == e["image_sha256"]
                result = (
                    read(target / "proposals.json")
                    if (target / "proposals.json").exists()
                    else run(
                        image,
                        target,
                        checkpoint=checkpoint,
                        expected_sha256=lock["checkpoint_sha256"],
                        profile="refined-full",
                        normalize_ink=True,
                    )
                )
                assert result["model"]["checkpoint_sha256"] == protocol["model_sha256"]
                assert result["profile_configuration"]["decoder"]["version"] == "shape-decoder/2.9"
                assert result["failure"] is None, result["failure"]
                docs = [result["authoring"]] + result["alternatives"]
                assert len(docs) == 3 and all((not validate_authoring(d) for d in docs))
                assert all(
                    (d["physical_design"]["acceptance"]["status"] == "pending" for d in docs)
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
            if i % 10 == 0 or i == 119:
                print(
                    json.dumps(
                        {
                            "completed": i + 1,
                            "total": 120,
                            "sample": e["id"],
                            "elapsed_seconds": round(time.perf_counter() - started, 1),
                        }
                    ),
                    flush=True,
                )
    print("New predictions persisted; reference scoring starts.", flush=True)
    overrides = read(OVERRIDES)
    source_refs = {
        sid: reference_new20(
            int(sid.split("_")[1]), {"original_to_working": np.eye(3).tolist()}, overrides
        )[0]
        for sid in parent_map
    }
    rows = []
    for old in previous["rows"]:
        row = copy.deepcopy(old)
        row["cohort"] = "old50" if row["source_origin"] == "human" else "synthetic"
        row["prediction_directory"] = str(
            (PREVIOUS / "predictions" / row["sample_id"]).relative_to(ROOT)
        )
        row["inference"] = "verified_previous_run"
        rows.append(row)
    for e in todo:
        archive = OUT / "predictions" / e["id"] / "proposals.json.gz"
        with gzip.open(archive, "rt", encoding="utf8") as f:
            result = json.load(f)
        transfer = (
            np.eye(3)
            if e["profile"] == "original"
            else np.asarray(read(DATA / e["transform_path"])["source_to_augmented"])
        )
        reference = transform_reference(
            source_refs[e["source_id"]],
            np.asarray(result["preprocessing"]["original_to_working"]) @ transfer,
        )
        metric = scored(result["authoring"], reference, result["preprocessing"]["working_size_px"])
        row = {k: e[k] for k in ["source_id", "source_origin", "base_plan_id", "profile", "split"]}
        row.update(
            sample_id=e["id"],
            cohort="new20",
            metrics=metric,
            unique_pair_metrics=evaluate_new20(
                result["authoring"], reference, result["preprocessing"]["working_size_px"]
            ),
            status=result["status"],
            failure=result["failure"],
            elapsed_seconds=result["elapsed_seconds"],
            prediction_sha256=sha(archive),
            prediction_directory=str(archive.parent.relative_to(ROOT)),
            inference="fresh_v2",
        )
        save(OUT / "metrics" / f"{e['id']}.json", row)
        save(OUT / "evaluation_references" / f"{e['id']}.json", reference)
        rows.append(row)
    assert len(rows) == 840 and len({r["sample_id"] for r in rows}) == 840
    profiles = ["original"] + list(PROFILES) + ["augmented_all"]
    select = lambda rs, p: [
        r for r in rs if (r["profile"] != "original" if p == "augmented_all" else r["profile"] == p)
    ]
    cohorts = {
        c: {p: aggregate(select([r for r in rows if r["cohort"] == c], p)) for p in profiles}
        for c in ["old50", "new20", "synthetic"]
    }
    summary = {
        o: {p: aggregate(select([r for r in rows if r["source_origin"] == o], p)) for p in profiles}
        for o in ["human", "synthetic"]
    }
    splits = {
        c: {
            s: {
                p: aggregate(
                    select(
                        [
                            r
                            for r in rows
                            if r["source_origin"] == "human"
                            and (c == "all70" or r["cohort"] == c)
                            and (r["split"] == s)
                        ],
                        p,
                    )
                )
                for p in profiles
            }
            for s in ["train", "validation", "test"]
        }
        for c in ["all70", "old50", "new20"]
    }
    original = {r["source_id"]: r for r in rows if r["profile"] == "original"}
    paired = []
    for r in rows:
        if r["profile"] == "original":
            continue
        for k in KEYS:
            a = original[r["source_id"]]["metrics"][k]
            b = r["metrics"][k]
            paired.append(
                {
                    "source_id": r["source_id"],
                    "sample_id": r["sample_id"],
                    "cohort": r["cohort"],
                    "profile": r["profile"],
                    "metric": k,
                    "original_f1": a["f1"] if a else None,
                    "augmented_f1": b["f1"] if b else None,
                    "delta_f1": (
                        b["f1"] - a["f1"]
                        if a and b and (a["f1"] is not None) and (b["f1"] is not None)
                        else None
                    ),
                }
            )
    intervals = paired_intervals(rows)
    result = {
        "summary": summary,
        "cohorts": cohorts,
        "human_split_summary": splits,
        "rows": rows,
        "paired": paired,
        "scope": protocol["scope"],
        "connection_unit": "Opening-level, same rule for every cohort. new20 unique pairs retained separately.",
        "fresh_predictions": 120,
        "verified_reused_predictions": 720,
        "model_training": False,
    }
    save(OUT / "report.json", result)
    save(
        OUT / "paired_intervals.json",
        {"rows": intervals, "seed": 20261107, "replicates": 5000, "cluster": "base_plan_id"},
    )
    with (OUT / "metrics.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "scope",
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
        for scope, group in {**summary, **cohorts}.items():
            for profile, m in group.items():
                for k in KEYS:
                    w.writerow(
                        [scope, profile, m["samples"], k]
                        + [
                            m[k][v]
                            for v in [
                                "true_positive",
                                "predicted",
                                "reference",
                                "precision",
                                "recall",
                                "f1",
                            ]
                        ]
                    )
    with (OUT / "paired.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(paired[0]))
        w.writeheader()
        w.writerows(paired)
    assert all((sha(ROOT / p) == h for p, h in protocol["source_hashes"].items()))
    assert all((sha(ROOT / p) == h for p, h in protocol["protected_hashes"].items()))
    assert sha(PREVIOUS / "report.json") == protocol["previous_report_sha256"]
    save(
        OUT / "verification.json",
        {
            "predictions": 840,
            "fresh_predictions": 120,
            "verified_reused_predictions": 720,
            "originals": 140,
            "augmented": 700,
            "human_sources": 70,
            "human_augmented": 350,
            "synthetic_sources": 70,
            "synthetic_augmented": 350,
            "contract_valid_documents": 2520,
            "protected_files_checked": len(protocol["protected_hashes"]),
            "protected_changed": [],
            "source_changed": [],
            "model_training": False,
            "reference_inference_inputs": False,
            "data51_to70_all_five_profiles": True,
        },
    )
    print("Complete: " + str(OUT), flush=True)


if __name__ == "__main__":
    main()
