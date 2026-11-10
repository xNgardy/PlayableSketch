import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "Saved/Experiments/hybrid_unet_yolo11_v1"
BASE = ROOT / "Saved/Experiments/independent_boundaries_v1"
os.environ.setdefault("YOLO_CONFIG_DIR", str(OUT / "settings"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
import cv2
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from Scripts.independent_boundary_experiment import (
    BoundaryUNet,
    inputs,
    references,
    door_box,
    synthetic_rooms,
    write,
    sha,
    counts,
    bbox_iou,
    metrics,
    polygons,
    polygon_iou,
)
from Scripts.independent_boundary_stress_data import generate
from SketchPipeline.shape_authoring.human_supervision import (
    prepare_human,
    structural_labels,
    weak_targets,
    source_image,
)
from SketchPipeline.shape_authoring.synthetic import render

SEED = 91127


def save_sample(record, gray, target, known, doors, rooms):
    identifier = record["id"]
    split = record["split"]
    image = OUT / "dataset/images" / split / (identifier + ".png")
    image.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(image), gray)
    boxes = [(np.asarray(door_box(np.asarray(p) / 2)) * 2).tolist() for p in doors]
    labels = OUT / "dataset/labels" / split / (identifier + ".txt")
    labels.parent.mkdir(parents=True, exist_ok=True)
    labels.write_text(
        "".join(
            f"0 {(x+X)/2048:.7f} {(y+Y)/2048:.7f} {(X-x)/1024:.7f} {(Y-y)/1024:.7f}\n"
            for x, y, X, Y in boxes
        )
    )
    cache = OUT / "cache"
    cache.mkdir(exist_ok=True)
    np.savez_compressed(
        cache / (identifier + ".npz"),
        gray=gray,
        target=target.astype(np.uint8),
        known=known.astype(np.float16),
    )
    return {
        **record,
        "image": str(image),
        "boxes": boxes,
        "doors": doors,
        "rooms": rooms,
        "prepared_sha256": sha(image),
    }


def prepare_data():
    path = OUT / "protocol.json"
    if path.exists():
        return
    OUT.mkdir(parents=True, exist_ok=True)
    original = json.loads((BASE / "protocol.json").read_text())
    rows = []
    for record in original["samples"]:
        identifier = record["id"]
        n = int(identifier.split("_")[1])
        if record["kind"] == "human":
            gray, meta = prepare_human(n, 1024)
            target, known, _ = weak_targets(gray, meta, structural_labels(n))
            doors, rooms = references(n, meta)
            target, known = target[0], known[0]
        else:
            styles = (
                ["clean", "wavy", "stray"]
                if record["split"] == "train"
                else ["clean", "wavy", "broken", "stray"]
            )
            index = n - (
                500000
                if record["split"] == "train"
                else 600000 if record["split"] == "validation" else 700000
            )
            gray, masks, spec = render(n, styles[index % len(styles)], size=1024)
            target = np.uint8(masks[0] > 0)
            known = np.ones_like(target)
            doors = []
            for opening in spec["openings"]:
                if opening["type"] != "door":
                    continue
                p, q = [0.0, 0.0], [0.0, 0.0]
                axis = opening["axis"]
                p[axis], q[axis] = np.asarray(opening["interval"]) * 4
                p[1 - axis] = q[1 - axis] = opening["fixed"] * 4
                doors.append([p, q])
            rooms = [
                [(np.asarray(p) * 2).tolist() for p in parts] for parts in synthetic_rooms(spec)
            ]
        rows.append(
            save_sample(
                {k: record[k] for k in ["id", "split", "kind", "source_sha256"]},
                gray,
                target,
                known,
                doors,
                rooms,
            )
        )
    for split, start, count in [("train", 920000, 120), ("validation", 930000, 24)]:
        extra = generate(OUT / "generated" / split, start, count, split)
        for record in extra:
            data = np.load(OUT / "generated" / split / "cache" / f"{record['id']}.npz")
            gray = cv2.resize(data["gray"], (1024, 1024), interpolation=cv2.INTER_CUBIC)
            target = cv2.resize(data["target"][0], (1024, 1024), interpolation=cv2.INTER_NEAREST)
            doors = [(np.asarray(p) * 2).tolist() for p in record["doors"]]
            rooms = [[(np.asarray(p) * 2).tolist() for p in parts] for parts in record["rooms"]]
            rows.append(
                save_sample(
                    {
                        "id": "Shape_" + record["id"].split("_")[1],
                        "kind": "connected_shapes",
                        "split": split,
                        "source_sha256": record["source_sha256"],
                    },
                    gray,
                    target,
                    np.ones_like(target),
                    doors,
                    rooms,
                )
            )
    protocol = {
        "version": "hybrid-unet-yolo11/1.0",
        "seed": SEED,
        "samples": rows,
        "counts": {
            split: {
                kind: sum(r["split"] == split and r["kind"] == kind for r in rows)
                for kind in ["human", "synthetic", "connected_shapes"]
            }
            for split in ["train", "validation", "test"]
        },
        "initialization": {
            "wall": str(BASE / "unet-best.pt"),
            "wall_sha256": sha(BASE / "unet-best.pt"),
            "door": str(BASE / "training/yolo11n/weights/best.pt"),
            "door_sha256": sha(BASE / "training/yolo11n/weights/best.pt"),
        },
        "training": {
            "wall_epochs": 40,
            "door_epochs": 40,
            "wall_batch": 4,
            "door_batch": 4,
            "wall_tile": 512,
            "door_imgsz": 640,
            "wall_lr": 0.0002,
            "door_lr": 0.0003,
            "wall_human_repeat": 3,
            "patience": 12,
        },
        "evaluation": {
            "evidence_size": 1024,
            "door_full_and_tiled": True,
            "door_tile": 640,
            "nms_iou": 0.4,
            "wall_thresholds": [0.35, 0.5, 0.65],
            "door_thresholds": [0.15, 0.3, 0.5],
            "closing_kernels": [3, 5],
            "selection": "Human validation region F1 + 0.25*exact room-count accuracy + 0.25*door F1. No test or photo selection.",
            "test_scope": "Same 14 original human test drawings as the pilot; excluded from training but inspected in previous experiments. Retrospective development, not a new blind/writer holdout.",
        },
        "room_definition": "Connected floor interior, separated only by walls and doors; no corridor class.",
        "human_labels": "Approximate traces with uncertainty masks; no invented dense human ground truth.",
        "deployment": "Separate candidate only. Production service and selected DINO unchanged.",
    }
    groups = {}
    for r in rows:
        groups.setdefault(r["source_sha256"], set()).add(r["split"])
    assert all(len(v) == 1 for v in groups.values())
    write(path, protocol)
    (OUT / "dataset.yaml").write_text(
        f'path: {OUT/"dataset"}\ntrain: images/train\nval: images/validation\nnames:\n  0: door_notches\n'
    )
    print(protocol["counts"], flush=True)


class WallUNet(BoundaryUNet):
    def __init__(self):
        super().__init__()
        self.head = nn.Conv2d(12, 1, 1)


def wall_loss(logits, target, known):
    loss = F.binary_cross_entropy_with_logits(
        logits, target, reduction="none", pos_weight=torch.tensor(8.0, device=logits.device)
    )
    bce = (loss * known).sum() / known.sum().clamp_min(1)
    probability = logits.sigmoid()
    dice = 1 - (2 * (probability * target * known).sum() + 1) / (
        (probability * known).sum() + (target * known).sum() + 1
    )
    return bce + dice


@lru_cache(maxsize=24)
def sample_cache(identifier):
    with np.load(OUT / "cache" / (identifier + ".npz")) as value:
        return dict(value)


def train_wall():
    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    protocol = json.loads((OUT / "protocol.json").read_text())
    recipe = protocol["training"]
    rng = np.random.default_rng(SEED)
    model = WallUNet()
    state = torch.load(protocol["initialization"]["wall"], weights_only=True, map_location="cpu")[
        "state_dict"
    ]
    state["head.weight"] = state["head.weight"][:1]
    state["head.bias"] = state["head.bias"][:1]
    model.load_state_dict(state)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=recipe["wall_lr"])
    train = [r for r in protocol["samples"] if r["split"] == "train"]
    validation = [r for r in protocol["samples"] if r["split"] == "validation"]
    history = []
    best = float("inf")
    stale = 0
    started = time.time()
    print("Wall training device", device, flush=True)
    for epoch in range(1, recipe["wall_epochs"] + 1):
        rows = [
            r
            for r in train
            for _ in range(recipe["wall_human_repeat"] if r["kind"] == "human" else 1)
        ]
        rng.shuffle(rows)
        model.train()
        losses = []
        for offset in range(0, len(rows), recipe["wall_batch"]):
            xs = []
            ys = []
            ks = []
            for row in rows[offset : offset + recipe["wall_batch"]]:
                c = sample_cache(row["id"])
                positive = np.argwhere(c["target"] > 0)
                if len(positive) and rng.random() < 0.8:
                    center = positive[int(rng.integers(len(positive)))]
                    y, x = np.clip(center - 256 + rng.integers(-128, 129, 2), 0, 512)
                else:
                    y, x = rng.integers(0, 513, 2)
                g = c["gray"][y : y + 512, x : x + 512].copy()
                target = c["target"][y : y + 512, x : x + 512].copy()
                known = c["known"][y : y + 512, x : x + 512].astype(np.float32)
                rotation = int(rng.integers(4))
                g = np.rot90(g, rotation).copy()
                target = np.rot90(target, rotation).copy()
                known = np.rot90(known, rotation).copy()
                positions = np.argwhere(target > 0)
                for _ in range(int(rng.integers(1, 6))):
                    if not len(positions):
                        break
                    py, px = positions[int(rng.integers(len(positions)))]
                    radius = int(rng.integers(1, 4))
                    g[
                        max(0, py - radius) : py + radius + 1, max(0, px - radius) : px + radius + 1
                    ] = np.median(g)
                g = np.uint8(
                    np.clip(
                        (g.astype(float) - 255) * rng.uniform(0.35, 1.15)
                        + rng.uniform(210, 255)
                        + rng.normal(0, rng.uniform(0, 1.5), g.shape),
                        0,
                        255,
                    )
                )
                if rng.random() < 0.3:
                    g = cv2.GaussianBlur(g, (3, 3), 0.5)
                xs.append(inputs(g))
                ys.append(target[None])
                ks.append(known[None])
            optimizer.zero_grad()
            loss = wall_loss(
                model(torch.from_numpy(np.stack(xs)).to(device)),
                torch.from_numpy(np.stack(ys)).float().to(device),
                torch.from_numpy(np.stack(ks)).to(device),
            )
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        validation_losses = {"human": [], "synthetic": []}
        with torch.inference_mode():
            for row in validation:
                c = sample_cache(row["id"])
                g = c["gray"]
                target = torch.from_numpy(c["target"][None, None]).float().to(device)
                known = torch.from_numpy(c["known"][None, None].astype(np.float32)).to(device)
                value = float(
                    wall_loss(model(torch.from_numpy(inputs(g)[None]).to(device)), target, known)
                )
                validation_losses["human" if row["kind"] == "human" else "synthetic"].append(value)
        score = float(np.mean([np.mean(v) for v in validation_losses.values()]))
        history.append(
            {
                "epoch": epoch,
                "training_loss": float(np.mean(losses)),
                "validation_loss": score,
                "elapsed_seconds": time.time() - started,
            }
        )
        checkpoint = {
            "architecture": "wall-unet/1.0",
            "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "epoch": epoch,
            "validation_loss": score,
            "seed": SEED,
            "device": device,
            "channels": ["wall"],
        }
        torch.save(checkpoint, OUT / "wall-last.pt")
        if score < best:
            best = score
            stale = 0
            torch.save(checkpoint, OUT / "wall-best.pt")
        else:
            stale += 1
        write(OUT / "wall-history.json", history)
        print("WALL", history[-1], flush=True)
        if epoch >= 20 and stale >= recipe["patience"]:
            break


def train_door():
    from ultralytics import YOLO, settings

    settings.update(
        {
            key: False
            for key in [
                "sync",
                "hub",
                "wandb",
                "mlflow",
                "clearml",
                "comet",
                "neptune",
                "tensorboard",
                "dvc",
            ]
            if key in settings
        }
    )
    torch.set_num_threads(3)
    p = json.loads((OUT / "protocol.json").read_text())
    r = p["training"]
    model = YOLO(p["initialization"]["door"])
    model.train(
        data=str(OUT / "dataset.yaml"),
        epochs=r["door_epochs"],
        imgsz=r["door_imgsz"],
        batch=r["door_batch"],
        device="mps" if torch.backends.mps.is_available() else "cpu",
        workers=0,
        seed=SEED,
        deterministic=True,
        project=str(OUT / "door-training"),
        name="yolo11n",
        exist_ok=False,
        plots=False,
        save=True,
        cache=False,
        amp=False,
        optimizer="AdamW",
        lr0=r["door_lr"],
        patience=r["patience"],
        degrees=5,
        translate=0.05,
        scale=0.2,
        flipud=0.5,
        fliplr=0.5,
        mosaic=0.2,
        close_mosaic=8,
        pretrained=True,
        verbose=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "wall", "door"])
    args = parser.parse_args()
    {"prepare": prepare_data, "wall": train_wall, "door": train_door}[args.phase]()
