import argparse
import copy
import json
from pathlib import Path
import shutil
import time
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.perception.structural import suppress_grid
from .dino_model import (
    ROOT,
    LOCK,
    ARCHITECTURE,
    CHANNELS,
    LAYERS,
    INPUT_SIDE,
    DinoDecoder,
    prepare_tensors,
    extract_features,
    load_backbone,
    sha,
)
from .human_supervision import (
    freeze as human_freeze,
    prepare_human,
    structural_labels,
    weak_targets,
    source_image,
    CURATION,
)
from .diagnostic_preprocessing import prepare_variant, suggest_crop
from .propose import prepare_image, run
from .synthetic import render, write_json
from .pilot import score, aggregate, synthetic_reference
from .human_error_review import reference
from .diagnose import panel


def auxiliary_targets(gray, metadata, labels, target, known):
    h, w = gray.shape
    scale = max(gray.shape) / 256
    extra = np.zeros((2, h, w), np.float32)
    weights = np.zeros_like(extra)
    weights[0] = known[3] * 0.5
    weights[1] = np.maximum(known[1], known[2]) * 0.5
    forward = lambda points: np.rint(project(points, metadata["original_to_working"])).astype(
        np.int32
    )
    for region in labels["regions"]:
        polygon = forward(region["polygon_px"])
        cv2.polylines(extra[1], [polygon], True, 1, max(2, round(3 * scale)))
    weights[1, extra[1] > 0] = 1
    for gap in labels["gaps"]:
        if gap["kind"] != "door":
            continue
        for x, y in forward([gap["start_px"], gap["end_px"]]):
            cv2.circle(extra[0], (int(x), int(y)), max(2, round(3 * scale)), 1, -1)
    weights[0, extra[0] > 0] = 1
    return (np.concatenate([target, extra]), np.concatenate([known, weights]))


def synthetic_targets(masks, spec):
    target = np.zeros((len(CHANNELS), 256, 256), np.uint8)
    target[:6] = (masks > 0).astype(np.uint8)
    for region in spec["regions"]:
        x, y, X, Y = map(int, region["bounds_px"])
        cv2.rectangle(target[7], (x, y), (X, Y), 1, 3)
    for opening in spec["openings"]:
        if opening["type"] != "door":
            continue
        for t in opening["interval"]:
            point = [t, opening["fixed"]] if opening["axis"] == 0 else [opening["fixed"], t]
            cv2.circle(target[6], tuple(np.rint(point).astype(int)), 3, 1, -1)
    return (target, np.ones_like(target, np.float32))


def freeze(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "protocol.json"
    if path.exists():
        return json.loads(path.read_text())
    base = human_freeze(output / "data-split")
    value = {
        "version": "dino-shape-pilot/1.0",
        "date": "2026-11-04",
        "seed": 51104,
        "human_splits": base["human_splits"],
        "groups": base["groups"],
        "protected_data": base["protected_data"],
        "curation_sha256": sha(CURATION),
        "backbone_lock_sha256": sha(LOCK),
        "backbone_lock": json.loads(LOCK.read_text()),
        "base_model_lock": base["base_model_lock"],
        "channels": CHANNELS,
        "input_side": INPUT_SIDE,
        "feature_layers": LAYERS,
        "backbone_frozen": True,
        "train_synthetic_parents": list(range(1000, 1096)),
        "train_synthetic_styles": ["clean", "wavy", "grid", "stray"],
        "validation_synthetic_ids": [f"{n}_wavy" for n in range(2000, 2006)],
        "training": {
            "epochs": 40,
            "checkpoints": [10, 20, 40],
            "batch_size": 8,
            "width": 32,
            "learning_rate": 0.001,
            "weight_decay": 0.0001,
            "human_repeats": 2,
            "loss_positive_weights": [5, 1, 4, 12, 8, 12, 15, 8],
        },
        "selection": "Max human validation region F1 + correctly-attached opening F1, subject to synthetic region F1>=.80 and attached-opening F1>=.75; tie goes to earlier epoch. No retrospective/test selection.",
        "evaluation_ids": list(range(1, 51)),
        "evaluation_scope": "All existing human plans were previously curated; the old test split was inspected in prior experiments. Retrospective diagnostic only, not a fresh blind or writer-disjoint evaluation.",
        "writer_holdout": False,
        "writer_overlap": base["leakage_audit"]["writer_train_test_overlap"],
        "targets": {
            "human_region_recall": 0.6,
            "human_attached_opening_recall": 0.5,
            "human_attached_opening_precision": 0.8,
            "synthetic_attached_opening_precision": 0.95,
            "synthetic_attached_opening_recall": 0.8,
        },
        "numeric_text_read": False,
        "physical_sizes_used_for_training": False,
        "reference_policy_version": "structural-openings/2.0",
    }
    write_json(path, value)
    sources = [p for p in Path(__file__).parent.glob("*.py")] + [
        LOCK,
        CURATION,
        Path(__file__).with_name("decoder_refined.config.json"),
    ]
    hashes = {}
    for source in sources:
        relative = source.relative_to(ROOT)
        destination = output / "source_snapshot" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[str(relative)] = sha(source)
    write_json(
        output / "source-freeze.json", {"source_hashes": hashes, "protocol_sha256": sha(path)}
    )
    return value


def human_views(n):
    labels = structural_labels(n)
    native, metadata = prepare_human(n, 512)
    target, known, _ = weak_targets(native, metadata, labels)
    target, known = auxiliary_targets(native, metadata, labels, target, known)
    bounds = metadata.get("diagnostic_content_bounds_px", [0, 0, 512, 512])
    views = [("full_square", native, target, known, bounds)]
    baseline, base_meta = prepare_image(source_image(n))
    crop, _ = suggest_crop(source_image(n))
    cropped, cmeta = prepare_variant(
        source_image(n),
        {"name": "dino_training_crop", "max_side": 512, "square": True, "crop": True},
        baseline,
        base_meta,
        crop,
    )
    ct, ck, _ = weak_targets(cropped, cmeta, labels)
    ct, ck = auxiliary_targets(cropped, cmeta, labels, ct, ck)
    views.append(("image_only_crop", cropped, ct, ck, cmeta.get("diagnostic_content_bounds_px")))
    rng = np.random.default_rng(51104 + n)
    for channel, name in [(6, "endpoint_tile"), (0, "wall_tile")]:
        choices = np.argwhere((target[channel] > 0) & (known[channel] > 0))
        center = choices[int(rng.integers(len(choices)))] if len(choices) else np.array([256, 256])
        top, left = np.clip(center - 128, 0, 256).astype(int)
        b = [
            max(0, bounds[0] - left),
            max(0, bounds[1] - top),
            min(256, bounds[2] - left),
            min(256, bounds[3] - top),
        ]
        if b[0] >= b[2] or b[1] >= b[3]:
            b = None
        views.append(
            (
                name,
                native[top : top + 256, left : left + 256],
                target[:, top : top + 256, left : left + 256],
                known[:, top : top + 256, left : left + 256],
                b,
            )
        )
    return views


def prepare_cache(output, device):
    output = Path(output).resolve()
    p = freeze(output)
    cache = output / "cache"
    manifest = cache / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    cache.mkdir(exist_ok=True)
    records = []
    count = len(p["human_splits"]["train"]) * 4 + len(p["train_synthetic_parents"]) * len(
        p["train_synthetic_styles"]
    )
    arrays = {
        name: np.lib.format.open_memmap(
            cache / (name + ".npy"), mode="w+", dtype=dtype, shape=shape
        )
        for name, dtype, shape in [
            ("gray", np.uint8, (count, 448, 448)),
            ("ink", np.float16, (count, 2, 256, 256)),
            ("target", np.uint8, (count, len(CHANNELS), 256, 256)),
            ("known", np.float16, (count, len(CHANNELS), 256, 256)),
        ]
    }
    from .contrast import normalize_ink

    def append(gray, target, known, bounds, record, normalize):
        clean, _, _ = suppress_grid(gray)
        if normalize:
            gray, _ = normalize_ink(gray, bounds)
            clean, _ = normalize_ink(clean, bounds)
        rgb, ink, _ = prepare_tensors(gray, clean)
        index = len(records)
        arrays["gray"][index] = (
            np.rint((rgb[0] * 0.229 + 0.485) * 255).clip(0, 255).astype(np.uint8)
        )
        arrays["ink"][index] = ink
        arrays["target"][index] = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in target]
        ).astype(np.uint8)
        arrays["known"][index] = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in known]
        )
        records.append(record)

    for n in p["human_splits"]["train"]:
        for name, gray, target, known, bounds in human_views(n):
            append(
                gray,
                target,
                known,
                bounds,
                {
                    "origin": "human",
                    "sample_id": f"Data_{n}",
                    "view": name,
                    "parent": p["groups"][f"Data_{n}"]["base_plan_id"],
                    "role": "train",
                    "source_sha256": sha(source_image(n)),
                },
                True,
            )
        print(json.dumps({"prepared_human": n}), flush=True)
    for seed in p["train_synthetic_parents"]:
        for style in p["train_synthetic_styles"]:
            gray, masks, spec = render(seed, style)
            target, known = synthetic_targets(masks, spec)
            append(
                gray,
                target,
                known,
                None,
                {
                    "origin": "synthetic",
                    "sample_id": f"{seed}_{style}",
                    "parent": f"synthetic_{seed}",
                    "role": "train",
                },
                False,
            )
    for array in arrays.values():
        array.flush()
    backbone = load_backbone(device)
    started = time.perf_counter()
    features = np.lib.format.open_memmap(
        cache / "features.npy", mode="w+", dtype=np.float16, shape=(count, 4, 384, 32, 32)
    )
    for start in range(0, count, 2):
        gray = arrays["gray"][start : start + 2].astype(np.float32) / 255
        rgb = np.repeat(gray[:, None], 3, axis=1)
        rgb = (rgb - np.array([0.485, 0.456, 0.406], np.float32)[None, :, None, None]) / np.array(
            [0.229, 0.224, 0.225], np.float32
        )[None, :, None, None]
        batch = extract_features(backbone, torch.from_numpy(rgb).to(device)).detach().cpu().numpy()
        features[start : start + len(batch)] = batch
        if start % 40 == 0:
            print(
                json.dumps(
                    {
                        "encoded": start + len(batch),
                        "total": count,
                        "seconds": time.perf_counter() - started,
                    }
                ),
                flush=True,
            )
    features.flush()
    value = {
        "version": "dino-feature-cache/1.0",
        "records": records,
        "count": count,
        "encoder_seconds": time.perf_counter() - started,
        "feature_device": device,
        "backbone_sha256": p["backbone_lock"]["checkpoint_sha256"],
        "backbone_lock_sha256": sha(LOCK),
        "train_parent_humans": len(p["human_splits"]["train"]),
        "human_views": 140,
        "unknown_human_pixels_ignored": True,
        "numeric_transcription_used": False,
        "files": {str(path.name): sha(path) for path in sorted(cache.glob("*.npy"))},
    }
    write_json(manifest, value)
    return value


def masked_loss(logits, target, known, positive_weights):
    positive = torch.as_tensor(positive_weights, device=logits.device, dtype=logits.dtype)[
        None, :, None, None
    ]
    count = known.sum((2, 3))
    active = count > 0
    bce = F.binary_cross_entropy_with_logits(logits, target, pos_weight=positive, reduction="none")
    per = (bce * known).sum((2, 3)) / count.clamp_min(1)
    probability = logits.sigmoid()
    dice = 1 - (2 * (probability * target * known).sum((2, 3)) + 1) / (
        (probability * known).sum((2, 3)) + (target * known).sum((2, 3)) + 1
    )
    return ((per + dice) * active).sum() / active.sum().clamp_min(1)


def attached_counts(rows):
    predicted = sum(
        (
            r["metrics"]["openings"]["predicted"]
            for r in rows
            if r.get("reference_has_regions", True)
        )
    )
    reference = sum((r["attachment_reference_count"] for r in rows))
    correct = sum((r["metrics"]["attachment_correct"] for r in rows))
    from SketchPipeline.evaluation.metrics import counts

    return counts(correct, predicted, reference)


def summarize(rows):
    result = aggregate(rows)
    result["attached_openings"] = attached_counts(rows)
    return result


def score_human(n, directory, checkpoint):
    result = run(
        source_image(n),
        directory,
        checkpoint=checkpoint,
        expected_sha256=sha(checkpoint),
        profile="refined-full",
        normalize_ink=True,
    )
    if result["failure"]:
        raise RuntimeError(f"Data {n}: " + result["failure"])
    ref = reference(n, result["preprocessing"])
    metrics = score(result["authoring"], ref, result["preprocessing"]["working_size_px"])
    row = {
        "sample_id": f"Data_{n}",
        "origin": "human",
        "status": result["status"],
        "failure": result["failure"],
        "elapsed_seconds": result["elapsed_seconds"],
        "metrics": metrics,
        "reference_has_regions": bool(ref["regions"]),
        "attachment_reference_count": sum((bool(g["entity_ids"]) for g in ref["openings"])),
    }
    write_json(directory / "metrics.json", row)
    with np.load(directory / "model-masks.npz") as data:
        probabilities = data["probabilities"]
    gray = cv2.imread(str(directory / "working.png"), 0)
    panel(gray, probabilities, result["authoring"], ref, directory / "comparison.png")
    return row


def score_synthetic(sample, directory, checkpoint):
    from .decoder_refined import decode

    folder = ROOT / "Saved/ShapeFirst/v1/development" / sample
    result = run(
        folder / "source.png",
        directory,
        checkpoint=checkpoint,
        expected_sha256=sha(checkpoint),
        profile="refined-full",
    )
    if result["failure"]:
        raise RuntimeError(sample + ": " + result["failure"])
    ref = synthetic_reference(folder / "reference.json")
    row = {
        "sample_id": sample,
        "origin": "synthetic",
        "status": result["status"],
        "elapsed_seconds": result["elapsed_seconds"],
        "metrics": score(result["authoring"], ref, result["preprocessing"]["working_size_px"]),
        "reference_has_regions": True,
        "attachment_reference_count": len(ref["openings"]),
    }
    write_json(directory / "metrics.json", row)
    return row


def validation(checkpoint, output, p):
    human = [
        score_human(n, output / f"Data_{n}", checkpoint) for n in p["human_splits"]["validation"]
    ]
    synthetic = [score_synthetic(s, output / s, checkpoint) for s in p["validation_synthetic_ids"]]
    h, s = (summarize(human), summarize(synthetic))
    eligible = (s["regions"]["f1"] or 0) >= 0.8 and (s["attached_openings"]["f1"] or 0) >= 0.75
    objective = (h["regions"]["f1"] or 0) + (h["attached_openings"]["f1"] or 0)
    value = {
        "human": h,
        "synthetic": s,
        "objective": objective,
        "eligible_synthetic_guard": eligible,
        "human_rows": human,
        "synthetic_rows": synthetic,
        "test_used": False,
    }
    write_json(output / "summary.json", value)
    return value


def train(output, device):
    output = Path(output).resolve()
    p = freeze(output)
    prepare_cache(output, device)
    directory = output / "training"
    directory.mkdir(exist_ok=False)
    torch.manual_seed(p["seed"])
    rng = np.random.default_rng(p["seed"])
    cache = output / "cache"
    manifest = json.loads((cache / "manifest.json").read_text())
    arrays = {
        name: np.load(cache / (name + ".npy"), mmap_mode="r")
        for name in ["features", "ink", "target", "known"]
    }
    model = DinoDecoder(p["training"]["width"]).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=p["training"]["learning_rate"],
        weight_decay=p["training"]["weight_decay"],
    )
    human = [i for i, r in enumerate(manifest["records"]) if r["origin"] == "human"]
    synthetic = [i for i, r in enumerate(manifest["records"]) if r["origin"] == "synthetic"]
    history = []
    candidates = []
    started = time.perf_counter()
    batch = p["training"]["batch_size"]
    for epoch in range(1, p["training"]["epochs"] + 1):
        model.train()
        order = np.asarray(human * p["training"]["human_repeats"] + synthetic)
        rng.shuffle(order)
        losses = []
        for start in range(0, len(order), batch):
            indices = order[start : start + batch]
            feature, ink, target, known = [
                torch.from_numpy(np.asarray(arrays[name][indices], dtype=np.float32)).to(device)
                for name in ["features", "ink", "target", "known"]
            ]
            logits = model(feature, ink)
            loss = masked_loss(logits, target, known, p["training"]["loss_positive_weights"])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        item = {
            "epoch": epoch,
            "loss": float(np.mean(losses)),
            "elapsed_seconds": time.perf_counter() - started,
        }
        history.append(item)
        print(json.dumps(item), flush=True)
        if epoch in p["training"]["checkpoints"]:
            checkpoint = directory / f"epoch_{epoch}.pt"
            state = {key: value.detach().cpu() for key, value in model.state_dict().items()}
            torch.save(
                {
                    "architecture": ARCHITECTURE,
                    "channels": CHANNELS,
                    "width": p["training"]["width"],
                    "state_dict": state,
                    "backbone_lock_sha256": sha(LOCK),
                    "protocol_sha256": sha(output / "protocol.json"),
                    "epoch": epoch,
                },
                checkpoint,
            )
            checked = validation(checkpoint, directory / f"validation_epoch_{epoch}", p)
            candidate = {
                "epoch": epoch,
                "path": str(checkpoint.relative_to(ROOT)),
                "sha256": sha(checkpoint),
                "objective": checked["objective"],
                "eligible": checked["eligible_synthetic_guard"],
            }
            candidates.append(candidate)
            print(json.dumps({"validation": candidate, "human": checked["human"]}), flush=True)
    eligible = [c for c in candidates if c["eligible"]]
    selected = max(eligible or candidates, key=lambda c: (c["objective"], -c["epoch"]))
    report = {
        "selected": selected,
        "candidates": candidates,
        "history": history,
        "device": device,
        "selection_used_test": False,
        "synthetic_guard_passed": bool(eligible),
        "backbone_updated": False,
        "training_seconds": time.perf_counter() - started,
        "backbone_license": "Apache-2.0",
        "model_promoted": False,
    }
    write_json(output / "training_report.json", report)
    print(json.dumps({"selected": selected}), flush=True)


def evaluate(output):
    output = Path(output).resolve()
    p = freeze(output)
    training = json.loads((output / "training_report.json").read_text())
    selected = training["selected"]
    checkpoint = ROOT / selected["path"]
    if sha(checkpoint) != selected["sha256"] or training["selection_used_test"]:
        raise ValueError("Selection or checkpoint mismatch")
    directory = output / "evaluation"
    directory.mkdir(exist_ok=False)
    write_json(
        directory / "freeze.json",
        {
            "selected": selected,
            "training_report_sha256": sha(output / "training_report.json"),
            "protocol_sha256": sha(output / "protocol.json"),
            "scope": p["evaluation_scope"],
            "further_model_selection_from_these_results": False,
        },
    )
    baseline = ROOT / p["base_model_lock"]["checkpoint_path"]
    rows = []
    figures = []
    for n in p["evaluation_ids"]:
        print(json.dumps({"evaluate_human": n}), flush=True)
        for arm, model in [("baseline", baseline), ("dino", checkpoint)]:
            row = score_human(n, directory / "human" / f"Data_{n}" / arm, model)
            row.update(arm=arm, role=p["groups"][f"Data_{n}"]["split"])
            rows.append(row)
            figures.append(
                f"""<figure><figcaption>Data {n} · {row['role']} · {arm} · regions {row['metrics']['regions']} · openings {row['metrics']['openings']} · attachment {row['metrics']['attachment_correct']}/{row['metrics']['attachment_scorable']}</figcaption><img loading="lazy" src="human/Data_{n}/{arm}/comparison.png"></figure>"""
            )
    syn = []
    for seed in range(2000, 2012):
        for style in ["clean", "wavy", "grid", "stray", "broken"]:
            sample = f"{seed}_{style}"
            for arm, model in [("baseline", baseline), ("dino", checkpoint)]:
                row = score_synthetic(sample, directory / "synthetic" / sample / arm, model)
                row["arm"] = arm
                syn.append(row)
    summaries = {
        arm: {
            role: summarize([r for r in rows if r["arm"] == arm and r["role"] == role])
            for role in ["train", "validation", "test"]
        }
        for arm in ["baseline", "dino"]
    }
    synthetic = {
        arm: summarize([r for r in syn if r["arm"] == arm]) for arm in ["baseline", "dino"]
    }
    changed = [path for path, digest in p["protected_data"].items() if sha(ROOT / path) != digest]
    if changed:
        raise ValueError("Protected data changed")
    h = summaries["dino"]["test"]
    s = synthetic["dino"]
    targets = p["targets"]
    gates = {
        "human_region_recall": (h["regions"]["recall"] or 0) >= targets["human_region_recall"],
        "human_attached_opening_recall": (h["attached_openings"]["recall"] or 0)
        >= targets["human_attached_opening_recall"],
        "human_attached_opening_precision": (h["attached_openings"]["precision"] or 0)
        >= targets["human_attached_opening_precision"],
        "synthetic_attached_opening_precision": (s["attached_openings"]["precision"] or 0)
        >= targets["synthetic_attached_opening_precision"],
        "synthetic_attached_opening_recall": (s["attached_openings"]["recall"] or 0)
        >= targets["synthetic_attached_opening_recall"],
        "validation_synthetic_guard": training["synthetic_guard_passed"],
    }
    value = {
        "version": "dino-shape-evaluation/1.0",
        "selected": selected,
        "scope": p["evaluation_scope"],
        "human": summaries,
        "synthetic": synthetic,
        "rows": rows,
        "synthetic_rows": syn,
        "gates": gates,
        "all_gates_passed": all(gates.values()),
        "model_promoted": False,
        "protected_data_files_checked": len(p["protected_data"]),
        "protected_data_changed": changed,
        "writer_holdout": False,
        "writer_overlap": p["writer_overlap"],
        "reference_policy_version": "structural-openings/2.0",
        "baseline_human_photo_normalized": True,
        "baseline_profile": "refined-full",
        "human_attachment_reference": "Approximate nearest polygon boundaries; missing region references excluded from attached-opening denominator.",
        "human_correction_time_seconds": None,
        "numeric_ocr_called": False,
        "unreal_export_automatically_accepted": False,
    }
    write_json(output / "report.json", value)
    (directory / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>DINOv2 shape pilot</title><style>body{font:14px system-ui;margin:24px}figure{padding:12px;border:1px solid #ccc}img{max-width:100%}figcaption{overflow-wrap:anywhere}</style><h1>DINOv2 shape pilot</h1><p>Retrospective development comparison; original train/validation/test roles shown. Train results are training fit. No fresh blind or unseen-writer claim. Green: approximate references, orange: predicted regions, red: opening proposals.</p>'
        + "".join(figures)
    )
    print(json.dumps({"human": summaries, "synthetic": synthetic, "gates": gates}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "train", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "mps", "auto"], default="auto")
    args = parser.parse_args()
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    device = (
        ("mps" if torch.backends.mps.is_available() else "cpu")
        if args.device == "auto"
        else args.device
    )
    if args.stage == "prepare":
        prepare_cache(args.output, device)
    elif args.stage == "train":
        train(args.output, device)
    else:
        evaluate(args.output)


if __name__ == "__main__":
    main()
