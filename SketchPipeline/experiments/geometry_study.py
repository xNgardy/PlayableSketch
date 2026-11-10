import argparse
from collections import Counter
import copy
import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
from SketchPipeline.experiments.evaluate_v1 import (
    MANIFEST,
    OUT as BASE,
    freeze,
    region_metrics,
    enrich,
)
from SketchPipeline.perception.evaluate import evaluate, aggregate
from SketchPipeline.perception.geometry import gap_evidence
from SketchPipeline.perception.run import topology_preview
from SketchPipeline.perception.structural import structural_evidence, structural_lines, CONFIG
from SketchPipeline.perception.topology import build_topology
from SketchPipeline.preprocessing.prepare import prepare, project
from SketchPipeline.synthetic.augment import ROOT, read, write, sha
from SketchPipeline.validation.validate import validate_document

OUT = ROOT / "Saved/GeometryStudy/v1"
ARMS = ["baseline", "grid", "structural", "vlm_only", "hybrid"]
MODEL = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
REVISION = "46d4cf06a06ffc1a766c214174f9cbed2f45bcab"


def samples():
    split = freeze()
    return [
        s
        for s in read(MANIFEST)["samples"]
        if s["origin"] != "augmented" and split["group_split"][s["base_plan_id"]] == "validation"
    ]


def protocol():
    path = OUT / "protocol.json"
    code_paths = [
        "SketchPipeline/perception/structural.py",
        "SketchPipeline/experiments/geometry_study.py",
        "SketchPipeline/experiments/geometry_vlm.py",
    ]
    value = dict(
        version="geometry-pilot/1.0",
        samples=[s["id"] for s in samples()],
        sample_hashes={s["id"]: s["image_sha256"] for s in samples()},
        arms=ARMS,
        structural_config=CONFIG,
        model=MODEL,
        revision=REVISION,
        max_side=1600,
        vlm_max_side=1008,
        temperature=0,
        max_tokens=1800,
        wall_gate_radius_px=12,
        wall_gate_min_support=0.35,
        timing="Wall-clock geometry/VLM + topology, excludes cached OCR and model initialization. Cold model initialization recorded separately.",
        scope="19 validation originals, 11 parent groups. Retrospective development pilot; not a test or new-writer benchmark.",
        human_correction_time_seconds=None,
        code_hashes={p: sha(ROOT / p) for p in code_paths if (ROOT / p).exists()},
    )
    if path.exists():
        previous = read(path)
        if previous != value:
            raise ValueError(
                "Protocol/code changed after freeze; use a new experiment directory/version."
            )
    else:
        write(path, value)
    return value


def finish_prediction(sample, arm, working, observations, images, masks, started):
    directory = OUT / arm / sample["id"]
    inverse = np.asarray(working["preprocessing"]["working_to_original"])

    def original(points):
        q = project(points, inverse)
        w, h = working["preprocessing"]["original_size_px"]
        return np.clip(q, [0, 0], [w - 1, h - 1]).tolist()

    for lines in list(working["line_detectors"].values()) + list(
        working["geometry"]["recovery_lines"].values()
    ):
        for line in lines:
            line["start_original"], line["end_original"] = original([line["start"], line["end"]])
    opening_observations = []
    for gap in working["gaps"]:
        gap["start_original"], gap["end_original"] = original([gap["start"], gap["end"]])
        if gap["role"] != "opening_candidate":
            continue
        points = np.asarray([gap["start"], gap["end"]])
        lo, hi = (points.min(axis=0) - 10, points.max(axis=0) + 10)
        oid = f"o{len(opening_observations) + 1:03d}"
        gap["observation_id"] = oid
        opening_observations.append(
            dict(
                id=oid,
                polygon_px=original(
                    [[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]]
                ),
                score=None,
            )
        )
    observations["opening_candidates"] = opening_observations
    observations["lines"] = [
        dict(id=l["id"], start_px=l["start_original"], end_px=l["end_original"], score=None)
        for l in working["line_detectors"]["lsd"]
    ]
    observations["revision_id"] = "geometry-study-" + arm
    check = validate_document(observations)
    if not check["schema_valid"] or check["issues"]:
        raise ValueError(str(check["issues"]))
    working["experiment_arm"] = arm
    working["duration_seconds"] = time.perf_counter() - started
    write(directory / "observations.json", observations)
    write(directory / "working.json", working)
    write(
        directory / "prediction_status.json",
        dict(status="complete", geometry_seconds=working["duration_seconds"]),
    )
    preview = topology_preview(images["color"], working["topology"])
    draw = ImageDraw.Draw(preview)
    for gap in working["gaps"]:
        if gap["role"] == "opening_candidate":
            draw.line([tuple(gap["start"]), tuple(gap["end"])], fill=(255, 0, 0), width=5)
    preview.thumbnail((1100, 1100))
    preview.save(directory / "preview.jpg")
    for name in ["geometry_input", "grid_suppression"]:
        if name in masks:
            Image.fromarray(masks[name]).save(directory / (name + ".png"))


def classical(sample, arm):
    cv2.setNumThreads(1)
    cached = read(BASE / "baseline" / sample["id"] / "working.json")
    observations = read(BASE / "baseline" / sample["id"] / "observations.json")
    image_path = (MANIFEST.parent / sample["image_path"]).resolve()
    assert sha(image_path) == sample["image_sha256"]
    images, preprocessing = prepare(image_path, max_side=1600)
    started = time.perf_counter()
    detectors, geometry, masks = structural_evidence(
        images["gray"], [f["polygon_working"] for f in cached["fragments"]], arm
    )
    primary = structural_lines(detectors["lsd"])
    recovery = structural_lines(geometry["recovery_lines"]["lsd"])
    gaps = gap_evidence(
        primary,
        cached["text_groups"],
        images["gray"].shape,
        recovery_lines=recovery,
        ink=masks["wall_ink"],
        diagnostics=False,
    )
    topology = build_topology(
        primary + recovery,
        gaps,
        images["gray"].shape,
        geometry["dominant_rotation_degrees"],
        ink=masks["unmasked_wall_ink"],
    )
    working = dict(
        cached,
        preprocessing=preprocessing,
        geometry=geometry,
        line_detectors=detectors,
        gaps=gaps,
        topology=topology,
    )
    finish_prediction(sample, arm, working, observations, images, masks, started)


def connectivity(working, sidecar, region_report, annotation_path):
    if region_report is None:
        return None
    mapping = {p["prediction_id"]: p["reference_id"] for p in region_report["matched_pairs"]}
    draft = read(annotation_path.parent / sidecar["reference_draft_path"])
    truth = Counter(
        (
            tuple(sorted((e["id"] for e in op["connected_entities"])))
            for op in draft["layout"]["openings"]
        )
    )
    predicted = Counter()
    for i, edge in enumerate(working["topology"]["region_connectivity_graph"]["edges"]):
        ids = edge.get("region_ids_by_side", edge.get("adjacent_region_ids", []))
        key = tuple(sorted((mapping.get(r, "unmapped:" + r) for r in ids if r is not None)))
        predicted[key if len(key) == 2 else ("unresolved:" + str(i),)] += 1
    tp, p, r = (sum((truth & predicted).values()), sum(predicted.values()), sum(truth.values()))
    return dict(
        true_positive=tp,
        predicted=p,
        reference=r,
        precision=tp / p if p else None,
        recall=tp / r if r else None,
        f1=2 * tp / (p + r) if p + r else None,
        full_plan_exact=region_report["all_regions_exact"] and predicted == truth,
    )


def score(sample, arm):
    directory = OUT / arm / sample["id"]
    working = read(directory / "working.json")
    obs = read(directory / "observations.json")
    reference = read(MANIFEST.parent / sample["observations_path"])
    annotation_path = (MANIFEST.parent / sample["annotations_path"]).resolve()
    side = read(annotation_path)
    m = evaluate(obs, working, reference, side)
    m["regions"] = region_metrics(working, side)
    m["connectivity"] = connectivity(working, side, m["regions"], annotation_path)
    for pair in m["openings"]["matched_pairs"]:
        p = next((x for x in working["gaps"] if x["id"] == pair["prediction_id"]))
        g = next((x for x in side["gaps"] if x["id"] == pair["reference_id"]))
        a = np.array([p["start_original"], p["end_original"]])
        b = np.array([g["start_px"], g["end_px"]])
        pair["max_endpoint_error_px"] = float(
            min(np.linalg.norm(a - b, axis=1).max(), np.linalg.norm(a - b[::-1], axis=1).max())
        )
    m["correction_proxy"] = dict(
        false_openings=m["openings"]["predicted"] - m["openings"]["true_positive"],
        missed_openings=m["openings"]["reference"] - m["openings"]["true_positive"],
    )
    native = working.get("vlm_native_regions")
    if native is not None:
        auxiliary = copy.deepcopy(working)
        auxiliary["topology"] = dict(rotation_degrees_removed=0, regions=native)
        m["vlm_native_regions"] = region_metrics(auxiliary, side)
    write(
        directory / "metrics.json",
        dict(
            id=sample["id"],
            arm=arm,
            metrics=m,
            geometry_seconds=working["duration_seconds"],
            status="complete",
            origin=sample["origin"],
            base_plan_id=sample["base_plan_id"],
        ),
    )


def run_classical():
    protocol()
    for s in samples():
        for arm in ARMS[:3]:
            directory = OUT / arm / s["id"]
            if (directory / "metrics.json").exists():
                continue
            start = time.monotonic()
            try:
                p = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "SketchPipeline.experiments.geometry_study",
                        "--worker",
                        s["id"],
                        "--arm",
                        arm,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if p.returncode:
                    write(directory / "failure.json", dict(status="failed", error=p.stderr[-2500:]))
            except subprocess.TimeoutExpired:
                write(directory / "failure.json", dict(status="timeout", time_limit_seconds=120))
            print(
                s["id"],
                arm,
                "complete" if (directory / "metrics.json").exists() else "failed",
                f"{time.monotonic() - start:.1f}s",
                flush=True,
            )


def summary():
    reports = {}
    for arm in ARMS:
        reports[arm] = {}
        for cohort in ["all", "human", "synthetic"]:
            selected = [s for s in samples() if cohort == "all" or s["origin"] == cohort]
            records = [
                read(OUT / arm / s["id"] / "metrics.json")
                for s in selected
                if (OUT / arm / s["id"] / "metrics.json").exists()
            ]
            if not records:
                reports[arm][cohort] = dict(expected=len(selected), complete=0)
                continue
            result = enrich(aggregate(records))
            times = [x["geometry_seconds"] for x in records]
            topology = [
                x["metrics"]["connectivity"]
                for x in records
                if x["metrics"]["connectivity"] is not None
            ]
            regions = [
                x["metrics"]["regions"] for x in records if x["metrics"]["regions"] is not None
            ]
            result.update(
                expected=len(selected),
                complete=sum((x["status"] == "complete" for x in records)),
                evaluated=len(records),
                failed=sum((x["status"] != "complete" for x in records)),
                missing=len(selected) - len(records),
                inference_seconds=dict(
                    p50=float(np.median(times)), p95=float(np.percentile(times, 95))
                ),
                exact_topology=dict(
                    correct=sum((x["full_plan_exact"] for x in topology)), scorable=len(topology)
                ),
                correction_time_seconds=None,
                opening_correction_proxy=sum(
                    (
                        x["metrics"]["correction_proxy"]["false_openings"]
                        + x["metrics"]["correction_proxy"]["missed_openings"]
                        for x in records
                    )
                ),
            )
            for name, metrics in [("regions", regions), ("connections", topology)]:
                tp = sum((x["true_positive"] for x in metrics))
                p = sum((x["predicted"] for x in metrics))
                r = sum((x["reference"] for x in metrics))
                result[name] = dict(
                    true_positive=tp,
                    predicted=p,
                    reference=r,
                    f1=2 * tp / (p + r) if p + r else None,
                )
            errors = [
                p["max_endpoint_error_px"]
                for x in records
                for p in x["metrics"]["openings"]["matched_pairs"]
            ]
            result["matched_endpoint_error_px_p50"] = float(np.median(errors)) if errors else None
            reports[arm][cohort] = result
    write(
        OUT / "report.json",
        dict(
            protocol=read(OUT / "protocol.json"),
            results=reports,
            warning="Completed-only metrics until all expected records exist. Failures/missing must be disclosed; no final selection from incomplete arms. Correction proxy is not measured reviewer time.",
        ),
    )
    return reports


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--worker")
    p.add_argument("--arm", choices=ARMS)
    p.add_argument("--summary", action="store_true")
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    if a.worker:
        s = next((x for x in samples() if x["id"] == a.worker))
        classical(s, a.arm)
        score(s, a.arm)
    elif a.summary:
        print(json.dumps(summary(), indent=2))
    elif a.freeze:
        print(json.dumps(protocol(), indent=2))
    else:
        run_classical()
        summary()
