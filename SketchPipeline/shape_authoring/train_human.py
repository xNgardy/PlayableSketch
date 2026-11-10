import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
import torch
import torch.nn.functional as F
from SketchPipeline.perception.structural import suppress_grid
from .human_supervision import (
    ROOT,
    CURATION,
    freeze,
    sha,
    prepare_human,
    structural_labels,
    weak_targets,
    source_image,
)
from .diagnostic_preprocessing import suggest_crop, prepare_variant
from .model import ShapeUNet, ARCHITECTURE, features
from .propose import prepare_image, run
from .human_error_review import reference
from .pilot import score, aggregate, synthetic_reference
from .synthetic import CHANNELS, write_json


def masked_loss(logits, target, known):
    positive = torch.tensor([5.0, 1.0, 4.0, 14.0, 10.0, 15.0], device=logits.device).reshape(
        1, -1, 1, 1
    )
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none", pos_weight=positive)
    count = known.sum((2, 3))
    active = count > 0
    per = (bce * known).sum((2, 3)) / count.clamp_min(1)
    probability = logits.sigmoid()
    dice = 1 - (2 * (probability * target * known).sum((2, 3)) + 1) / (
        (probability * known).sum((2, 3)) + (target * known).sum((2, 3)) + 1
    )
    return ((per + dice) * active).sum() / active.sum().clamp_min(1)


def prepare_cache(output):
    protocol = freeze(output)
    cache = output / "human-training.npz"
    manifest_path = output / "supervision-manifest.json"
    if cache.exists():
        return json.loads(manifest_path.read_text())
    xs = []
    ys = []
    weights = []
    records = []
    audit = []
    for n in protocol["human_splits"]["train"]:
        labels = structural_labels(n)
        native, metadata = prepare_human(n, 512)
        target, known, stats = weak_targets(native, metadata, labels)
        rng = np.random.default_rng(protocol["seed"] + n)
        views = []
        global_gray = cv2.resize(native, (256, 256), interpolation=cv2.INTER_AREA)
        global_target = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in target]
        )
        global_known = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in known]
        )
        native_bounds = metadata.get("diagnostic_content_bounds_px", [0, 0, 512, 512])
        views.append(
            (
                "full_square",
                global_gray,
                global_target,
                global_known,
                [round(v / 2) for v in native_bounds],
            )
        )
        baseline, base_meta = prepare_image(source_image(n))
        crop, _ = suggest_crop(source_image(n))
        cropped, cmeta = prepare_variant(
            source_image(n),
            {"name": "training_crop", "max_side": 256, "square": True, "crop": True},
            baseline,
            base_meta,
            crop,
        )
        ct, ck, _ = weak_targets(cropped, cmeta, labels)
        views.append(
            ("image_only_crop", cropped, ct, ck, cmeta.get("diagnostic_content_bounds_px"))
        )
        for channel, label in [(3, "marker_tile"), (0, "wall_tile")]:
            choices = np.argwhere((target[channel] > 0) & (known[channel] > 0))
            center = (
                choices[int(rng.integers(len(choices)))] if len(choices) else np.array([256, 256])
            )
            top, left = np.clip(center - 128, 0, 256).astype(int)
            bounds = [
                max(0, native_bounds[0] - left),
                max(0, native_bounds[1] - top),
                min(256, native_bounds[2] - left),
                min(256, native_bounds[3] - top),
            ]
            if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                bounds = None
            views.append(
                (
                    label,
                    native[top : top + 256, left : left + 256],
                    target[:, top : top + 256, left : left + 256],
                    known[:, top : top + 256, left : left + 256],
                    bounds,
                )
            )
        for name, image, y, k, bounds in views:
            clean, _, _ = suppress_grid(image)
            if protocol["training"].get("normalize_ink"):
                from .contrast import normalize_ink

                image, _ = normalize_ink(image, bounds)
                clean, _ = normalize_ink(clean, bounds)
            xs.append(features(image, clean).astype(np.float16))
            ys.append(y.astype(np.uint8))
            weights.append(k.astype(np.float16))
            records.append(
                {
                    "image_id": f"Data_{n}",
                    "base_plan_id": protocol["groups"][f"Data_{n}"]["base_plan_id"],
                    "role": "train",
                    "view": name,
                    "known_fraction": float((k > 0).mean()),
                    "source_sha256": sha(source_image(n)),
                }
            )
        colors = np.stack([global_gray] * 3, axis=-1)
        colors[(global_target[0] > 0) & (global_known[0] > 0)] = [20, 170, 70]
        colors[(global_target[3] > 0) & (global_known[3] > 0)] = [230, 40, 40]
        colors[(global_target[3] == 0) & (global_known[3] >= 0.9)] = [70, 100, 240]
        audit.append((n, Image.fromarray(colors), stats))
        print(
            json.dumps({"prepared_human": n, "known_fraction": stats["known_fraction"]}), flush=True
        )
    np.savez_compressed(cache, x=np.stack(xs), y=np.stack(ys), known=np.stack(weights))
    manifest = {
        "version": "masked-human-supervision/1.0",
        "records": records,
        "human_parents": len(protocol["human_splits"]["train"]),
        "human_views": len(records),
        "cache_sha256": sha(cache),
        "curation_sha256": sha(CURATION),
        "unknown_pixels_ignored": True,
        "dense_human_background_masks": False,
        "numeric_transcription_used": False,
        "supervision_audit": {f"Data_{n}": stats for n, image, stats in audit},
        "audit_review_status": "Agent visual QA, weak supervision only; not human-author approval or dense GT.",
    }
    write_json(manifest_path, manifest)
    gallery = output / "label-audit"
    gallery.mkdir(exist_ok=True)
    for start in range(0, len(audit), 6):
        sheet = Image.new("RGB", (900, 620), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (n, image, stats) in enumerate(audit[start : start + 6]):
            x = index % 3 * 300
            y = index // 3 * 310
            sheet.paste(image.resize((280, 280)), (x, y + 22))
            draw.text(
                (x + 3, y + 4), f"Data {n} — known {stats['known_fraction']:.0%}", fill="black"
            )
        sheet.save(gallery / f"sheet_{start // 6 + 1}.jpg")
    return manifest


def augment(x, y, known, rng):
    matrix = cv2.getRotationMatrix2D(
        (127.5, 127.5), float(rng.uniform(-2, 2)), float(rng.uniform(0.93, 1.07))
    )
    matrix[:, 2] += rng.uniform(-5, 5, 2)
    x = np.stack(
        [cv2.warpAffine(c.astype(np.float32), matrix, (256, 256), borderValue=0) for c in x]
    )
    y = np.stack(
        [
            cv2.warpAffine(
                c.astype(np.float32), matrix, (256, 256), flags=cv2.INTER_NEAREST, borderValue=0
            )
            for c in y
        ]
    )
    known = np.stack(
        [
            cv2.warpAffine(
                c.astype(np.float32), matrix, (256, 256), flags=cv2.INTER_NEAREST, borderValue=0
            )
            for c in known
        ]
    )
    gain = float(rng.uniform(0.8, 1.2))
    background = float(rng.uniform(0, 0.12))
    x = np.clip(x * gain + background, 0, 1).astype(np.float32)
    return (x, y, known)


def configure_adaptation(model, recipe, device):
    if recipe not in ("marker_heads_only", "late_decoder_and_structural_heads"):
        raise ValueError("Unknown adaptation recipe")
    marker_only = recipe == "marker_heads_only"
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(
            name.startswith("head.") or (not marker_only and name.startswith("decoder.2."))
        )
    mask = torch.tensor(
        [0.0, 0.0, 0.0, 1.0, 1.0, 0.0] if marker_only else [1.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        device=device,
    )
    model.head.weight.register_hook(lambda gradient: gradient * mask[:, None, None, None])
    model.head.bias.register_hook(lambda gradient: gradient * mask)
    return mask


def validation(checkpoint, output, protocol):
    rows = []
    expected = sha(checkpoint)
    for n in protocol["human_splits"]["validation"]:
        folder = output / f"Data_{n}"
        result = run(
            source_image(n),
            folder,
            checkpoint=checkpoint,
            expected_sha256=expected,
            profile="refined-full",
            normalize_ink=protocol["training"].get("normalize_ink", False),
        )
        ref = reference(n, result["preprocessing"])
        rows.append(
            {
                "sample_id": f"Data_{n}",
                "status": result["status"],
                "elapsed_seconds": result["elapsed_seconds"],
                "metrics": score(
                    result["authoring"], ref, result["preprocessing"]["working_size_px"]
                ),
            }
        )
    humans = aggregate(rows)
    synthetic_rows = []
    for sample in protocol["validation_synthetic_ids"]:
        directory = ROOT / "Saved/ShapeFirst/v1/development" / sample
        result = run(
            directory / "source.png",
            output / sample,
            checkpoint=checkpoint,
            expected_sha256=expected,
            profile="baseline",
        )
        synthetic_rows.append(
            {
                "sample_id": sample,
                "status": result["status"],
                "elapsed_seconds": result["elapsed_seconds"],
                "metrics": score(
                    result["authoring"],
                    synthetic_reference(directory / "reference.json"),
                    result["preprocessing"]["working_size_px"],
                ),
            }
        )
    synthetic = aggregate(synthetic_rows)
    targets = protocol["targets"]
    eligible = (synthetic["regions"]["f1"] or 0) >= targets.get(
        "synthetic_validation_region_f1_floor", 0.85
    ) and (synthetic["openings"]["f1"] or 0) >= targets.get(
        "synthetic_validation_opening_f1_floor", 0.8
    )
    objective = (humans["regions"]["f1"] or 0) + (humans["openings"]["f1"] or 0)
    value = {
        "human_validation": humans,
        "synthetic_validation": synthetic,
        "eligible_synthetic_guard": eligible,
        "selection_objective": objective,
        "rows": rows,
        "synthetic_rows": synthetic_rows,
        "reference_policy_version": "structural-openings/2.0",
        "test_set_used": False,
    }
    write_json(output / "summary.json", value)
    return value


def train(output):
    output = Path(output).resolve()
    protocol = freeze(output)
    manifest = prepare_cache(output)
    training = output / "training"
    training.mkdir(exist_ok=False)
    source_paths = [
        Path(__file__),
        Path(__file__).with_name("human_supervision.py"),
        Path(__file__).with_name("human_error_review.py"),
        Path(__file__).with_name("model.py"),
        Path(__file__).with_name("decoder_refined.py"),
        Path(__file__).with_name("contrast.py"),
        Path(__file__).with_name("propose.py"),
        Path(__file__).with_name("pilot.py"),
    ]
    write_json(
        output / "training-freeze.json",
        {
            "protocol_sha256": sha(output / "protocol.json"),
            "cache_sha256": manifest["cache_sha256"],
            "curation_sha256": sha(CURATION),
            "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in source_paths},
            "validation_only_checkpoint_selection": True,
            "reserved_evaluation_accessed": False,
        },
    )
    torch.manual_seed(protocol["seed"])
    np.random.seed(protocol["seed"])
    random.seed(protocol["seed"])
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    with np.load(output / "human-training.npz") as data:
        hx, hy, hk = (data["x"], data["y"], data["known"])
    with np.load(ROOT / "Saved/ShapeFirst/v1/training.npz") as data:
        sx, sy = (data["x"], data["y"].astype(np.uint8))
    checkpoint = ROOT / protocol["base_model_lock"]["checkpoint_path"]
    if sha(checkpoint) != protocol["base_model_lock"]["checkpoint_sha256"]:
        raise ValueError("Base checkpoint changed")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model = ShapeUNet(state["width"])
    model.load_state_dict(state["state_dict"])
    model.to(device)
    teacher = None
    if protocol["training"].get("recipe") in (
        "late_decoder_and_structural_heads",
        "marker_heads_only",
    ):
        teacher = ShapeUNet(state["width"])
        teacher.load_state_dict(state["state_dict"])
        teacher.to(device).eval()
        for parameter in teacher.parameters():
            parameter.requires_grad_(False)
        configure_adaptation(model, protocol["training"]["recipe"], device)
    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=protocol["training"]["learning_rate"]
    )
    rng = np.random.default_rng(protocol["seed"])
    history = []
    candidates = []
    started = time.perf_counter()
    print(
        json.dumps(
            {
                "training_started": True,
                "device": device,
                "human_views": len(hx),
                "synthetic_pool": len(sx),
            }
        ),
        flush=True,
    )
    for epoch in range(1, protocol["training"]["epochs"] + 1):
        human = [
            ("human", i)
            for i in range(len(hx))
            for _ in range(protocol["training"]["human_repeats"])
        ]
        synthetic = [
            ("synthetic", int(i))
            for i in rng.choice(
                len(sx), protocol["training"]["synthetic_samples_per_epoch"], replace=False
            )
        ]
        order = human + synthetic
        rng.shuffle(order)
        losses = []
        batch_size = protocol["training"]["batch_size"]
        model.train()
        for start in range(0, len(order), batch_size):
            xs = []
            ys = []
            ks = []
            for origin, index in order[start : start + batch_size]:
                x, y, k = (
                    (hx[index], hy[index], hk[index])
                    if origin == "human"
                    else (sx[index], sy[index], np.ones_like(sy[index], np.float32))
                )
                if origin == "human":
                    x, y, k = augment(x, y, k, rng)
                xs.append(x.astype(np.float32))
                ys.append(y.astype(np.float32))
                ks.append(k.astype(np.float32))
            a = torch.from_numpy(np.stack(xs)).to(device)
            target = torch.from_numpy(np.stack(ys)).to(device)
            known = torch.from_numpy(np.stack(ks)).to(device)
            logits = model(a)
            loss = masked_loss(logits, target, known)
            if teacher is not None:
                with torch.no_grad():
                    prior = teacher(a).sigmoid()
                loss = loss + protocol["training"][
                    "teacher_weight"
                ] * F.binary_cross_entropy_with_logits(logits, prior)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        info = {
            "epoch": epoch,
            "mean_loss": float(np.mean(losses)),
            "elapsed_seconds": time.perf_counter() - started,
        }
        history.append(info)
        print(json.dumps(info), flush=True)
        if epoch in protocol["training"]["checkpoints"]:
            path = training / f"epoch_{epoch}.pt"
            model.to("cpu")
            torch.save(
                {
                    "architecture": ARCHITECTURE,
                    "channels": CHANNELS,
                    "width": state["width"],
                    "state_dict": model.state_dict(),
                    "training_protocol_sha256": sha(output / "protocol.json"),
                    "epoch": epoch,
                },
                path,
            )
            checked = validation(path, training / f"validation_epoch_{epoch}", protocol)
            candidates.append(
                {
                    "epoch": epoch,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha(path),
                    "objective": checked["selection_objective"],
                    "eligible": checked["eligible_synthetic_guard"],
                }
            )
            print(
                json.dumps(
                    {
                        "validation_epoch": epoch,
                        "objective": checked["selection_objective"],
                        "eligible": checked["eligible_synthetic_guard"],
                        "human_openings": checked["human_validation"]["openings"],
                    }
                ),
                flush=True,
            )
            model.to(device)
    eligible = [c for c in candidates if c["eligible"]]
    selected = max(eligible or candidates, key=lambda c: (c["objective"], -c["epoch"]))
    report = {
        "version": "human-geometry-finetuning/1.0",
        "device": device,
        "training_seconds": time.perf_counter() - started,
        "history": history,
        "candidates": candidates,
        "selected": selected,
        "selection_used_test": False,
        "synthetic_guard_passed": bool(eligible),
        "model_license": protocol["weights_license"],
        "base_model_sha256": protocol["base_model_lock"]["checkpoint_sha256"],
    }
    write_json(output / "training_report.json", report)
    print(json.dumps({"selected": selected}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        prepare_cache(args.output)
    else:
        train(args.output)
