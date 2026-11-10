import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault(
    "YOLO_CONFIG_DIR", str(ROOT / "Saved/Experiments/independent_boundaries_v1/settings")
)
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("HF_HOME", str(ROOT / "Saved/Experiments/independent_boundaries_v1/hf-cache"))
import cv2
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from shapely.geometry import Polygon
from shapely.ops import unary_union
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.shape_authoring.human_supervision import (
    prepare_human,
    structural_labels,
    source_image,
    weak_targets,
)
from SketchPipeline.shape_authoring.synthetic import render
from SketchPipeline.shape_authoring.human_error_review import reference

OUT = ROOT / "Saved/Experiments/independent_boundaries_v1"
SEED = 91126


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def door_box(points):
    p = np.asarray(points, float)
    lo, hi = p.min(0), p.max(0)
    axis = int(np.ptp(p[:, 1]) > np.ptp(p[:, 0]))
    normal = 1 - axis
    margin = max(5, (hi[axis] - lo[axis]) * 0.36)
    lo[normal] -= margin
    hi[normal] += margin
    lo[axis] -= 2
    hi[axis] += 2
    return np.clip(np.r_[lo, hi], 0, 511).tolist()


def references(n, meta):
    ref = reference(n, meta)
    polygons = {r["id"]: Polygon(r["polygon"]) for r in ref["regions"]}
    parent = {key: key for key in polygons}

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key

    for opening in ref["openings"]:
        owners = opening["entity_ids"]
        if opening["type"] == "open_passage" and len(owners) == 2:
            parent[root(owners[0])] = root(owners[1])
    groups = {}
    for key, polygon in polygons.items():
        groups.setdefault(root(key), []).append(polygon)
    rooms = []
    for values in groups.values():
        merged = unary_union(values)
        rooms.append(
            [list(p.exterior.coords) for p in merged.geoms]
            if hasattr(merged, "geoms")
            else [list(merged.exterior.coords)]
        )
    doors = [g["points_px"] for g in ref["openings"] if g["type"] == "door"]
    return doors, rooms


def synthetic_rooms(spec):
    from shapely.geometry import box

    parent = {r["id"]: r["id"] for r in spec["regions"]}

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key

    for opening in spec["openings"]:
        if opening["type"] == "open_passage":
            a, b = opening["entity_ids"]
            parent[root(a)] = root(b)
    groups = {}
    for r in spec["regions"]:
        groups.setdefault(root(r["id"]), []).append(box(*[v * 2 for v in r["bounds_px"]]))
    result = []
    for pieces in groups.values():
        merged = unary_union(pieces)
        result.append(
            [list(p.exterior.coords) for p in merged.geoms]
            if hasattr(merged, "geoms")
            else [list(merged.exterior.coords)]
        )
    return result


def prepare_data():
    if (OUT / "protocol.json").exists():
        print("Frozen dataset already exists", flush=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    roles = json.loads((ROOT / "Saved/Evaluation/v1/split.json").read_text())["group_split"]
    parents = {
        e["source_id"]: e["base_plan_id"]
        for e in json.loads((ROOT / "Data/augmented/v1/manifest.json").read_text())["samples"]
        if e["source_origin"] == "human"
    }
    extra = list(range(51, 71))
    random.Random(SEED).shuffle(extra)
    extra_roles = {
        n: "train" if i < 14 else "validation" if i < 16 else "test" for i, n in enumerate(extra)
    }
    records = []

    def save(identifier, split, kind, gray, target, known, doors, rooms, source_sha):
        folder = OUT / "cache"
        folder.mkdir(exist_ok=True)
        np.savez_compressed(
            folder / (identifier + ".npz"),
            gray=gray,
            target=target.astype(np.uint8),
            known=known.astype(np.float16),
        )
        image = OUT / "dataset/images" / split / (identifier + ".png")
        image.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(image), gray)
        labels = OUT / "dataset/labels" / split / (identifier + ".txt")
        labels.parent.mkdir(parents=True, exist_ok=True)
        boxes = [door_box(p) for p in doors]
        labels.write_text(
            "".join(
                f"0 {(x+X)/1024:.7f} {(y+Y)/1024:.7f} {(X-x)/512:.7f} {(Y-y)/512:.7f}\n"
                for x, y, X, Y in boxes
            )
        )
        records.append(
            dict(
                id=identifier,
                split=split,
                kind=kind,
                image=str(image),
                source_sha256=source_sha,
                boxes=boxes,
                doors=doors,
                rooms=rooms,
            )
        )

    for n in range(1, 71):
        gray, meta = prepare_human(n, 512)
        labels = structural_labels(n)
        targets, weights, _ = weak_targets(gray, meta, labels)
        target = np.stack([targets[0], targets[3], np.zeros(gray.shape)])
        known = np.stack([weights[0], weights[3], np.full(gray.shape, 0.25)])
        doors, rooms = references(n, meta)
        for points in doors:
            cv2.line(
                target[2],
                tuple(np.rint(points[0]).astype(int)),
                tuple(np.rint(points[1]).astype(int)),
                1,
                3,
            )
        known[2, target[2] > 0] = 1
        role = roles[parents[f"Data_{n}"]] if n <= 50 else extra_roles[n]
        save(f"Data_{n}", role, "human", gray, target, known, doors, rooms, sha(source_image(n)))
    for split, start, count in [
        ("train", 500000, 120),
        ("validation", 600000, 24),
        ("test", 700000, 30),
    ]:
        for index in range(count):
            seed = start + index
            gray, masks, spec = render(
                seed, ["clean", "wavy", "broken", "stray"][index % 4], size=512
            )
            target = np.stack([masks[0] > 0, masks[3] > 0, np.zeros(gray.shape, bool)]).astype(
                np.uint8
            )
            doors = []
            for o in spec["openings"]:
                if o["type"] != "door":
                    continue
                p, q = [0.0, 0.0], [0.0, 0.0]
                axis = o["axis"]
                p[axis], q[axis] = np.asarray(o["interval"]) * 2
                p[1 - axis] = q[1 - axis] = o["fixed"] * 2
                doors.append([p, q])
                cv2.line(
                    target[2], tuple(np.rint(p).astype(int)), tuple(np.rint(q).astype(int)), 1, 3
                )
            rooms = synthetic_rooms(spec)
            save(
                f"Syn_{seed}",
                split,
                "synthetic",
                gray,
                target,
                np.ones_like(target),
                doors,
                rooms,
                hashlib.sha256(gray.tobytes()).hexdigest(),
            )
    protocol = {
        "version": "independent-boundaries/1.0",
        "seed": SEED,
        "samples": records,
        "counts": {
            split: {
                kind: sum(r["split"] == split and r["kind"] == kind for r in records)
                for kind in ["human", "synthetic"]
            }
            for split in ["train", "validation", "test"]
        },
        "human_labels": "Approximate manual stroke traces and gaps; boxes derived from gap endpoints, not dense masks or manually verified boxes.",
        "holdout": "Original parent groups held out from these newly trained models. No writer holdout. Existing production DINO saw all 70 originals; its scores are not a clean holdout comparator.",
        "public_photos": "The two WhatsApp photos are development examples only, excluded from all train/validation/test datasets.",
        "checkpoints": "No project checkpoints initialize the new models; U-Net random initialization, YOLO public COCO initialization.",
        "selection": "Validation only. Thresholds frozen before reporting test scores.",
        "training": {"yolo_epochs": 20, "unet_epochs": 20, "yolo_size": 512, "unet_tile_size": 256},
        "pipeline": "Independent wall/gate masks + connected components. Does not initialize or call production DINO, its learned decoder, or production room_geometry inference.",
    }
    write(OUT / "protocol.json", protocol)
    (OUT / "dataset.yaml").write_text(
        f'path: {OUT / "dataset"}\ntrain: images/train\nval: images/validation\ntest: images/test\nnames:\n  0: door_notches\n'
    )
    print(protocol["counts"], flush=True)


class BoundaryUNet(nn.Module):
    def __init__(self, width=12):
        super().__init__()

        def block(a, b):
            return nn.Sequential(
                nn.Conv2d(a, b, 3, padding=1), nn.ReLU(), nn.Conv2d(b, b, 3, padding=1), nn.ReLU()
            )

        self.e1 = block(2, width)
        self.e2 = block(width, width * 2)
        self.e3 = block(width * 2, width * 4)
        self.d2 = block(width * 6, width * 2)
        self.d1 = block(width * 3, width)
        self.head = nn.Conv2d(width, 3, 1)

    def forward(self, x):
        a = self.e1(x)
        b = self.e2(F.max_pool2d(a, 2))
        c = self.e3(F.max_pool2d(b, 2))
        b = self.d2(
            torch.cat(
                [F.interpolate(c, size=b.shape[-2:], mode="bilinear", align_corners=False), b], 1
            )
        )
        return self.head(
            self.d1(
                torch.cat(
                    [F.interpolate(b, size=a.shape[-2:], mode="bilinear", align_corners=False), a],
                    1,
                )
            )
        )


def inputs(gray):
    background = cv2.GaussianBlur(gray, (0, 0), 5)
    return np.stack(
        [
            (255 - gray) / 255.0,
            np.clip(cv2.subtract(background, gray).astype(float) * 6 / 255, 0, 1),
        ]
    ).astype(np.float32)


def mask_loss(logits, target, known):
    positive = torch.tensor([8.0, 12.0, 30.0], device=logits.device).reshape(1, 3, 1, 1)
    loss = F.binary_cross_entropy_with_logits(logits, target, reduction="none", pos_weight=positive)
    bce = (loss * known).sum((0, 2, 3)) / known.sum((0, 2, 3)).clamp_min(1)
    prob = logits.sigmoid()
    dice = 1 - (2 * (prob * target * known).sum((0, 2, 3)) + 1) / (
        (prob * known).sum((0, 2, 3)) + (target * known).sum((0, 2, 3)) + 1
    )
    return (bce + dice).mean()


def train_unet():
    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print("UNET DEVICE", device, flush=True)
    protocol = json.loads((OUT / "protocol.json").read_text())
    rng = np.random.default_rng(SEED)
    samples = {
        split: [r for r in protocol["samples"] if r["split"] == split]
        for split in ["train", "validation"]
    }
    cache = {
        r["id"]: dict(np.load(OUT / "cache" / f"{r['id']}.npz"))
        for rows in samples.values()
        for r in rows
    }
    model = BoundaryUNet().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    history = []
    best = float("inf")
    started = time.time()
    for epoch in range(1, protocol["training"]["unet_epochs"] + 1):
        model.train()
        rows = samples["train"] * 2
        rng.shuffle(rows)
        losses = []
        for start in range(0, len(rows), 8):
            xs = []
            ys = []
            ks = []
            for row in rows[start : start + 8]:
                c = cache[row["id"]]
                g = c["gray"]
                target = c["target"]
                known = c["known"].astype(np.float32)
                if rng.random() < 0.65 and target[2].any():
                    point = np.argwhere(target[2] > 0)[int(rng.integers(target[2].sum()))]
                    y, x = np.clip(point - 128 + rng.integers(-64, 65, 2), 0, 256)
                else:
                    y, x = rng.integers(0, 257, 2)
                g = g[y : y + 256, x : x + 256].copy()
                t = target[:, y : y + 256, x : x + 256].copy()
                k = known[:, y : y + 256, x : x + 256].copy()
                rotation = int(rng.integers(4))
                g = np.rot90(g, rotation).copy()
                t = np.rot90(t, rotation, axes=(1, 2)).copy()
                k = np.rot90(k, rotation, axes=(1, 2)).copy()
                g = np.clip(
                    (g.astype(float) - 255) * rng.uniform(0.45, 1.2)
                    + rng.uniform(225, 255)
                    + rng.normal(0, rng.uniform(0, 1.5), g.shape),
                    0,
                    255,
                ).astype(np.uint8)
                xs.append(inputs(g))
                ys.append(t)
                ks.append(k)
            optimizer.zero_grad()
            loss = mask_loss(
                model(torch.from_numpy(np.stack(xs)).to(device)),
                torch.from_numpy(np.stack(ys)).float().to(device),
                torch.from_numpy(np.stack(ks)).to(device),
            )
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        validation = []
        with torch.inference_mode():
            for row in samples["validation"]:
                c = cache[row["id"]]
                g = c["gray"]
                t = torch.from_numpy(c["target"][None]).float()
                k = torch.from_numpy(c["known"][None]).float()
                validation.append(
                    float(
                        mask_loss(
                            model(torch.from_numpy(inputs(g)[None]).to(device)),
                            t.to(device),
                            k.to(device),
                        )
                    )
                )
        score = float(np.mean(validation))
        history.append(
            {
                "epoch": epoch,
                "loss": float(np.mean(losses)),
                "validation_loss": score,
                "elapsed_seconds": time.time() - started,
            }
        )
        if score < best:
            best = score
            torch.save(
                {
                    "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                    "epoch": epoch,
                    "seed": SEED,
                    "channels": ["wall", "tick", "door_gate"],
                    "initialization": "random",
                    "device": device,
                },
                OUT / "unet-best.pt",
            )
        write(OUT / "unet-history.json", history)
        print("UNET", history[-1], flush=True)


def train_yolo(name):
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
    protocol = json.loads((OUT / "protocol.json").read_text())
    weights = OUT / (name + ".pt")
    os.chdir(OUT)
    model = YOLO(str(weights) if weights.exists() else name + ".pt")
    model.train(
        data=str(OUT / "dataset.yaml"),
        epochs=protocol["training"]["yolo_epochs"],
        imgsz=512,
        batch=4,
        device="mps" if torch.backends.mps.is_available() else "cpu",
        workers=0,
        seed=SEED,
        deterministic=True,
        project=str(OUT / "training"),
        name=name,
        exist_ok=False,
        plots=False,
        save=True,
        cache=False,
        amp=False,
        optimizer="AdamW",
        lr0=0.001,
        patience=protocol["training"]["yolo_epochs"],
        degrees=5,
        translate=0.05,
        scale=0.2,
        flipud=0.5,
        fliplr=0.5,
        mosaic=0.3,
        close_mosaic=5,
        pretrained=True,
        verbose=False,
    )


def train_fasterrcnn():
    from torchvision.models.detection import (
        fasterrcnn_mobilenet_v3_large_320_fpn,
        FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
    )
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    device = "cpu"
    print("FASTER_RCNN DEVICE", device, flush=True)
    model = fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT,
        trainable_backbone_layers=0,
        min_size=512,
        max_size=512,
        rpn_pre_nms_top_n_train=400,
        rpn_post_nms_top_n_train=200,
        rpn_pre_nms_top_n_test=200,
        rpn_post_nms_top_n_test=100,
    )
    model.roi_heads.box_predictor = FastRCNNPredictor(
        model.roi_heads.box_predictor.cls_score.in_features, 2
    )
    model.to(device)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.0003)
    protocol = json.loads((OUT / "protocol.json").read_text())
    train = [r for r in protocol["samples"] if r["split"] == "train"]
    validation = [r for r in protocol["samples"] if r["split"] == "validation"]
    images = {
        r["id"]: torch.from_numpy(np.repeat(cv2.imread(r["image"], 0)[None], 3, axis=0)).float()
        / 255
        for r in train + validation
    }
    rng = random.Random(SEED)
    history = []
    best = -1
    started = time.time()
    for epoch in range(1, 21):
        rng.shuffle(train)
        model.train()
        losses = []
        for index in range(0, len(train), 4):
            rows = train[index : index + 4]
            xs = [images[r["id"]].to(device) for r in rows]
            targets = [
                {
                    "boxes": torch.tensor(r["boxes"], dtype=torch.float32, device=device).reshape(
                        -1, 4
                    ),
                    "labels": torch.ones(len(r["boxes"]), dtype=torch.int64, device=device),
                }
                for r in rows
            ]
            optimizer.zero_grad()
            loss = sum(model(xs, targets).values())
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        scores = []
        with torch.inference_mode():
            for row in validation:
                result = model([images[row["id"]].to(device)])[0]
                boxes = result["boxes"][result["scores"] > 0.3].cpu().tolist()
                scores.append(counts(boxes, row["boxes"], bbox_iou, 0.5))
        score = metrics(scores)["f1"]
        history.append(
            {
                "epoch": epoch,
                "loss": float(np.mean(losses)),
                "validation_door_f1": score,
                "elapsed_seconds": time.time() - started,
            }
        )
        if score > best:
            best = score
            torch.save(
                {
                    "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                    "epoch": epoch,
                    "architecture": "fasterrcnn_mobilenet_v3_large_320_fpn",
                    "backbone_frozen": True,
                },
                OUT / "fasterrcnn-best.pt",
            )
        write(OUT / "fasterrcnn-history.json", history)
        print("FASTER_RCNN", history[-1], flush=True)


def components(barrier):
    binary = np.uint8(barrier > 0)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(1 - binary)
    masks = []
    polygons = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if (
            x <= 0
            or y <= 0
            or x + w >= binary.shape[1]
            or y + h >= binary.shape[0]
            or area < binary.size * 0.0015
        ):
            continue
        mask = np.uint8(labels == i)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        contour = cv2.approxPolyDP(contour, 1.5, True)[:, 0]
        if len(contour) < 3:
            continue
        polygon = Polygon(contour)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.geom_type != "Polygon":
            continue
        masks.append(mask)
        polygons.append([list(polygon.exterior.coords)])
    return masks, polygons


def cv_mask(gray):
    weak = np.uint8(
        cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 5
        )
        > 0
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(weak)
    keep = [i for i in range(1, n) if stats[i, 4] >= 8]
    return np.uint8(np.isin(labels, keep))


def bbox_iou(a, b):
    a, b = np.asarray(a), np.asarray(b)
    span = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]))
    inter = span.prod()
    union = np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - inter
    return float(inter / union) if union else 0.0


def counts(predicted, expected, similarity, minimum):
    from scipy.optimize import linear_sum_assignment

    if not predicted or not expected:
        return {"tp": 0, "fp": len(predicted), "fn": len(expected)}
    scores = np.asarray([[similarity(a, b) for b in expected] for a in predicted])
    cost = np.where(scores >= minimum, -1000 - scores, 0)
    left, right = linear_sum_assignment(cost)
    matched = sum(scores[i, j] >= minimum for i, j in zip(left, right))
    return {
        "tp": int(matched),
        "fp": len(predicted) - int(matched),
        "fn": len(expected) - int(matched),
    }


def metrics(values):
    total = {k: sum(v[k] for v in values) for k in ["tp", "fp", "fn"]}
    tp, fp, fn = (total[k] for k in ["tp", "fp", "fn"])
    return {
        **total,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
    }


def polygons(values):
    return [unary_union([Polygon(p) for p in parts]).buffer(0) for parts in values]


def polygon_iou(a, b):
    return a.intersection(b).area / max(1, a.union(b).area)


def seal_box(barrier, box):
    x, y, X, Y = box
    axis = 0 if X - x >= Y - y else 1
    normal = 1 - axis
    lo, hi = (x, X) if axis == 0 else (y, Y)
    low, high = (y, Y) if axis == 0 else (x, X)
    best = None
    for fixed in range(max(0, round(low) - 3), min(barrier.shape[normal], round(high) + 4)):
        strengths = []
        for start, end in [(lo - 10, lo + 2), (hi - 2, hi + 10)]:
            positions = np.arange(max(0, round(start)), min(barrier.shape[axis], round(end) + 1))
            normals = np.arange(max(0, fixed - 1), min(barrier.shape[normal], fixed + 2))
            patch = (
                barrier[np.ix_(normals, positions)]
                if axis == 0
                else barrier[np.ix_(positions, normals)].T
            )
            strengths.append(float(patch.max(0).mean()) if patch.size else 0.0)
        rank = (min(strengths), sum(strengths), -abs(fixed - (low + high) / 2))
        if best is None or rank > best[0]:
            best = (rank, fixed)
    if best is None or best[0][0] < 0.2:
        return
    p, q = (
        ([lo - 3, best[1]], [hi + 3, best[1]])
        if axis == 0
        else ([best[1], lo - 3], [best[1], hi + 3])
    )
    cv2.line(barrier, tuple(np.rint(p).astype(int)), tuple(np.rint(q).astype(int)), 1, 3)


def gate_boxes(gate):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(np.uint8(gate))
    result = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 4 or max(w, h) < 5:
            continue
        p, q = (
            ([x, y + h / 2], [x + w, y + h / 2]) if w >= h else ([x + w / 2, y], [x + w / 2, y + h])
        )
        result.append(door_box([p, q]))
    return result


def evaluate():
    from ultralytics import YOLO

    torch.set_num_threads(3)
    protocol = json.loads((OUT / "protocol.json").read_text())
    model = BoundaryUNet()
    checkpoint = torch.load(OUT / "unet-best.pt", weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    rows = [r for r in protocol["samples"] if r["split"] != "train"]
    if (OUT / "stress-protocol.json").exists():
        rows += json.loads((OUT / "stress-protocol.json").read_text())["samples"]
    photos = [
        ("photo_L", "WhatsApp Image 2026-11-09 at 13.26.15.jpeg", 4, 3),
        ("photo_U", "WhatsApp Image 2026-11-09 at 13.54.14.jpeg", 2, 1),
    ]
    from SketchPipeline.preprocessing.prepare import prepare
    from SketchPipeline.shape_authoring.diagnostic_preprocessing import letterbox

    for identifier, filename, room_count, door_count in photos:
        source = Path("/Users/pelinsukaleli/Downloads") / filename
        images, meta = prepare(source, max_side=512)
        gray, _ = letterbox(images["gray"], meta, 512)
        path = OUT / (identifier + ".png")
        cv2.imwrite(str(path), gray)
        rows.append(
            {
                "id": identifier,
                "image": str(path),
                "split": "development",
                "kind": "photo",
                "expected_room_count": room_count,
                "expected_door_count": door_count,
            }
        )
    predictions = {}
    for row in rows:
        g = cv2.imread(row["image"], 0)
        with torch.inference_mode():
            prob = model(torch.from_numpy(inputs(g)[None])).sigmoid()[0].numpy()
        predictions[row["id"]] = {"gray": g, "unet": prob, "cv": cv_mask(g)}
    for name in ["yolov8n", "yolo11n"]:
        detector = YOLO(str(OUT / "training" / name / "weights/best.pt"))
        for row in rows:
            result = detector.predict(
                row["image"], imgsz=512, device="cpu", conf=0.05, verbose=False
            )[0]
            predictions[row["id"]][name] = [
                (box.tolist(), float(conf))
                for box, conf in zip(
                    result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()
                )
            ]
    if (OUT / "fasterrcnn-best.pt").exists():
        from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

        detector = fasterrcnn_mobilenet_v3_large_320_fpn(
            weights=None,
            weights_backbone=None,
            min_size=512,
            max_size=512,
            rpn_pre_nms_top_n_test=200,
            rpn_post_nms_top_n_test=100,
        )
        detector.roi_heads.box_predictor = FastRCNNPredictor(
            detector.roi_heads.box_predictor.cls_score.in_features, 2
        )
        detector.load_state_dict(
            torch.load(OUT / "fasterrcnn-best.pt", weights_only=True)["state_dict"]
        )
        detector.eval()
        with torch.inference_mode():
            for row in rows:
                g = predictions[row["id"]]["gray"]
                tensor = torch.from_numpy(np.repeat(g[None], 3, 0)).float() / 255
                output = detector([tensor])[0]
                predictions[row["id"]]["fasterrcnn"] = [
                    (box.tolist(), float(score))
                    for box, score in zip(output["boxes"], output["scores"])
                    if float(score) >= 0.05
                ]
    mask2former_present = (OUT / "mask2former-best").exists()
    if mask2former_present:
        from transformers import Mask2FormerForUniversalSegmentation, Mask2FormerImageProcessor

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        processor = Mask2FormerImageProcessor.from_pretrained(OUT / "mask2former-best")
        segmenter = (
            Mask2FormerForUniversalSegmentation.from_pretrained(OUT / "mask2former-best")
            .to(device)
            .eval()
        )
        with torch.inference_mode():
            for row in rows:
                image = cv2.cvtColor(predictions[row["id"]]["gray"], cv2.COLOR_GRAY2RGB)
                network_inputs = processor(images=image, return_tensors="pt").to(device)
                output = segmenter(**network_inputs)
                labels = (
                    processor.post_process_semantic_segmentation(output, target_sizes=[(512, 512)])[
                        0
                    ]
                    .cpu()
                    .numpy()
                )
                predictions[row["id"]]["mask2former"] = np.stack(
                    [labels == 1, np.zeros_like(labels, bool), labels == 2]
                )
    methods = ["cv_only", "cv+yolov8n", "cv+yolo11n", "unet_only", "unet+yolo11n"]
    if mask2former_present:
        methods += ["mask2former_only", "mask2former+yolo11n"]
    if (OUT / "fasterrcnn-best.pt").exists():
        methods += ["cv+fasterrcnn", "unet+fasterrcnn"]

    def predict(row, method, threshold):
        cached = predictions[row["id"]]
        unet = cached["unet"]
        if method.startswith("unet"):
            wall = unet[0] > 0.5
        elif method.startswith("mask2former"):
            wall = cached["mask2former"][0]
        else:
            wall = cached["cv"] > 0
        if method == "cv_only":
            boxes = []
        elif method == "unet_only":
            boxes = gate_boxes(unet[2] > threshold)
        elif method == "mask2former_only":
            boxes = gate_boxes(cached["mask2former"][2])
        else:
            boxes = [box for box, score in cached[method.split("+")[1]] if score >= threshold]
        barrier = np.uint8(wall)
        for box in boxes:
            seal_box(barrier, box)
        regions = components(barrier)[1]
        return boxes, regions

    selected = {}
    for method in methods:
        choices = []
        for threshold in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            scores = []
            for row in rows:
                if row["split"] != "validation" or row["kind"] != "human":
                    continue
                boxes, _ = predict(row, method, threshold)
                scores.append(counts(boxes, row["boxes"], bbox_iou, 0.5))
            choices.append((metrics(scores)["f1"], threshold))
        selected[method] = max(choices)[1]
    write(OUT / "selected-thresholds.json", selected)
    pixel_results = {}
    for kind in ["human", "synthetic", "stress"]:
        totals = [{"tp": 0, "fp": 0, "fn": 0} for _ in range(3)]
        for row in rows:
            if row["kind"] != kind or row["split"] != "test":
                continue
            data = np.load(OUT / "cache" / f"{row['id']}.npz")
            known = data["known"] > 0
            target = data["target"] > 0
            pred = predictions[row["id"]]["unet"] > 0.5
            for channel in range(3):
                totals[channel]["tp"] += int(
                    np.count_nonzero(pred[channel] & target[channel] & known[channel])
                )
                totals[channel]["fp"] += int(
                    np.count_nonzero(pred[channel] & ~target[channel] & known[channel])
                )
                totals[channel]["fn"] += int(
                    np.count_nonzero(~pred[channel] & target[channel] & known[channel])
                )
        pixel_results[kind] = {
            name: metrics([value]) for name, value in zip(["wall", "tick", "door_gate"], totals)
        }
    scored = []
    photo_results = []
    for row in rows:
        if row["split"] == "validation":
            continue
        for method in methods:
            boxes, region_points = predict(row, method, selected[method])
            regions = polygons(region_points)
            if row["kind"] == "photo":
                photo_results.append(
                    {
                        "id": row["id"],
                        "method": method,
                        "rooms": len(regions),
                        "doors": len(boxes),
                        "expected_rooms": row["expected_room_count"],
                        "expected_doors": row["expected_door_count"],
                    }
                )
                canvas = cv2.cvtColor(predictions[row["id"]]["gray"], cv2.COLOR_GRAY2BGR)
                for region in region_points:
                    for p in region:
                        cv2.polylines(canvas, [np.asarray(p, np.int32)], True, (40, 140, 30), 2)
                for box in boxes:
                    x, y, X, Y = np.rint(box).astype(int)
                    cv2.rectangle(canvas, (x, y), (X, Y), (20, 30, 230), 2)
                path = OUT / "figures" / f"{row['id']}_{method.replace('+','_')}.png"
                path.parent.mkdir(exist_ok=True)
                cv2.imwrite(str(path), canvas)
                continue
            item = {
                "id": row["id"],
                "kind": row["kind"],
                "method": method,
                "doors": counts(boxes, row["boxes"], bbox_iou, 0.5),
                "room_count_correct": len(regions) == len(row["rooms"]),
                "room_evaluable": bool(row["rooms"]),
            }
            if row["rooms"]:
                item["regions"] = counts(regions, polygons(row["rooms"]), polygon_iou, 0.5)
            scored.append(item)
    summaries = {}
    for kind in ["human", "synthetic", "stress"]:
        summaries[kind] = {}
        for method in methods:
            current = [r for r in scored if r["kind"] == kind and r["method"] == method]
            labelled = [r for r in current if r["room_evaluable"]]
            summaries[kind][method] = {
                "images": len(current),
                "doors": metrics([r["doors"] for r in current]),
                "regions": metrics([r["regions"] for r in labelled]),
                "room_count_accuracy": sum(r["room_count_correct"] for r in labelled)
                / max(1, len(labelled)),
                "room_labelled_images": len(labelled),
            }
    report = {
        "thresholds_selected_on_validation": selected,
        "unet_mask_metrics": pixel_results,
        "test": summaries,
        "development_photos": photo_results,
        "unet_selected_epoch": checkpoint["epoch"],
        "mask2former_training": (
            json.loads((OUT / "mask2former-protocol.json").read_text())
            if (OUT / "mask2former-protocol.json").exists()
            else None
        ),
        "limitations": [
            protocol["human_labels"],
            protocol["holdout"],
            protocol["public_photos"],
            "These are limited-budget pilot runs, not tuned full model comparisons. Bounding boxes alone do not determine exact door orientation or clearance. No production deployment.",
        ],
    }
    write(OUT / "report.json", report)
    write(OUT / "test-per-image.json", scored)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=["prepare", "unet", "yolov8n", "yolo11n", "fasterrcnn", "evaluate"]
    )
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare_data()
    elif args.phase == "unet":
        train_unet()
    elif args.phase == "evaluate":
        evaluate()
    elif args.phase == "fasterrcnn":
        train_fasterrcnn()
    else:
        train_yolo(args.phase)
