from copy import deepcopy
import json
import time
import numpy as np
from PIL import Image
from SketchPipeline.experiments.evaluate_v1 import MANIFEST, OUT, enrich, freeze
from SketchPipeline.experiments.train_ocr_v1 import TRAIN, model_tools, recognize
from SketchPipeline.perception.evaluate import aggregate, evaluate
from SketchPipeline.perception.numeric import parse_numeric
from SketchPipeline.perception.ocr import group_units, rectify_crop
from SketchPipeline.synthetic.augment import read, write


def evaluation_samples(samples, split):
    return [
        s
        for s in samples
        if s["origin"] != "augmented" or split["group_split"][s["base_plan_id"]] == "test"
    ]


def run():
    torch, processor, model, device = model_tools()
    model.load_state_dict(torch.load(TRAIN / "best.pt", map_location="cpu", weights_only=True))
    model.to(device)
    model.eval()
    split = freeze()
    samples = evaluation_samples(read(MANIFEST)["samples"], split)
    for index, sample in enumerate(samples, 1):
        dest = OUT / "finetuned" / sample["id"]
        done = dest / "metrics.json"
        if done.exists():
            continue
        baseline = OUT / "baseline" / sample["id"]
        if not (baseline / "metrics.json").exists():
            print("WAITING_BASELINE", sample["id"], flush=True)
            deadline = time.monotonic() + 600
            while not (baseline / "metrics.json").exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Baseline did not complete within 600s")
                time.sleep(5)
        working = read(baseline / "working.json")
        obs = read(baseline / "observations.json")
        fragments = deepcopy(working["fragments"])
        start = time.monotonic()
        crops = []
        with Image.open(MANIFEST.parent / sample["image_path"]) as im:
            rgb = np.asarray(im.convert("RGB"))
        for fragment in fragments:
            crop, _ = rectify_crop(rgb, fragment["polygon_original"])
            rotation = fragment["chosen"]["rotation_degrees"] // 90
            crops.append(Image.fromarray(np.ascontiguousarray(np.rot90(crop, rotation))))
        words = []
        for offset in range(0, len(crops), 16):
            words.extend(recognize(crops[offset : offset + 16], torch, processor, model, device))
        for fragment, word in zip(fragments, words):
            fragment["chosen"].update(raw_text=word, parsed=parse_numeric(word), score=0.0)
        groups = group_units(fragments)
        from SketchPipeline.preprocessing.prepare import project

        inverse = np.asarray(working["preprocessing"]["working_to_original"])
        width, height = working["preprocessing"]["original_size_px"]
        texts = []
        for i, g in enumerate(groups, 1):
            polygon = project(g["polygon_working"], inverse)
            polygon[:, 0] = np.clip(polygon[:, 0], 0, width - 1)
            polygon[:, 1] = np.clip(polygon[:, 1], 0, height - 1)
            texts.append(
                dict(
                    id=f"t{i:03d}",
                    raw_text=g["chosen"]["raw_text"] or "[unreadable]",
                    polygon_px=polygon.tolist(),
                    parsed_value_cm=g["chosen"]["parsed"]["value_cm"],
                    score=None,
                    method="ocr",
                )
            )
        obs["texts"] = texts
        obs["revision_id"] = "experimental-trocr-finetuned-1"
        obs["issues"] = [
            dict(
                code="SKETCH_PERCEPTION_REVIEW_REQUIRED",
                severity="warning",
                element_ids=[],
                message="Experimental recognition with frozen geometry; all evidence requires review.",
            )
        ]
        for text, group in zip(texts, groups):
            issue = group["chosen"]["parsed"].get("issue")
            if issue:
                obs["issues"].append(
                    dict(
                        code=issue,
                        severity="warning",
                        element_ids=[text["id"]],
                        message="Unreviewed OCR evidence: " + text["raw_text"],
                    )
                )
        obs["notes"].append(
            "Experimental fine-tuned recognition on fixed RapidOCR proposals and baseline orientations. Walls/openings frozen; no metric or gameplay export."
        )
        reference = read(MANIFEST.parent / sample["observations_path"])
        side = read(MANIFEST.parent / sample["annotations_path"])
        metrics = evaluate(obs, working, reference, side)
        from SketchPipeline.validation.validate import validate_document

        validation = validate_document(obs)
        if not validation["schema_valid"] or validation["issues"]:
            raise ValueError(validation)
        write(dest / "observations.json", obs)
        write(
            dest / "recognition.json",
            dict(
                source_id=sample["id"],
                fragments=[
                    dict(id=f["id"], predicted=t, rotation=f["chosen"]["rotation_degrees"])
                    for f, t in zip(fragments, words)
                ],
            ),
        )
        write(
            done,
            dict(
                id=sample["id"],
                metrics=metrics,
                duration_seconds=time.monotonic() - start,
                experiment_split=split["group_split"][sample["base_plan_id"]],
            ),
        )
        print(
            f"{index}/{len(samples)} {sample['id']}: {metrics['text']['numeric_exact_correct']}/{metrics['text']['reference']} numeric",
            flush=True,
        )
    summarize()


def summarize():
    samples = read(MANIFEST)["samples"]
    split = freeze()
    report = {}
    selectors = {
        "human_original": lambda s: s["origin"] == "human",
        "synthetic_original": lambda s: s["origin"] == "synthetic",
        "human_augmented": lambda s: s.get("source_origin") == "human",
        "synthetic_augmented": lambda s: s.get("source_origin") == "synthetic",
    }
    for stage in ["all", "validation", "test"]:
        for category, predicate in selectors.items():
            if stage != "test" and category.endswith("_augmented"):
                continue
            selected = [
                s
                for s in samples
                if predicate(s)
                and (stage == "all" or split["group_split"][s["base_plan_id"]] == stage)
            ]
            entry = {}
            for system in ["baseline", "finetuned"]:
                records = [read(OUT / system / s["id"] / "metrics.json") for s in selected]
                summary = enrich(aggregate(records))
                text = summary["text"]
                text["numeric_precision"] = (
                    text["numeric_exact_correct"] / text["predicted"] if text["predicted"] else None
                )
                text["numeric_f1"] = (
                    2 * text["numeric_exact_correct"] / (text["predicted"] + text["reference"])
                    if text["predicted"] + text["reference"]
                    else None
                )
                summary["images"] = len(records)
                entry[system] = summary
            report[f"{stage}/{category}"] = entry
    result = dict(
        comparison=report,
        scope="Fixed raw detection proposals and baseline orientation. Regrouping may change text boxes; walls/openings are frozen, not improved or retrained. Numeric F1 counts location match AND exact cm value.",
        training=read(TRAIN / "training_report.json"),
        complete=True,
        scope_images=240,
        held_out_test_images=144,
    )
    write(OUT / "comparison_report.json", result)
    return result


if __name__ == "__main__":
    from contextlib import redirect_stdout

    with (OUT / "comparison.log").open("a", buffering=1) as log, redirect_stdout(log):
        run()
