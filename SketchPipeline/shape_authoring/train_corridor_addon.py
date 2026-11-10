import argparse
import copy
from collections import defaultdict, Counter
import json
from pathlib import Path
import time
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from .dino_model import (
    ROOT,
    LOCK,
    CHANNELS,
    ARCHITECTURE,
    DinoDecoder,
    load_backbone,
    prepare_tensors,
    extract_features,
    sha,
)
from .dino_experiment import (
    human_views,
    synthetic_targets,
    masked_loss,
    score_human,
    score_synthetic,
    summarize,
)
from .synthetic import render, write_json
from .contrast import normalize_ink
from SketchPipeline.perception.structural import suppress_grid

OUT = ROOT / "Saved/ShapeFirst/dinov2/corridor_addon/v1"
ADDON = ROOT / "Data/synthetic/corridor_addon_v1"


def grouped_sample(records, rng, count=160):
    pools = {k: defaultdict(list) for k in ("historical", "new_human", "complex")}
    for i, r in enumerate(records):
        if r["split"] != "train":
            raise ValueError("Holdout record in training cache")
        pools[r["pool"]][r["group"]].append(i)
    selected = []
    for pool, n in [
        ("historical", count * 75 // 100),
        ("new_human", count * 20 // 100),
        ("complex", count * 5 // 100),
    ]:
        groups = sorted(pools[pool])
        if not groups:
            raise ValueError("Empty training pool")
        for _ in range(n):
            group = groups[int(rng.integers(len(groups)))]
            selected.append(int(rng.choice(pools[pool][group])))
    rng.shuffle(selected)
    return np.asarray(selected)


def eligible(value, baseline):
    checks = {}
    for group in ("old", "new", "synthetic"):
        for metric, tolerance in [("regions", 0.03), ("attached_openings", 0.04), ("doors", 0.04)]:
            a = value[group][metric]["f1"] or 0
            b = baseline[group][metric]["f1"] or 0
            checks[group + "_" + metric] = a >= b - tolerance
        a = value[group]["attached_openings"]["precision"] or 0
        b = baseline[group]["attached_openings"]["precision"] or 0
        checks[group + "_attachment_precision"] = a >= b - 0.03
    return (all(checks.values()), checks)


def objective(value):
    mean = lambda s: sum((s[k]["f1"] or 0 for k in ("regions", "attached_openings", "doors"))) / 3
    return 0.5 * mean(value["old"]) + 0.5 * mean(value["new"])


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "protocol.json"
    if path.exists():
        return json.loads(path.read_text())
    addon = json.loads((ADDON / "manifest.json").read_text())
    old = json.loads((ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json").read_text())
    plan = json.loads((ADDON / "training_plan.json").read_text())
    lock = json.loads(
        (ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json").read_text()
    )
    assert sha(ADDON / "manifest.json") == plan["addon_manifest_sha256"]
    assert sha(ROOT / plan["historical_protocol_path"]) == plan["historical_protocol_sha256"]
    assert sha(ROOT / lock["checkpoint_path"]) == lock["checkpoint_sha256"]
    files = [p for p in (ROOT / "Data").rglob("*") if p.is_file()]
    p = {
        "version": "corridor-addon-training/1.0",
        "seed": 5112026,
        "base_checkpoint": lock,
        "addon_manifest_sha256": sha(ADDON / "manifest.json"),
        "old": old,
        "new_splits": plan["new_human_splits"],
        "epochs": 10,
        "checkpoints": [2, 5, 10],
        "learning_rate": 0.0001,
        "weight_decay": 0.0001,
        "batch_size": 4,
        "samples_per_epoch": 160,
        "teacher_weight": 0.15,
        "loss_positive_weights": [5, 1, 4, 12, 8, 12, 15, 8],
        "sampling": "75% historical parents,20% new photo parents including grouped guide views,5% complex families; parent before view.",
        "selection": "Validation-only objective equally averages old/new region,attachment,door F1. Fixed historical/new/synthetic regression guards. Epoch0 is fallback. Ties retain earlier checkpoint.",
        "guards": {
            "max_f1_drop": {"regions": 0.03, "attached_openings": 0.04, "doors": 0.04},
            "max_attachment_precision_drop": 0.03,
        },
        "backbone_frozen": True,
        "decoder_version": "shape-decoder/2.7",
        "test_used_for_selection": False,
        "scope": "Same-writer development comparison; approximate human labels. Not fresh blind evaluation.",
        "protected": {str(f.relative_to(ROOT)): sha(f) for f in files},
        "model_promoted": False,
    }
    write_json(path, p)
    return p


def prepare(p):
    cache = OUT / "cache"
    manifest = cache / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    cache.mkdir(exist_ok=True)
    records = []
    inputs = []
    targets = []
    weights = []
    inks = []

    def append(gray, target, known, record, normalize=True, bounds=None):
        clean, _, _ = suppress_grid(gray)
        if normalize:
            gray, _ = normalize_ink(gray, bounds)
            clean, _ = normalize_ink(clean, bounds)
        rgb, ink, _ = prepare_tensors(gray, clean)
        inputs.append(rgb)
        inks.append(ink.astype(np.float16))
        targets.append(
            np.stack(
                [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in target]
            ).astype(np.uint8)
        )
        weights.append(
            np.stack(
                [cv2.resize(c, (256, 256), interpolation=cv2.INTER_NEAREST) for c in known]
            ).astype(np.float16)
        )
        records.append(record)

    for n in p["old"]["human_splits"]["train"]:
        for name, gray, t, k, b in human_views(n):
            append(
                gray,
                t,
                k,
                {
                    "pool": "historical",
                    "group": "human_" + str(n),
                    "id": f"Data_{n}_{name}",
                    "split": "train",
                },
                bounds=b,
            )
    for seed in p["old"]["train_synthetic_parents"]:
        for style in p["old"]["train_synthetic_styles"]:
            gray, masks, spec = render(seed, style)
            t, k = synthetic_targets(masks, spec)
            append(
                gray,
                t,
                k,
                {
                    "pool": "historical",
                    "group": f"synthetic_{seed}",
                    "id": f"{seed}_{style}",
                    "split": "train",
                },
                normalize=False,
            )
    addon = json.loads((ADDON / "manifest.json").read_text())
    for entry in addon["samples"]:
        if entry["split"] != "train":
            continue
        gray = cv2.imread(str(ADDON / entry.get("input_512_path", entry["image_path"])), 0)
        with np.load(ADDON / entry["targets_path"]) as z:
            t, k = (z["target"], z["known"])
        complex_ = entry["origin"] == "procedural_complex"
        append(
            gray,
            t,
            k,
            {
                "pool": "complex" if complex_ else "new_human",
                "group": entry["geometry_family"] if complex_ else entry["base_plan_id"],
                "id": entry["id"],
                "split": "train",
            },
            normalize=entry["origin"] in ("human", "human_derivative"),
        )
    count = len(records)
    for name, array in [("ink", inks), ("target", targets), ("known", weights)]:
        np.save(cache / (name + ".npy"), np.asarray(array))
    del inks, targets, weights
    backbone = load_backbone("cpu")
    features = np.lib.format.open_memmap(
        cache / "features.npy", mode="w+", dtype=np.float16, shape=(count, 4, 384, 32, 32)
    )
    start = time.perf_counter()
    for i in range(0, count, 2):
        features[i : i + 2] = (
            extract_features(backbone, torch.from_numpy(np.asarray(inputs[i : i + 2])))
            .cpu()
            .numpy()
        )
        if i % 40 == 0:
            print(
                json.dumps(
                    {
                        "stage": "features",
                        "done": i + 2,
                        "total": count,
                        "seconds": time.perf_counter() - start,
                    }
                ),
                flush=True,
            )
    features.flush()
    value = {
        "records": records,
        "count": count,
        "files": {str(f.name): sha(f) for f in cache.glob("*.npy")},
        "backbone_frozen": True,
        "addon_manifest_sha256": p["addon_manifest_sha256"],
    }
    write_json(manifest, value)
    return value


def validate(checkpoint, folder, p):
    summary_path = folder / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text())
    groups = {
        "old": [
            score_human(n, folder / "old" / f"Data_{n}", checkpoint)
            for n in p["old"]["human_splits"]["validation"]
        ],
        "new": [
            score_human(n, folder / "new" / f"Data_{n}", checkpoint)
            for n in p["new_splits"]["validation"]
        ],
        "synthetic": [
            score_synthetic(s, folder / "synthetic" / s, checkpoint)
            for s in p["old"]["validation_synthetic_ids"]
        ],
    }
    value = {name: summarize(rows) for name, rows in groups.items()}
    value["rows"] = groups
    value["objective"] = objective(value)
    value["test_used"] = False
    write_json(summary_path, value)
    return value


def save_model(model, path, epoch, p):
    torch.save(
        {
            "architecture": ARCHITECTURE,
            "channels": CHANNELS,
            "width": model.width,
            "state_dict": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            "backbone_lock_sha256": sha(LOCK),
            "protocol_sha256": sha(OUT / "protocol.json"),
            "epoch": epoch,
            "continued_from_sha256": p["base_checkpoint"]["checkpoint_sha256"],
        },
        path,
    )


def train():
    p = freeze()
    torch.manual_seed(p["seed"])
    np.random.seed(p["seed"])
    rng = np.random.default_rng(p["seed"])
    source = ROOT / p["base_checkpoint"]["checkpoint_path"]
    print(json.dumps({"stage": "baseline_validation"}), flush=True)
    baseline = validate(source, OUT / "validation/epoch_0", p)
    manifest = prepare(p)
    cache = OUT / "cache"
    arrays = {
        n: np.load(cache / (n + ".npy"), mmap_mode="r")
        for n in ["features", "ink", "target", "known"]
    }
    state = torch.load(source, map_location="cpu", weights_only=True)
    model = DinoDecoder(state["width"])
    model.load_state_dict(state["state_dict"])
    teacher = DinoDecoder(state["width"])
    teacher.load_state_dict(state["state_dict"])
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=p["learning_rate"], weight_decay=p["weight_decay"]
    )
    directory = OUT / "checkpoints"
    directory.mkdir(exist_ok=False)
    candidates = [
        {
            "epoch": 0,
            "path": str(source.relative_to(ROOT)),
            "sha256": sha(source),
            "objective": baseline["objective"],
            "eligible": True,
        }
    ]
    history = []
    started = time.perf_counter()
    for epoch in range(1, p["epochs"] + 1):
        model.train()
        order = grouped_sample(manifest["records"], rng, p["samples_per_epoch"])
        losses = []
        for start in range(0, len(order), p["batch_size"]):
            indices = order[start : start + p["batch_size"]]
            feature, ink, target, known = [
                torch.from_numpy(np.asarray(arrays[n][indices], dtype=np.float32))
                for n in ["features", "ink", "target", "known"]
            ]
            logits = model(feature, ink)
            loss = masked_loss(logits, target, known, p["loss_positive_weights"])
            old = [
                i for i, j in enumerate(indices) if manifest["records"][j]["pool"] == "historical"
            ]
            if old:
                with torch.no_grad():
                    prior = teacher(feature[old], ink[old]).sigmoid()
                loss = loss + p["teacher_weight"] * F.binary_cross_entropy_with_logits(
                    logits[old], prior
                )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach()))
        row = {
            "epoch": epoch,
            "loss": float(np.mean(losses)),
            "seconds": time.perf_counter() - started,
            "pool_counts": dict(Counter((manifest["records"][i]["pool"] for i in order))),
        }
        history.append(row)
        write_json(OUT / "history.json", history)
        print(json.dumps(row), flush=True)
        if epoch in p["checkpoints"]:
            checkpoint = directory / f"epoch_{epoch}.pt"
            save_model(model, checkpoint, epoch, p)
            result = validate(checkpoint, OUT / f"validation/epoch_{epoch}", p)
            passed, guards = eligible(result, baseline)
            candidate = {
                "epoch": epoch,
                "path": str(checkpoint.relative_to(ROOT)),
                "sha256": sha(checkpoint),
                "objective": result["objective"],
                "eligible": passed,
                "guards": guards,
            }
            candidates.append(candidate)
            write_json(OUT / "candidates.json", candidates)
            print(json.dumps({"candidate": candidate}), flush=True)
    selected = max(
        [c for c in candidates if c["eligible"]], key=lambda c: (c["objective"], -c["epoch"])
    )
    report = {
        "selected": selected,
        "candidates": candidates,
        "history": history,
        "selection_used_test": False,
        "backbone_updated": False,
        "model_promoted": False,
        "training_seconds": time.perf_counter() - started,
    }
    assert sha(source) == p["base_checkpoint"]["checkpoint_sha256"]
    assert all((sha(ROOT / path) == digest for path, digest in p["protected"].items()))
    write_json(OUT / "training_report.json", report)
    print(json.dumps({"selected": selected}), flush=True)


def evaluate():
    p = freeze()
    selection_path = (
        OUT / "final_selection.json"
        if (OUT / "final_selection.json").exists()
        else OUT / "training_report.json"
    )
    training = json.loads(selection_path.read_text())
    selected = training["selected"]
    checkpoint = ROOT / selected["path"]
    assert sha(checkpoint) == selected["sha256"]
    directory = OUT / "reserved_evaluation_corrected"
    directory.mkdir(exist_ok=True)
    write_json(
        directory / "selection_freeze.json",
        {
            "selected": selected,
            "selection_report_sha256": sha(selection_path),
            "further_selection_from_test": False,
        },
    )
    baseline = ROOT / p["base_checkpoint"]["checkpoint_path"]
    rows = []
    for group, ids in [
        ("old_test", p["old"]["human_splits"]["test"]),
        ("new_test", p["new_splits"]["test"]),
    ]:
        for n in ids:
            for arm, model in [("baseline", baseline), ("selected", checkpoint)]:
                if (
                    arm == "selected"
                    and selected["sha256"] == p["base_checkpoint"]["checkpoint_sha256"]
                ):
                    row = copy.deepcopy(rows[-1])
                    row["prediction_reused_same_checkpoint"] = True
                else:
                    metrics_path = directory / group / f"Data_{n}" / arm / "metrics.json"
                    row = (
                        json.loads(metrics_path.read_text())
                        if metrics_path.exists()
                        else score_human(n, metrics_path.parent, model)
                    )
                row.update(group=group, arm=arm)
                rows.append(row)
            print(json.dumps({"reserved": n}), flush=True)
    for seed in range(2000, 2012):
        for style in ["clean", "wavy", "grid", "stray", "broken"]:
            sample = f"{seed}_{style}"
            for arm, model in [("baseline", baseline), ("selected", checkpoint)]:
                if (
                    arm == "selected"
                    and selected["sha256"] == p["base_checkpoint"]["checkpoint_sha256"]
                ):
                    row = copy.deepcopy(rows[-1])
                    row["prediction_reused_same_checkpoint"] = True
                else:
                    metrics_path = directory / "synthetic" / sample / arm / "metrics.json"
                    row = (
                        json.loads(metrics_path.read_text())
                        if metrics_path.exists()
                        else score_synthetic(sample, metrics_path.parent, model)
                    )
                row.update(group="synthetic", arm=arm)
                rows.append(row)
        print(json.dumps({"reserved_synthetic": seed}), flush=True)
    summaries = {
        arm: {
            group: summarize([r for r in rows if r["group"] == group and r["arm"] == arm])
            for group in ["old_test", "new_test", "synthetic"]
        }
        for arm in ["baseline", "selected"]
    }
    assert all((sha(ROOT / path) == digest for path, digest in p["protected"].items()))
    write_json(
        OUT / "evaluation_report.json",
        {
            "summary": summaries,
            "rows": rows,
            "selected": selected,
            "test_used_for_selection": False,
            "model_promoted": False,
            "scope": p["scope"],
            "protected_data_unchanged": True,
        },
    )
    print(json.dumps(summaries), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "train", "evaluate"])
    args = parser.parse_args()
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    if args.stage == "prepare":
        prepare(freeze())
    elif args.stage == "train":
        train()
    else:
        evaluate()


if __name__ == "__main__":
    main()
