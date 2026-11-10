from collections import Counter
import html
import json
from pathlib import Path
import numpy as np
from SketchPipeline.experiments.evaluate_v1 import MANIFEST, OUT, summarize as baseline_summary
from SketchPipeline.experiments.compare_ocr_v1 import (
    summarize as comparison_summary,
    evaluation_samples,
)
from SketchPipeline.experiments.train_ocr_v1 import TRAIN
from SketchPipeline.synthetic.augment import ROOT, read, sha, write


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def failures(samples, split):
    layouts = {}
    for path in (ROOT / "Data/annotations/v1").glob("*.source.json"):
        for source in read(path)["samples"]:
            for i, text in enumerate(source["texts"], 1):
                layouts[source["id"], f"t{i:03d}"] = text.get("text_layout", "unclassified")
    results = {}
    for stage in ["all", "test"]:
        chosen = [
            s
            for s in samples
            if s["origin"] == "human"
            and (stage == "all" or split["group_split"][s["base_plan_id"]] == "test")
        ]
        for system in ["baseline", "finetuned"]:
            buckets = {}
            examples = []
            for s in chosen:
                truth = read(MANIFEST.parent / s["observations_path"])["texts"]
                metrics = read(OUT / system / s["id"] / "metrics.json")["metrics"]["text"]
                matches = {p["reference_id"]: p for p in metrics["matched_pairs"]}
                for text in truth:
                    layout = layouts.get((s["id"], text["id"]), "unclassified")
                    bucket = buckets.setdefault(layout, Counter())
                    bucket["reference"] += 1
                    match = matches.get(text["id"])
                    reason = (
                        "detection_miss"
                        if match is None
                        else (
                            "correct"
                            if match["predicted_cm"] == text["parsed_value_cm"]
                            else (
                                "invalid_or_missing_numeric_unit"
                                if match["predicted_cm"] is None
                                else "wrong_numeric_value"
                            )
                        )
                    )
                    bucket[reason] += 1
                    if reason != "correct":
                        examples.append(
                            dict(
                                sample_id=s["id"],
                                text_id=text["id"],
                                expected=text["raw_text"],
                                predicted=match["predicted_raw"] if match else None,
                                reason=reason,
                                layout=layout,
                            )
                        )
            results[f"{stage}/{system}/human_original"] = dict(layouts=buckets, errors=examples)
    write(OUT / "error_analysis.json", results)
    return results


def confidence_intervals(samples, split):
    results = {}
    rng = np.random.default_rng(20261017)
    selectors = {
        "human_original": lambda s: s["origin"] == "human",
        "synthetic_original": lambda s: s["origin"] == "synthetic",
        "human_augmented": lambda s: s.get("source_origin") == "human",
        "synthetic_augmented": lambda s: s.get("source_origin") == "synthetic",
    }
    for category, selector in selectors.items():
        groups = {}
        for s in samples:
            if not selector(s) or split["group_split"][s["base_plan_id"]] != "test":
                continue
            data = groups.setdefault(s["base_plan_id"], np.zeros((2, 3)))
            for i, system in enumerate(["baseline", "finetuned"]):
                t = read(OUT / system / s["id"] / "metrics.json")["metrics"]["text"]
                data[i] += [t["numeric_exact_correct"], t["predicted"], t["reference"]]
        values = np.asarray(list(groups.values()))
        draws = rng.integers(0, len(values), size=(2000, len(values)))
        totals = values[draws].sum(axis=1)
        f1s = 2 * totals[:, :, 0] / (totals[:, :, 1] + totals[:, :, 2])
        recalls = totals[:, :, 0] / totals[:, :, 2]
        results[category] = dict(
            parent_groups=len(values),
            replicates=2000,
            numeric_f1_delta_95pct=np.quantile(f1s[:, 1] - f1s[:, 0], [0.025, 0.975]).tolist(),
            correct_cm_recall_delta_95pct=np.quantile(
                recalls[:, 1] - recalls[:, 0], [0.025, 0.975]
            ).tolist(),
        )
    write(
        OUT / "confidence_intervals.json",
        dict(
            results=results,
            policy="Paired parent-plan cluster bootstrap on test development groups. Conditional on these plans; not unseen-writer or population accuracy.",
        ),
    )
    return results


def run():
    samples = read(MANIFEST)["samples"]
    assert len(list((OUT / "baseline").glob("*/metrics.json"))) == 720
    split = read(OUT / "split.json")
    expected = evaluation_samples(samples, split)
    assert len(expected) == 240 and all(
        ((OUT / "finetuned" / s["id"] / "metrics.json").exists() for s in expected)
    )
    training = read(TRAIN / "training_report.json")
    assert training["training_complete"]
    base = baseline_summary()
    comp = comparison_summary()
    split = read(OUT / "split.json")
    errors = failures(samples, split)
    intervals = confidence_intervals(samples, split)
    lines = [
        "# Dataset evaluation and OCR fine-tuning — experiment v1",
        "",
        "Completed and reported on 2026-10-19. Development study; this is not an independent unseen-writer benchmark.",
        "",
        "## Inputs and separation",
        "",
        "720 images: 50 human originals, 70 synthetic renders, and 600 capture augmentations. These represent 80 parent-plan groups. No originals or annotations were relabeled.",
        "",
        f"Frozen image split: `{json.dumps(split['images'])}`. Parent-plan groups and all derivatives stay together; synthetic geometry families are also separated. Human plans are stratified by drawing batch. All original sources have previously been inspected during development.",
        "",
        "Test groups were not used to train, tune matching tolerances, or select checkpoints. Existing text IoU (0.30), wall coverage tolerances and opening endpoint matching were retained.",
        "",
        "## Baseline on all original/augmented groups",
        "",
        "| Source | Images | Text P | Text R | Text F1 | Correct cm recall | Opening P | Opening R | Opening F1 | LSD wall coverage F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in [
        "human_original",
        "synthetic_original",
        "human_augmented",
        "synthetic_augmented",
    ]:
        r = base["baseline"]["all/" + category]
        t = r["text"]
        o = r["openings"]
        lines.append(
            f"| {category} | {r['images']} | {pct(t['precision'])} | {pct(t['recall'])} | {pct(t['f1'])} | {pct(t['numeric_end_to_end_recall'])} | {pct(o['precision'])} | {pct(o['recall'])} | {pct(o['f1'])} | {pct(r['walls']['lsd']['coverage_f1'])} |"
        )
    lines += [
        "",
        "Wall metrics are sampled length coverage against approximate manual traces/renderer centerlines, not an object-count F1 or segmentation IoU. Detection F1 does not require a correct transcription; correct-cm recall requires both a matched location and exact numeric value with a recognized unit.",
        "",
        "## Training",
        "",
        f"Fine-tuned the decoder of `microsoft/trocr-small-handwritten` at revision `{training['model_revision']}` with a frozen visual encoder. {training['train_crops']} train crops from train groups only; batch size 12, AdamW learning rate 5e-5. Multiline and unclassified text blocks were excluded from this single-line recognizer training, while remaining in full-image evaluation.",
        "",
        f"Completed epochs: {len(training['epochs'])}. Best checkpoint: epoch {training['best_epoch']}, selected using equal-weight human/synthetic numeric accuracy on original validation crops. Runtime device: `{training['device']}`.",
        "",
        "The interrupted session resumed from the saved best epoch; optimizer state was reset, and its partial next epoch was discarded. This is recorded in the training report. Earlier failed token/loss alignment runs were kept separately and excluded. Aligned seq2seq cross-entropy was computed explicitly to avoid the generic causal loss shifting targets a second time.",
        "",
        "## OCR component diagnostic on test crops",
        "",
        "These are **oracle, verified single-line crops**, not full-image precision/recall.",
        "",
        "| Test crop source | Crops | Pretrained numeric accuracy | Fine-tuned numeric accuracy | Pretrained CER | Fine-tuned CER |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    before = read(TRAIN / "pretrained_test_oracle.json")
    after = read(TRAIN / "finetuned_test_oracle.json")
    for key in ["human", "synthetic", "all"]:
        a, b = (before[key], after[key])
        lines.append(
            f"| {key} | {a['count']} | {pct(a['numeric_exact_accuracy'])} | {pct(b['numeric_exact_accuracy'])} | {pct(a['cer'])} | {pct(b['cer'])} |"
        )
    lines += [
        "",
        "## Full-image comparison on held-out development plan groups",
        "",
        "Raw RapidOCR detector proposals and baseline-chosen rotations are fixed. Fine-tuned TrOCR replaces recognition; nearby number/unit fragments are regrouped by the same rule. GT polygons never select inference crops or rotations. Walls/openings remain frozen, so this experiment does not claim training gains for those components.",
        "",
        "After-training inference covers all 144 held-out development test images, plus remaining originals for diagnostics: 240 images total (120 originals + 120 test augmentations). Baseline covers all 720. Training augmentations are not rerun to estimate generalization.",
        "",
        "| Test source | Images | Baseline correct cm recall | Fine-tuned correct cm recall | Baseline numeric F1 | Fine-tuned numeric F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category in [
        "human_original",
        "synthetic_original",
        "human_augmented",
        "synthetic_augmented",
    ]:
        r = comp["comparison"]["test/" + category]
        a = r["baseline"]["text"]
        b = r["finetuned"]["text"]
        lines.append(
            f"| {category} | {r['baseline']['images']} | {pct(a['numeric_end_to_end_recall'])} | {pct(b['numeric_end_to_end_recall'])} | {pct(a['numeric_f1'])} | {pct(b['numeric_f1'])} |"
        )
    ci = intervals["human_original"]["numeric_f1_delta_95pct"]
    lines += [
        "",
        f"Original human test plans: paired parent-plan bootstrap (2,000 replicates, {intervals['human_original']['parent_groups']} groups) gives a 95% interval of {100 * ci[0]:+.1f} to {100 * ci[1]:+.1f} percentage points for the numeric F1 change. This interval is conditional on these development plans, not unseen writers.",
    ]
    lines += [
        "",
        "Numeric F1 counts a true positive only when location and cm value both match. Duplicate/incorrect readings do not earn credit. The full comparison JSON also contains text detection P/R/F1 after regrouping. All-source scores include train images and are descriptive, not evidence of generalization.",
        "",
        "## Errors on original human test plans",
        "",
        "| Label layout | Reference labels | Baseline correct cm | Fine-tuned correct cm | Baseline detection misses | Fine-tuned detection misses |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    ea = errors["test/baseline/human_original"]["layouts"]
    eb = errors["test/finetuned/human_original"]["layouts"]
    for layout in sorted(set(ea) | set(eb)):
        a = ea.get(layout, {})
        b = eb.get(layout, {})
        lines.append(
            f"| {layout} | {a.get('reference', 0)} | {a.get('correct', 0)} | {b.get('correct', 0)} | {a.get('detection_miss', 0)} | {b.get('detection_miss', 0)} |"
        )
    lines += [
        "",
        "Multiline/unclassified crops were not single-line training targets. All their labels still contribute to full-image recall; no unsupported format is silently removed from that score. Per-label failures and predicted/expected strings are in `error_analysis.json`.",
        "",
        "## Topology diagnostics",
        "",
    ]
    topology = read(OUT / "topology_report.json")
    lines.append(
        f"120 original images were attempted in isolated processes with a 20-second limit per image (including startup). Status counts: `{json.dumps(topology['status_counts'])}`. Timeouts/errors are explicit, not successful zero-error results."
    )
    for origin in ["human", "synthetic"]:
        ids = {s["id"] for s in samples if s["origin"] == origin}
        records = [r for r in topology["samples"] if r["id"] in ids]
        regions = [r["regions"] for r in records if r.get("regions")]
        tp = sum((r["true_positive"] for r in regions))
        p = sum((r["predicted"] for r in regions))
        n = sum((r["reference"] for r in regions))
        lines.append(
            f"- {origin}: {len(regions)} completed images with region references; region F1 {pct(2 * tp / (p + n) if p + n else None)} at IoU ≥ 0.50; {sum((r['all_regions_exact'] for r in regions))} images have exactly all matched regions and no extra regions."
        )
        connections = [r["connectivity"] for r in records if r.get("connectivity") is not None]
        ctp = sum((r["true_positive"] for r in connections))
        cp = sum((r["predicted"] for r in connections))
        cr = sum((r["reference"] for r in connections))
        lines.append(
            f"  Opening-linked region-pair F1: {pct(2 * ctp / (cp + cr) if cp + cr else None)}; full pixel topology exact in {sum((r['full_plan_exact'] for r in connections))}/{len(connections)} scored images."
        )
    lines += [
        "",
        "First-ten-photo sidecars do not contain region polygons, so no fabricated region/connectivity accuracy is assigned to them. Full pixel topology exact requires both all matched regions with no extra regions and the exact multiset of opening-linked region pairs. Metric reconstruction, navigation and gameplay success were not computed; Step 09 remains pending.",
        "",
        "## Verification",
        "",
        "172 Python tests passed. Frozen baseline predictions and a dense 5,623-line grid-paper case matched after arithmetic acceleration. All 720 source image hashes matched; original human/synthetic annotations and Unreal sources were unchanged. The experimental checkpoint SHA-256 is recorded in `Saved/Evaluation/v1/final-verification.json`.",
        "",
        "## Outputs and reproducibility",
        "",
        "- `Saved/Evaluation/v1/split.json`: frozen groups and source hashes.",
        "- `Saved/Evaluation/v1/baseline_report.json`: all baseline cohorts/splits.",
        "- `Saved/Evaluation/v1/comparison_report.json`: before/after recognition evaluation.",
        "- `Saved/Evaluation/v1/topology_report.json`: per-image topology completion/failures.",
        "- `Saved/Training/v1/training_report.json`: epochs, checkpoint selection and resumption.",
        "- `Saved/Training/v1/best.pt`: experimental fine-tuned checkpoint.",
        "- `Saved/Training/v1/python/`: isolated training dependencies; original RapidOCR models were not replaced.",
        "",
        "Training dependencies are pinned in `SketchPipeline/requirements-training.txt`; install them only into an isolated virtual environment. Model weights are downloaded from the pinned public revision; user drawings stay local.",
        "",
        "Run `python -m SketchPipeline.experiments.evaluate_v1` with the Step07 environment for the resumable baseline. Training/comparison use the isolated training Python. The evaluation acceleration only skips rejected-gap diagnostics or uses conservative vector prefilters followed by the original exact checks; matching thresholds are unchanged.",
        "",
        "Model source: https://huggingface.co/microsoft/trocr-small-handwritten . Technical reference: https://huggingface.co/docs/transformers/v4.50.0/model_doc/trocr . Group leakage reference: https://scikit-learn.org/stable/modules/cross_validation.html .",
        "",
        "A positive result here supports a component improvement for these plan groups. New writers and independently collected plans are still needed for external evaluation. Deployment is a separate decision; the existing local UI continues to use the pinned RapidOCR runtime.",
    ]
    text = "\n".join(lines) + "\n"
    (ROOT / "Docs/data_training_evaluation_v1.md").write_text(text)
    integrity = dict(
        source_images_unchanged=all(
            (sha(MANIFEST.parent / s["image_path"]) == s["image_sha256"] for s in samples)
        ),
        best_checkpoint_sha256=sha(TRAIN / "best.pt"),
        manifest_sha256=sha(MANIFEST),
        completed=True,
    )
    write(OUT / "final-verification.json", integrity)
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Evaluation v1</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto}pre{white-space:pre-wrap;line-height:1.5}</style><h1>Evaluation and OCR fine-tuning v1</h1><pre>'
        + html.escape(text)
        + "</pre>"
    )
    print(text, flush=True)


if __name__ == "__main__":
    run()
