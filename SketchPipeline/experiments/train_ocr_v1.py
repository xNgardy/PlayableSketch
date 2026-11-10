import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import re
import time
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.experiments.evaluate_v1 import MANIFEST, OUT, freeze
from SketchPipeline.perception.ocr import rectify_crop
from SketchPipeline.synthetic.augment import ROOT, read, write

TRAIN = ROOT / "Saved/Training/v1"


def prepare_crops():
    path = TRAIN / "crops.json"
    if path.exists():
        return read(path)["samples"]
    split = freeze()
    layouts = {}
    for p in (ROOT / "Data/annotations/v1").glob("*.source.json"):
        for s in read(p)["samples"]:
            for i, t in enumerate(s["texts"], 1):
                layouts[s["id"], f"t{i:03d}"] = t.get("text_layout", "unclassified")
    records = []
    for s in read(MANIFEST)["samples"]:
        original_id = s.get("source_id", s["id"])
        origin = s.get("source_origin", s["origin"])
        obs = read(MANIFEST.parent / s["observations_path"])
        with Image.open(MANIFEST.parent / s["image_path"]) as im:
            rgb = np.asarray(im.convert("RGB"))
        for t in obs["texts"]:
            layout = (
                "single_line"
                if origin == "synthetic"
                else layouts.get((original_id, t["id"]), "unclassified")
            )
            if layout != "single_line":
                continue
            crop, H = rectify_crop(rgb, t["polygon_px"])
            dest = TRAIN / "crops" / f"{s['id']}_{t['id']}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(crop).save(dest)
            records.append(
                dict(
                    id=dest.stem,
                    path=str(dest),
                    image_id=s["id"],
                    origin=origin,
                    augmented=s["origin"] == "augmented",
                    base_plan_id=s["base_plan_id"],
                    split=split["group_split"][s["base_plan_id"]],
                    text=t["raw_text"],
                    value_cm=t["parsed_value_cm"],
                    original_to_crop=H.tolist(),
                )
            )
    report = dict(
        samples=records,
        counts=dict(Counter((r["split"] for r in records))),
        note="Only explicitly classified single-line labels. Multiline and unclassified labels excluded, not relabeled.",
    )
    write(path, report)
    print("CROPS", report["counts"], flush=True)
    return records


def model_tools():
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    torch.set_num_threads(2)
    torch.manual_seed(20261017)
    path = (TRAIN / "model-path.txt").read_text().strip()
    processor = TrOCRProcessor.from_pretrained(path)
    model = VisionEncoderDecoderModel.from_pretrained(path)
    model.config.decoder_start_token_id = model.generation_config.decoder_start_token_id
    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.config.eos_token_id = processor.tokenizer.sep_token_id
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    return (torch, processor, model.to(device), device)


def numeric(text):
    match = re.fullmatch("\\s*(\\d+(?:[.,]\\d+)?)\\s*cm\\s*[.]?\\s*", text.lower())
    return float(match.group(1).replace(",", ".")) if match else None


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def recognize(images, torch, processor, model, device):
    pixels = processor(images=images, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        generated = model.generate(pixels, max_new_tokens=12, num_beams=1, do_sample=False)
    return processor.batch_decode(generated, skip_special_tokens=True)


def evaluate_crops(records, torch, processor, model, device):
    model.eval()
    predictions = []
    for offset in range(0, len(records), 16):
        batch = records[offset : offset + 16]
        images = []
        for r in batch:
            with Image.open(r["path"]) as im:
                images.append(im.convert("RGB"))
        texts = recognize(images, torch, processor, model, device)
        predictions.extend(
            (
                dict(
                    id=r["id"],
                    origin=r["origin"],
                    expected=r["text"],
                    expected_cm=r["value_cm"],
                    predicted=t,
                    predicted_cm=numeric(t),
                )
                for r, t in zip(batch, texts)
            )
        )

    def score(items):
        n = len(items)
        return dict(
            count=n,
            numeric_exact_correct=sum((r["predicted_cm"] == r["expected_cm"] for r in items)),
            numeric_exact_accuracy=(
                sum((r["predicted_cm"] == r["expected_cm"] for r in items)) / n if n else None
            ),
            text_exact_accuracy=(
                sum(
                    (r["predicted"].strip().lower() == r["expected"].strip().lower() for r in items)
                )
                / n
                if n
                else None
            ),
            cer=(
                sum((edit_distance(r["predicted"].lower(), r["expected"].lower()) for r in items))
                / sum((len(r["expected"]) for r in items))
                if n
                else None
            ),
        )

    return dict(
        all=score(predictions),
        human=score([r for r in predictions if r["origin"] == "human"]),
        synthetic=score([r for r in predictions if r["origin"] == "synthetic"]),
        predictions=predictions,
    )


def run():
    records = prepare_crops()
    torch, processor, model, device = model_tools()
    train = [r for r in records if r["split"] == "train"]
    validation = [r for r in records if r["split"] == "validation" and (not r["augmented"])]
    test = [r for r in records if r["split"] == "test" and (not r["augmented"])]
    for p in model.encoder.parameters():
        p.requires_grad = False
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=5e-05, weight_decay=0.01
    )
    report = dict(
        model="microsoft/trocr-small-handwritten",
        model_revision=read(TRAIN / "hub-model.json")["sha"],
        torch_version=torch.__version__,
        device=device,
        train_crops=len(train),
        validation_original_crops=len(validation),
        test_original_crops=len(test),
        batch_size=12,
        max_epochs=4,
        learning_rate=5e-05,
        seed=20261017,
        frozen_encoder=True,
        selection="equal-weight human/synthetic numeric exact accuracy on validation originals only",
        scope="Oracle single-line crops for component diagnostics; not full-image detection F1. Runtime RapidOCR remains pinned and unchanged.",
        epochs=[],
    )
    best = -1
    best_epoch = None
    stale = 0
    randomizer = random.Random(20261017)
    first_epoch = 1
    if (TRAIN / "training_report.json").exists() and (TRAIN / "best.pt").exists():
        prior = read(TRAIN / "training_report.json")
        if prior.get("training_complete"):
            print("Already complete; retained existing experiment.", flush=True)
            return
        report = prior
        model.load_state_dict(torch.load(TRAIN / "best.pt", map_location="cpu", weights_only=True))
        model.to(device)
        best = prior["best_validation_score"]
        best_epoch = prior["best_epoch"]
        first_epoch = best_epoch + 1
        report.setdefault("resumptions", []).append(
            dict(
                from_best_epoch=best_epoch,
                optimizer="reset; interrupted run did not save optimizer",
                partial_epoch_discarded=True,
            )
        )
        for _ in range(first_epoch - 1):
            discarded = list(train)
            randomizer.shuffle(discarded)
        before = read(TRAIN / "pretrained_validation.json")
    else:
        before = evaluate_crops(validation, torch, processor, model, device)
        write(TRAIN / "pretrained_validation.json", before)
    print(
        "DEVICE",
        device,
        "TRAIN",
        len(train),
        "VAL",
        len(validation),
        "pretrained",
        before["all"],
        flush=True,
    )
    for epoch in range(first_epoch, 5):
        order = list(train)
        randomizer.shuffle(order)
        model.train()
        model.encoder.eval()
        losses = []
        start = time.monotonic()
        for offset in range(0, len(order), 12):
            batch = order[offset : offset + 12]
            images = []
            for r in batch:
                with Image.open(r["path"]) as im:
                    images.append(im.convert("RGB"))
            pixels = processor(images=images, return_tensors="pt").pixel_values.to(device)
            labels = processor.tokenizer(
                [r["text"] for r in batch],
                padding=True,
                truncation=True,
                max_length=16,
                return_tensors="pt",
            ).input_ids.to(device)
            labels[labels == processor.tokenizer.pad_token_id] = -100
            optimizer.zero_grad(set_to_none=True)
            decoder_ids = model.prepare_decoder_input_ids_from_labels(labels)
            logits = model(
                pixel_values=pixels, decoder_input_ids=decoder_ids, use_cache=False
            ).logits
            loss = torch.nn.functional.cross_entropy(
                logits.reshape(-1, logits.shape[-1]), labels.reshape(-1), ignore_index=-100
            )
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
            if offset // 12 % 25 == 0:
                print(
                    f"EPOCH {epoch} STEP {offset // 12}/{(len(order) + 11) // 12} loss {losses[-1]:.4f} elapsed {time.monotonic() - start:.1f}s",
                    flush=True,
                )
        validation_result = evaluate_crops(validation, torch, processor, model, device)
        scores = [
            validation_result[k]["numeric_exact_accuracy"]
            for k in ["human", "synthetic"]
            if validation_result[k]["count"]
        ]
        selection = sum(scores) / len(scores)
        item = dict(
            epoch=epoch,
            loss=float(np.mean(losses)),
            seconds=time.monotonic() - start,
            validation={k: validation_result[k] for k in ["all", "human", "synthetic"]},
            selection_score=selection,
        )
        report["epochs"].append(item)
        write(TRAIN / f"validation_epoch_{epoch}.json", validation_result)
        if selection > best:
            best = selection
            best_epoch = epoch
            stale = 0
            torch.save(model.state_dict(), TRAIN / "best.pt")
            processor.save_pretrained(TRAIN / "processor")
            model.config.save_pretrained(TRAIN / "processor")
        else:
            stale += 1
        report.update(best_epoch=best_epoch, best_validation_score=best)
        write(TRAIN / "training_report.json", report)
        print("EPOCH_DONE", json.dumps(item), flush=True)
        if stale >= 2:
            break
    model.load_state_dict(torch.load(TRAIN / "best.pt", map_location="cpu", weights_only=True))
    model.to(device)
    write(
        TRAIN / "finetuned_test_oracle.json", evaluate_crops(test, torch, processor, model, device)
    )
    del model
    torch.mps.empty_cache() if device == "mps" else None
    torch, processor, model, device = model_tools()
    write(
        TRAIN / "pretrained_test_oracle.json", evaluate_crops(test, torch, processor, model, device)
    )
    report["training_complete"] = True
    report["test_evaluated_after_selection"] = True
    write(TRAIN / "training_report.json", report)
    print("COMPLETE", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    a = p.parse_args()
    prepare_crops() if a.prepare else run()
