import csv
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import torch
from SketchPipeline.shape_authoring.dino_model import DinoDecoder, decoder_channels, prepare_tensors
from SketchPipeline.shape_authoring.decoder_refined import decode as refined_decode
from SketchPipeline.shape_authoring.corridor_geometry import decode as geometry_decode
from SketchPipeline.shape_authoring.contrast import normalize_ink
from SketchPipeline.perception.structural import suppress_grid
from SketchPipeline.shape_authoring.contract import validate_authoring
from Scripts.evaluate_augmented_shape import read, save, sha, scored, aggregate

OUT = ROOT / "Saved/ShapeFirst/all_data_training/v1"
KEYS = ["regions", "doors", "openings", "connections", "attached_doors"]


def load(path):
    state = torch.load(path, map_location="cpu", weights_only=True)
    model = DinoDecoder(state["width"])
    model.load_state_dict(state["state_dict"])
    return model.eval()


def decode(probability, native, working, entry):
    wm = entry["working_metadata"]
    nm = entry["native_metadata"]
    matrix = np.asarray(wm["original_to_working"]) @ np.asarray(nm["working_to_original"])
    probabilities = decoder_channels(
        np.stack([cv2.resize(c, (512, 512), interpolation=cv2.INTER_LINEAR) for c in probability])
    )
    doc, detail = refined_decode(
        native,
        probabilities,
        entry["source"],
        nm,
        working_gray=working,
        working_metadata=wm,
        evidence_to_working=matrix,
        region_threshold=0.5,
        region_policy="supported-corridors",
        opening_policy="corridor-passages",
        door_policy="observed-jambs",
        opening_alignment=True,
    )
    doc, geometry, _ = geometry_decode(
        native,
        probabilities,
        entry["source"],
        nm,
        working_metadata=wm,
        evidence_to_working=matrix,
        baseline_result=(doc, detail),
        opening_alignment=True,
    )
    assert not validate_authoring(doc)
    return (doc, geometry)


def summarize_rows(rows):
    return {
        arm: {
            cohort: {
                profile: aggregate(
                    [
                        r
                        for r in rows
                        if r["arm"] == arm
                        and (
                            cohort == "all"
                            or (cohort == "all_human" and r["origin"] == "human")
                            or (cohort == "audited_human70" and r["cohort"] in ("old50", "new20"))
                            or (r["cohort"] == cohort)
                        )
                        and (
                            profile == "all"
                            or (
                                profile == "augmented"
                                and r["profile"]
                                not in (
                                    "original",
                                    "ink",
                                    "pencil",
                                    "photo",
                                    "clean",
                                    "wavy",
                                    "grid",
                                    "stray",
                                )
                            )
                            or r["profile"] == profile
                        )
                    ]
                )
                for profile in [
                    "all",
                    "original",
                    "augmented",
                    "rotate",
                    "perspective",
                    "lighting",
                    "capture",
                    "combined",
                ]
            }
            for cohort in [
                "all",
                "all_human",
                "audited_human70",
                "old50",
                "new20",
                "synthetic",
                "addon_human",
                "addon_dense",
                "synthetic_replay",
                "previous_controls",
            ]
        }
        for arm in ["before", "after"]
    }


def main():
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    protocol = read(OUT / "protocol.json")
    candidate = read(OUT / "candidate.json")
    manifest = read(OUT / "cache/manifest.json")
    assert all((sha(ROOT / p) == h for p, h in protocol["source_hashes"].items()))
    assert sha(ROOT / candidate["checkpoint_path"]) == candidate["checkpoint_sha256"]
    models = {
        "before": load(ROOT / protocol["starting_checkpoint"]),
        "after": load(ROOT / candidate["checkpoint_path"]),
    }
    arrays = {
        n: np.load(OUT / "cache" / (n + ".npy"), mmap_mode="r") for n in ["features", "native"]
    }
    rows = []
    started = time.perf_counter()
    for i, entry in enumerate(manifest["records"]):
        record = entry["record"]
        native = np.array(arrays["native"][i])
        nm = entry["native_metadata"]
        working = cv2.imread(str(OUT / "cache/working" / f"{i}.png"), 0)
        feature = torch.from_numpy(np.array(arrays["features"][i : i + 1], dtype=np.float32))
        clean, _, _ = suppress_grid(native)
        bounds = nm.get("diagnostic_content_bounds_px")
        a, _ = normalize_ink(native, bounds)
        b, _ = normalize_ink(clean, bounds)
        _, ink, _ = prepare_tensors(a, b)
        ink = torch.from_numpy(ink[None])
        for arm, model in models.items():
            folder = OUT / "evaluation" / arm / record["id"]
            metric_path = folder / "metrics.json"
            if metric_path.exists():
                row = read(metric_path)
            else:
                tick = time.perf_counter()
                with torch.inference_mode():
                    probability = model(feature, ink).sigmoid()[0].numpy()
                document, detail = decode(probability, native, working, entry)
                save(folder / "authoring.json", document)
                metric = scored(
                    document, entry["reference"], entry["working_metadata"]["working_size_px"]
                )
                row = {
                    "sample_id": record["id"],
                    "source_id": record["source_id"],
                    "cohort": record["cohort"],
                    "origin": record["origin"],
                    "base_plan_id": record["parent"],
                    "profile": record["profile"],
                    "arm": arm,
                    "metrics": metric,
                    "status": "needs_attention",
                    "failure": None,
                    "elapsed_seconds": time.perf_counter() - tick,
                    "geometry_status": detail.get("status"),
                    "checkpoint_sha256": (
                        protocol["starting_sha256"]
                        if arm == "before"
                        else candidate["checkpoint_sha256"]
                    ),
                }
                save(metric_path, row)
            rows.append(row)
        if i % 20 == 0 or i == len(manifest["records"]) - 1:
            print(
                json.dumps(
                    {
                        "phase": "evaluate",
                        "completed": i + 1,
                        "total": len(manifest["records"]),
                        "seconds": round(time.perf_counter() - started, 1),
                        "sample": record["id"],
                    }
                ),
                flush=True,
            )
    summary = summarize_rows(rows)
    old = {
        r["sample_id"]: r
        for r in read(ROOT / "Saved/ShapeFirst/augmented_robustness/v2/report.json")["rows"]
    }
    parity = []
    for r in rows:
        if r["arm"] != "before" or r["sample_id"] not in old:
            continue
        equal = all((r["metrics"][k] == old[r["sample_id"]]["metrics"][k] for k in KEYS))
        parity.append({"sample_id": r["sample_id"], "all_five_metrics_equal": equal})
    save(
        OUT / "evaluation/report.json",
        {
            "summary": summary,
            "rows": rows,
            "training_scope": protocol["scope"],
            "all_images_used_in_training": True,
            "independent_test": False,
            "baseline_cached_vs_prior_full_entrypoint": parity,
            "backbone_feature_cache_dtype": "float32",
            "ink_inference_dtype": "float32",
            "candidate": candidate,
        },
    )
    with (OUT / "evaluation/metrics.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "arm",
                "cohort",
                "profile",
                "images",
                "metric",
                "TP",
                "predicted",
                "reference",
                "precision",
                "recall",
                "f1",
            ]
        )
        for arm, groups in summary.items():
            for group, profiles in groups.items():
                for profile, m in profiles.items():
                    for k in KEYS:
                        w.writerow(
                            [arm, group, profile, m["samples"], k]
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
    assert all((sha(ROOT / p) == h for p, h in protocol["protected_hashes"].items()))
    save(
        OUT / "evaluation/verification.json",
        {
            "cases": len(manifest["records"]),
            "arms": 2,
            "documents_schema_valid": len(rows),
            "active_model_unchanged": sha(ROOT / protocol["starting_checkpoint"])
            == protocol["starting_sha256"],
            "protected_files_unchanged": True,
            "baseline_parity_equal": sum((p["all_five_metrics_equal"] for p in parity)),
            "baseline_parity_checked": len(parity),
            "all_examples_in_training": True,
            "heldout_test": False,
        },
    )
    print("Evaluation complete", flush=True)


if __name__ == "__main__":
    main()
