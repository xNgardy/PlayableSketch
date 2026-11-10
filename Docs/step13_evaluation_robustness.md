# Step 13 — Evaluation, robustness and release acceptance

Completed on 2026-10-21. This step implements repeatable development evaluation and explicit release decisions. It does not claim that automatic reconstruction is solved. No model weights or source annotations were modified. Step 14 was subsequently completed for the local Mac Development package; see [Step 14](step14_packaged_runtime.md). This historical evaluation and its release restrictions remain unchanged.

## Reproducible run and scope

Final artifacts are in `Saved/Step13/v3/`. The protocol pins 5,871 source/code/model-runtime/evidence files with SHA-256, including all 720 source images, annotations, prediction artifacts, the existing grouped split and Step 12 physical evidence. `artifact-integrity.json` independently seals generated reports, solver outputs, gallery images and robustness artifacts. Both inventories are checked by `--verify-only`.

The 720 samples comprise 50 human originals, 70 synthetic originals and 600 derivatives. The existing development split is reused; derivatives remain with their base plan and synthetic geometry families cannot cross splits. Writer IDs are incomplete, so this is **not an independent unseen-writer test**. Scores are retrospective development measurements.

Historical RapidOCR baseline predictions are replayed without rerunning the entire 720-image inference job. Current solver/evaluator code runs independently. Topology evidence covers 120 original sources; topology is not computed for all augmentation variants. Automatic metric geometry and automatic text-to-metric-span outputs are absent from this historical run and remain `not_computed/null`.

```bash
Saved/Step07/python/bin/python -m SketchPipeline.evaluation --output Saved/Step13/NEW_RUN --challenges
Saved/Step07/python/bin/python -m SketchPipeline.evaluation --output Saved/Step13/v3 --verify-only
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
node --check SketchPipeline/review/web/metric.js
```

Use a new directory if input/code hashes change. Re-running with unchanged frozen inputs recomputes scoring/solver diagnostics; output timestamps and timings can vary. Missing stages remain visible. Current artifacts are not training data or user approval.

## Baseline results

| Cohort | Images | Exact numeric / reference | Numeric recall | Opening P | Opening R | Opening F1 | Exact topology / scorable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| origin/human | 50 | 232/512 | 45.31% | 18.41% | 79.83% | 29.92% | 7/40 |
| origin/synthetic | 70 | 1093/1424 | 76.76% | 24.95% | 81.63% | 38.22% | 0/70 |
| origin/augmented | 600 | 6814/9680 | 70.39% | 21.68% | 79.60% | 34.07% | 0/0 |
| all | 720 | 8139/11616 | 70.07% | 21.87% | 79.86% | 34.33% | 7/110 |

For the 50 human originals, exact topology is 7/40 scorable (17.5%); the 10 images without suitable region/connectivity reference coverage remain explicitly not computed. The full-denominator measured success fraction is 7/50, not an accuracy claim for those missing labels.

Opening precision on human originals is 95/516; recall is 95/119. That is 421 unmatched opening predictions and 24 missed reference openings. This makes false openings a clear product priority. It does not prove that every false opening is caused by a dimension tick or grid stroke. The failure gallery marks unmatched predicted opening spans in orange and OCR boxes in red.

One-to-one graph wall and junction P/R, separate sampled wall-length coverage, digit error rate, latency P50/P95, per-sample failures and cohort/profile/split breakdowns are in `report.json`. DER includes matched digit edit distance, missed-reference deletions and extra-prediction insertions; punctuation/units are excluded. Human-original digit error rate is 378/1516 = 24.93%.

## Matching and denominator policy

- Text uses the existing spatial IoU 0.30 policy; region correspondence uses IoU 0.50. Graph wall matching uses maximum-cardinality one-to-one endpoint correspondence within max(8 px, 2% of the original long image side). Manual whole strokes and predicted graph edges have different fragmentation, which remains visible in object P/R.
- Graph nodes include opening endpoints; extra unmatched nodes count as false positives. No junction-type accuracy is claimed.
- Metric comparison matches regions and walls geometrically, then compares opening type/region relation/wall placement, width, center displacement, height, settings and Start/Goal. Different IDs and array order do not establish or break correspondence.
- Canonical metric alignment removes arbitrary translation only. Default yaw is fixed; scale and reflection are never fitted away. Metric exactness tolerance is 0.1 cm. Opening offset is evaluated as physical center displacement after wall correspondence, avoiding dependence on wall-local segmentation.
- Whole-plan exact topology requires correct region recovery and the complete multiset of opening-linked region pairs. Duplicate doors retain multiplicity.
- Missing/failed/unsupported cases stay in sample and state counts. Missing stage measurements remain null. Each aggregate includes computed-sample counts, all-reference counts and full-denominator recall separately; partial results cannot silently become a perfect score.
- `compare_reports` refuses different reference/data hashes, split or tolerance policy, and refuses dropping failed samples. Optional model adapters can use the same metrics without changing the canonical contract.

## Current solver and known-invalid checks

The current solver runs on all 50 manual topology/confirmed-dimension references after deliberately scrambling existing cm coordinates and opening values. This isolates constraint solving; it is **not perception accuracy or review-after-correction accuracy**.

- 24 determined cases: all 24 match the validated metric reference within 0.1 cm, with dimension residual and opening width/placement diagnostics recorded.
- 21 underdetermined cases: 7 known missing-dimension fixtures plus 14 reference-valid layouts whose alignment/entrance premises are not fully expressed by their confirmed dimension equations. Missing values remain unresolved; stored reference coordinates are never used as constraints.
- 5 inconsistent cases: confirmed conflicts remain visible.
- All 12 known invalid/missing references remain blocked from acceptance; zero invalid exports. Controlled `as_validated` checks return no written exports or user approvals.
- Data_8 uses the same two explicit reference premises as Step 09 (centered local entrance and full-span far entrance). Historical reversed unresolved wall directions in Data_9/10/19/20 are normalized in test copies from documented SW-first CCW rectangular loops. Original files remain unchanged.
- The prior Step 09 regression statuses match. Step 12 collision/Pawn/lifecycle evidence is linked and hash-checked separately; its success is not represented as image-to-Pawn success on all 720 images.

## Fresh robustness and convention probes

Eight current-baseline inference probes were run from Data_3 and Data_41: blur, shadow, crop and an extra diagonal interior boundary violating the orthogonal rectangular convention. All eight completed inference and stayed review-required; no canonical metric layout or acceptance was emitted. Blur/shadow retain their original label geometry and have scored OCR/opening diagnostics. Crop and convention probes have no transferred accuracy ground truth, so those scores are null.

The final v3 report explicitly reuses the eight hash-matched successful v2 probe predictions. V1 is retained as a failed runner attempt: it pre-created a directory owned by the prediction writer. That integration error was fixed and covered by a regression test before v2 inference. This provenance is not hidden or counted as perception accuracy.

The existing five derivative profiles (rotate, perspective, lighting, capture, combined) are reported separately for human and synthetic parents. These are controlled variations of known plans, not new handwriting writers or new phone photos. A mandatory-review result checks the safety contract; it does not prove that the particular crop/diagonal defect was semantically recognized.

## Correction cost instrumentation

New metric save/undo/redo/accept requests can include anonymous `browser-visible-interaction/v1` timing. The browser counts focused, visible work, stops after 60 seconds idle, and excludes server computation. The backend validates integer bounds and stores telemetry in the immutable revision ledger/hash only; canonical geometry/acceptance data is unchanged.

Reports count edit commands and affected entities separately from interaction events. Historical timestamps yield wall elapsed time only. If any revision lacks timing, total active review time stays null; observed partial time is labeled separately. Unsaved work, closed tabs and topology-review time are not captured. Client time is self-reported and not a calibrated productivity benchmark.

Browser verification used a copied controlled fixture at localhost:8772, saved a pending revision, and verified timing persisted outside canonical JSON. Its observed 10.99 seconds and two interactions are automation evidence, not human correction time. No real drawing was approved. Screenshot: `Saved/Step13/ui_timing.jpg`.

## Release decision and next intervention

**Local workflow with mandatory review: passed. Autonomous/general release: blocked.** This is a deliberate acceptance outcome, not an unfinished evaluation implementation.

The blockers are unmeasured real human correction cost, no independent unseen-writer evaluation, and the historical baseline latency exceeding the frozen 30-second P95 budget (all images P95 31.62 s; human originals P95 61.53 s). Historical inference timings include their recorded configuration/hardware and are not current live-service SLA measurements. Fresh challenge timings/model initialization are separate.

Priority: reduce false opening hypotheses and wall/dimension confusion; make missing alignment premises explicit during review; then collect timed reviews and new writers/captures. Existing VLM/grid pilot results remain development evidence. No new training or model promotion was justified by this step; the baseline and review/validator gate remain. A learned segmentation/junction or VLM proposal adapter should be compared using the same frozen metrics and real correction cost before promotion.

## Verification

262 Python tests passed, including 28 Step 13 tests for matching/cardinality, ID changes, translation/scale/reflection/yaw policy, opening errors, null stages, digit errors, association spans, leakage, corrupted inputs/artifacts, false-auto-accept release blocking, invalid fixtures, model-comparison denominators and immutable bounded telemetry. JS syntax checks and frozen input/output verification passed. No C++ changed; Step 12 engine evidence remains separately pinned.

Artifacts: `protocol.json`, `artifact-integrity.json`, `report.json`, `release.json`, `failures.json`, `index.html`, `solver/`, `challenges/`, plus `Saved/Step13/final-tests.log` and `integrity.log`.
