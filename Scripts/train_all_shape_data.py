import argparse
import copy
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import torch
from SketchPipeline.shape_authoring.dino_model import (
    DinoDecoder,
    load_backbone,
    prepare_tensors,
    extract_features,
    LOCK,
)
from SketchPipeline.shape_authoring.dino_experiment import (
    masked_loss,
    auxiliary_targets,
    synthetic_targets,
)
from SketchPipeline.shape_authoring.human_supervision import structural_labels, weak_targets
from SketchPipeline.shape_authoring.propose import prepare_image
from SketchPipeline.shape_authoring.diagnostic_preprocessing import prepare_variant
from SketchPipeline.shape_authoring.contrast import normalize_ink
from SketchPipeline.perception.structural import suppress_grid
from SketchPipeline.shape_authoring.diagnose_new20 import reference as new_reference
from SketchPipeline.shape_authoring.synthetic import render
from Scripts.evaluate_augmented_shape import (
    read,
    save,
    sha,
    transform_reference,
    source_reference,
    inventory as old_inventory,
)

OUT = ROOT / "Saved/ShapeFirst/all_data_training/v1"
ADDON = ROOT / "Data/synthetic/corridor_addon_v1"
OVERRIDES = ROOT / "Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json"
AUDIT = ROOT / "Saved/ShapeFirst/augmented_robustness/v2"
POSITIVE = [5, 1, 4, 12, 8, 12, 15, 8]


def human_labels(n):
    labels = structural_labels(n)
    if n >= 51:
        _, raw = new_reference(n, {"original_to_working": np.eye(3).tolist()}, read(OVERRIDES))
        labels["regions"] = copy.deepcopy(raw["regions"])
        labels["gaps"] = [
            g for g in labels["gaps"] if g["kind"] not in ("door", "open_passage")
        ] + copy.deepcopy(raw["openings"])
        for c in read(OVERRIDES)["changes"]:
            if c["sample_id"] != f"Data_{n}":
                continue
            line = c["related_observation_error"]
            identifier = line["line_id"]
            assert labels["lines"][identifier]["start_px"] == line["old_start_px"]
            assert labels["lines"][identifier]["end_px"] == line["old_end_px"]
            labels["lines"][identifier] = {
                "start_px": line["proposed_start_px"],
                "end_px": line["proposed_end_px"],
            }
    return labels


def labels_from_files(side_path, obs_path):
    side = read(side_path)
    obs = read(obs_path)
    return {
        "regions": side.get("regions", []),
        "gaps": side["gaps"],
        "strokes": side["strokes"],
        "lines": {
            v["id"]: {"start_px": v["start_px"], "end_px": v["end_px"]} for v in obs["lines"]
        },
        "junctions": side["junctions"],
        "distractor_polygons": [v["polygon_px"] for v in obs["texts"] if v.get("polygon_px")],
    }


def structural_reference(raw):
    regions = []
    for v in raw["regions"]:
        p = np.asarray(v["polygon_px"])
        regions.append(
            {
                "id": v["region_id"],
                "type": "room" if v["kind"] == "room" else "corridor_segment",
                "polygon": p.tolist(),
                "bounds_px": np.r_[p.min(0), p.max(0)].tolist(),
            }
        )
    openings = [
        {
            "id": g["id"],
            "type": g["kind"],
            "points_px": [g["start_px"], g["end_px"]],
            "entity_ids": g["entity_ids"],
        }
        for g in raw["openings"]
    ]
    return {"regions": regions, "openings": openings, "approximate_human_labels": True}


def replay_reference(spec):
    regions = []
    for r in spec["regions"]:
        x, y, X, Y = r["bounds_px"]
        regions.append({**r, "polygon": [[x, y], [X, y], [X, Y], [x, Y]]})
    openings = []
    for g in spec["openings"]:
        points = [[t, g["fixed"]] if g["axis"] == 0 else [g["fixed"], t] for t in g["interval"]]
        openings.append({**g, "points_px": points})
    return {"regions": regions, "openings": openings, "approximate_human_labels": False}


def records():
    items = []
    for e in read(AUDIT / "inventory.json")["samples"]:
        H = np.eye(3)
        if e["profile"] != "original":
            folder = ROOT / (
                "Data/augmented/new20_v1" if e["cohort"] == "new20" else "Data/augmented/v1"
            )
            H = np.asarray(
                read(folder / "transforms" / f"{e['sample_id']}.json")["source_to_augmented"]
            )
        items.append(
            {
                "id": e["sample_id"],
                "image": e["source_image"],
                "sha256": e["source_sha256"],
                "source_id": e["source_id"],
                "cohort": e["cohort"],
                "origin": e["source_origin"],
                "profile": e["profile"],
                "parent": e["base_plan_id"],
                "H": H.tolist(),
                "kind": "human" if e["source_origin"] == "human" else "rendered",
            }
        )
    for e in read(ADDON / "manifest.json")["samples"]:
        if e["origin"] == "human":
            continue
        human = e["origin"] == "human_derivative"
        H = (
            read(ADDON / "transforms" / f"{e['id']}.json")["matrix"]
            if human
            else np.eye(3).tolist()
        )
        items.append(
            {
                "id": e["id"],
                "image": str((ADDON / e["image_path"]).resolve()),
                "sha256": e["image_sha256"],
                "source_id": e.get("parent_id", e["id"]),
                "cohort": "addon_human" if human else "addon_dense",
                "origin": "human" if human else "synthetic",
                "profile": e["id"].split("_")[-1] if human else "original",
                "parent": e["base_plan_id"],
                "H": H,
                "kind": "human" if human else "dense",
                "target_path": str(ADDON / e["targets_path"]),
                "reference_path": str(ADDON / e["structural_reference_path"]),
            }
        )
    for seed in range(1000, 1096):
        for style in ["clean", "wavy", "grid", "stray"]:
            items.append(
                {
                    "id": f"replay_{seed}_{style}",
                    "source_id": f"{seed}_{style}",
                    "cohort": "synthetic_replay",
                    "origin": "synthetic",
                    "profile": style,
                    "parent": f"replay_{seed}",
                    "kind": "replay",
                    "seed": seed,
                    "style": style,
                    "H": np.eye(3).tolist(),
                }
            )
    from SketchPipeline.shape_authoring.evaluate_unified_areas import cases

    for origin, sample, _, folder in cases():
        if origin != "synthetic":
            continue
        seed, style = sample.split("_", 1)
        items.append(
            {
                "id": f"control_{sample}",
                "source_id": sample,
                "cohort": "previous_controls",
                "origin": "synthetic",
                "profile": style,
                "parent": f"control_{seed}",
                "kind": "replay",
                "seed": int(seed),
                "style": style,
                "H": np.eye(3).tolist(),
            }
        )
    assert len(items) == 1376 and len({r["id"] for r in items}) == 1376
    return items


def freeze(items):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "protocol.json"
    if path.exists():
        return read(path)
    active = ROOT / "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt"
    protected = [
        p for p in (ROOT / "Data").rglob("*") if p.is_file() and "__pycache__" not in p.parts
    ] + [active, LOCK, OVERRIDES]
    sources = list((ROOT / "SketchPipeline/shape_authoring").glob("*.py")) + list(
        (ROOT / "SketchPipeline/shape_authoring").glob("*.json")
    )
    sources += [Path(__file__).resolve(), ROOT / "Scripts/evaluate_augmented_shape.py"]
    p = {
        "version": "all-data-continuation/1.0",
        "date": "2026-11-07",
        "training_examples": len(items),
        "cohorts": dict(Counter((r["cohort"] for r in items))),
        "training": {
            "seed": 71126,
            "epochs": 6,
            "batch_size": 4,
            "learning_rate": 0.0001,
            "weight_decay": 0.0001,
            "positive_weights": POSITIVE,
            "backbone_frozen": True,
            "all_decoder_parameters_trainable": True,
            "epoch_order": "Every example exactly once per epoch, random permutation; no holdout filtering.",
            "selection": "Fixed final epoch 6, chosen before optimization; epochs 2/4 recovery snapshots are not result-selected.",
        },
        "starting_checkpoint": str(active.relative_to(ROOT)),
        "starting_sha256": sha(active),
        "scope": "All-data training including former train/validation/test sources. Every reported image has been trained on; resubstitution only, no independent test claim.",
        "labels": "Uncertain human pixels weight=0. Renderer masks used only for their defined channels. No human dense masks fabricated. Existing audited Data_63 endpoint and stroke correction applied in memory to supervision; source labels immutable.",
        "numeric_ocr": False,
        "physical_dimensions_training": False,
        "active_model_replaced": False,
        "source_hashes": {str(s.relative_to(ROOT)): sha(s) for s in sources},
        "protected_hashes": {str(s.relative_to(ROOT)): sha(s) for s in protected},
        "prior_audit_sha256": sha(AUDIT / "report.json"),
        "records": items,
    }
    save(path, p)
    for s in sources:
        dest = OUT / "source_snapshot" / s.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(s, dest)
    return p


def prepare(p):
    path = OUT / "cache/manifest.json"
    if path.exists():
        return read(path)
    directory = path.parent
    directory.mkdir(exist_ok=True)
    items = p["records"]
    N = len(items)
    specs = {
        "features": (np.float32, (N, 4, 384, 32, 32)),
        "ink": (np.float16, (N, 2, 256, 256)),
        "target": (np.uint8, (N, 8, 256, 256)),
        "known": (np.float16, (N, 8, 256, 256)),
        "native": (np.uint8, (N, 512, 512)),
    }
    required = sum((np.dtype(dtype).itemsize * np.prod(shape) for dtype, shape in specs.values()))
    assert (
        shutil.disk_usage(OUT).free > required + 5 * 1024**3
    ), "Insufficient space for cache plus safety margin"
    arrays = {
        k: np.lib.format.open_memmap(directory / (k + ".npy"), mode="w+", dtype=dtype, shape=shape)
        for k, (dtype, shape) in specs.items()
    }
    oldparents = old_inventory()[1]
    syn_labels = {}
    syn_refs = {}
    syn_masks = {}
    human_cache = {}
    reference_cache = {}
    for sid, parent in oldparents.items():
        if parent["source_origin"] == "human":
            continue
        syn_labels[sid] = labels_from_files(
            (ROOT / "Data/augmented/v1" / parent["source_files"]["side_path"]["path"]).resolve(),
            (ROOT / "Data/augmented/v1" / parent["source_files"]["obs_path"]["path"]).resolve(),
        )
        syn_refs[sid] = source_reference(parent)
        meta = read(ROOT / f"Data/augmented/v1/transforms/AUG_{sid}_rotate.json")
        manifest = (ROOT / "Data/augmented/v1" / meta["source_manifest"]).resolve()
        entry = next((e for e in read(manifest)["samples"] if e["id"] == sid))
        rendering = read(manifest.parent / entry["rendering_path"])
        syn_masks[sid] = {
            k: cv2.imread(str(manifest.parent / v), 0)
            for k, v in rendering["masks"].items()
            if k in ("walls", "door_ticks")
        }
    backbone = load_backbone("cpu")
    metadata = []
    batch = []
    indices = []
    started = time.perf_counter()
    for i, record in enumerate(items):
        H = np.asarray(record["H"])
        image = Path(record.get("image", ""))
        dense = None
        if record["kind"] == "replay":
            gray, masks, spec = render(record["seed"], record["style"])
            dense = synthetic_targets(masks, spec)
            image = OUT / "generated_replay" / f"{record['id']}.png"
            image.parent.mkdir(exist_ok=True)
            cv2.imwrite(str(image), gray)
            ref = replay_reference(spec)
        else:
            assert sha(image) == record["sha256"], record["id"]
        working, wm = prepare_image(image)
        native, nm = prepare_variant(
            image,
            {"name": "refined-full", "max_side": 512, "square": True, "crop": False},
            working,
            wm,
            None,
        )
        forward = np.asarray(nm["original_to_working"]) @ H
        if record["kind"] in ("human", "rendered"):
            if record["kind"] == "human":
                n = int(record["source_id"].split("_")[1])
                if n not in human_cache:
                    human_cache[n] = human_labels(n)
                    if n >= 51:
                        reference_cache[n] = new_reference(
                            n, {"original_to_working": np.eye(3).tolist()}, read(OVERRIDES)
                        )[0]
                    else:
                        reference_cache[n] = source_reference(oldparents[f"Data_{n}"])
                labels = human_cache[n]
                ref = reference_cache[n]
            else:
                labels = syn_labels[record["source_id"]]
                ref = syn_refs[record["source_id"]]
            sm = {**nm, "original_to_working": forward.tolist()}
            target, known, _ = weak_targets(native, sm, labels)
            target, known = auxiliary_targets(native, sm, labels, target, known)
            if record["kind"] == "rendered":
                for name, channel in [("walls", 0), ("door_ticks", 3)]:
                    mask = syn_masks[record["source_id"]].get(name)
                    if mask is None:
                        continue
                    mapped = cv2.warpPerspective(
                        mask, forward, (512, 512), flags=cv2.INTER_LINEAR, borderValue=0
                    )
                    coverage = cv2.warpPerspective(
                        np.ones(mask.shape, np.uint8),
                        forward,
                        (512, 512),
                        flags=cv2.INTER_NEAREST,
                        borderValue=0,
                    )
                    target[channel] = (mapped >= 64).astype(np.uint8)
                    known[channel] = coverage
        else:
            if dense is None:
                with np.load(record["target_path"]) as z:
                    dense = (z["target"], z["known"])
                ref = structural_reference(read(record["reference_path"]))
            target, known = [
                np.stack(
                    [
                        cv2.warpPerspective(
                            c.astype(np.float32),
                            forward,
                            (512, 512),
                            flags=cv2.INTER_NEAREST,
                            borderValue=0,
                        )
                        for c in value
                    ]
                )
                for value in dense
            ]
        reference = transform_reference(ref, np.asarray(wm["original_to_working"]) @ H)
        clean, _, _ = suppress_grid(native)
        bounds = nm.get("diagnostic_content_bounds_px")
        a, _ = normalize_ink(native, bounds)
        b, _ = normalize_ink(clean, bounds)
        rgb, ink, _ = prepare_tensors(a, b)
        arrays["native"][i] = native
        arrays["ink"][i] = ink
        arrays["target"][i] = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in target]
        ).astype(np.uint8)
        arrays["known"][i] = np.stack(
            [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in known]
        ).astype(np.float16)
        target_folder = directory / "working"
        target_folder.mkdir(exist_ok=True)
        cv2.imwrite(str(target_folder / f"{i}.png"), working)
        source = {
            "image_path": str(image.resolve()),
            "image_sha256": sha(image),
            "width_px": wm["original_size_px"][0],
            "height_px": wm["original_size_px"][1],
        }
        metadata.append(
            {
                "record": record,
                "source": source,
                "working_metadata": wm,
                "native_metadata": nm,
                "reference": reference,
                "known_fraction": float((known > 0).mean()),
                "supervision_positive_by_channel": [int((v > 0).sum()) for v in target],
            }
        )
        batch.append(rgb)
        indices.append(i)
        if len(batch) == 2 or i == N - 1:
            features = extract_features(backbone, torch.from_numpy(np.stack(batch))).cpu().numpy()
            arrays["features"][indices] = features
            batch = []
            indices = []
        if i % 20 == 0 or i == N - 1:
            print(
                json.dumps(
                    {
                        "phase": "prepare",
                        "completed": i + 1,
                        "total": N,
                        "seconds": round(time.perf_counter() - started, 1),
                        "sample": record["id"],
                    }
                ),
                flush=True,
            )
    for v in arrays.values():
        v.flush()
    value = {
        "count": N,
        "records": metadata,
        "features_dtype": "float32",
        "features_lossy_compression": False,
        "every_example_in_training": True,
        "unknown_human_pixels_ignored": True,
        "cache_bytes": int(required),
        "files": {name: sha(directory / (name + ".npy")) for name in specs},
    }
    save(path, value)
    return value


def train(p):
    directory = OUT / "training"
    directory.mkdir(exist_ok=True)
    final = directory / "epoch_6.pt"
    if final.exists():
        return final
    torch.manual_seed(p["training"]["seed"])
    rng = np.random.default_rng(p["training"]["seed"])
    state = torch.load(ROOT / p["starting_checkpoint"], map_location="cpu", weights_only=True)
    model = DinoDecoder(state["width"])
    model.load_state_dict(state["state_dict"])
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=p["training"]["learning_rate"],
        weight_decay=p["training"]["weight_decay"],
    )
    cache = OUT / "cache"
    arrays = {
        n: np.load(cache / (n + ".npy"), mmap_mode="r")
        for n in ["features", "ink", "target", "known"]
    }
    N = len(arrays["features"])
    history = []
    started = time.perf_counter()
    batch = p["training"]["batch_size"]
    first = 1
    resume = directory / "resume.pt"
    if resume.exists():
        saved = torch.load(resume, map_location="cpu", weights_only=False)
        model.load_state_dict(saved["state_dict"])
        optimizer.load_state_dict(saved["optimizer"])
        rng.bit_generator.state = saved["rng"]
        torch.set_rng_state(saved["torch_rng"])
        history = saved["history"]
        first = saved["epoch"] + 1
    for epoch in range(first, 7):
        model.train()
        order = rng.permutation(N)
        losses = []
        for start in range(0, N, batch):
            ix = order[start : start + batch]
            feature, ink, target, known = [
                torch.from_numpy(np.asarray(arrays[k][ix], dtype=np.float32))
                for k in ["features", "ink", "target", "known"]
            ]
            logits = model(feature, ink)
            loss = masked_loss(logits, target, known, POSITIVE)
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach()))
            if start % 80 == 0:
                print(
                    json.dumps(
                        {
                            "phase": "training",
                            "epoch": epoch,
                            "seen": min(start + batch, N),
                            "total": N,
                            "mean_loss": round(float(np.mean(losses)), 5),
                            "seconds": round(time.perf_counter() - started, 1),
                        }
                    ),
                    flush=True,
                )
        item = {
            "epoch": epoch,
            "loss": float(np.mean(losses)),
            "examples_seen": N,
            "seconds": time.perf_counter() - started,
        }
        history.append(item)
        saved = {
            **{k: state[k] for k in ["architecture", "channels", "width", "backbone_lock_sha256"]},
            "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "epoch": epoch,
            "protocol_sha256": sha(OUT / "protocol.json"),
            "training_scope": "all data; no heldout; final fixed epoch",
        }
        if epoch in (2, 4, 6):
            torch.save(saved, directory / f"epoch_{epoch}.pt")
        temp = directory / "resume.tmp"
        torch.save(
            {
                **saved,
                "optimizer": optimizer.state_dict(),
                "rng": rng.bit_generator.state,
                "torch_rng": torch.get_rng_state(),
                "history": history,
            },
            temp,
        )
        temp.replace(resume)
        save(directory / "history.json", history)
        print(json.dumps({"epoch_complete": item}), flush=True)
    save(
        OUT / "candidate.json",
        {
            "checkpoint_path": str(final.relative_to(ROOT)),
            "checkpoint_sha256": sha(final),
            "starting_sha256": p["starting_sha256"],
            "backbone_frozen": True,
            "active_model_replaced": False,
            "all_data_training": True,
            "independent_test": False,
        },
    )
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["all", "prepare", "train"], default="all")
    args = parser.parse_args()
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    items = records()
    p = freeze(items)
    assert all((sha(ROOT / s) == h for s, h in p["source_hashes"].items()))
    assert all((sha(ROOT / s) == h for s, h in p["protected_hashes"].items()))
    prepare(p)
    if args.phase != "prepare":
        print("Candidate ready: " + str(train(p)), flush=True)
    assert all((sha(ROOT / s) == h for s, h in p["protected_hashes"].items()))


if __name__ == "__main__":
    main()
