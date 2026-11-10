# Step 10 — Metric review, corrections and explicit acceptance

Implemented on 2026-10-21. The local browser flow now continues from topology review to measurement correction, dimension-driven cm preview and explicitly accepted `validated_layout` download. [Step 11 service/jobs and Unreal integration](step11_pipeline_jobs_unreal.md) is now implemented; Step 12 physical/Pawn verification is next.

## Run and use

Use the existing image/perception environment:

```bash
Saved/Step07/python/bin/python -m SketchPipeline.review.server
```

Open `http://127.0.0.1:8768/`. Existing `--run`, `--output` and `--port` options remain available. Backend code changes require restarting the server; the plain HTML/JS editor requires a browser reload after source changes.

1. Upload/select a drawing. Add/delete walls, snap/join junctions and add/move/approve openings in the existing **pixel topology** editor. These edits affect observed px geometry, never metric coordinate locks.
2. Approve the corrected topology and choose **Continue to metric review**. Direct URL: `/metric.html?case=CASE_ID`. The current topology must be approved and source hashes must still match.
3. Inspect the **Observed drawing** and its OCR boxes alongside the separate **Reconstructed plan**. Selecting evidence, a target span, wall, region or opening highlights the corresponding geometry. The cm view is independently reconstructed from confirmed dimensions; it is not an inverse-warped image overlay. Partially located regions remain absent, with unresolved values explicitly reported.
4. Select a measurement. Inspect its original raw OCR, numeric candidate/confidence and crop, edit its value, select the target and check **I confirm this exact value and target**. Changing a value/target requires confirmation again. The unchanged original observation remains linked by evidence ID. The correction carries `user_correction` provenance and a note.
5. Choose full room width/depth, an ordered contiguous wall chain, clear opening width, min/max corner offset or same-wall edge-to-edge separation. Wall-chain choices show the actual ordered wall IDs, including multi-edge spans across T junctions. Paper offsets are **corner → near clear opening edge**, not center; explicit center-based targets are separately labeled. Unreadable values can be entered manually, or left missing. Unwritten measurements can be added without pretending to have OCR evidence.
6. Mark irrelevant OCR evidence **Not a measurement**. Its evidence ID and reason are retained; the original observation is untouched. **Restore** returns it to review. A text cannot simultaneously be ignored and bound to a dimension.
7. Check every region's room/corridor type, give display names, and explicitly confirm the types. Configure wall/floor thickness, wall/door heights, and geometry-only/gameplay mode. Gameplay requires distinct Start/Goal rooms and passage connectivity; geometry-only supports a single room without roles.
8. Explicit centering/full-span entrance assumptions and metric vertex locks have dedicated controls. They never become hidden defaults. A full-span corridor entrance recomputes its clear width from supporting centerline span minus configured thickness. Pixel changes belong in the topology editor; metric locks use cm and the solver's origin frame.
9. Choose **Recompute & save draft**. Live previews are suggestions; saving creates a new immutable metric revision. Click an issue to select its associated measurement/entity. Resolve missing, inferred and conflicting inputs. **Undo saved edit / Redo saved edit** create new recomputed revisions from command history.
10. When the current saved revision passes all checks, enter a reviewer name and explicitly **Accept metric layout**. Only then can **Download validated JSON** export that exact revision. Any later edit/save creates a pending draft; prior accepted files remain immutable.

The topology review JSON remains a separate px artifact. The metric download is the canonical cm contract understood by the existing Unreal importer. Step 10 itself does not run Unreal. Step 11 now connects accepted jobs to asynchronous canonical import; actual Pawn/navigation verification remains Step 12. Metric corrections do not train models or change automatic perception accuracy.

## Acceptance and concurrency

`SketchPipeline/review/metric_store.py` owns metric transactions. Step 09 remains the core solver; its production path never reads manual ground truth. Each metric revision records:

- `schema_version: playablesketch-metric-review/1.0`, unique revision ID, parent revision and creation time;
- exact topology revision ID/digest, preserved solver source fingerprints and linked observations;
- complete input state: bindings, explicit relations/locks, ignored evidence, settings, names, semantic confirmation and roles;
- command type, `base_revision_id` and server-computed affected entity IDs;
- pending draft, full association/solver/validation report, bounded undo/redo state history;
- an accepted canonical snapshot only after explicit reviewer acceptance;
- a digest covering the persisted revision.

Storage is `<topology-output>/metric/<case>/revisions/<revision>.json` plus `latest.json`. Up to 100 prior input states per undo/redo branch are retained. Undo/redo recomputes against unchanged evidence; acceptance never changes source observations. Editing after acceptance produces a new pending revision, including a new immutable undo/redo command when used.

Every mutation/preview requires the current metric `base_revision_id`. Stale requests return 409 and cannot overwrite a newer correction. The browser also checks case/version/request tickets before applying asynchronous preview results and disables form edits during transactions. Unsaved edits block acceptance/download and trigger a navigation warning.

Every load, computation, acceptance and download rechecks the current accepted topology and source integrity. A newer topology invalidates metric bindings; reopening starts a fresh draft and asks for rebinding rather than silently migrating potentially changed IDs. A topology draft or changed original/observations blocks metric work/export. Old accepted metric files remain on disk for history but cannot be downloaded as the current result.

Acceptance recomputes the saved inputs, applies semantic metadata/roles, runs schema/custom validation with matching observations, and calls `as_validated` with a named reviewer. Download rechecks the exact displayed metric revision ID, recomputes and compares its accepted content. A different newly accepted revision in another tab is not silently substituted. Engine geometry/navigation remain `not_run`.

## API

The existing localhost server and session token/origin policy cover these routes:

| Route | Purpose |
| --- | --- |
| `GET /api/metric?case=ID` | Current state, linked evidence/crop boxes, target catalog, separate previews and report |
| `POST /api/metric/preview` | Stateless recompute tied to the current `base_revision_id` |
| `POST /api/metric/save` | Immutable pending metric revision |
| `POST /api/metric/undo`, `/redo` | New revision restoring a prior input state and recomputing |
| `POST /api/metric/accept` | Explicit reviewer acceptance of the current saved passing state |
| `GET /api/metric/export?case=ID&revision_id=REV` | Current accepted canonical JSON, checked against displayed revision |

POST bodies contain `case_id`, `base_revision_id`, and `state` for preview/save. Acceptance additionally requires `reviewer`; an unsaved replacement state cannot be accepted. Session token/origin checks are shared with topology actions. Existing `/api/export` continues to export px topology only.

The Step 09 metric-input schema adds optional `ignored_texts: [{evidence_id, reason}]` for explicit nonmeasurement rejection. It does not change the canonical layout or observations schema, or Unreal types. Original OCR remains immutable and ignored evidence can be restored.

## Verification

`SketchPipeline/tests/test_metric_review.py` adds 19 backend/API tests for raw evidence preservation, 800→600 corrections, wrong targets, confirmed conflict correction, missing dimensions, gameplay roles, settings, undo/redo, stale requests, source changes, immutable accepted snapshots, topology deletion/restoration, reviewer confirmation, session policy and revision-bound downloads. A Data_8 reference topology verifies moving the paper near-edge offset while retaining the 100 cm wall-local center and updating the right room's placement. A corridor fixture with the Data_10 missing-width/depth/corridor-width pattern stays blocked until all three values are supplied.

```bash
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
node --check SketchPipeline/review/web/editor.js
node --check SketchPipeline/review/web/metric.js
```

Browser verification used the actual served UI on a **controlled test fixture**, not a user drawing: value editing and reconfirmation, save, undo/redo, named acceptance and validated JSON download. The downloaded file independently passed `validate_document` with its matching observations (`schema_valid`, `metric_valid`, `exportable` all true). A subsequent save returned the session to draft and disabled download.

Artifacts: `Saved/Step10/v1/metric_review.jpg`, `ui_download.validated.json`, `ui_download_validation.json`, `verification.json` and `tests.log`. The controlled fixture uses a blank synthetic image and artificial OCR labels; its programmatic approvals and browser test actions are not training ground truth or human reviews of the 50 original drawings. No actual user drawing was auto-approved.

Final verification on 2026-10-21: **224 tests passed**; both editor JS syntax checks passed. The normal project server was also checked through its existing Data_2 topology→metric handoff, without saving corrections or approving any real user metric data.

Step 13 subsequently adds optional bounded active-review timing to the immutable revision ledger. This metadata is not part of canonical JSON or acceptance decisions; historical review time remains unknown. See [Step 13](step13_evaluation_robustness.md).
