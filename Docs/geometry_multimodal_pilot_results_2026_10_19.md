# Geometry separation and local VLM pilot — 2026-10-19

**Decision:** use conservative grid suppression as the leading opt-in candidate. Keep the baseline available. The simple annotation filter and this small local VLM need further validation before default deployment.

## Scope and method

19 frozen validation originals: five human drawings and 14 synthetic renders, representing 11 parent-plan groups. This is an adaptive, retrospective development study. Images from the same synthetic plan are not independent observations; no new writers or test-set generalization are claimed.

Every arm shares the saved RapidOCR hypotheses and working-image frame. Ground truth enters only after prediction is persisted. Existing opening endpoint tolerances and region IoU ≥ 0.50 are unchanged. Exact topology requires both all matched regions with no extras and the correct multiset of opening-linked region pairs. One human sample has no region reference, leaving 18 scorable images.

Arms: baseline replay; conservative periodic grid suppression; grid plus a deterministic contrast/width annotation rule; local VLM-only geometry; bounded hybrid using structural candidates and VLM keep/reject decisions. The annotation rule is not a trained semantic segmentation model.

The local model is quantized Qwen2.5-VL-3B-Instruct, pinned at `46d4cf06a06ffc1a766c214174f9cbed2f45bcab`, using MLX-VLM. No fine-tuning or external image submission took place.

An initial strict-format preflight and an array-constrained preflight failed through schema confusion, repetition, or truncation. Their responses are preserved separately. The final run constrains JSON syntax and uses boolean decisions for supplied candidate IDs, normalized deterministically to selected-ID lists. Native rectangle suggestions are disabled; every reported exact-topology score uses the same graph decoder. This format iteration used validation data and is explicitly not a fresh holdout.

The bounded hybrid can add up to four opening intervals but cannot add new walls; its wall recall is limited by the structural candidate set. This experiment does not rule out stronger VLMs, local crop classifiers, different fusion rules, or trained geometry models.

## Measured results

### all

| Arm | Opening P | Opening R | Opening F1 | Exact topology | Geometry/VLM p50 / p95 seconds | Failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 21.7% | 76.4% | 33.8% | 1/18 | 0.36 / 6.73 | 0 |
| grid | 38.0% | 75.0% | 50.5% | 2/18 | 0.40 / 0.47 | 0 |
| structural | 62.7% | 58.3% | 60.4% | 2/18 | 0.52 / 0.59 | 0 |
| vlm_only | undefined | 0.0% | 0.0% | 0/18 | 5.70 / 7.01 | 0 |
| hybrid | 62.7% | 58.3% | 60.4% | 2/18 | 13.17 / 14.00 | 0 |

### human

| Arm | Opening P | Opening R | Opening F1 | Exact topology | Geometry/VLM p50 / p95 seconds | Failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 18.5% | 85.7% | 30.4% | 1/4 | 0.26 / 3.35 | 0 |
| grid | 92.3% | 85.7% | 88.9% | 2/4 | 0.27 / 0.42 | 0 |
| structural | 92.3% | 85.7% | 88.9% | 2/4 | 0.40 / 0.44 | 0 |
| vlm_only | undefined | 0.0% | 0.0% | 0/4 | 4.64 / 4.91 | 0 |
| hybrid | 92.3% | 85.7% | 88.9% | 2/4 | 11.25 / 14.72 | 0 |

### synthetic

| Arm | Opening P | Opening R | Opening F1 | Exact topology | Geometry/VLM p50 / p95 seconds | Failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 22.9% | 74.1% | 35.0% | 0/14 | 0.41 / 6.74 | 0 |
| grid | 32.6% | 72.4% | 44.9% | 0/14 | 0.41 / 0.47 | 0 |
| structural | 55.6% | 51.7% | 53.6% | 0/14 | 0.54 / 0.59 | 0 |
| vlm_only | undefined | 0.0% | 0.0% | 0/14 | 5.83 / 8.06 | 0 |
| hybrid | 55.6% | 51.7% | 53.6% | 0/14 | 13.20 / 13.83 | 0 |

Timings exclude shared cached OCR, source-image preparation and initial model loading, and include the common topology stage. Hybrid timing adds the measured structural-stage cost. These are observed local wall-clock timings, not a controlled hardware performance benchmark. Model initialization and peak generation memory are separately recorded.

## Interpretation

- Grid suppression removes only faint pixels supported by repeated axis-aligned line families. High-contrast crossings and original RGB are retained. Rotated/perspective grids can cause abstention; faint wall pixels remain a known risk requiring broader capture tests.
- The major human precision improvement comes from Data_18: baseline 2 matched openings out of 54 predictions becomes 2 out of 2 after grid suppression. Other human validation cases retain their opening counts. Five human plans are too few to establish broad generalization.
- The annotation rule removes many nonstructural rail candidates but also loses genuine openings, especially in synthetic cases. A higher F1 alone does not justify accepting its recall loss.
- VLM quality must be judged by these localization and topology results, not by valid JSON. The guided grammar has no ground-truth coordinates. Unsupported new walls are rejected using pixel evidence; unresolved opening attachments remain visible to the common graph decoder.
- In all 19 hybrid responses the model retained every supplied candidate and added no geometry. A no-op guard preserves the complete structural recovery evidence. The final hybrid predictions are therefore equivalent to the structural arm; the VLM provided no semantic improvement. Original recorded model times were retained when replaying this postprocessing fix.
- Region and wall coverage metrics, endpoint errors on matched openings, unmatched-opening correction proxies and parent-plan bootstrap intervals are in `final_report.json`. Bootstrap intervals remain conditional on this small validation set.

## Actual correction time

Human correction time has not been measured and remains null. No duration was inferred from false-positive counts. `review_benchmark.html` records actual wall/opening additions, deletions, endpoint movement, wall-clock duration and visible-tab duration. It exports local JSON; the result is not accepted metric geometry or automatically trusted training GT.

For a useful timing study, allocate blinded variants to reviewers, counterbalance order and use separate practice examples. Seeing the same plan repeatedly introduces learning effects. Independently verify corrected geometry before comparing speed. The comparison gallery reveals arm identities and should be viewed after assigned blinded reviews.

Browser file navigation was blocked by the computer-use security policy. Static JavaScript syntax was checked; browser interaction was not verified. No alternate route was used to bypass that restriction.

## Integration and next decision

The production UI still defaults to the existing baseline. The Python API/CLI now accepts an explicit `geometry_profile` / `--geometry-profile` of `baseline`, `grid`, or `structural`; the new settings affect geometry only and receive distinct revision hashes. OCR uses untouched source RGB. VLM runs remain offline experiments.

Example opt-in run from the repository root:

```sh
Saved/Step07/python/bin/python -m SketchPipeline.perception.run --image Data/Data_18.png --geometry-profile grid --output Saved/GeometryStudy/v1/integrated-grid
```

Before a dedicated segmentation/keypoint training run, export versioned dimension-rail/grid supervision and review real same-ink annotation confusions. Existing synthetic masks omit separate rail/grid masks, while human traces are approximate rather than dense pixel GT. This pilot does not justify training against unverified background labels. No geometry training was started.

Reproduce classical arms with `python -m SketchPipeline.experiments.geometry_study` in the Step07 runtime; final VLM arms with `python -m SketchPipeline.experiments.geometry_vlm_guided` in the isolated geometry-study runtime; publish with `python -m SketchPipeline.experiments.geometry_report`. All existing source images, GT and Unreal code remain unchanged.

Artifacts: `Saved/GeometryStudy/v1/final_report.json`, `index.html`, `review_benchmark.html`, per-arm predictions/metrics, raw model prompts/responses, protocols, dependency freeze and verification.

The 720-image and 973-protected-file integrity checks passed before the final postprocessing replay. Subsequent raw-image reads returned an OS permission error; the final replay reused stored predictions and that explicitly dated integrity check. No source data was rewritten. Full fresh-source reproduction requires file access to be available.

Model sources: [original Qwen card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct), [quantized snapshot](https://huggingface.co/mlx-community/Qwen2.5-VL-3B-Instruct-4bit/tree/46d4cf06a06ffc1a766c214174f9cbed2f45bcab), [MLX-VLM](https://github.com/Blaizzy/mlx-vlm).

## Final verification

184 Python tests passed. The real-RapidOCR `--geometry-profile grid` CLI run on Data_18 reproduced the pilot opening matches. All 95 final prediction records were scored; no final arm had a failed image. See `Saved/GeometryStudy/v1/final-verification.json`.
