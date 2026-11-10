import argparse
from collections import Counter
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from SketchPipeline.evaluation.metrics import pairs
from . import decoder
from .decoder_refined import canonical_frame
from .human_error_review import reference
from .synthetic import write_json

ROOT = Path(__file__).resolve().parents[2]
POLICY = {
    "version": "dino-region-stage-audit/1.0",
    "region_threshold": 0.5,
    "region_matching_iou": 0.5,
    "reference_interior_erosion_px": 1,
    "low_response_fraction": 0.5,
    "reference_use": "Post-hoc matching and mask probes only; never inputs to replay.",
    "scope": "Diagnosis of existing development predictions, not a new accuracy benchmark.",
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def components(binary, kind):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8))
    side = max(binary.shape)
    records = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        fill = area / (w * h)
        aspect = max(w / h, h / w)
        expanded = np.clip(
            [x - 4, y - 4, x + w + 3, y + h + 3],
            [0] * 4,
            [binary.shape[1] - 1, binary.shape[0] - 1] * 2,
        )
        gate = (
            "minimum_area"
            if area < side * side * decoder.CONFIG["region_min_area_fraction"]
            else (
                "rectangular_fill"
                if fill < decoder.CONFIG["region_min_rectangular_fill"]
                else (
                    "maximum_aspect"
                    if aspect > decoder.CONFIG["region_max_aspect_ratio"]
                    else "passes_component_gates"
                )
            )
        )
        records.append(
            {
                "id": f"{kind}_component_{label}",
                "type": kind,
                "bounds_px": expanded.tolist(),
                "component_bounds_px": [x, y, x + w, y + h],
                "area_px": area,
                "fill": fill,
                "aspect": aspect,
                "minimum_area_px": side * side * decoder.CONFIG["region_min_area_fraction"],
                "minimum_fill": decoder.CONFIG["region_min_rectangular_fill"],
                "first_gate": gate,
            }
        )
    return records


def trace_regions(probabilities, gray):
    original = decoder.regularize_boxes
    captured = {}

    def regularizer(boxes, shape, stroke=None):
        caller = inspect.currentframe().f_back
        try:
            fitted = caller.f_locals["boxes"]
            ids = {id(box): f"candidate_{i + 1:04d}" for i, box in enumerate(fitted)}
            captured["fitted"] = [dict(copy.deepcopy(box), id=ids[id(box)]) for box in fitted]
            captured["after_nms"] = [dict(copy.deepcopy(box), id=ids[id(box)]) for box in boxes]
            captured["barrier"] = caller.f_locals["barrier"].copy()
        finally:
            del caller
        previous = sys.getprofile()

        def profile(frame, event, arg):
            if frame.f_code == original.__code__ and event == "return" and isinstance(arg, list):
                result = frame.f_locals["result"]
                kept = frame.f_locals["kept"]
                result_ids = {
                    id(box): captured["after_nms"][i]["id"] for i, box in enumerate(result)
                }
                captured["after_snap"] = [
                    dict(copy.deepcopy(box), id=result_ids[id(box)]) for box in result
                ]
                captured["kept_ids"] = [result_ids[id(box)] for box in kept]
                captured["snap_tolerance_px"] = frame.f_locals["tolerance"]

        sys.setprofile(profile)
        try:
            return original(boxes, shape, stroke)
        finally:
            sys.setprofile(previous)

    with patch.object(decoder, "regularize_boxes", regularizer):
        boxes, rejected = decoder.region_boxes(probabilities, gray, POLICY["region_threshold"])
    expected, expected_rejected = decoder.region_boxes(
        probabilities, gray, POLICY["region_threshold"]
    )
    if boxes != expected or rejected != expected_rejected:
        raise ValueError("Tracing changed decoder output")
    captured["final"] = boxes
    captured["rejected"] = rejected
    kept = []
    drops = []
    for box in captured["after_snap"]:
        conflicts = [old for old in kept if decoder.iou(box["bounds_px"], old["bounds_px"]) > 0]
        if conflicts:
            overlaps = []
            for old in conflicts:
                a, b = (box["bounds_px"], old["bounds_px"])
                overlaps.append(
                    {
                        "candidate_id": old["id"],
                        "bounds_px": b,
                        "overlap_size_px": [
                            max(0, min(a[2], b[2]) - max(a[0], b[0])),
                            max(0, min(a[3], b[3]) - max(a[1], b[1])),
                        ],
                        "iou": decoder.iou(a, b),
                    }
                )
            drops.append(
                {"candidate_id": box["id"], "bounds_px": box["bounds_px"], "conflicts": overlaps}
            )
        else:
            kept.append(box)
    if [box["id"] for box in kept] != captured["kept_ids"]:
        raise ValueError("Overlap trace diverged")
    captured["overlap_drops"] = drops
    captured["post_barrier_components"] = sum(
        [
            components((probabilities[channel] > 0.5) & (captured["barrier"] == 0), kind)
            for channel, kind in [(1, "room"), (2, "corridor_segment")]
        ],
        [],
    )
    return captured


def stage_matches(boxes, regions):
    matched = pairs(
        boxes, regions, lambda a, b: 1 - decoder.iou(a["bounds_px"], b["bounds_px"]), 0.5
    )
    return {j: {"candidate": boxes[i], "iou": 1 - cost} for i, j, cost in matched}


def interior_probes(region, raw, projected, barrier):
    mask = np.zeros(raw.shape[1:], np.uint8)
    cv2.fillPoly(mask, [np.rint(region["polygon"]).astype(np.int32)], 1)
    eroded = cv2.erode(mask, np.ones((3, 3), np.uint8))
    valid = eroded > 0 if eroded.any() else mask > 0
    channel = 2 if region["type"] == "corridor_segment" else 1
    fraction = lambda plane: float(plane[valid].mean()) if valid.any() else None
    return {
        "probe_uses_approximate_reference": True,
        "probe_pixels": int(valid.sum()),
        "raw_correct_class_fraction": fraction(raw[channel] > 0.5),
        "raw_other_class_fraction": fraction(raw[3 - channel] > 0.5),
        "after_projection_fraction": fraction(projected[channel] > 0.5),
        "after_barrier_fraction": fraction((projected[channel] > 0.5) & (barrier == 0)),
        "raw_mean_response": fraction(raw[channel]),
    }


def classify(index, region, trace, raw, projected, raw_components, projected_components, matches):
    probes = interior_probes(region, raw, projected, trace["barrier"])
    row = {
        "reference_region_id": region["id"],
        "type": region["type"],
        "reference_bounds_px": region["bounds_px"],
        "probes": probes,
        "stage_matches": {
            name: values[index] for name, values in matches.items() if index in values
        },
    }
    if index in matches["final"]:
        row["first_loss"] = "retained"
        return row
    snapped = matches["after_snap"].get(index)
    if snapped and snapped["candidate"]["id"] not in trace["kept_ids"]:
        row["first_loss"] = "overlap_rejection"
        row["overlap_evidence"] = next(
            (
                drop
                for drop in trace["overlap_drops"]
                if drop["candidate_id"] == snapped["candidate"]["id"]
            )
        )
    elif index in matches["after_nms"] and index not in matches["after_snap"]:
        row["first_loss"] = "snapping_deformation"
    elif index in matches["fitted"] and index not in matches["after_nms"]:
        row["first_loss"] = "nms_rejection"
    elif index in matches["post_barrier_components"]:
        component = matches["post_barrier_components"][index]["candidate"]
        row["component_evidence"] = component
        row["first_loss"] = (
            component["first_gate"]
            if component["first_gate"] != "passes_component_gates"
            else "wall_fit_or_minimum_extent"
        )
    elif index in matches["projected_components"]:
        row["first_loss"] = "barrier_fragmentation"
    elif index in matches["raw_components"]:
        row["first_loss"] = "logical_boundary_projection_fragmentation"
    elif (probes["raw_correct_class_fraction"] or 0) < 0.5 and (
        probes["raw_other_class_fraction"] or 0
    ) >= 0.5:
        row["first_loss"] = "model_wrong_region_class"
    elif (probes["raw_correct_class_fraction"] or 0) >= 0.5:
        row["first_loss"] = "model_region_not_separated"
    else:
        row["first_loss"] = "model_weak_or_fragmented_region"
    row["mixed_weak_model_response"] = (probes["raw_correct_class_fraction"] or 0) < 0.5
    channel_kind = region["type"]
    for name, items in [
        ("raw", raw_components),
        ("projected", projected_components),
        ("post_barrier", trace["post_barrier_components"]),
    ]:
        candidates = [box for box in items if box["type"] == channel_kind]
        if candidates:
            best = max(
                candidates, key=lambda box: decoder.iou(box["bounds_px"], region["bounds_px"])
            )
            row[f"best_{name}_component"] = {
                "candidate": best,
                "iou": decoder.iou(best["bounds_px"], region["bounds_px"]),
            }
    return row


def draw_case(gray, raw, projected, trace, regions, rows, path):
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font = (
        ImageFont.truetype(font_path, 14) if Path(font_path).exists() else ImageFont.load_default()
    )
    w, h = (gray.shape[1], gray.shape[0])
    scale = 2
    panels = [
        ("Saved prediction", gray),
        ("Raw room response", np.uint8(raw[1] * 255)),
        ("Raw corridor response", np.uint8(raw[2] * 255)),
        ("Boundary/barrier removed", np.uint8((trace["barrier"] > 0) * 255)),
    ]
    canvas = Image.new("RGB", (w * scale * 4, h * scale + 180), "white")
    draw = ImageDraw.Draw(canvas)
    for i, (title, im) in enumerate(panels):
        tile = Image.fromarray(im).convert("RGB").resize((w * scale, h * scale))
        local = ImageDraw.Draw(tile)
        for region, row in zip(regions, rows):
            color = "#16a34a" if row["first_loss"] == "retained" else "#dc2626"
            local.rectangle(
                [value * scale for value in region["bounds_px"]], outline=color, width=2
            )
            local.text(
                (region["bounds_px"][0] * scale + 2, region["bounds_px"][1] * scale + 2),
                region["id"],
                fill=color,
                font=font,
            )
        if i == 0:
            for box in trace["final"]:
                local.rectangle([v * scale for v in box["bounds_px"]], outline="#f59e0b", width=2)
            for box in trace["after_snap"]:
                if box["id"] not in trace["kept_ids"]:
                    local.rectangle(
                        [v * scale for v in box["bounds_px"]], outline="#2563eb", width=3
                    )
        canvas.paste(tile, (i * w * scale, 30))
        draw.text((i * w * scale + 4, 5), title, font=font, fill="black")
    y = h * scale + 38
    for row in rows:
        if row["first_loss"] == "retained":
            continue
        text = f"{row['reference_region_id']}: {row['first_loss']}"
        if "component_evidence" in row:
            c = row["component_evidence"]
            text += f" | area {c['area_px']}/{c['minimum_area_px']:.1f}, fill {c['fill']:.3f}/{c['minimum_fill']}"
        if "overlap_evidence" in row:
            text += (
                " | overlap "
                + str(row["overlap_evidence"]["conflicts"][0]["overlap_size_px"])
                + " px"
            )
        draw.text((8, y), text, font=font, fill="black")
        y += 21
    draw.text(
        (8, h * scale + 145),
        "Green/red: retained/missing approximate references; orange: final boxes; blue: actual overlap-rejected boxes. No inference rerun.",
        font=font,
        fill="#444444",
    )
    canvas.save(path)


def audit(study, output):
    study = Path(study).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((study / "protocol.json").read_text())
    sources = [
        Path(__file__),
        Path(decoder.__file__),
        Path(__file__).with_name("decoder_refined.py"),
    ]
    frozen = {
        "policy": POLICY,
        "study_report_sha256": sha(study / "report.json"),
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "model_weights_sha256": json.loads((study / "training_report.json").read_text())[
            "selected"
        ]["sha256"],
        "model_inference_run": False,
        "decoder_modified": False,
        "input_hashes": {},
    }
    rows = []
    cases = []
    figures = []
    replays = 0
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    for folder in folders:
        result = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "working.png"), 0)
        for name in [
            "proposals.json",
            "working.png",
            "model-masks.npz",
            "native-auxiliary-masks.npz",
            "evidence.png",
        ]:
            frozen["input_hashes"][str((folder / name).relative_to(ROOT))] = sha(folder / name)
        with np.load(folder / "model-masks.npz") as cache:
            probabilities = cache["probabilities"]
            native = cache["native_probabilities"]
        trace = trace_regions(probabilities, gray)
        if trace["final"] != result["diagnostics"][0]["region_boxes"]:
            raise ValueError("Replay disagrees with saved prediction: " + str(folder))
        replays += 1
        if folder.parent.parent.name != "human":
            continue
        n = int(folder.parent.name.split("_")[1])
        sample = f"Data_{n}"
        evidence = cv2.imread(str(folder / "evidence.png"), 0)
        with np.load(folder / "native-auxiliary-masks.npz") as cache:
            auxiliary = cache["probabilities"]
        projected = auxiliary[:6].copy()
        projected[3] = np.maximum(projected[3], auxiliary[6])
        projected[1:3] = np.minimum(projected[1:3], 1 - auxiliary[7:8])
        if not np.array_equal(projected, native):
            raise ValueError("Adapter projection differs from saved native masks")
        matrix = np.asarray(result["preprocessing"]["original_to_working"]) @ np.asarray(
            result["evidence_preprocessing"]["working_to_original"]
        )
        _, raw, _ = canonical_frame(
            evidence,
            auxiliary,
            gray,
            matrix,
            result["evidence_preprocessing"].get("diagnostic_content_bounds_px"),
        )
        ref = reference(n, result["preprocessing"])
        role = protocol["groups"][sample]["split"]
        raw_components = sum(
            [
                components(raw[channel] > 0.5, kind)
                for channel, kind in [(1, "room"), (2, "corridor_segment")]
            ],
            [],
        )
        projected_components = sum(
            [
                components(probabilities[channel] > 0.5, kind)
                for channel, kind in [(1, "room"), (2, "corridor_segment")]
            ],
            [],
        )
        stages = {
            name: trace[name]
            for name in ["fitted", "after_nms", "after_snap", "post_barrier_components", "final"]
        }
        stages.update(raw_components=raw_components, projected_components=projected_components)
        matches = {name: stage_matches(boxes, ref["regions"]) for name, boxes in stages.items()}
        region_rows = [
            classify(
                i, region, trace, raw, probabilities, raw_components, projected_components, matches
            )
            for i, region in enumerate(ref["regions"])
        ]
        for row in region_rows:
            row.update(sample_id=sample, role=role)
        rows.extend(region_rows)
        directory = output / sample
        directory.mkdir()
        serial = {k: v for k, v in trace.items() if k != "barrier"}
        write_json(
            directory / "trace.json",
            {
                "sample_id": sample,
                "role": role,
                "trace": serial,
                "region_rows": region_rows,
                "source_prediction_sha256": sha(folder / "proposals.json"),
            },
        )
        if any((row["first_loss"] != "retained" for row in region_rows)):
            draw_case(
                gray,
                raw,
                probabilities,
                trace,
                ref["regions"],
                region_rows,
                directory / "stages.png",
            )
            figures.append(
                f'<section><h2>{sample} · {role}</h2><img loading="lazy" src="{sample}/stages.png"></section>'
            )
        cases.append(
            {
                "sample_id": sample,
                "role": role,
                "reference_regions": len(ref["regions"]),
                "missing_regions": sum((row["first_loss"] != "retained" for row in region_rows)),
            }
        )
    summary = {
        role: dict(Counter((row["first_loss"] for row in rows if row["role"] == role)))
        for role in ["train", "validation", "test"]
    }
    opening_audit = json.loads((study / "opening-audit.json").read_text())
    lookup = {(r["sample_id"], r["reference_region_id"]): r for r in rows}
    opening_rows = []
    for opening in opening_audit["rows"]:
        if opening["reason"] != "connected_region_missing":
            continue
        evidence = [
            lookup[opening["sample_id"], identifier] for identifier in opening["missing_region_ids"]
        ]
        opening_rows.append(
            {
                "sample_id": opening["sample_id"],
                "role": opening["role"],
                "opening_id": opening["opening_id"],
                "missing_region_stages": {
                    r["reference_region_id"]: r["first_loss"] for r in evidence
                },
            }
        )
    changed = [
        path for path, digest in frozen["input_hashes"].items() if sha(ROOT / path) != digest
    ]
    if changed:
        raise ValueError("Saved predictions changed")
    frozen["replays_verified_against_unchanged_decoder_and_saved_output"] = replays
    write_json(output / "freeze.json", frozen)
    value = {
        "version": POLICY["version"],
        "summary": summary,
        "rows": rows,
        "cases": cases,
        "opening_rows": opening_rows,
        "model_inference_run": False,
        "model_retrained": False,
        "production_decoder_changed": False,
        "saved_input_files_checked": len(frozen["input_hashes"]),
        "saved_inputs_changed": changed,
        "replay_cases": replays,
        "reference_policy": "Approximate annotations for diagnostic matching; no new blind accuracy claim.",
    }
    write_json(output / "report.json", value)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>DINO region stage audit</title><style>body{font:14px system-ui;margin:24px}section{border:1px solid #ddd;padding:12px;margin:12px 0}img{max-width:100%}</style><h1>DINO region stage audit</h1><p>Saved model masks; unchanged decoder replay. Approximate references are diagnostic probes only. Green/red: retained/missing references, orange: final boxes, blue: overlap-rejected candidates.</p>'
        + "".join(figures)
    )
    print(
        json.dumps(
            {
                "summary": summary,
                "replay_cases": replays,
                "saved_input_files_checked": len(frozen["input_hashes"]),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.study, args.output)
