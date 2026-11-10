from functools import lru_cache
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name("dinov2.lock.json")
ARCHITECTURE = "shape-dinov2/1.0"
CHANNELS = [
    "wall",
    "room_interior",
    "corridor_interior",
    "tick",
    "junction",
    "open_interface",
    "door_endpoint",
    "logical_boundary",
]
INPUT_SIDE = 448
OUTPUT_SIDE = 256
LAYERS = [2, 5, 8, 11]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dependencies():
    lock = json.loads(LOCK.read_text())
    repo = ROOT / lock["source_directory"]
    checkpoint = ROOT / lock["checkpoint_path"]
    for name, expected in lock["source_hashes"].items():
        if sha(repo / name) != expected:
            raise ValueError("DINOv2 source checksum mismatch: " + name)
    if sha(repo / "LICENSE") != lock["license_sha256"]:
        raise ValueError("DINOv2 license changed")
    if sha(checkpoint) != lock["checkpoint_sha256"]:
        raise ValueError("DINOv2 backbone checksum mismatch")
    return (lock, repo, checkpoint)


@lru_cache(maxsize=2)
def _backbone(repo, checkpoint, device, lock_hash):
    sys.path.insert(0, str(repo))
    package = importlib.import_module("dinov2")
    if not Path(package.__file__).resolve().is_relative_to(repo):
        raise ValueError("Another DINOv2 package shadows the pinned source")
    from dinov2.hub.backbones import dinov2_vits14

    model = dinov2_vits14(pretrained=False)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.eval().to(device)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model


def load_backbone(device="cpu"):
    lock, repo, checkpoint = verify_dependencies()
    return _backbone(repo, checkpoint, device, sha(LOCK))


def prepare_tensors(gray, cleaned=None):
    if gray.dtype != np.uint8 or gray.ndim != 2:
        raise ValueError("Expected grayscale uint8")
    if cleaned is None:
        cleaned = gray
    if cleaned.shape != gray.shape or cleaned.dtype != np.uint8:
        raise ValueError("Raw/clean frames differ")
    h, w = gray.shape
    side = max(h, w)
    top = (side - h) // 2
    left = (side - w) // 2
    pad = lambda im: np.pad(
        im, ((top, side - h - top), (left, side - w - left)), constant_values=255
    )
    a, b = (pad(gray), pad(cleaned))
    rgb = (
        np.repeat(
            cv2.resize(a, (INPUT_SIDE, INPUT_SIDE), interpolation=cv2.INTER_AREA)[None], 3, axis=0
        ).astype(np.float32)
        / 255
    )
    rgb = (rgb - np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]) / np.array(
        [0.229, 0.224, 0.225], np.float32
    )[:, None, None]
    ink = np.stack(
        [
            (255 - cv2.resize(im, (OUTPUT_SIDE, OUTPUT_SIDE), interpolation=cv2.INTER_AREA)) / 255.0
            for im in (a, b)
        ]
    ).astype(np.float32)
    return (rgb, ink, {"square_side": side, "top": top, "left": left, "height": h, "width": w})


def extract_features(backbone, rgb):
    with torch.no_grad():
        return torch.stack(backbone.get_intermediate_layers(rgb, n=LAYERS, reshape=True), dim=1)


class DinoDecoder(nn.Module):

    def __init__(self, width=32):
        super().__init__()
        self.width = width
        block = lambda a, b: nn.Sequential(
            nn.Conv2d(a, b, 3, padding=1),
            nn.GroupNorm(8, b),
            nn.GELU(),
            nn.Conv2d(b, b, 3, padding=1),
            nn.GroupNorm(8, b),
            nn.GELU(),
        )
        self.projections = nn.ModuleList([nn.Conv2d(384, width, 1) for _ in LAYERS])
        self.coarse = block(width * 4, width * 2)
        self.raw = nn.Sequential(
            nn.Conv2d(2, 16, 3, padding=1), nn.GELU(), nn.Conv2d(16, 16, 3, padding=1), nn.GELU()
        )
        self.mid = block(width * 2 + 16, width)
        self.fine = block(width + 16, width)
        self.head = nn.Conv2d(width, len(CHANNELS), 1)

    def forward(self, features, ink):
        projected = torch.cat(
            [layer(features[:, i]) for i, layer in enumerate(self.projections)], dim=1
        )
        x = self.coarse(
            F.interpolate(projected, size=(64, 64), mode="bilinear", align_corners=False)
        )
        raw = self.raw(ink)
        x = self.mid(
            torch.cat(
                [
                    F.interpolate(x, size=(128, 128), mode="bilinear", align_corners=False),
                    F.interpolate(raw, size=(128, 128), mode="bilinear", align_corners=False),
                ],
                dim=1,
            )
        )
        return self.head(
            self.fine(
                torch.cat(
                    [
                        F.interpolate(x, size=ink.shape[-2:], mode="bilinear", align_corners=False),
                        raw,
                    ],
                    dim=1,
                )
            )
        )


def decoder_channels(probabilities):
    if probabilities.shape[0] != len(CHANNELS):
        raise ValueError("DINO output channel contract changed")
    result = probabilities[:6].copy()
    result[3] = np.maximum(result[3], probabilities[6])
    result[1:3] = np.minimum(result[1:3], 1 - probabilities[7:8])
    return result


class DinoSegmenter:

    def __init__(self, checkpoint, expected_sha256=None, device="cpu", state=None):
        started = time.perf_counter()
        checkpoint = Path(checkpoint)
        digest = sha(checkpoint)
        if expected_sha256 and digest != expected_sha256:
            raise ValueError("Shape model checksum mismatch")
        if state is None:
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if state["architecture"] != ARCHITECTURE or state["channels"] != CHANNELS:
            raise ValueError("Unsupported DINO decoder checkpoint")
        if state["backbone_lock_sha256"] != sha(LOCK):
            raise ValueError("DINO checkpoint dependency lock mismatch")
        self.device = device
        self.backbone = load_backbone(device)
        self.model = DinoDecoder(state["width"])
        self.model.load_state_dict(state["state_dict"], strict=True)
        self.model.to(device).eval()
        self.last_auxiliary = None
        lock = json.loads(LOCK.read_text())
        self.metadata = {
            "backend": "pytorch-local",
            "architecture": ARCHITECTURE,
            "checkpoint_sha256": digest,
            "backbone": "dinov2_vits14",
            "backbone_sha256": lock["checkpoint_sha256"],
            "backbone_source_revision": lock["revision"],
            "backbone_frozen": True,
            "backbone_license": "Apache-2.0",
            "input_side": INPUT_SIDE,
            "channels": CHANNELS,
            "device": device,
            "torch_version": torch.__version__,
            "width": state["width"],
            "initialization_seconds": time.perf_counter() - started,
            "numeric_text_read": False,
            "decoder_projection": "max(tick,endpoint); interiors capped by 1-logical-boundary",
        }

    def predict(self, gray, cleaned=None):
        rgb, ink, frame = prepare_tensors(gray, cleaned)
        with torch.inference_mode():
            feature = extract_features(self.backbone, torch.from_numpy(rgb[None]).to(self.device))
            probability = (
                self.model(feature, torch.from_numpy(ink[None]).to(self.device))
                .sigmoid()[0]
                .cpu()
                .numpy()
            )
        side = frame["square_side"]
        top, left = (frame["top"], frame["left"])
        h, w = (frame["height"], frame["width"])
        probability = np.stack(
            [
                cv2.resize(c, (side, side), interpolation=cv2.INTER_LINEAR)[
                    top : top + h, left : left + w
                ]
                for c in probability
            ]
        )
        if not np.isfinite(probability).all():
            raise ValueError("Non-finite DINO output")
        self.last_auxiliary = probability
        return decoder_channels(probability)
