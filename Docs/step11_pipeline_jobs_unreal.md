# Step 11 — Pipeline orchestration, persistent jobs and Unreal handoff

Implemented on 2026-10-21. The local workflow now connects image intake, recorded processing stages, mandatory topology/metric review, accepted canonical exports and asynchronous Unreal Editor import. The subsequent **Step 12: collision/navigation, actual Pawn traversal and lifecycle verification** was completed for the flat-floor adapter on the same date; see [Step 12](step12_physical_navigation.md).

## Browser workflow

Start the same local server:

```bash
Saved/Step07/python/bin/python -m SketchPipeline.review.server
```

Open `http://127.0.0.1:8768/`. **Upload drawing** now sends a multipart image/config request to the persistent job API. The **Pipeline jobs** panel provides recent jobs, processing mode, explicit cache policy, stage/status, cancellation, retry and reopening. Automatic inference remains the default; explicit manual preparation is separately labeled. Neither mode approves topology or metric measurements.

The acknowledgement returns a job ID promptly. A single background supervisor starts an isolated Python worker. Processing updates named stages (`model_loading`, `preprocess`, `ocr`, `walls`, `topology`, `artifact_validation`); percentages are not invented. Completed predictions open the existing topology editor. Approve the corrected topology, continue to metric review, correct/confirm measurements and semantics, then explicitly accept a named metric revision. All Step 09/10 gates remain active.

`/?job=JOB_ID` opens an existing job, waits for active processing and then opens its review. Failed/cancelled jobs remain visible for inspection/retry, including after a service restart. `/?case=CASE_ID` still opens an already registered drawing. `GET /jobs/JOB_ID/draft` returns either the pending topology case or the metric review state, depending on the current reviewed stage.

A model/detection failure can produce clearly marked `manual_fallback` preparation with the original reason in the run manifest. Such a result still requires drawing/correcting topology and entering confirmed measurements. It is not reported as successful automatic inference.

## CLI

Real inference on a single image:

```bash
Saved/Step07/python/bin/python -m SketchPipeline.pipeline analyze \
  --image Data/Data_2.jpeg --output Saved/MySketchRun
```

Explicit configuration (JSON file, strict unknown-field/type checks):

```json
{
  "mode":"inference",
  "geometry_profile":"baseline",
  "max_side":1600,
  "detector":"lsd",
  "settings":{"wall_thickness_cm":20,"wall_height_cm":300,"door_height_cm":220,"floor_thickness_cm":20},
  "timeout_seconds":300,
  "cache_policy":"fresh",
  "drawing_convention":"drawing-convention/v1"
}
```

Pass it with `--config config.json`. Explicit manual preparation uses `"mode":"manual"` and performs no OCR inference. Explicit replay:

```bash
Saved/Step07/python/bin/python -m SketchPipeline.pipeline analyze \
  --image Data/Data_2.jpeg --replay Saved/Step11/inference_smoke/prediction \
  --output Saved/MyReplay
```

Replay verifies source-image identity, records input prediction hashes, preserves the source prediction configuration and reports `execution_mode: replay`. Requested perception settings are not rerun during replay. Outputs must be new; no existing run is overwritten. The CLI prepares unreviewed prediction artifacts; acceptance remains an explicit review transaction. Service upload invokes the same pipeline runner in its supervised subprocess, with configured cancellation/timeout handling. The direct analyze CLI itself is a foreground local command; its configured timeout is enforced when run as a service job.

## Persistence, stages and publication

Implementation:

- `SketchPipeline/pipeline.py`: strict configuration, runtime/model/code identity, real stage callbacks, inference/manual/replay paths and atomic prediction manifest.
- `SketchPipeline/jobs.py`: persistent metadata, one bounded worker queue, process supervision, restart recovery, explicit cache selection and immutable metric/export ledgers.
- `SketchPipeline/job_api.py`: multipart and HTTP adapters over stage/review functions.
- Existing review server, topology correction UI, metric review and canonical validator remain the authoring gates.

Storage under `<review-output>/jobs/JOB_ID/`:

```text
source.png|jpg|jpeg           immutable staged original
job.json                     persistent operational state/config/runtime/source hash
progress.json                named processing stage and elapsed time
worker.log                   diagnostic subprocess output
prediction/                  observations, working transform/evidence, topology, review image
manifest.json                immutable prediction run manifest
metric_revisions/METRIC_ID/   draft, solver report, corrections and per-revision manifest
exports/METRIC_ID/            accepted layout, observations, solver report and export manifest
```

The immutable prediction manifest records source hash, normalized config/hash, model lock hash, code hash, installed runtime/package versions, execution mode, timings and prediction artifact hashes/versions/revisions. Original images and prediction files are reverified before review/export. Unknown or missing artifact inventory and changed configs fail verification. Inference byte-for-byte reproducibility across different hardware is not promised.

Association/solve/semantics/metric validation are explicitly deferred until reviewed topology and confirmed measurement input exist. Each metric transaction then publishes its own immutable stage ledger, linked to the initial run manifest, topology revision, review-record digest and exact input-state hash. It contains pending draft/report/corrections and an accepted file only after named acceptance. The metric `latest.json` pointer advances after this ledger is complete. Job metadata/progress stays outside canonical layout JSON.

Accepted export stages files in a temporary directory, verifies review/observations/source identity, writes a complete manifest and atomically renames the directory. Repeated export of the same selected revision verifies and reuses the same immutable files. Missing/conflicting/inferred/draft results cannot be returned by the accepted-layout endpoint. Exported observation paths are rebased to the original staged source; the source file remains hash-linked. Source references remain local provenance for the canonical importer.

### States and failure behavior

```text
uploaded → processing → needs_review
processing → failed | cancelled
needs_review → confirmed corrections / metric validation → explicit acceptance → validated
validated → selected canonical export → exported
validated/exported → edit → new needs_review revision
```

The stored job record tracks processing state; API status derives current review/accepted/exported state from the latest verified topology and metric revision. A metric validation failure is review work, not an inference-worker crash.

- Maximum 3 active/queued jobs and one processing worker. Default service timeout 300 seconds, configurable 1–900 seconds.
- Cancel/timeout terminates the worker; it escalates to kill if required. Partial predictions or manifests cannot enter review/export.
- Worker failure records a readable reason; logs remain local. Interrupted queued/processing jobs become failed on restart rather than resuming a possibly stale publication.
- Retry creates a **new** job with `parent_job_id`. It verifies the original source and retains prior results/accepted snapshots.
- All metric mutations/previews use `base_revision_id`. Stale responses do not overwrite current corrections. Topology changes require rebinding measurements.
- `cache_policy: fresh` creates a new unreviewed job. `reuse_job` explicitly reuses only an intact matching completed job; response labels the cache hit and records that inference did not rerun. Source/config/model/runtime identity enters the key. Operational timeout/cache selection does not change logical layout identity.
- Fresh jobs with the same source/semantic configuration/runtime share a stable canonical document identity; revisions remain distinct. Unreal reuses the assigned asset and deterministic entity identity rather than creating a new Data Asset per request.

## Local API

Every mutation requires the existing `X-Review-Token` from `/api/bootstrap` and passes the local Origin/session checks. The server listens on loopback. Existing `/api/upload` remains available for compatibility; the browser uses `/jobs`.

| Method/path | Input/result |
| --- | --- |
| `POST /jobs` | multipart `image` plus optional `config` JSON form field → immediate job acknowledgement |
| `GET /jobs/ID` | state, stage, error, review URL, current/accepted metric revision |
| `GET /jobs/ID/manifest` | verified prediction run manifest |
| `GET /jobs/ID/evidence` | linked observations |
| `GET /jobs/ID/draft` | pending topology or metric review payload |
| `PATCH /jobs/ID/draft` | metric correction state + `base_revision_id` → new draft revision |
| `POST /jobs/ID/validate` | exact `base_revision_id` → current metric checks, without acceptance |
| `POST /jobs/ID/accept` | current `base_revision_id` + reviewer → accepted immutable metric revision |
| `GET /jobs/ID/layout?revision_id=METRIC_ID` | selected current accepted canonical cm JSON; also publishes verified export bundle |
| `POST /jobs/ID/cancel` | cancel an uploaded/processing job |
| `POST /jobs/ID/retry` | failed/cancelled job → new job |

Topology edits/approval and metric undo/redo remain exposed through the existing review APIs. A passing validate response is not acceptance. Requesting a draft, stale, unknown or omitted revision from `/layout` returns an error. Engine import success remains separate from accepted job/export state.

## Unreal Editor workflow

Build/restart `PlayableSketchEditor`, then select a `PlayableSketchLevelActor` and expand **PlayableSketch → Pipeline**:

1. Keep `Pipeline Service Url` at `http://127.0.0.1:8768` (explicit loopback HTTP/port only).
2. Set `Pipeline Image Path` to a PNG/JPEG (project-relative or absolute, up to 20 MB), then choose **Upload Pipeline Image**. Current actor thickness/height settings accompany the image/config multipart request.
3. **Refresh Pipeline Job** asynchronously reads state/stage. No OCR or long model call runs on the Editor/game thread.
4. **Open Pipeline Review** opens the selected job in the local browser. Complete topology and metric review, then explicitly accept.
5. Refresh again. `Pipeline Accepted Revision Id` is populated from the current accepted status if empty; it remains editable so the intended snapshot is explicit. Assign an **ImportedLayoutAsset** and keep actor scale `(1,1,1)`.
6. Choose **Import Pipeline Accepted Layout**. It fetches that job/revision asynchronously, verifies the returned canonical revision and invokes the existing canonical parser/builder/publication path on the game thread. A changed job, selected revision, service, target asset or target asset revision discards a stale response.
7. Inspect **Last Pipeline Status**, **Last Import Report** and the separate geometry/navigation reports. Save the asset and map explicitly.

HTTP dispatch/failure does not mutate the accepted actor asset or scene. The canonical importer still preflights parsing, geometry, wall ownership, openings and component publication before changing persistent state. A metric-accepted plan can be physically rejected by the builder; the accepted job remains available and the prior valid actor design is retained. Reimporting the same snapshot does not accumulate components. This step adds no public hosting, distributed workers, automatic asset creation or packaged-runtime authoring.

## Verification — 2026-10-21

- **234 Python tests passed**, including 10 new job/API/subprocess/cache/restart/export regressions. Targeted job tests were repeated after final config/inventory integrity checks and passed. JS syntax checks passed.
- Real `Data_2` image ran through actual inference via CLI: `Saved/Step11/inference_smoke/manifest.json` records `execution_mode: inference`, preprocess/OCR/walls/topology stages, transforms and unreviewed output. No metric result or human approval was invented for that image.
- A separate **controlled synthetic fixture** exercised multipart upload → persistent worker → explicit topology correction → metric correction/validate → named acceptance → selected layout export. Programmatic fixture approvals are test actions, not training annotations or human reviews of original drawings.
- Mac Editor build succeeded. As in Step 05, the existing local Xcode 27 verification wrapper temporarily admitted the installed SDK range and restored the engine SDK configuration byte-for-byte afterward. `Saved/Step11/build.log` and `build_with_current_xcode.py` preserve this local verification limit.
- All **11 `PlayableSketch.*` Unreal automation tests passed**, including new `Pipeline.RequestGuards` and `Pipeline.LocalJobImport`. The existing authoring negative case retains its expected overlap warning. No tests failed or were skipped.
- The live Unreal test actually contacted the controlled local service, selected the accepted metric revision, imported canonical explicit geometry, reimported without component accumulation and rejected a stale selection while retaining the existing asset/components. These are transient test worlds, not edits to the user's map.
- Browser upload used the real job controls and file chooser, opened a new pending review automatically and kept missing topology blocked.

Artifacts: `Saved/Step11/verification.json`, `tests.log`, `job-tests.log`, `unreal-full-report/index.json`, `unreal-full-tests.log`, `e2e/service.json`, `e2e/layout.json` and the controlled service's immutable job/export ledgers. The controlled fixture service is only for tests; normal use remains port 8768.

Reproduce the controlled live engine test:

```bash
mkdir -p Saved/Step11/e2e/input_predictions
Saved/Step07/python/bin/python -m SketchPipeline.review.server \
  --run Saved/Step11/e2e/input_predictions --output Saved/Step11/e2e/review --port 8771
# In another terminal:
Saved/Step07/python/bin/python -m SketchPipeline.experiments.pipeline_fixture \
  --url http://127.0.0.1:8771 --output Saved/Step11/e2e
# Run PlayableSketch.Pipeline.LocalJobImport in Unreal Automation with that service running.
```

Actual flat-floor Pawn traversal, collision-grid clearance and expanded lifecycle checks were subsequently completed in [Step 12](step12_physical_navigation.md). NavMesh/AI and CharacterMovement gravity/stairs remain outside that adapter’s certification.
