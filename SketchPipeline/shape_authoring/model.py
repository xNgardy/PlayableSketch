import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from .synthetic import CHANNELS

ARCHITECTURE = "shape-unet/1.0"


class ShapeUNet(nn.Module):

    def __init__(self, width=12):
        super().__init__()

        def block(a, b):
            return nn.Sequential(
                nn.Conv2d(a, b, 3, padding=1), nn.ReLU(), nn.Conv2d(b, b, 3, padding=1), nn.ReLU()
            )

        self.encoder = nn.ModuleList(
            [
                block(2, width),
                block(width, width * 2),
                block(width * 2, width * 4),
                block(width * 4, width * 8),
            ]
        )
        self.decoder = nn.ModuleList(
            [block(width * 12, width * 4), block(width * 6, width * 2), block(width * 3, width)]
        )
        self.head = nn.Conv2d(width, len(CHANNELS), 1)

    def forward(self, x):
        features = []
        for i, encoder in enumerate(self.encoder):
            x = encoder(x)
            features.append(x)
            if i < 3:
                x = F.max_pool2d(x, 2)
        for decoder, skip in zip(self.decoder, reversed(features[:-1])):
            x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            x = decoder(torch.cat([x, skip], dim=1))
        return self.head(x)


def features(gray, cleaned=None):
    if cleaned is None:
        cleaned = gray
    return np.stack([(255 - gray) / 255.0, (255 - cleaned) / 255.0]).astype(np.float32)


class LocalSegmenter:

    def __init__(self, checkpoint, expected_sha256=None, device="cpu"):
        started = time.perf_counter()
        checkpoint = Path(checkpoint)
        self.sha256 = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if expected_sha256 and self.sha256 != expected_sha256:
            raise ValueError("Shape model checksum mismatch")
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if state.get("architecture") == "shape-dinov2/1.0":
            from .dino_model import DinoSegmenter

            self.delegate = DinoSegmenter(checkpoint, expected_sha256, device, state=state)
            self.metadata = self.delegate.metadata
            return
        if state["architecture"] != ARCHITECTURE or state["channels"] != CHANNELS:
            raise ValueError("Unsupported shape model")
        self.model = ShapeUNet(state["width"])
        self.model.load_state_dict(state["state_dict"])
        self.device = device
        self.model.to(device).eval()
        self.metadata = {
            "backend": "pytorch-local",
            "architecture": ARCHITECTURE,
            "checkpoint_sha256": self.sha256,
            "width": state["width"],
            "torch_version": torch.__version__,
            "device": device,
            "initialization_seconds": time.perf_counter() - started,
            "channels": CHANNELS,
        }

    def predict(self, gray, cleaned=None):
        if hasattr(self, "delegate"):
            prediction = self.delegate.predict(gray, cleaned)
            self.last_auxiliary = self.delegate.last_auxiliary
            return prediction
        tensor = torch.from_numpy(features(gray, cleaned))[None].to(self.device)
        with torch.inference_mode():
            prediction = self.model(tensor).sigmoid()[0].cpu().numpy()
        if not np.isfinite(prediction).all():
            raise ValueError("Non-finite model output")
        return prediction
