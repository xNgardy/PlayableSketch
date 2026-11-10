import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time
import cv2
import numpy as np
from SketchPipeline.experiments.evaluate_v1 import MANIFEST, OUT, region_metrics
from SketchPipeline.perception.evaluate import greedy_pairs, polygon_iou
from SketchPipeline.perception.topology import build_topology
from SketchPipeline.preprocessing.prepare import prepare
from SketchPipeline.synthetic.augment import read, write


def worker(sid):
    cv2.setNumThreads(1)
    sample = next((s for s in read(MANIFEST)["samples"] if s["id"] == sid))
    working = read(OUT / "baseline" / sid / "working.json")
    if working.get("topology") is None:
        images, _ = prepare(MANIFEST.parent / sample["image_path"], max_side=1600)
        gray = images["gray"]
        enhanced = cv2.GaussianBlur(
            cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray), (3, 3), 0.7
        )
        ink = np.uint8(cv2.subtract(cv2.medianBlur(enhanced, 31), enhanced) > 12) * 255
        working["topology"] = build_topology(
            working["line_detectors"]["lsd"] + working["geometry"]["recovery_lines"]["lsd"],
            working["gaps"],
            gray.shape,
            working["geometry"]["dominant_rotation_degrees"],
            ink=ink,
        )
    side = read(MANIFEST.parent / sample["annotations_path"])
    metrics = region_metrics(working, side)
    topo = working["topology"]
    result = dict(
        id=sid,
        status="complete",
        regions=metrics,
        region_candidates=len(topo["regions"]),
        connections=len(topo["region_connectivity_graph"]["edges"]),
        connectivity_accuracy=None,
        note="Region IoU/count recovery; complete connectivity correctness not computed.",
    )
    result["connectivity"] = None
    if metrics is not None:
        mapping = {p["prediction_id"]: p["reference_id"] for p in metrics["matched_pairs"]}
        draft = read(
            (MANIFEST.parent / sample["annotations_path"]).parent / side["reference_draft_path"]
        )
        truth = Counter(
            (
                tuple(sorted((e["id"] for e in opening["connected_entities"])))
                for opening in draft["layout"]["openings"]
            )
        )
        predicted = Counter()
        for index, edge in enumerate(topo["region_connectivity_graph"]["edges"]):
            ids = edge.get("region_ids_by_side", edge.get("adjacent_region_ids", []))
            key = tuple(sorted((mapping.get(r, f"unmapped:{r}") for r in ids if r is not None)))
            if len(key) != 2:
                key = (f"unresolved:{index}",)
            predicted[key] += 1
        tp = sum((truth & predicted).values())
        p = sum(predicted.values())
        r = sum(truth.values())
        result["connectivity"] = dict(
            true_positive=tp,
            predicted=p,
            reference=r,
            precision=tp / p if p else None,
            recall=tp / r if r else None,
            f1=2 * tp / (p + r) if p + r else None,
            exact=predicted == truth,
            full_plan_exact=metrics["all_regions_exact"] and predicted == truth,
        )
        result["note"] = (
            "One-to-one regions at IoU .5, then multiset of opening-linked region pairs. Unresolved/unmapped predicted edges count as unmatched; duplicate doors retain multiplicity. No metric/playability acceptance."
        )
    write(OUT / "topology" / f"{sid}.json", result)


def run():
    samples = [s for s in read(MANIFEST)["samples"] if s["origin"] != "augmented"]
    for i, s in enumerate(samples, 1):
        sid = s["id"]
        dest = OUT / "topology" / f"{sid}.json"
        if dest.exists() and "connectivity" in read(dest):
            continue
        start = time.monotonic()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "SketchPipeline.experiments.topology_v1", "--worker", sid],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode:
                write(dest, dict(id=sid, status="failed", error=result.stderr[-2000:]))
        except subprocess.TimeoutExpired:
            write(dest, dict(id=sid, status="timeout", time_limit_seconds=20, regions=None))
        print(
            f"{i}/{len(samples)} {sid}: {read(dest)['status']} {time.monotonic() - start:.1f}s",
            flush=True,
        )
    reports = [read(OUT / "topology" / f"{s['id']}.json") for s in samples]
    write(
        OUT / "topology_report.json",
        dict(
            samples=reports,
            status_counts=dict(Counter((r["status"] for r in reports))),
            scope="120 originals. 20s isolated-process limit includes startup. Timeouts/failed cases remain explicit; no zero-error substitution. Pixel regions and opening-linked region pairs, not metric solving or gameplay.",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--worker")
    a = p.parse_args()
    worker(a.worker) if a.worker else run()
