import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "Saved/Experiments/independent_boundaries_v1"
os.environ.setdefault("HF_HOME", str(OUT / "hf-cache"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import cv2
import numpy as np
import torch
from transformers import (
    Mask2FormerForUniversalSegmentation,
    Mask2FormerImageProcessor,
    Mask2FormerConfig,
)
from Scripts.independent_boundary_experiment import SEED, write


def run():
    torch.set_num_threads(3)
    torch.manual_seed(SEED)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    checkpoint = "facebook/mask2former-swin-tiny-ade-semantic"
    processor = Mask2FormerImageProcessor.from_pretrained(
        checkpoint, do_resize=False, do_reduce_labels=False, ignore_index=255
    )
    config = Mask2FormerConfig.from_pretrained(checkpoint)
    config.num_labels = 3
    config.id2label = {0: "background", 1: "wall", 2: "door_gate"}
    config.label2id = {value: key for key, value in config.id2label.items()}
    config.train_num_points = 2048
    model = Mask2FormerForUniversalSegmentation.from_pretrained(
        checkpoint, config=config, ignore_mismatched_sizes=True
    )
    for parameter in model.model.pixel_level_module.encoder.parameters():
        parameter.requires_grad_(False)
    model.to(device)
    protocol = json.loads((OUT / "protocol.json").read_text())
    records = {
        split: [r for r in protocol["samples"] if r["split"] == split and r["kind"] == "synthetic"]
        for split in ["train", "validation"]
    }
    cache = {}
    for rows in records.values():
        for row in rows:
            data = np.load(OUT / "cache" / f"{row['id']}.npz")
            target = data["target"]
            seg = np.zeros((512, 512), np.int64)
            seg[target[0] > 0] = 1
            seg[target[2] > 0] = 2
            image = cv2.cvtColor(data["gray"], cv2.COLOR_GRAY2RGB)
            cache[row["id"]] = processor(images=image, segmentation_maps=seg, return_tensors="pt")
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.0001)
    rng = np.random.default_rng(SEED)
    history = []
    best = float("inf")
    started = time.time()
    for epoch in range(1, 6):
        model.train()
        rows = list(records["train"])
        rng.shuffle(rows)
        losses = []
        optimizer.zero_grad()
        for i, row in enumerate(rows):
            inputs = cache[row["id"]]
            inputs = {
                key: [v.to(device) for v in value] if isinstance(value, list) else value.to(device)
                for key, value in inputs.items()
            }
            output = model(**inputs)
            loss = output.loss
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite Mask2Former loss")
            (loss / 4).backward()
            losses.append(float(loss.detach()))
            if (i + 1) % 4 == 0 or i + 1 == len(rows):
                optimizer.step()
                optimizer.zero_grad()
        model.eval()
        validation = []
        with torch.inference_mode():
            for row in records["validation"]:
                inputs = cache[row["id"]]
                inputs = {
                    key: (
                        [v.to(device) for v in value]
                        if isinstance(value, list)
                        else value.to(device)
                    )
                    for key, value in inputs.items()
                }
                validation.append(float(model(**inputs).loss))
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
            model.save_pretrained(OUT / "mask2former-best", safe_serialization=True)
            processor.save_pretrained(OUT / "mask2former-best")
        write(OUT / "mask2former-history.json", history)
        print("MASK2FORMER", history[-1], flush=True)
    write(
        OUT / "mask2former-protocol.json",
        {
            "initialization": checkpoint,
            "epochs": 5,
            "input_size": 512,
            "device": device,
            "backbone_frozen": True,
            "train_images": len(records["train"]),
            "validation_images": len(records["validation"]),
            "human_training_images": 0,
            "reason": "Only synthetic samples have dense masks. Approximate human traces are not converted into invented dense background labels. This is synthetic-domain transfer, not a matched training-data comparison with the other models.",
            "test_images_used_for_selection": False,
        },
    )


if __name__ == "__main__":
    run()
