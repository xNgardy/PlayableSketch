import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from SketchPipeline.perception.structural import suppress_grid
from .model import ShapeUNet, ARCHITECTURE, features
from .synthetic import render, freeze, write_json, CHANNELS


def train(output, width):
    protocol = freeze(output)
    if width not in protocol["candidates"]:
        raise ValueError("Candidate not frozen in protocol")
    directory = output / f"candidate_{width}"
    directory.mkdir(exist_ok=False)
    seed = protocol["seed"]
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.set_num_threads(4)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(json.dumps({"status": "preparing", "candidate": width, "device": device}), flush=True)
    cache = output / "training.npz"
    if cache.exists():
        with np.load(cache) as data:
            x, y = (data["x"], data["y"])
    else:
        xs = []
        ys = []
        for parent in protocol["train_parent_seeds"]:
            for style in protocol["train_styles"]:
                image, masks, _ = render(parent, style)
                clean, _, _ = suppress_grid(image)
                xs.append(features(image, clean))
                ys.append((masks > 0).astype(np.float32))
        x, y = (np.stack(xs), np.stack(ys))
        np.savez_compressed(cache, x=x, y=y)
    model = ShapeUNet(width).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=protocol["learning_rate"])
    batch_size = protocol["batch_size"]
    history = []
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    pos_weight = torch.tensor([5.0, 1.0, 4.0, 14.0, 10.0, 15.0], device=device).reshape(1, -1, 1, 1)
    for epoch in range(protocol["epochs"]):
        order = rng.permutation(len(x))
        losses = []
        for start in range(0, len(x), batch_size):
            selected = order[start : start + batch_size]
            a = torch.from_numpy(x[selected]).to(device)
            target = torch.from_numpy(y[selected]).to(device)
            logits = model(a)
            probability = logits.sigmoid()
            bce = F.binary_cross_entropy_with_logits(logits, target, pos_weight=pos_weight)
            dice = 1 - (2 * (probability * target).sum((0, 2, 3)) + 1) / (
                probability.sum((0, 2, 3)) + target.sum((0, 2, 3)) + 1
            )
            loss = bce + dice.mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        item = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)),
            "elapsed_seconds": time.perf_counter() - started,
        }
        history.append(item)
        print(json.dumps({"candidate": width, **item}), flush=True)
    model.to("cpu")
    checkpoint = directory / "model.pt"
    torch.save(
        {
            "architecture": ARCHITECTURE,
            "channels": CHANNELS,
            "width": width,
            "state_dict": model.state_dict(),
        },
        checkpoint,
    )
    report = {
        "candidate_width": width,
        "device": device,
        "training_seconds": time.perf_counter() - started,
        "history": history,
        "training_samples": len(x),
        "training_parent_groups": len(protocol["train_parent_seeds"]),
        "protocol_sha256": hashlib.sha256((output / "protocol.json").read_bytes()).hexdigest(),
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "opencv_version": cv2.__version__,
        "training_cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
        "source_hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path(__file__).with_name("model.py"),
                Path(__file__).with_name("synthetic.py"),
            ]
        },
    }
    write_json(directory / "training_report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("Saved/ShapeFirst/v1"))
    parser.add_argument("--width", type=int, required=True)
    args = parser.parse_args()
    train(args.output, args.width)
