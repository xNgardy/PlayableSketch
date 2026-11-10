import copy
import json
import time
from collections import Counter
import numpy as np
import torch
import torch.nn.functional as F
from . import train_corridor_addon as base
from .dino_model import DinoDecoder, ROOT, LOCK, CHANNELS, ARCHITECTURE, sha
from .dino_experiment import masked_loss
from .synthetic import write_json

OUT = base.OUT / "markers"
ACTIVE = [3, 5, 6]
FIXED = [0, 1, 2, 4, 7]


def configure(model):
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    model.head.weight.requires_grad_(True)
    model.head.bias.requires_grad_(True)
    w = torch.zeros_like(model.head.weight)
    w[ACTIVE] = 1
    b = torch.zeros_like(model.head.bias)
    b[ACTIVE] = 1
    model.head.weight.register_hook(lambda grad: grad * w)
    model.head.bias.register_hook(lambda grad: grad * b)


def main():
    torch.set_num_threads(4)
    previous = json.loads((base.OUT / "training_report.json").read_text())
    p = copy.deepcopy(base.freeze())
    p.update(
        epochs=5,
        checkpoints=[1, 3, 5],
        learning_rate=0.0003,
        teacher_weight=0.4,
        strategy="Only tick,open_interface,door_endpoint rows of final head trainable; all geometry weights frozen.",
        validation_adaptation="Second recipe after full-decoder validation regressions. No test inspection or test-driven selection.",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "protocol.json", p)
    torch.manual_seed(p["seed"])
    rng = np.random.default_rng(p["seed"])
    cache = base.OUT / "cache"
    manifest = json.loads((cache / "manifest.json").read_text())
    arrays = {
        n: np.load(cache / (n + ".npy"), mmap_mode="r")
        for n in ["features", "ink", "target", "known"]
    }
    source = ROOT / p["base_checkpoint"]["checkpoint_path"]
    state = torch.load(source, map_location="cpu", weights_only=True)
    model = DinoDecoder(state["width"])
    model.load_state_dict(state["state_dict"])
    configure(model)
    teacher = DinoDecoder(state["width"])
    teacher.load_state_dict(state["state_dict"])
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    optimizer = torch.optim.AdamW(
        [model.head.weight, model.head.bias], lr=p["learning_rate"], weight_decay=0.0
    )
    baseline = base.validate(source, base.OUT / "validation/epoch_0", p)
    candidates = [previous["selected"]]
    history = []
    started = time.perf_counter()
    for epoch in range(1, p["epochs"] + 1):
        model.train()
        order = base.grouped_sample(manifest["records"], rng, p["samples_per_epoch"])
        losses = []
        for start in range(0, len(order), p["batch_size"]):
            indices = order[start : start + p["batch_size"]]
            feature, ink, target, known = [
                torch.from_numpy(np.asarray(arrays[n][indices], dtype=np.float32))
                for n in ["features", "ink", "target", "known"]
            ]
            logits = model(feature, ink)
            loss = masked_loss(
                logits[:, ACTIVE],
                target[:, ACTIVE],
                known[:, ACTIVE],
                [p["loss_positive_weights"][i] for i in ACTIVE],
            )
            old = [
                i for i, j in enumerate(indices) if manifest["records"][j]["pool"] == "historical"
            ]
            if old:
                with torch.no_grad():
                    prior = teacher(feature[old], ink[old])[:, ACTIVE].sigmoid()
                loss = loss + p["teacher_weight"] * F.binary_cross_entropy_with_logits(
                    logits[old][:, ACTIVE], prior
                )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
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
            for key, value in model.state_dict().items():
                original = state["state_dict"][key]
                assert (
                    torch.equal(value[FIXED], original[FIXED])
                    if key.startswith("head.")
                    else torch.equal(value, original)
                ), key
            checkpoint = OUT / f"epoch_{epoch}.pt"
            torch.save(
                {
                    "architecture": ARCHITECTURE,
                    "channels": CHANNELS,
                    "width": state["width"],
                    "state_dict": {
                        k: v.detach().cpu().clone() for k, v in model.state_dict().items()
                    },
                    "backbone_lock_sha256": sha(LOCK),
                    "protocol_sha256": sha(OUT / "protocol.json"),
                    "epoch": epoch,
                    "continued_from_sha256": sha(source),
                    "trainable_head_rows": ACTIVE,
                },
                checkpoint,
            )
            result = base.validate(checkpoint, OUT / f"validation/epoch_{epoch}", p)
            passed, guards = base.eligible(result, baseline)
            candidate = {
                "recipe": "marker_rows_only",
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
        "geometry_weights_bit_identical": True,
        "model_promoted": False,
        "training_seconds": time.perf_counter() - started,
        "previous_training_report_sha256": sha(base.OUT / "training_report.json"),
    }
    write_json(OUT / "training_report.json", report)
    write_json(
        base.OUT / "final_selection.json",
        {
            "selected": selected,
            "selection_used_test": False,
            "recipes": [
                str((base.OUT / "training_report.json").relative_to(ROOT)),
                str((OUT / "training_report.json").relative_to(ROOT)),
            ],
            "decision": "Validation-only, fixed regression guards and epoch0 fallback. Test evaluation follows once, no further selection.",
        },
    )
    print(json.dumps({"final_selected": selected}), flush=True)


if __name__ == "__main__":
    main()
