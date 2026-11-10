import copy
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import project
from .decoder_refined import ink_evidence
from .diagnostic_preprocessing import prepare_variant
from .propose import prepare_image
from .synthetic import write_json

ROOT = Path(__file__).resolve().parents[2]
CURATION = Path(__file__).with_name("curation") / "human-geometry.v1.json"
CHANNELS = ["wall", "room_interior", "corridor_interior", "tick", "junction", "open_interface"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_image(n):
    paths = [
        p
        for p in (ROOT / "Data").glob(f"Data_{n}.*")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg")
    ]
    if len(paths) != 1:
        raise ValueError("Source image is not unique")
    return paths[0]


def structural_labels(n, curation=None):
    folder = ROOT / "Data/annotations/v1"
    annotation = json.loads((folder / f"Data_{n}.annotations.json").read_text())
    observations = json.loads((folder / f"Data_{n}.observations.json").read_text())
    regions = copy.deepcopy(annotation.get("regions", []))
    sidecar = curation if curation is not None else json.loads(CURATION.read_text())
    extra = sidecar["samples"].get(f"Data_{n}")
    if extra:
        if sha(source_image(n)) != extra["source_sha256"]:
            raise ValueError("Curated source changed")
        if regions:
            raise ValueError("Sidecar must not overwrite existing region labels")
        regions = copy.deepcopy(extra["regions"])
    lines = {
        v["id"]: {"start_px": v["start_px"], "end_px": v["end_px"]} for v in observations["lines"]
    }
    return {
        "regions": regions,
        "strokes": annotation["strokes"],
        "lines": lines,
        "junctions": annotation["junctions"],
        "gaps": annotation["gaps"],
        "distractor_polygons": [
            t["polygon_px"] for t in observations["texts"] if t.get("polygon_px")
        ],
        "precision": "approximate_manual_traces_with_uncertainty_margins",
    }


def prepare_human(n, size=512):
    image = source_image(n)
    gray, metadata = prepare_image(image)
    native, native_metadata = prepare_variant(
        image,
        {"name": "human_supervision", "max_side": size, "square": True, "crop": False},
        gray,
        metadata,
    )
    return (native, native_metadata)


def weak_targets(gray, metadata, labels):
    height, width = gray.shape
    side = max(gray.shape)
    scale = side / 256
    target = np.zeros((6, height, width), np.float32)
    known = np.zeros_like(target)
    ink, stroke, _ = ink_evidence(gray)
    stroke_bands = {kind: np.zeros(gray.shape, np.uint8) for kind in ("wall", "tick")}
    project_points = lambda points: np.rint(
        project(points, metadata["original_to_working"])
    ).astype(np.int32)
    for record in labels["strokes"]:
        if record["kind"] not in stroke_bands:
            continue
        for identifier in record["line_ids"]:
            line = labels["lines"][identifier]
            a, b = project_points([line["start_px"], line["end_px"]])
            cv2.line(stroke_bands[record["kind"]], tuple(a), tuple(b), 1, max(3, round(scale * 3)))
    wall = stroke_bands["wall"]
    tick = stroke_bands["tick"]
    protect = cv2.dilate(wall | tick, np.ones((max(3, round(scale * 5)) | 1,) * 2, np.uint8))
    for channel, band in [(0, wall), (3, tick)]:
        positive = (band > 0) & (ink > 0)
        target[channel, positive] = 1
        known[channel, positive] = 1
    tick_guard = cv2.dilate(tick, np.ones((max(3, round(scale * 7)) | 1,) * 2, np.uint8))
    known[3, (wall > 0) & (ink > 0) & (tick_guard == 0)] = 0.5
    known[5, (wall > 0) & (ink > 0)] = 0.5
    region_polygons = []
    region_boundary = np.zeros(gray.shape, np.uint8)
    for region in labels["regions"]:
        polygon = project_points(region["polygon_px"])
        region_polygons.append(polygon)
        filled = np.zeros(gray.shape, np.uint8)
        cv2.fillPoly(filled, [polygon], 1)
        margin = max(3, round(scale * 4))
        inside = cv2.erode(filled, np.ones((margin * 2 + 1,) * 2, np.uint8)) > 0
        channel = 2 if region["kind"] == "corridor" else 1
        target[channel, inside] = 1
        known[channel, inside] = 0.7
        known[3 - channel, inside] = 0.7
        for other in (0, 3, 4, 5):
            known[other, inside & (protect == 0)] = 0.25
        cv2.polylines(region_boundary, [polygon], True, 1, max(1, round(scale)))
    for channel in (1, 2):
        target[channel, region_boundary > 0] = 0
        known[channel, region_boundary > 0] = 0.2
    if region_polygons:
        points = np.concatenate(region_polygons)
        lo = np.floor(points.min(axis=0) - side * 0.05).astype(int)
        hi = np.ceil(points.max(axis=0) + side * 0.05).astype(int)
        outside = np.ones(gray.shape, bool)
        outside[max(0, lo[1]) : min(height, hi[1] + 1), max(0, lo[0]) : min(width, hi[0] + 1)] = (
            False
        )
        for channel in (1, 2):
            known[channel, outside] = 0.5
    distractors = np.zeros(gray.shape, np.uint8)
    for polygon in labels["distractor_polygons"]:
        cv2.fillPoly(distractors, [project_points(polygon)], 1)
    negative = (distractors > 0) & (ink > 0) & (protect == 0)
    for channel in (0, 3, 4, 5):
        target[channel, negative] = 0
        known[channel, negative] = 1
    for junction in labels["junctions"]:
        x, y = project_points([junction["point_px"]])[0]
        region = np.zeros(gray.shape, np.uint8)
        cv2.circle(region, (int(x), int(y)), max(1, round(scale)), 1, -1)
        target[4, region > 0] = 1
        known[4, region > 0] = 0.5
    for gap in labels["gaps"]:
        mask = np.zeros(gray.shape, np.uint8)
        a, b = project_points([gap["start_px"], gap["end_px"]])
        cv2.line(mask, tuple(a), tuple(b), 1, max(1, round(scale)))
        if gap["kind"] not in ("door", "open_passage"):
            target[3, mask > 0] = 0
            known[3, mask > 0] = 0.5
        if gap["kind"] == "open_passage":
            target[5, mask > 0] = 1
            known[5, mask > 0] = 0.7
        else:
            known[5, mask > 0] = 0.5
        for channel in (1, 2):
            target[channel, mask > 0] = 0
            known[channel, mask > 0] = 0.2
    return (
        target,
        known,
        {
            "known_fraction": float((known > 0).mean()),
            "positive_pixels_by_channel": [
                int(((target[i] > 0) & (known[i] > 0)).sum()) for i in range(6)
            ],
            "text_ink_negative_pixels": int(negative.sum()),
            "unknown_pixels_ignored": True,
            "human_dense_ground_truth": False,
            "numeric_transcription_used": False,
        },
    )


def freeze(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "protocol.json"
    if path.exists():
        return json.loads(path.read_text())
    split = json.loads((ROOT / "Saved/Evaluation/v1/split.json").read_text())
    inventory = json.loads((ROOT / "Data/augmented/v1/manifest_with_originals.json").read_text())[
        "samples"
    ]
    samples = [r for r in inventory if r["origin"] == "human"]
    roles = {
        part: sorted(
            (
                int(r["id"].split("_")[1])
                for r in samples
                if split["group_split"][r["base_plan_id"]] == part
            )
        )
        for part in ("train", "validation", "test")
    }
    known = [3, 8, 18, 31, 41, 45]
    excluded = sorted(set(roles["test"]) & set(known))
    groups = {
        r["id"]: {
            "base_plan_id": r["base_plan_id"],
            "writer_id": r.get("writer_id"),
            "split": split["group_split"][r["base_plan_id"]],
            "image_sha256": r["image_sha256"],
        }
        for r in samples
    }
    value = {
        "version": "shape-human-adaptation/1.3",
        "date": "2026-11-04",
        "seed": 41126,
        "human_splits": roles,
        "previously_inspected_diagnostic_ids": known,
        "reserved_development_evaluation_ids": sorted(set(roles["test"]) - set(known)),
        "test_ids_previously_used_in_decoder_diagnostics": excluded,
        "groups": groups,
        "writer_holdout": False,
        "scope": "Retrospective development; preserve original parent split. All images previously curated; not unseen-writer evaluation.",
        "training": {
            "epochs": 12,
            "checkpoints": [4, 8, 12],
            "batch_size": 8,
            "learning_rate": 0.0002,
            "recipe": "marker_heads_only",
            "teacher_weight": 0.5,
            "normalize_ink": True,
            "normalizer_version": "shape-photo-paper/1.1",
            "human_views_per_parent": 4,
            "human_repeats": 2,
            "synthetic_samples_per_epoch": 192,
            "dense_synthetic_weight": 1.0,
            "masked_human_weight": 1.0,
            "synthetic_seeds": list(range(1000, 1096)),
            "selection": "Maximize validation region F1 + opening F1 with synthetic F1 floors; never select from test outcomes.",
        },
        "validation_synthetic_ids": [f"{n}_wavy" for n in range(2000, 2006)],
        "targets": {
            "validation_region_f1_floor": 0.6,
            "validation_opening_precision_floor": 0.8,
            "synthetic_validation_region_f1_floor": 0.85,
            "synthetic_validation_opening_f1_floor": 0.8,
            "reserved_opening_precision": 0.8,
            "reserved_opening_recall": 0.5,
        },
        "base_model_lock": json.loads(
            (ROOT / "SketchPipeline/shape_authoring/models.lock.json").read_text()
        ),
        "curation_sha256": sha(CURATION),
        "historical_split_sha256": sha(ROOT / "Saved/Evaluation/v1/split.json"),
        "protected_data": {
            str(p.relative_to(ROOT)): sha(p)
            for p in (ROOT / "Data").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        },
        "labels": "Masked weak structural supervision; uncertain pixels weight zero, no numeric text or physical dimensions.",
        "source_license": "Existing project drawings and new procedural renders; no externally sourced training image or pretrained weight.",
        "weights_license": "Project-authored derivative weights; repository redistribution license remains unspecified.",
    }
    parent_roles = {}
    hash_roles = {}
    for r in inventory:
        role = split["group_split"][r["base_plan_id"]]
        parent_roles.setdefault(r["base_plan_id"], set()).add(role)
        hash_roles.setdefault(r["image_sha256"], set()).add(role)
    if any((len(v) > 1 for v in list(parent_roles.values()) + list(hash_roles.values()))):
        raise ValueError("Group or image leakage")
    value["leakage_audit"] = {
        "parent_split_consistent": True,
        "identical_image_split_consistent": True,
        "derived_views_inherit_parent": True,
        "writer_train_test_overlap": sorted(
            {
                groups[f"Data_{n}"]["writer_id"]
                for n in roles["train"]
                if groups[f"Data_{n}"]["writer_id"]
            }
            & {
                groups[f"Data_{n}"]["writer_id"]
                for n in roles["test"]
                if groups[f"Data_{n}"]["writer_id"]
            }
        ),
    }
    write_json(path, value)
    return value
