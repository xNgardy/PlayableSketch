import hashlib
import json
import os
from pathlib import Path
import cv2
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from shapely.geometry import Polygon
from .diagnostic_preprocessing import letterbox
from SketchPipeline.preprocessing.prepare import prepare

DEFAULT_PACKAGE = Path(__file__).with_name("models") / "hybrid-unet-yolo11-v1" / "model-lock.json"


def validate_package(path, expected_sha256=None):
    path = Path(path).resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Hybrid manifest checksum mismatch")
    config = json.loads(path.read_text())
    if config.get("version") != "hybrid-unet-yolo11/1.0":
        raise ValueError("Unsupported hybrid model version")
    parameters = config["parameters"]
    if (
        not 0 < parameters["wall_threshold"] < 1
        or not 0 < parameters["door_threshold"] < 1
        or parameters["closing_kernel"] not in (3, 5)
    ):
        raise ValueError("Invalid hybrid inference parameters")
    if config.get("input_side") != 1024 or config.get("door_full_and_tiled") is not True:
        raise ValueError("Unsupported hybrid input policy")
    paths = {}
    for kind in ("wall", "door"):
        checkpoint = (path.parent / config[kind]["path"]).resolve()
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != config[kind]["sha256"]:
            raise ValueError(kind + " checkpoint checksum mismatch")
        paths[kind] = checkpoint
    return config, paths, digest


def native_input(image):
    from .propose import prepare_image

    _, baseline = prepare_image(image)
    rotation = baseline.get("automatic_deskew_degrees", 0)
    images, metadata = prepare(Path(image), max_side=1024, deskew_degrees=rotation)
    metadata["automatic_deskew_degrees"] = rotation
    return letterbox(images["gray"], metadata, 1024)


class WallUNet(nn.Module):
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
        self.head = nn.Conv2d(width, 1, 1)

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


def features(gray):
    background = cv2.GaussianBlur(gray, (0, 0), 5)
    return np.stack(
        [
            (255 - gray) / 255.0,
            np.clip(cv2.subtract(background, gray).astype(float) * 6 / 255, 0, 1),
        ]
    ).astype(np.float32)


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


def door_predictions(detector, gray, device):
    windows = [(0, 0, gray.shape[1], gray.shape[0])]
    for y in (0, 384):
        for x in (0, 384):
            windows.append((x, y, x + 640, y + 640))
    boxes = []
    scores = []
    for x, y, X, Y in windows:
        tile = cv2.cvtColor(gray[y:Y, x:X], cv2.COLOR_GRAY2RGB)
        result = detector.predict(tile, imgsz=640, device=device, conf=0.05, verbose=False)[0]
        for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
            if (
                x > 0
                and box[0] < 6
                or y > 0
                and box[1] < 6
                or X < gray.shape[1]
                and box[2] > X - x - 6
                or Y < gray.shape[0]
                and box[3] > Y - y - 6
            ):
                continue
            box = box + np.array([x, y, x, y])
            boxes.append(box)
            scores.append(float(score))
    if not boxes:
        return []
    from torchvision.ops import nms

    kept = nms(
        torch.tensor(np.asarray(boxes), dtype=torch.float32), torch.tensor(scores), 0.4
    ).tolist()
    return [(boxes[i].tolist(), scores[i]) for i in kept]


def seal_door(barrier, bounds):
    x, y, X, Y = bounds
    axis = 0 if X - x >= Y - y else 1
    normal = 1 - axis
    lo, hi = (x, X) if axis == 0 else (y, Y)
    low, high = (y, Y) if axis == 0 else (x, X)
    best = None
    for fixed in range(max(0, round(low) - 6), min(barrier.shape[normal], round(high) + 7)):
        strengths = []
        for start, end in [(lo - 20, lo + 4), (hi - 4, hi + 20)]:
            positions = np.arange(max(0, round(start)), min(barrier.shape[axis], round(end) + 1))
            normals = np.arange(max(0, fixed - 2), min(barrier.shape[normal], fixed + 3))
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
        return False
    p, q = (
        ([lo - 6, best[1]], [hi + 6, best[1]])
        if axis == 0
        else ([best[1], lo - 6], [best[1], hi + 6])
    )
    cv2.line(barrier, tuple(np.rint(p).astype(int)), tuple(np.rint(q).astype(int)), 1, 6)
    return True


def regions_from_predictions(probability, doors, parameters):
    if probability.ndim != 2 or not np.isfinite(probability).all():
        raise ValueError("Expected a finite two-dimensional wall probability map")
    barrier = np.uint8(probability > parameters["wall_threshold"])
    boxes = [box for box, score in doors if score >= parameters["door_threshold"]]
    attached = [seal_door(barrier, box) for box in boxes]
    kernel = parameters["closing_kernel"]
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    masks, regions = components(barrier)
    return boxes, regions, barrier, attached


class HybridModel:
    def __init__(self, checkpoint=DEFAULT_PACKAGE, expected_sha256=None, device=None):
        os.environ.setdefault(
            "YOLO_CONFIG_DIR",
            str(Path(__file__).resolve().parents[2] / "Saved/Runtime/hybrid-v1/settings"),
        )
        os.environ.setdefault("YOLO_AUTOINSTALL", "false")
        from ultralytics import YOLO, settings

        settings.update(
            {
                key: False
                for key in (
                    "sync",
                    "hub",
                    "wandb",
                    "mlflow",
                    "clearml",
                    "comet",
                    "neptune",
                    "tensorboard",
                    "dvc",
                )
                if key in settings
            }
        )
        self.config, paths, digest = validate_package(checkpoint, expected_sha256)
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.wall = WallUNet()
        state = torch.load(paths["wall"], weights_only=True, map_location="cpu")
        if state.get("architecture") != "wall-unet/1.0":
            raise ValueError("Unexpected wall model architecture")
        self.wall.load_state_dict(state["state_dict"])
        self.wall.to(self.device).eval()
        self.door = YOLO(str(paths["door"]))
        self.metadata = {
            "architecture": "hybrid-unet-yolo11/1.0",
            "backend": "pytorch-ultralytics-local",
            "checkpoint_sha256": digest,
            "wall_sha256": self.config["wall"]["sha256"],
            "door_sha256": self.config["door"]["sha256"],
            "device": self.device,
            "torch_version": torch.__version__,
            "channels": ["wall"],
        }

    def predict(self, image):
        gray, metadata = native_input(image)
        with torch.inference_mode():
            probability = (
                self.wall(torch.from_numpy(features(gray)[None]).to(self.device))
                .sigmoid()[0, 0]
                .cpu()
                .numpy()
            )
        detected = door_predictions(self.door, gray, self.device)
        boxes, regions, barrier, attached = regions_from_predictions(
            probability, detected, self.config["parameters"]
        )
        return {
            "gray": gray,
            "preprocessing": metadata,
            "wall_probability": probability,
            "door_boxes": boxes,
            "regions": regions,
            "closed_barrier": barrier,
            "door_attached": attached,
        }
