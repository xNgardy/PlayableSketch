import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import numpy as np
from PIL import Image, ImageDraw
from SketchPipeline.preprocessing.prepare import InputError, prepare, project, overlay
from SketchPipeline.validation.validate import load_json, validate_document
from .geometry import line_evidence, gap_evidence
from .ocr import RapidOCRAdapter, ocr_evidence, rectify_crop
from .evaluate import evaluate, aggregate
from .topology import build_topology

VERSION = "playablesketch-perception/1.2"
DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "Data/annotations/v1/manifest.json"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def topology_preview(image, topology):
    canvas = Image.fromarray(np.asarray(image).astype(np.uint8)).convert("RGB")
    draw = ImageDraw.Draw(canvas, "RGBA")
    height, width = np.asarray(image).shape[:2]
    center = np.asarray([width / 2, height / 2], float)
    angle = np.radians(topology["rotation_degrees_removed"])

    def to_working(point):
        x, y = np.asarray(point, float) - center
        return (
            float(center[0] + np.cos(angle) * x - np.sin(angle) * y),
            float(center[1] + np.sin(angle) * x + np.cos(angle) * y),
        )

    for region in topology["regions"]:
        corners = [to_working(point) for point in region["corners_px_rotated"]]
        color = (
            (180, 55, 55)
            if not region["rectangle_candidate"]
            else (175, 115, 20) if region.get("unresolved_opening_ids") else (120, 70, 180)
        )
        draw.polygon(corners, fill=(*color, 32), outline=(*color, 230), width=3)
        if corners:
            x, y = corners[0]
            draw.text((x + 4, y + 4), region["id"], fill=(*color, 255))
    for edge in topology["wall_graph"]["edges"]:
        color = (0, 130, 145, 230) if edge["kind"] == "physical_wall" else (235, 125, 20, 255)
        draw.line([to_working(edge["a"]), to_working(edge["b"])], fill=color, width=4)
    return canvas


def predict(
    path,
    adapter,
    *,
    max_side=1600,
    detector="lsd",
    compute_topology=True,
    collect_gap_diagnostics=True,
    geometry_profile="baseline",
    progress=None,
):
    if detector not in ("hough", "lsd"):
        raise InputError("Choose hough or lsd.")
    if geometry_profile not in ("baseline", "grid", "structural"):
        raise InputError("Choose baseline, grid or structural geometry profile.")
    started = time.perf_counter()
    if progress:
        progress("preprocess")
    images, preprocessing = prepare(path, max_side=max_side)
    if progress:
        progress("ocr")
    fragments, texts = ocr_evidence(images["color"], adapter)
    inverse = np.asarray(preprocessing["working_to_original"])
    forward = np.asarray(preprocessing["original_to_working"])
    width, height = preprocessing["original_size_px"]

    def original(points):
        result = project(points, inverse)
        result[:, 0] = np.clip(result[:, 0], 0, width - 1)
        result[:, 1] = np.clip(result[:, 1], 0, height - 1)
        return result.tolist()

    issues = []
    for i, text in enumerate(texts, 1):
        text["id"] = f"t{i:03d}"
        text["polygon_original"] = original(text["polygon_working"])
        if code := text["chosen"]["parsed"]["issue"]:
            issues.append(
                {
                    "code": code,
                    "severity": "warning",
                    "element_ids": [text["id"]],
                    "message": "Unreviewed OCR evidence: " + text["chosen"]["raw_text"],
                }
            )
    polygons = [f["polygon_working"] for f in fragments]
    if progress:
        progress("walls")
    if geometry_profile == "baseline":
        detectors, geometry, masks = line_evidence(images["gray"], polygons)
        primary_lines = detectors[detector]
        recovery_lines = geometry["recovery_lines"][detector]
    else:
        from .structural import structural_evidence, structural_lines

        detectors, geometry, masks = structural_evidence(images["gray"], polygons, geometry_profile)
        primary_lines = structural_lines(detectors[detector])
        recovery_lines = structural_lines(geometry["recovery_lines"][detector])
    from .openings import CONFIG as OPENING_CONFIG

    geometry["opening_config"] = OPENING_CONFIG
    gaps = gap_evidence(
        primary_lines,
        texts,
        images["gray"].shape,
        recovery_lines=recovery_lines,
        ink=masks["wall_ink"],
        diagnostics=collect_gap_diagnostics,
    )
    if progress:
        progress("topology")
    topology = (
        build_topology(
            list(primary_lines) + list(recovery_lines),
            gaps,
            images["gray"].shape,
            geometry["dominant_rotation_degrees"],
            ink=masks["unmasked_wall_ink"],
        )
        if compute_topology
        else None
    )
    for lines in list(detectors.values()) + list(geometry["recovery_lines"].values()):
        for line in lines:
            line["start_original"], line["end_original"] = original([line["start"], line["end"]])
    opening_observations = []
    for gap in gaps:
        gap["start_original"], gap["end_original"] = original([gap["start"], gap["end"]])
        if gap["role"] == "opening_candidate":
            points = np.asarray([gap["start"], gap["end"]])
            lo = points.min(axis=0) - max(5, max_side * 0.006)
            hi = points.max(axis=0) + max(5, max_side * 0.006)
            polygon = original([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
            oid = f"o{len(opening_observations) + 1:03d}"
            gap["observation_id"] = oid
            opening_observations.append({"id": oid, "polygon_px": polygon, "score": None})
    for fragment in fragments:
        fragment["polygon_original"] = original(fragment["polygon_working"])
        for reading in fragment["readings"]:
            reading["original_to_crop"] = (
                np.asarray(reading["working_to_crop"]) @ forward
            ).tolist()
            reading["crop_to_original"] = (
                inverse @ np.asarray(reading["crop_to_working"])
            ).tolist()
    config_spec = {
        "max_side": max_side,
        "detector": detector,
        "ocr": adapter.runtime,
        "geometry": geometry["config"],
        "openings": geometry["opening_config"],
        "topology": topology["config"] if topology is not None else None,
    }
    if geometry_profile != "baseline":
        config_spec["structural_experiment"] = geometry["structural_experiment"]
    config_hash = hashlib.sha256(json.dumps(config_spec, sort_keys=True).encode()).hexdigest()[:12]
    observations = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": "prediction-" + preprocessing["source_sha256"][:16],
        "revision_id": "perception-" + config_hash,
        "source": {
            "image_path": str(Path(path).resolve()),
            "image_sha256": preprocessing["source_sha256"],
            "legacy_draft_path": None,
        },
        "units": "px",
        "coordinate_system": "u_right_v_down",
        "frame": {
            "id": "original",
            "width_px": width,
            "height_px": height,
            "original_to_frame": np.eye(3).tolist(),
        },
        "region_annotation_status": "partial",
        "texts": [
            {
                "id": t["id"],
                "raw_text": t["chosen"]["raw_text"] or "[unreadable]",
                "polygon_px": t["polygon_original"],
                "parsed_value_cm": t["chosen"]["parsed"]["value_cm"],
                "score": t["chosen"]["score"],
                "method": "ocr",
            }
            for t in texts
        ],
        "lines": [
            {
                "id": segment["id"],
                "start_px": segment["start_original"],
                "end_px": segment["end_original"],
                "score": None,
            }
            for segment in detectors[detector]
        ],
        "opening_candidates": opening_observations,
        "issues": issues,
        "notes": [
            "Automated unreviewed evidence only. Numeric candidates are not confirmed dimensions.",
            "Original encoded frame; zero-based pixel centers. Roles/alternatives/crop transforms are in working.json.",
            "No cm inference from pixels. Unreviewed topology hypotheses are in topology.json; no manual reference substitution.",
        ],
    }
    if not texts:
        observations["issues"].append(
            {
                "code": "SKETCH_TEXT_NOT_DETECTED",
                "severity": "warning",
                "element_ids": [],
                "message": "OCR detector found no text regions; review the original image.",
            }
        )
    observations["issues"].append(
        {
            "code": "SKETCH_PERCEPTION_REVIEW_REQUIRED",
            "severity": "warning",
            "element_ids": [],
            "message": "All line roles, OCR readings and gap interpretations require downstream review.",
        }
    )
    checked = validate_document(observations)
    if not checked["schema_valid"] or checked["issues"]:
        raise InputError(f"Invalid prediction observation: {checked['issues']}")
    working = {
        "schema_version": VERSION,
        "primary_detector": detector,
        "preprocessing": preprocessing,
        "ocr_runtime": adapter.runtime,
        "text_detection": getattr(adapter, "detection_debug", None),
        "fragments": fragments,
        "text_groups": texts,
        "geometry": geometry,
        "line_detectors": detectors,
        "gaps": gaps,
        "topology": topology,
        "duration_seconds": time.perf_counter() - started,
    }
    return (observations, working, images, masks)


def write_prediction(directory, observations, working, images, masks):
    directory.mkdir()
    observations["source"]["image_path"] = os.path.relpath(
        observations["source"]["image_path"], directory
    )
    write_json(directory / "observations.json", observations)
    write_json(directory / "working.json", working)
    if "topology" in working:
        write_json(directory / "topology.json", working["topology"])
        topology_preview(images["color"], working["topology"]).save(
            directory / "topology_review.png"
        )
    overlay(images["original"], observations, np.eye(3)).save(directory / "prediction_original.png")
    overlay(images["color"], observations, working["preprocessing"]["original_to_working"]).save(
        directory / "prediction_working.png"
    )
    for name, img in masks.items():
        Image.fromarray(img).save(directory / f"{name}.png")
    crop_dir = directory / "crops"
    crop_dir.mkdir()
    for f in working["fragments"]:
        crop, _ = rectify_crop(images["color"], f["polygon_working"])
        for k in range(4):
            Image.fromarray(np.rot90(crop, k)).save(crop_dir / f"{f['id']}-r{k * 90}.png")
    for method, lines in working["line_detectors"].items():
        canvas = Image.fromarray(images["original"])
        draw = ImageDraw.Draw(canvas)
        for line in lines:
            color = "#008890" if line["role"] == "wall_candidate" else "#b08000"
            draw.line(
                [tuple(line["start_original"]), tuple(line["end_original"])], fill=color, width=3
            )
        canvas.save(directory / f"{method}_lines.png")


def run_single(image, output, adapter, **options):
    output = Path(output)
    if output.exists():
        raise InputError("Output already exists; choose a new run directory.")
    result = predict(image, adapter, **options)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".perception-", dir=output.parent))
    try:
        write_prediction(staging / "sample", *result)
        result[0]["source"]["image_path"] = os.path.relpath(Path(image).resolve(), output.resolve())
        write_json(staging / "sample" / "observations.json", result[0])
        os.rename(staging / "sample", output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def run_dataset(manifest_path, output, adapter, **options):
    manifest_path = Path(manifest_path).resolve()
    manifest = load_json(manifest_path)
    output = Path(output)
    if output.exists():
        raise InputError("Output already exists; choose a new run directory.")
    if manifest["schema_version"] != "playablesketch-dataset/1.0":
        raise InputError("Unsupported manifest.")
    sample_ids = [s["id"] for s in manifest["samples"]]
    if (
        not sample_ids
        or len(set(sample_ids)) != len(sample_ids)
        or any((not re.fullmatch("[A-Za-z][A-Za-z0-9_-]{0,127}", i) for i in sample_ids))
    ):
        raise InputError("Invalid dataset sample IDs.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".perception-", dir=output.parent))
    try:
        report = {
            "schema_version": VERSION,
            "split": "development",
            "ocr_runtime": adapter.runtime,
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "samples": [],
            "status": "complete",
            "training_performed": False,
            "evaluation_note": "Manual labels are loaded after predictions. No oracle crops or metric drafts enter the predictor.",
        }
        for sample in manifest["samples"]:
            image = (manifest_path.parent / sample["image_path"]).resolve()
            if hashlib.sha256(image.read_bytes()).hexdigest() != sample["image_sha256"]:
                raise InputError(f"{sample['id']}: source hash mismatch.")
            result = predict(image, adapter, **options)
            observations, working, images, masks = result
            reference = load_json(manifest_path.parent / sample["observations_path"])
            sidecar = load_json(manifest_path.parent / sample["annotations_path"])
            if reference["source"]["image_sha256"] != observations["source"]["image_sha256"]:
                raise InputError("Evaluation source mismatch.")
            metrics = evaluate(observations, working, reference, sidecar)
            dest = staging / sample["id"]
            write_prediction(dest, *result)
            observations["source"]["image_path"] = os.path.relpath(
                image, (output / sample["id"]).resolve()
            )
            write_json(dest / "observations.json", observations)
            write_json(dest / "metrics.json", metrics)
            overlay(images["original"], reference, np.eye(3)).save(dest / "reference.png")
            a = Image.open(dest / "reference.png")
            b = Image.open(dest / "prediction_original.png")
            for im in [a, b]:
                im.thumbnail((1000, 800))
            comparison = Image.new("RGB", (a.width + b.width, max(a.height, b.height)), "white")
            comparison.paste(a, (0, 0))
            comparison.paste(b, (a.width, 0))
            comparison.save(dest / "comparison.png")
            report["samples"].append(
                {
                    "id": sample["id"],
                    "metrics": metrics,
                    "topology": {
                        "bounded_faces": working["topology"]["polygonization"]["bounded_faces"],
                        "regions": len(working["topology"]["regions"]),
                        "ambiguous_regions": sum(
                            (
                                bool(region.get("unresolved_opening_ids"))
                                for region in working["topology"]["regions"]
                            )
                        ),
                        "corridor_hypotheses": len(working["topology"]["corridor_hypotheses"]),
                        "connectivity_edges": len(
                            working["topology"]["region_connectivity_graph"]["edges"]
                        ),
                        "issues": len(working["topology"]["issues"]),
                    },
                    "duration_seconds": working["duration_seconds"],
                }
            )
            print(
                f"{sample['id']}: {metrics['text']['numeric_exact_correct']}/{metrics['text']['reference']} exact numeric, {len(observations['opening_candidates'])} opening candidates, {len(working['topology']['regions'])} regions",
                flush=True,
            )
        report["aggregate"] = aggregate(report["samples"])
        write_json(staging / "report.json", report)
        cards = "".join(
            (
                f"<article><h2>{s['id']}</h2><a href='{s['id']}/topology_review.png'><img src='{s['id']}/topology_review.png'></a><p>Topology: {s['topology']['regions']} face candidates, {s['topology']['ambiguous_regions']} with unresolved openings, {s['topology']['connectivity_edges']} links, {s['topology']['corridor_hypotheses']} corridor hypotheses; {s['topology']['issues']} issues. Numeric exact: {s['metrics']['text']['numeric_exact_correct']}/{s['metrics']['text']['reference']}.</p><a href='{s['id']}/comparison.png'>Reference / perception comparison</a> | <a href='{s['id']}/hough_lines.png'>Hough</a> | <a href='{s['id']}/lsd_lines.png'>LSD</a> | <a href='{s['id']}/topology.json'>Topology</a> | <a href='{s['id']}/metrics.json'>Metrics</a> | <a href='{s['id']}/working.json'>Alternatives, roles, transforms</a> | <a href='{s['id']}/observations.json'>V1 observations</a></article>"
                for s in report["samples"]
            )
        )
        summary = html.escape(json.dumps(report["aggregate"], indent=2))
        (staging / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>Steps 07–08 review</title><style>body{font:16px system-ui;margin:24px;background:#eee}article,pre{background:white;padding:16px;margin:20px 0}img{max-width:100%}</style><h1>Steps 07–08: perception and topology</h1><p>Topology overlays: teal = physical wall evidence; orange = virtual opening boundary; purple = rectangular region candidate; amber = unresolved opening boundary; red = unsupported face. Counts describe hypotheses, not accuracy. All outputs require review. No metric layout is produced. Development set only.</p><p>The reference/perception comparison links show the manual reference on the left and independent predictions on the right.</p><pre>"
            + summary
            + "</pre>"
            + cards
        )
        os.rename(staging, output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(
        description="Image -> unreviewed original-frame observations; manual labels only evaluate."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", type=Path)
    group.add_argument("--dataset", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detector", choices=["hough", "lsd"], default="lsd")
    parser.add_argument("--max-side", type=int, default=1600)
    parser.add_argument(
        "--geometry-profile",
        choices=["baseline", "grid", "structural"],
        default="baseline",
        help="Opt-in geometry experiment; structural can reduce opening recall. Default preserves baseline.",
    )
    args = parser.parse_args()
    try:
        adapter = RapidOCRAdapter()
        options = {
            "detector": args.detector,
            "max_side": args.max_side,
            "geometry_profile": args.geometry_profile,
        }
        if args.dataset:
            run_dataset(args.manifest, args.output, adapter, **options)
        else:
            run_single(args.image, args.output, adapter, **options)
        print(f"Perception output: {args.output}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Perception failed: {exc}\n")


if __name__ == "__main__":
    main()
