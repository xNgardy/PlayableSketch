import argparse
from collections import defaultdict
import copy
import hashlib
import html
import json
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, Point
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.perception.structural import suppress_grid
from .contract import validate_authoring
from .decoder import (
    CONFIG,
    region_boxes,
    boundary_graph,
    opening_candidates,
    authoring_document,
    regularize_boxes,
)
from .diagnostic_preprocessing import suggest_crop, prepare_variant, map_probabilities
from .model import LocalSegmenter
from .pilot import human_reference, synthetic_reference, score, aggregate
from .propose import prepare_image, DEFAULT_LOCK
from .synthetic import write_json, CHANNELS

ROOT = Path(__file__).resolve().parents[2]
ARMS = [
    dict(name="baseline_256", max_side=256, square=False, crop=False),
    dict(name="square_256", max_side=256, square=True, crop=False),
    dict(name="aspect_512", max_side=512, square=False, crop=False),
    dict(name="square_512", max_side=512, square=True, crop=False),
    dict(name="square_768", max_side=768, square=True, crop=False),
    dict(name="crop_square_256", max_side=256, square=True, crop=True),
    dict(name="crop_square_512", max_side=512, square=True, crop=True),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_masks(probabilities, gray, metadata, source):
    boxes, rejected = region_boxes(probabilities, gray, 0.5)
    openings, unresolved = opening_candidates(boundary_graph(boxes)[0], gray, probabilities)
    document = authoring_document(source, metadata, boxes, openings)
    errors = validate_authoring(document)
    if errors:
        raise ValueError("; ".join(errors))
    return (
        document,
        {
            "boxes": boxes,
            "rejected": rejected,
            "unresolved": unresolved,
            "opening_count": len(openings),
        },
    )


def positive_probe_metrics(probabilities, reference, observations, annotations, metadata, coverage):
    height, width = probabilities.shape[1:]
    radius = 2
    lines = {line["id"]: line for line in observations["lines"]}
    targets = defaultdict(list)
    for stroke in annotations["strokes"]:
        kind = stroke["kind"]
        if kind not in ("wall", "tick"):
            continue
        for identifier in stroke["line_ids"]:
            line = lines[identifier]
            a, b = project([line["start_px"], line["end_px"]], metadata["original_to_working"])
            points = np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b - a))) + 1))
            targets[kind].extend(points.tolist())
    for junction in annotations["junctions"]:
        targets["junction"].append(
            project([junction["point_px"]], metadata["original_to_working"])[0].tolist()
        )
    for region in reference["regions"]:
        polygon = Polygon(region["polygon"])
        x, y, X, Y = polygon.bounds
        for u in np.linspace(x, X, 7)[1:-1]:
            for v in np.linspace(y, Y, 7)[1:-1]:
                p = Point(u, v)
                if polygon.contains(p) and polygon.boundary.distance(p) >= 3:
                    targets[
                        (
                            "corridor_interior"
                            if region["type"] == "corridor_segment"
                            else "room_interior"
                        )
                    ].append([u, v])
    indices = {name: i for i, name in enumerate(CHANNELS)}
    thresholds = {
        "wall": 0.45,
        "tick": CONFIG["tick_model_threshold"],
        "junction": 0.45,
        "room_interior": 0.5,
        "corridor_interior": 0.5,
    }
    result = {}
    for kind, points in targets.items():
        responses = []
        covered = []
        for x, y in points:
            x, y = (round(x), round(y))
            if not (0 <= x < width and 0 <= y < height):
                continue
            patch = probabilities[
                indices[kind],
                max(0, y - radius) : y + radius + 1,
                max(0, x - radius) : x + radius + 1,
            ]
            responses.append(float(patch.max()))
            covered.append(bool(coverage[y, x]))
        result[kind] = {
            "positive_probes": len(responses),
            "hits": sum((v >= thresholds[kind] for v in responses)),
            "hit_fraction": (
                float(np.mean(np.asarray(responses) >= thresholds[kind])) if responses else None
            ),
            "mean_local_max_response": float(np.mean(responses)) if responses else None,
            "covered_probes": sum(covered),
            "threshold": thresholds[kind],
            "radius_px": radius,
        }
    return result


def oracle_region_interventions(reference, gray, probabilities, metadata, source):
    supplied = [
        {"type": r["type"], "bounds_px": copy.deepcopy(r["bounds_px"]), "model_score": 1.0}
        for r in reference["regions"]
    ]
    if not supplied:
        return {"status": "unscorable_missing_region_reference"}
    boxes = regularize_boxes(supplied, gray.shape)
    outcomes = {}
    for name, masks in [
        ("reference_regions_predicted_markers", probabilities),
        ("reference_regions_raw_gate", None),
    ]:
        openings, unresolved = opening_candidates(boundary_graph(boxes)[0], gray, masks)
        document = authoring_document(source, metadata, boxes, openings)
        outcomes[name] = {
            "diagnostic_only": True,
            "labels_used_as_input": True,
            "supplied_regions": len(supplied),
            "retained_regions": len(boxes),
            "metrics": score(document, reference, metadata["working_size_px"]),
            "authoring": document,
            "unresolved": unresolved,
        }
    return outcomes


def panel(gray, probabilities, document, reference, path):
    height, width = gray.shape
    view = Image.fromarray(gray).convert("RGB")
    draw = ImageDraw.Draw(view)
    for region in reference["regions"]:
        draw.rectangle(region["bounds_px"], outline="#16a34a", width=1)
    for region in document["topology"]["regions"]:
        points = np.asarray(region["geometry"]["points_px"])
        draw.rectangle(
            np.r_[points.min(axis=0), points.max(axis=0)].tolist(), outline="#f97316", width=2
        )
    for opening in document["topology"]["openings"]:
        draw.line([tuple(p) for p in opening["geometry"]["points_px"]], fill="#ef4444", width=3)
    columns = [("Plan / green reference", view)] + [
        (
            CHANNELS[index] + " response",
            Image.fromarray(np.uint8(probabilities[index] * 255)).convert("RGB"),
        )
        for index in (0, 1, 3)
    ]
    canvas = Image.new("RGB", (width * 4, height + 24), "#fafafa")
    draw = ImageDraw.Draw(canvas)
    for index, (label, image) in enumerate(columns):
        canvas.paste(image, (index * width, 24))
        draw.text((index * width + 4, 4), label, fill="black")
    canvas.save(path)


def synthetic_reference_in_frame(path, metadata):
    reference = synthetic_reference(path)
    matrix = metadata["original_to_working"]
    for region in reference["regions"]:
        x, y, X, Y = region["bounds_px"]
        corners = project([[x, y], [X, y], [X, Y], [x, Y]], matrix)
        region["bounds_px"] = np.r_[corners.min(axis=0), corners.max(axis=0)].tolist()
    for opening in reference["openings"]:
        opening["points_px"] = project(opening["points_px"], matrix).tolist()
    return reference


def run_diagnostics(output):
    import torch

    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(DEFAULT_LOCK.read_text())
    checkpoint = ROOT / lock["checkpoint_path"]
    human_ids = [3, 8, 18, 31, 41, 45]
    controls = [f"{seed}_{style}" for seed in range(2000, 2006) for style in ("wavy", "grid")]
    protected = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (ROOT / "Data").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    protocol = {
        "version": "shape-diagnosis/1.0",
        "created_date": "2026-11-03",
        "human_development_ids": human_ids,
        "synthetic_controls": controls,
        "arms": ARMS,
        "checkpoint_sha256": sha(checkpoint),
        "decoder_config_sha256": sha(Path(__file__).with_name("proposals.config.json")),
        "source_hashes": {
            str(p.relative_to(ROOT)): sha(p)
            for p in sorted(Path(__file__).parent.glob("*.py"))
            + [
                ROOT / "SketchPipeline/preprocessing/prepare.py",
                ROOT / "SketchPipeline/perception/structural.py",
            ]
        },
        "runtime": {
            "torch": torch.__version__,
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "device": "cpu",
            "threads": 4,
        },
        "protected_data_hashes": protected,
        "thresholds": {
            "region_iou": 0.5,
            "opening_endpoint_fraction": 0.04,
            "positive_probe_radius": 2,
        },
        "policy": "Frozen same development images/weights; no training, no threshold sweep, no production default changes.",
        "oracle_policy": "Label-assisted interventions are diagnostic only; never count as AI accuracy. Human positive probes are approximate and not dense pixel GT.",
        "timing": "Prediction elapsed excludes model initialization, references, probe scoring, visualizations and oracle interventions.",
        "unseen_writer_generalization": "unknown",
    }
    if protocol["checkpoint_sha256"] != lock["checkpoint_sha256"]:
        raise ValueError("Pinned checkpoint changed")
    write_json(output / "protocol.json", protocol)
    adapter = LocalSegmenter(checkpoint, lock["checkpoint_sha256"])
    rows = []
    gallery = []
    for n in human_ids:
        paths = [
            p
            for p in (ROOT / "Data").glob(f"Data_{n}.*")
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")
        ]
        if len(paths) != 1:
            raise ValueError(f"Ambiguous source for Data_{n}")
        image = paths[0]
        base_gray, base_metadata = prepare_image(image)
        crop, crop_report = suggest_crop(image)
        source = {
            "image_path": str(image),
            "image_sha256": sha(image),
            "width_px": base_metadata["original_size_px"][0],
            "height_px": base_metadata["original_size_px"][1],
        }
        for arm in ARMS:
            print(f"Data_{n} {arm['name']}", flush=True)
            directory = output / f"Data_{n}" / arm["name"]
            directory.mkdir(parents=True)
            started = time.perf_counter()
            native, metadata = prepare_variant(image, arm, base_gray, base_metadata, crop)
            clean, grid_mask, grid = suppress_grid(native)
            native_masks = adapter.predict(native, clean)
            masks, coverage = map_probabilities(native_masks, metadata, base_metadata)
            document, decoder = decode_masks(masks, base_gray, base_metadata, source)
            prediction = {
                "authoring": document,
                "decoder": decoder,
                "preprocessing": metadata,
                "canonical_preprocessing": base_metadata,
                "crop": crop_report,
                "arm": arm,
                "elapsed_seconds": time.perf_counter() - started,
                "model": adapter.metadata,
                "numeric_ocr_called": False,
                "labels_used_as_input": False,
                "native_size_px": [native.shape[1], native.shape[0]],
                "decoder_size_px": base_metadata["working_size_px"],
            }
            write_json(directory / "prediction.json", prediction)
            np.savez_compressed(
                directory / "masks.npz", native=native_masks, canonical=masks, coverage=coverage
            )
            cv2.imwrite(str(directory / "input.png"), native)
            cv2.imwrite(str(directory / "cleaned.png"), clean)
            cv2.imwrite(str(directory / "grid-mask.png"), grid_mask)
            reference = human_reference(n, base_metadata)
            annotation = json.loads(
                (ROOT / f"Data/annotations/v1/Data_{n}.annotations.json").read_text()
            )
            observation = json.loads(
                (ROOT / f"Data/annotations/v1/Data_{n}.observations.json").read_text()
            )
            metrics = score(document, reference, base_metadata["working_size_px"])
            probes = positive_probe_metrics(
                masks, reference, observation, annotation, base_metadata, coverage
            )
            interventions = oracle_region_interventions(
                reference, base_gray, masks, base_metadata, source
            )
            row = {
                "sample_id": f"Data_{n}",
                "origin": "human",
                "arm": arm["name"],
                "status": (
                    "needs_attention" if document["topology"]["regions"] else "manual_required"
                ),
                "elapsed_seconds": prediction["elapsed_seconds"],
                "metrics": metrics,
                "positive_probes": probes,
                "reference_region_interventions": {
                    k: (
                        {a: b for a, b in v.items() if a not in ("authoring", "unresolved")}
                        if isinstance(v, dict)
                        else v
                    )
                    for k, v in interventions.items()
                },
                "native_size_px": prediction["native_size_px"],
                "crop": crop_report,
            }
            write_json(directory / "metrics.json", row)
            write_json(directory / "oracle-interventions.json", interventions)
            panel(base_gray, masks, document, reference, directory / "panel.png")
            rows.append(row)
            gallery.append(
                f"""<section><h2>Data {n} · {arm['name']}</h2><p>Regions matched {metrics['regions'] and metrics['regions']['true_positive']}; openings {metrics['openings']['true_positive']}/{metrics['openings']['reference']}. Input {native.shape[1]}×{native.shape[0]}. Prediction only; oracle interventions excluded.</p><a href="Data_{n}/{arm['name']}/input.png">Model input</a><img loading="lazy" src="Data_{n}/{arm['name']}/panel.png"></section>"""
            )
    control_rows = []
    for name in controls:
        folder = ROOT / "Saved/ShapeFirst/v1/development" / name
        image = folder / "source.png"
        gray, metadata = prepare_image(image)
        source = {
            "image_path": str(image),
            "image_sha256": sha(image),
            "width_px": 256,
            "height_px": 256,
        }
        directory = output / "synthetic_controls" / name
        directory.mkdir(parents=True)
        predictions = []
        for arm in (ARMS[0], ARMS[1], ARMS[2]):
            native, nmeta = prepare_variant(image, arm, gray, metadata)
            clean, _, _ = suppress_grid(native)
            raw = adapter.predict(native, clean)
            mapped, coverage = map_probabilities(raw, nmeta, metadata)
            predicted, detail = decode_masks(mapped, gray, metadata, source)
            write_json(
                directory / (arm["name"] + ".prediction.json"),
                {
                    "authoring": predicted,
                    "decoder": detail,
                    "native_size_px": [native.shape[1], native.shape[0]],
                },
            )
            predictions.append((arm, predicted))
        reference = synthetic_reference_in_frame(folder / "reference.json", metadata)
        with np.load(folder / "masks.npz") as data:
            perfect = data["masks"].astype(np.float32) / 255.0
        if not np.allclose(metadata["original_to_working"], np.eye(3)):
            perfect = np.stack(
                [
                    cv2.warpPerspective(
                        c,
                        np.asarray(metadata["original_to_working"]),
                        tuple(metadata["working_size_px"]),
                    )
                    for c in perfect
                ]
            )
        document, detail = decode_masks(perfect, gray, metadata, source)
        exact_row = {
            "sample_id": name,
            "origin": "synthetic",
            "arm": "exact_masks_decoder_control",
            "labels_used_as_input": True,
            "diagnostic_only": True,
            "status": "diagnostic",
            "elapsed_seconds": None,
            "metrics": score(document, reference, metadata["working_size_px"]),
            "decoder": detail,
        }
        control_rows.append(exact_row)
        write_json(directory / "oracle-control.json", exact_row)
        for arm, predicted in predictions:
            control_rows.append(
                {
                    "sample_id": name,
                    "origin": "synthetic",
                    "arm": arm["name"],
                    "labels_used_as_input": False,
                    "status": (
                        "needs_attention" if predicted["topology"]["regions"] else "manual_required"
                    ),
                    "elapsed_seconds": None,
                    "metrics": score(predicted, reference, metadata["working_size_px"]),
                }
            )
    changed = [path for path, expected in protected.items() if sha(ROOT / path) != expected]
    if changed:
        raise ValueError("Protected input files changed: " + str(changed))
    summary = {arm["name"]: aggregate([r for r in rows if r["arm"] == arm["name"]]) for arm in ARMS}
    probe_summary = {}
    for arm in ARMS:
        totals = defaultdict(lambda: {"hits": 0, "positive_probes": 0, "covered_probes": 0})
        for row in rows:
            if row["arm"] != arm["name"]:
                continue
            for name, values in row["positive_probes"].items():
                for key in ("hits", "positive_probes", "covered_probes"):
                    totals[name][key] += values[key]
        probe_summary[arm["name"]] = {
            name: {
                **v,
                "hit_fraction": v["hits"] / v["positive_probes"] if v["positive_probes"] else None,
            }
            for name, v in totals.items()
        }
    report = {
        "version": "shape-diagnosis-report/1.0",
        "scope": "Development diagnostics only; fixed model; no training or production changes.",
        "protocol_sha256": sha(output / "protocol.json"),
        "arms": summary,
        "positive_probes": probe_summary,
        "synthetic_controls": {
            arm: aggregate([r for r in control_rows if r["arm"] == arm])
            for arm in sorted({r["arm"] for r in control_rows})
        },
        "rows": rows,
        "synthetic_rows": control_rows,
        "protected_files_checked": len(protected),
        "protected_files_changed": changed,
        "model_sha256_after": sha(checkpoint),
        "human_correction_time_seconds": None,
        "unseen_writer_generalization": "unknown",
    }
    write_json(output / "report.json", report)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Shape input and decoder diagnostics</title><style>body{font:14px system-ui;background:#f7f7f7;margin:24px}section{padding:12px;background:white;border:1px solid #ddd;margin:16px 0}img{display:block;max-width:100%;margin-top:10px}h2{font-size:16px}</style><h1>Input and model/decoder diagnostics</h1><p>Same six human development drawings and fixed checkpoint. Green: approximate reference bounds; orange: proposed bounds. Wall/region/tick images show raw model responses in a common frame. Human traces are not dense mask ground truth. Privileged oracle interventions are excluded from these predictions.</p>'
        + "".join(gallery)
    )
    print(
        json.dumps({"output": str(output), "protected_changes": changed, "human_summary": summary}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Frozen input and model/decoder interventions. Development diagnostics, no training."
    )
    parser.add_argument("--output", type=Path, default=ROOT / "Saved/ShapeFirst/diagnostics/v1")
    args = parser.parse_args()
    run_diagnostics(args.output)
