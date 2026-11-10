# Dataset evaluation and OCR fine-tuning — experiment v1

Completed and reported on 2026-10-19. Development study; this is not an independent unseen-writer benchmark.

## Inputs and separation

720 images: 50 human originals, 70 synthetic renders, and 600 capture augmentations. These represent 80 parent-plan groups. No originals or annotations were relabeled.

Frozen image split: `{"test": 144, "train": 462, "validation": 114}`. Parent-plan groups and all derivatives stay together; synthetic geometry families are also separated. Human plans are stratified by drawing batch. All original sources have previously been inspected during development.

Test groups were not used to train, tune matching tolerances, or select checkpoints. Existing text IoU (0.30), wall coverage tolerances and opening endpoint matching were retained.

## Baseline on all original/augmented groups

| Source | Images | Text P | Text R | Text F1 | Correct cm recall | Opening P | Opening R | Opening F1 | LSD wall coverage F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| human_original | 50 | 75.3% | 99.4% | 85.7% | 45.3% | 18.4% | 79.8% | 29.9% | 81.2% |
| synthetic_original | 70 | 95.2% | 89.8% | 92.4% | 76.8% | 25.0% | 81.6% | 38.2% | 70.8% |
| human_augmented | 250 | 75.0% | 98.8% | 85.2% | 46.2% | 18.8% | 81.5% | 30.6% | 76.9% |
| synthetic_augmented | 350 | 96.5% | 90.0% | 93.1% | 79.1% | 23.0% | 78.9% | 35.6% | 65.7% |

Wall metrics are sampled length coverage against approximate manual traces/renderer centerlines, not an object-count F1 or segmentation IoU. Detection F1 does not require a correct transcription; correct-cm recall requires both a matched location and exact numeric value with a recognized unit.

## Training

Fine-tuned the decoder of `microsoft/trocr-small-handwritten` at revision `b4648cfa171985a6745f37ddd637e98c0da958ac` with a frozen visual encoder. 6096 train crops from train groups only; batch size 12, AdamW learning rate 5e-5. Multiline and unclassified text blocks were excluded from this single-line recognizer training, while remaining in full-image evaluation.

Completed epochs: 4. Best checkpoint: epoch 2, selected using equal-weight human/synthetic numeric accuracy on original validation crops. Runtime device: `mps`.

The interrupted session resumed from the saved best epoch; optimizer state was reset, and its partial next epoch was discarded. This is recorded in the training report. Earlier failed token/loss alignment runs were kept separately and excluded. Aligned seq2seq cross-entropy was computed explicitly to avoid the generic causal loss shifting targets a second time.

## OCR component diagnostic on test crops

These are **oracle, verified single-line crops**, not full-image precision/recall.

| Test crop source | Crops | Pretrained numeric accuracy | Fine-tuned numeric accuracy | Pretrained CER | Fine-tuned CER |
| --- | ---: | ---: | ---: | ---: | ---: |
| human | 54 | 59.3% | 79.6% | 25.4% | 3.4% |
| synthetic | 358 | 96.4% | 99.7% | 9.7% | 0.0% |
| all | 412 | 91.5% | 97.1% | 11.7% | 0.5% |

## Full-image comparison on held-out development plan groups

Raw RapidOCR detector proposals and baseline-chosen rotations are fixed. Fine-tuned TrOCR replaces recognition; nearby number/unit fragments are regrouped by the same rule. GT polygons never select inference crops or rotations. Walls/openings remain frozen, so this experiment does not claim training gains for those components.

After-training inference covers all 144 held-out development test images, plus remaining originals for diagnostics: 240 images total (120 originals + 120 test augmentations). Baseline covers all 720. Training augmentations are not rerun to estimate generalization.

| Test source | Images | Baseline correct cm recall | Fine-tuned correct cm recall | Baseline numeric F1 | Fine-tuned numeric F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| human_original | 10 | 49.4% | 69.7% | 42.5% | 59.0% |
| synthetic_original | 14 | 71.5% | 85.2% | 72.0% | 85.6% |
| human_augmented | 50 | 51.0% | 72.1% | 44.2% | 61.5% |
| synthetic_augmented | 70 | 76.0% | 85.9% | 77.1% | 86.9% |

Original human test plans: paired parent-plan bootstrap (2,000 replicates, 10 groups) gives a 95% interval of +2.0 to +26.1 percentage points for the numeric F1 change. This interval is conditional on these development plans, not unseen writers.

Numeric F1 counts a true positive only when location and cm value both match. Duplicate/incorrect readings do not earn credit. The full comparison JSON also contains text detection P/R/F1 after regrouping. All-source scores include train images and are descriptive, not evidence of generalization.

## Errors on original human test plans

| Label layout | Reference labels | Baseline correct cm | Fine-tuned correct cm | Baseline detection misses | Fine-tuned detection misses |
| --- | ---: | ---: | ---: | ---: | ---: |
| multiline | 27 | 3 | 19 | 0 | 0 |
| single_line | 54 | 36 | 38 | 1 | 1 |
| unclassified | 8 | 5 | 5 | 0 | 0 |

Multiline/unclassified crops were not single-line training targets. All their labels still contribute to full-image recall; no unsupported format is silently removed from that score. Per-label failures and predicted/expected strings are in `error_analysis.json`.

## Topology diagnostics

120 original images were attempted in isolated processes with a 20-second limit per image (including startup). Status counts: `{"complete": 120}`. Timeouts/errors are explicit, not successful zero-error results.
- human: 40 completed images with region references; region F1 14.5% at IoU ≥ 0.50; 7 images have exactly all matched regions and no extra regions.
  Opening-linked region-pair F1: 25.2%; full pixel topology exact in 7/40 scored images.
- synthetic: 70 completed images with region references; region F1 23.5% at IoU ≥ 0.50; 0 images have exactly all matched regions and no extra regions.
  Opening-linked region-pair F1: 0.0%; full pixel topology exact in 0/70 scored images.

First-ten-photo sidecars do not contain region polygons, so no fabricated region/connectivity accuracy is assigned to them. Full pixel topology exact requires both all matched regions with no extra regions and the exact multiset of opening-linked region pairs. Metric reconstruction, navigation and gameplay success were not computed; Step 09 remains pending.

## Verification

172 Python tests passed. Frozen baseline predictions and a dense 5,623-line grid-paper case matched after arithmetic acceleration. All 720 source image hashes matched; original human/synthetic annotations and Unreal sources were unchanged. The experimental checkpoint SHA-256 is recorded in `Saved/Evaluation/v1/final-verification.json`.

## Outputs and reproducibility

- `Saved/Evaluation/v1/split.json`: frozen groups and source hashes.
- `Saved/Evaluation/v1/baseline_report.json`: all baseline cohorts/splits.
- `Saved/Evaluation/v1/comparison_report.json`: before/after recognition evaluation.
- `Saved/Evaluation/v1/topology_report.json`: per-image topology completion/failures.
- `Saved/Training/v1/training_report.json`: epochs, checkpoint selection and resumption.
- `Saved/Training/v1/best.pt`: experimental fine-tuned checkpoint.
- `Saved/Training/v1/python/`: isolated training dependencies; original RapidOCR models were not replaced.

Training dependencies are pinned in `SketchPipeline/requirements-training.txt`; install them only into an isolated virtual environment. Model weights are downloaded from the pinned public revision; user drawings stay local.

Run `python -m SketchPipeline.experiments.evaluate_v1` with the Step07 environment for the resumable baseline. Training/comparison use the isolated training Python. The evaluation acceleration only skips rejected-gap diagnostics or uses conservative vector prefilters followed by the original exact checks; matching thresholds are unchanged.

Model source: https://huggingface.co/microsoft/trocr-small-handwritten . Technical reference: https://huggingface.co/docs/transformers/v4.50.0/model_doc/trocr . Group leakage reference: https://scikit-learn.org/stable/modules/cross_validation.html .

A positive result here supports a component improvement for these plan groups. New writers and independently collected plans are still needed for external evaluation. Deployment is a separate decision; the existing local UI continues to use the pinned RapidOCR runtime.
