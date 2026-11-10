# PlayableSketch product architecture and dataset plan

## Recommended first product

Use a **local web UI + local Python backend + Unreal canonical geometry core**, available through both Unreal Editor integration and the Step 14 Mac packaged runtime. The browser is the interface; it does not require cloud hosting. The current editor already runs on localhost and processes uploaded images on this computer.

Keep one image-processing implementation and one versioned data contract. The local Mac Development package now reuses the same review UI/backend through an external Python sidecar. Public hosting is a separate deployment decision, not a prerequisite for finishing recognition or Unreal integration.

| Option | User flow | Main tradeoff |
| --- | --- | --- |
| Local web UI, recommended now | Start local backend, open browser, upload/review, import validated JSON into Unreal | Reuses current implementation; needs local Python environment until packaged |
| Local Mac package, implemented | Launch app, browser upload/review, import accepted revision, play and save/load | Uses repository + existing Python sidecar; redistribution/update installer remains future work |
| Hosted website, later | Upload to hosted inference, review online, download validated JSON or use a local companion/plugin | Centralized deployment; adds hosting, accounts/storage and a connection to the user's local Unreal |

A hosted website cannot assume it has direct control over an Unreal instance on the user's computer. Explicit JSON download/import remains supported. The Step 11 actor actions now upload to the local job service, open review, inspect status and fetch an explicitly selected **validated metric revision** into the existing canonical importer. Import failures preserve the prior valid design; actor/service/job/asset selection remains explicit.

Epic's [Remote Control quick start](https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-quick-start-for-unreal-engine) documents HTTP/JSON control of Unreal Editor. It is an optional future bridge mechanism, not a required dependency or something enabled by this change. Epic recommends keeping that server on a LAN/VPN rather than exposing it to the public internet; the feature is marked Beta. A purpose-built local importer bridge remains another option.

## Current shape-first local flow (4 November 2026)

The default web/runtime launchers now use shape-first/1.0: image → local DINO
geometry proposals → visual corrections → design size suggestions/locks → exact
saved-plan confirmation → strict validated canonical bundle → existing Unreal
importer → engine collision/navigation and actual Pawn checks. Numeric OCR is not
called and handwritten numbers are not treated as physical dimensions. The global
model default remains unchanged; these launchers explicitly select the experimental
candidate. The old strict-measurement pipeline below remains a separate supported
workflow with its original fixtures and accuracy results.

Exports are immutable snapshots with source, policy/model and authoring lineage.
Stale/tampered snapshots reject download/import; editing requires re-confirmation.
Confirmed design dimensions never become image-ground-truth labels automatically.
See [Step 5 shape-first delivery](step05_shape_delivery_2026_11_04.md).

## End-to-end logic and current boundaries

```text
JPEG/PNG upload
  -> preprocessing + pretrained OCR + line/opening detection
  -> automatic pixel topology hypotheses
  -> mandatory topology review (current editor)
  -> dimension association + metric constraint solving (Step 09)
  -> measurement/semantic review + explicit acceptance (Step 10)
  -> validated_layout JSON
  -> existing Unreal canonical importer / explicit geometry builder
  -> collision + navigation + Pawn verification
```

The original roadmap has Step 05–14 as ten implementation steps; it does not end at Step 10.

- **Step 08:** Wall Graph, rectangular regions and opening connections. The current editor corrects this stage's output; automatic perception remains fallible.
- **Step 09 (core/CLI implemented 2026-10-21):** Associate written dimensions with measured spans/openings, solve cm coordinates and report missing/conflicting constraints. An opening offset is corner-to-near-opening-edge, per the author's 2026-10-16 correction. Derive its center by adding half the clear width when measuring from the minimum corner. Never infer metric lengths from sketch proportions.
- **Step 10 (implemented 2026-10-21):** Extend review to OCR text, dimension targets, cm geometry, room/corridor semantics, settings and Start/Goal. Produce an explicitly accepted metric revision. The local browser now provides metric editing, immutable revision commands and validated JSON download after named acceptance. See [Step 10](step10_metric_review.md).
- **Step 11 (implemented 2026-10-21):** Persistent subprocess jobs, CLI manifests, multipart API, cancellation/timeout/retry/restart, explicit cache/replay, review-gated atomic exports and asynchronous Unreal Editor upload/status/review/selected-revision import are ready. See [Step 11](step11_pipeline_jobs_unreal.md).
- **Step 12 (implemented 2026-10-21):** Published collision grid, explicit agent contract, actual swept capsule Pawn, negative fixtures and separate-process save/reopen/Local/Full/BeginPlay verification. Flat horizontal floors; Recast/AI and CharacterMovement gravity/stairs are not certified. See [Step 12](step12_physical_navigation.md).
- **Step 13 (implemented 2026-10-21):** Frozen development evaluation, robustness probes, ID-independent metric comparison, failure gallery, review-time ledger metadata and release gates. Local review-required workflow passes; autonomy/general release remains blocked by measured evidence gaps and historical latency. No new training. See [Step 13](step13_evaluation_robustness.md).
- **Step 14 (implemented 2026-10-21):** Local Mac arm64 Development package with native Slate client, browser upload/review, accepted-revision import, atomic ready state, actual Pawn play and checksummed two-bank SaveGame. Cosmetic seed changes preserve geometry and route. 14 Unreal tests and three cooked-process scenarios passed with `WITH_EDITOR=false`. See [Step 14](step14_packaged_runtime.md).

Step 09 currently runs through the Python core/CLI with explicit measurement bindings. It verifies the latest reviewed topology and its sources, proposes associations, solves confirmed constraints and preserves a pending metric draft. It does not automatically confirm OCR. The Step 10 browser screen now edits these bindings and accepts passing metric snapshots. Usage, regressions and limits: [Step 09](step09_metric_solving.md).

Wall thickness and height remain settings outside the paper drawing. They are editable on the metric review screen; topology remains a px-only stage. Reviewed px JSON must not be fed directly to the metric importer.

## What is trained today?

The production system combines pretrained `RapidOCRAdapter` inference with OpenCV geometry heuristics and Shapely topology operations. Neither an upload nor clicking approval updates any model weights.

On 2026-10-19, an isolated offline experiment completed decoder fine-tuning of `microsoft/trocr-small-handwritten` on 6,096 single-line training crops. The experiment measured the existing baseline on all 720 images and compared recognition on the 144 grouped development-test images, with original-image diagnostics reported separately. The experimental checkpoint does not replace RapidOCR in the local UI. No wall/topology model was trained. Results, limitations and artifacts: [dataset evaluation and OCR fine-tuning](data_training_evaluation_v1.md). Step 09 metric core/CLI was subsequently implemented on 2026-10-21; Step 10 metric review was also completed; Step 11 service/jobs and Unreal integration were subsequently completed. Step 12 physical/Pawn verification was subsequently completed for the flat-floor adapter. Step 13 evaluation/robustness was subsequently completed; Step 14 local Mac packaged/runtime integration was subsequently completed; core Steps 05–14 are implemented within their documented scopes. General release and autonomous inference remain gated by Step 13 evidence. See [metric solving](step09_metric_solving.md).

The ten Data_1–10 photos have informed implementation and tuning. They are a development set; their scores cannot establish generalization to new users' sketches.

## When to collect more data

**Now, for evaluation:** collect an initial 30–50 fresh drawings as an engineering target, from multiple writers and capture conditions. Freeze a portion as holdout before inspecting/tuning on its outcomes. Include rectangles, shared walls, corridors, T junctions, missing dimensions and dimension conflicts. Add different number styles, rotated labels, faint strokes, shadows and perspective. There is no universal minimum number that guarantees accuracy.

Keep the same drawing, its crops, recaptures and augmentations in one split. Group by writer/plan/capture session where possible; an unseen-writer test estimates generalization better than a random crop split. Use a separate development set for repeated tuning and preserve a final holdout for an unbiased check.

**During review, for curation:** retain source images, untouched predictions, reviewed revisions and changes. Use each label only for the task it actually describes:

| Task | Labels required | What current corrections provide |
| --- | --- | --- |
| OCR recognition | Text crop + verified transcription | Not provided by topology approval |
| OCR detection | Verified text polygons | Existing manual pixel annotations; numeric values can be corrected against preserved polygons in Step 10; no polygon editor |
| Wall/opening detection | Verified segments, junctions and opening spans | Reviewed topology can provide candidates for curated labels |
| Dimension association | Verified number-to-span/opening links and measurement basis | Step 09 proposals + Step 10 explicit target/value correction UI ready |
| Metric reconstruction | Verified cm layout, dimension conflicts and settings | Step 09 solver/validator and Step 10 explicit metric review/acceptance UI ready |

A structurally valid graph is not automatically ground truth. Curate examples, confirm intent and keep source transforms. Review artifacts currently remain local project artifacts; no training ingestion is connected.

**Later, for training:** fine-tune only when independent evaluation shows a repeatable failure that the learned component should solve. For example, repeated handwritten digit confusions suggest OCR recognition training; poor number-to-wall association suggests improving association rather than retraining OCR. Missing junctions may need geometry changes before a segmentation/junction model is justified.

PaddleOCR's [general OCR pipeline documentation](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html) describes using domain-specific fine-tuning when pretrained models are insufficient. Its [recognition training guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version2.x/ppocr/model_train/recognition.en.md) describes image/transcription labels and separate training/evaluation datasets. Training new PaddleOCR weights would also require a separately validated export/runtime integration with the current RapidOCR adapter; it is not already wired up.

Choose training volume from learning curves and failure coverage rather than a fixed photo count. One floor-plan photo can supply several text crops, but those crops are correlated and cannot be treated as independent holdout examples. Evaluate text accuracy, opening precision/recall, region/connectivity correctness, complete-plan success and correction effort separately.
