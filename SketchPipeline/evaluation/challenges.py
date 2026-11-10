import argparse
from copy import deepcopy
import html
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .protocol import ROOT, read, sha, write


def generate(output):
    output = Path(output)
    manifest = output / "manifest.json"
    if manifest.exists():
        existing = read(manifest)
        for s in existing["samples"]:
            if sha(output / s["image_path"]) != s["image_sha256"]:
                raise ValueError("Challenge source changed")
        return existing
    output.mkdir(parents=True, exist_ok=True)
    samples = []
    source_manifest = ROOT / "Data/annotations/v1/manifest_all_50.json"
    for base in ("Data_3", "Data_41"):
        s = next((s for s in read(source_manifest)["samples"] if s["id"] == base))
        source = (source_manifest.parent / s["image_path"]).resolve()
        if sha(source) != s["image_sha256"]:
            raise ValueError("Challenge source mismatch")
        with Image.open(source) as image:
            original = image.convert("RGB")
        w, h = original.size
        for kind in ("blur", "shadow", "crop", "convention_violation"):
            image = original.copy()
            if kind == "blur":
                image = image.filter(ImageFilter.GaussianBlur(2.2))
            elif kind == "shadow":
                pixels = np.asarray(image, dtype=float)
                x = np.linspace(0, 1, w)
                factor = 0.35 + 0.65 * np.minimum(1, np.abs(x - 0.4) * 2.5)
                image = Image.fromarray(np.uint8(np.clip(pixels * factor[None, :, None], 0, 255)))
            elif kind == "crop":
                image = image.crop((round(w * 0.2), 0, w, h))
            else:
                draw = ImageDraw.Draw(image)
                draw.line(
                    [(int(0.2 * w), int(0.3 * h)), (int(0.7 * w), int(0.7 * h))],
                    fill="black",
                    width=5,
                )
            id = base + "_" + kind
            path = output / (id + ".png")
            image.save(path)
            samples.append(
                dict(
                    id=id,
                    base_plan_id=s["base_plan_id"],
                    source_id=base,
                    kind=kind,
                    image_path=path.name,
                    image_sha256=sha(path),
                    source_sha256=s["image_sha256"],
                    expected="needs_review_or_explicit_failure",
                    labels_unchanged=kind in {"blur", "shadow"},
                    split="development",
                    interpretation="Crop/convention challenge has no transferred accuracy ground truth; gate behavior only.",
                )
            )
    result = dict(
        schema_version="step13-challenges/1.0",
        samples=samples,
        scope="Eight fresh controlled degradation/convention probes from two previously seen human plans; no new writer or phone-capture claim.",
        config=dict(max_side=1600, geometry_profile="baseline", detector="lsd", timeout_seconds=45),
    )
    write(manifest, result)
    return result


def worker(output, id):
    import cv2
    from SketchPipeline.perception.ocr import RapidOCRAdapter
    from SketchPipeline.perception.run import predict, write_prediction
    from SketchPipeline.perception.evaluate import evaluate

    output = Path(output)
    spec = read(output / "manifest.json")
    s = next((s for s in spec["samples"] if s["id"] == id))
    image = output / s["image_path"]
    assert sha(image) == s["image_sha256"]
    cv2.setNumThreads(1)
    started = time.perf_counter()
    adapter = RapidOCRAdapter()
    loaded = time.perf_counter()
    result = predict(image, adapter, max_side=1600, collect_gap_diagnostics=False)
    folder = output / id
    write_prediction(folder, *result)
    observations, working, _, _ = result
    record = dict(
        id=id,
        status="inference_complete",
        automatic_state="needs_review",
        canonical_layout_written=False,
        model_initialization_seconds=loaded - started,
        inference_seconds=working["duration_seconds"],
        runtime=adapter.runtime,
        source_sha256=s["image_sha256"],
        metrics=None,
        specific_violation_detected=None,
        gate_passed=True,
    )
    if s["labels_unchanged"]:
        ref = read(ROOT / f"Data/annotations/v1/{s['source_id']}.observations.json")
        side = read(ROOT / f"Data/annotations/v1/{s['source_id']}.annotations.json")
        record["metrics"] = evaluate(observations, working, ref, side)
    write(output / (id + ".result.json"), record)


def run(output):
    output = Path(output).resolve()
    spec = generate(output)
    records = []
    reused = []
    for s in spec["samples"]:
        dest = output / (s["id"] + ".result.json")
        if dest.exists():
            reused.append(s["id"])
        if not dest.exists():
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "SketchPipeline.evaluation.challenges",
                        "--worker",
                        s["id"],
                        "--output",
                        str(output),
                    ],
                    timeout=spec["config"]["timeout_seconds"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    write(
                        dest,
                        dict(
                            id=s["id"],
                            status="failed",
                            automatic_state="failed",
                            metrics=None,
                            error=result.stderr[-1800:],
                            gate_passed=True,
                            canonical_layout_written=False,
                            inference_seconds=None,
                        ),
                    )
            except subprocess.TimeoutExpired:
                write(
                    dest,
                    dict(
                        id=s["id"],
                        status="timeout",
                        automatic_state="failed",
                        metrics=None,
                        gate_passed=True,
                        canonical_layout_written=False,
                        inference_seconds=None,
                    ),
                )
        r = read(dest)
        if r["status"] == "inference_complete" and r.get("source_sha256") != s["image_sha256"]:
            raise ValueError("Cached challenge source mismatch")
        records.append(r)
        print(s["id"] + ": " + r["status"], flush=True)
    write(
        output / "report.json",
        dict(
            protocol=spec,
            samples=records,
            reused_prediction_ids=reused,
            execution="Existing hash-matched predictions explicitly reused when present; otherwise fresh bounded inference.",
            note="Review-required state is the product safety contract, not successful detection of the particular crop/convention defect. Failed inference is retained.",
        ),
    )
    cards = []
    for s, r in zip(spec["samples"], records):
        preview = f"{s['id']}/prediction_original.png"
        cards.append(
            f"<article><h2>{s['id']}</h2><img src='{s['image_path']}'><p>{html.escape(r['status'])}; {html.escape(r['automatic_state'])}</p><a href='{s['id']}.result.json'>Result/evidence</a> · <a href='{preview}'>Prediction overlay (if complete)</a></article>"
        )
    (output / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Fresh robustness probes</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;background:#eee}article{background:white;padding:20px;margin:20px 0}img{max-width:100%;max-height:500px}</style><h1>Fresh capture/convention probes</h1><p>Previously seen plans, baseline adapter. No metric export or user acceptance. Crop/diagonal probes have no accuracy ground truth.</p>"
        + "".join(cards)
    )
    return records


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--worker")
    args = p.parse_args()
    worker(args.output, args.worker) if args.worker else run(args.output)
