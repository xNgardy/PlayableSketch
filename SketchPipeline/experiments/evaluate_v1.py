import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import random
import time
import numpy as np
from SketchPipeline.perception.ocr import RapidOCRAdapter
from SketchPipeline.perception.run import predict
from SketchPipeline.perception.evaluate import (
    aggregate,
    evaluate,
    greedy_pairs,
    object_counts,
    polygon_iou,
)
from SketchPipeline.synthetic.augment import ROOT, read, sha, write

OUT = ROOT / "Saved/Evaluation/v1"
MANIFEST = ROOT / "Data/augmented/v1/manifest_with_originals.json"


def f1(p, r):
    return None if p is None or r is None else 2 * p * r / (p + r) if p + r else 0.0


def enrich(report):
    for key in ["text", "openings"]:
        report[key]["f1"] = f1(report[key]["precision"], report[key]["recall"])
    for method in report["walls"].values():
        method["coverage_f1"] = f1(method["precision"]["coverage"], method["recall"]["coverage"])
    return report


def freeze():
    target = OUT / "split.json"
    if target.exists():
        result = read(target)
        assert result["manifest_sha256"] == sha(MANIFEST), "Changed experiment input"
        return result
    samples = read(MANIFEST)["samples"]
    assignment = {}
    rng = random.Random(20261017)
    for batch in range(5):
        groups = [f"plan_{i:02d}" for i in range(batch * 10 + 1, batch * 10 + 11)]
        groups = [
            s["base_plan_id"]
            for s in samples
            if s["id"] in {f"Data_{i}" for i in range(batch * 10 + 1, batch * 10 + 11)}
        ]
        rng.shuffle(groups)
        for i, g in enumerate(groups):
            assignment[g] = "train" if i < 7 else "validation" if i < 8 else "test"
    families = {}
    for name in ["handdrawn_pilot", "extra_plans"]:
        for plan in read(ROOT / "Data/synthetic/v1" / name / "plans.json")["plans"]:
            family = plan["family"]
            families[plan["id"]] = family
            assignment[plan["id"]] = (
                "train"
                if family in [0, 1, 2, 5, 6, 8]
                else "validation" if family in [4, 9] else "test"
            )
    result = dict(
        schema_version="playablesketch-experiment-split/1.0",
        seed=20261017,
        manifest_sha256=sha(MANIFEST),
        group_split=assignment,
        synthetic_geometry_families=families,
        groups=dict(Counter(assignment.values())),
        images=dict(Counter((assignment[s["base_plan_id"]] for s in samples))),
        policy="Human acquisition-batch stratified plan groups; synthetic entire geometry families grouped. All derivatives inherit parent. Development experiment, not independent unseen-writer holdout.",
        source_hashes={s["id"]: s["image_sha256"] for s in samples},
    )
    write(target, result)
    return result


def region_metrics(working, sidecar):
    topo = working["topology"]
    center = np.array(working["preprocessing"]["working_size_px"]) / 2
    angle = np.radians(topo["rotation_degrees_removed"])
    c, s = (np.cos(angle), np.sin(angle))
    rot = np.array([[c, -s], [s, c]])
    inv = np.array(working["preprocessing"]["working_to_original"])
    predictions = []
    for region in topo["regions"]:
        pts = (np.array(region["corners_px_rotated"]) - center) @ rot.T + center
        q = np.c_[pts, np.ones(len(pts))] @ inv.T
        predictions.append((q[:, :2] / q[:, 2:]).tolist())
    truth = [r["polygon_px"] for r in sidecar.get("regions", [])]
    if not truth:
        return None
    pairs = greedy_pairs(predictions, truth, polygon_iou, 0.5)
    result = object_counts(predictions, truth, pairs)
    result["f1"] = f1(result["precision"], result["recall"])
    result["all_regions_exact"] = len(pairs) == len(predictions) == len(truth)
    result["matched_pairs"] = [
        dict(
            prediction_id=topo["regions"][i]["id"],
            reference_id=sidecar["regions"][j]["region_id"],
            iou=score,
        )
        for i, j, score in pairs
    ]
    result["note"] = (
        "Polygon IoU >= .5; counts measure region recovery, not connectivity correctness."
    )
    return result


def run(shard=0, shards=1):
    import cv2

    cv2.setNumThreads(1)
    split = freeze()
    samples = read(MANIFEST)["samples"]
    adapter = RapidOCRAdapter()
    write(OUT / "runtime.json", adapter.runtime)
    for index, sample in enumerate(samples, 1):
        if (index - 1) % shards != shard:
            continue
        destination = OUT / "baseline" / sample["id"]
        done = destination / "metrics.json"
        if done.exists():
            continue
        path = (MANIFEST.parent / sample["image_path"]).resolve()
        assert sha(path) == sample["image_sha256"]
        t = time.monotonic()
        observations, working, images, masks = predict(
            path, adapter, compute_topology=False, collect_gap_diagnostics=False
        )
        reference = read(MANIFEST.parent / sample["observations_path"])
        sidecar = read(MANIFEST.parent / sample["annotations_path"])
        metrics = evaluate(observations, working, reference, sidecar)
        metrics["regions"] = None
        write(destination / "observations.json", observations)
        write(destination / "working.json", working)
        write(
            done,
            dict(
                id=sample["id"],
                metrics=metrics,
                duration_seconds=time.monotonic() - t,
                image_sha256=sample["image_sha256"],
                experiment_split=split["group_split"][sample["base_plan_id"]],
            ),
        )
        print(
            f"{index}/{len(samples)} {sample['id']}: numeric {metrics['text']['numeric_exact_correct']}/{metrics['text']['reference']}; openings {metrics['openings']['true_positive']}/{metrics['openings']['reference']}; {time.monotonic() - t:.1f}s",
            flush=True,
        )
    if len(list((OUT / "baseline").glob("*/metrics.json"))) == len(samples):
        summarize()


def summarize():
    split = freeze()
    samples = read(MANIFEST)["samples"]
    groups = {}
    predicates = {
        "human_original": lambda s: s["origin"] == "human",
        "synthetic_original": lambda s: s["origin"] == "synthetic",
        "human_augmented": lambda s: s.get("source_origin") == "human",
        "synthetic_augmented": lambda s: s.get("source_origin") == "synthetic",
    }
    for stage in ["all", "train", "validation", "test"]:
        for name, predicate in predicates.items():
            selected = [
                s
                for s in samples
                if predicate(s)
                and (stage == "all" or split["group_split"][s["base_plan_id"]] == stage)
            ]
            records = [
                read(OUT / "baseline" / s["id"] / "metrics.json")
                for s in selected
                if (OUT / "baseline" / s["id"] / "metrics.json").exists()
            ]
            if not records:
                continue
            result = enrich(aggregate(records))
            result["images"] = len(records)
            result["expected_images"] = len(selected)
            result["topology"] = dict(
                computed_separately=True,
                report="topology_report.json",
                scope="120 original sources; not augmentation variants",
            )
            groups[f"{stage}/{name}"] = result
    report = dict(
        split=split,
        baseline=groups,
        policy="Development evaluation. Fixed existing match tolerances; never tune on test. Region metrics are not connectivity or metric reconstruction.",
        completed_images=len(list((OUT / "baseline").glob("*/metrics.json"))),
        expected_images=len(samples),
        execution=dict(
            max_side=1600,
            topology_computed_separately=True,
            rejected_gap_diagnostics_omitted=True,
            unchanged_match_policy=True,
            original_reference_predictions_equivalence="final_acceleration_equivalence.json; grid_acceleration_equivalence.json",
        ),
    )
    write(OUT / "baseline_report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    if args.freeze:
        print(json.dumps(freeze(), indent=2))
    elif args.summary:
        print(json.dumps(summarize(), indent=2))
    else:
        run(args.shard, args.shards)
