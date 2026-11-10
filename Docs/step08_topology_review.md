# Step 08 — Topology review and drawing upload

This local web editor lets a user correct detected walls, openings and region connections over a drawing. Every new upload opens a review, including drawings with no usable automatic detection. The UI, help, validation messages and upload messages are in English.

Approval at this stage covers **pixel topology**, not dimensions, gameplay validity or an Unreal-ready layout. A plausible automatic result still requires explicit user approval.

## Run

From the repository root:

```sh
Saved/Step07/python/bin/python -m SketchPipeline.review.server
```

Open `http://127.0.0.1:8768/`. Defaults:

- Existing predictions: `Saved/Step08/final-review-v4`.
- Uploaded drawings and review revisions: `Saved/Step08/topology-review`.
- Server binds only to `127.0.0.1`; processing runs on this computer.

Optional settings:

```sh
Saved/Step07/python/bin/python -m SketchPipeline.review.server \
  --run Saved/Step08/final-review-v4 \
  --output Saved/Step08/my-topology-review \
  --port 8768
```

Keep the process running; use Ctrl+C to stop it. Start only one server per review output directory. The existing Python environment supplies perception dependencies; no additional web framework is required. `--run` must be an existing directory and may be empty for upload-only use.

## Upload and mandatory review

1. Click **Upload drawing** and select one JPEG/PNG image. Limits: 20 MB, at least 16×16 pixels, at most 40 MP. File contents are checked, not just the extension.
2. If the current drawing has unsaved corrections, the editor saves them as a **draft** before switching. A failed draft save cancels the upload. Editing and drawing selection pause while the upload is processed.
3. The server assigns a unique upload ID and runs the existing preprocessing, OCR, wall/opening detection and topology pipeline. It uses image pixels and fixed configuration, without ground truth input. A single worker processes jobs; up to three queued/processing jobs are admitted.
4. When processing finishes, the new drawing opens automatically. Its review starts **unsaved**, its opening candidates start **pending**, and it has no accepted revision. Uploading the same image again creates a fresh review rather than inheriting an earlier approval.
5. If automatic detection fails for a decodable image, the drawing still opens with an empty editable graph and a manual-review notice. Add the missing walls and openings over the image. No guessed evidence or metric geometry is fabricated. A file that cannot be decoded is rejected with an English error.
6. Correct the geometry, resolve blocking issues, visually compare the result with the drawing, then click **Approve topology**. The system never clicks this button for the user.

Detection can be incomplete even when the inference job succeeds. The normal review notice, pending openings, graph checks and editable overlay cover that case. This version has no calibrated overall confidence score; structural checks cannot prove that the inferred plan matches the user's intention.

## Correct the drawing

1. **Select:** click a wall/opening. Drag an endpoint or edit its coordinates and click **Apply coordinates**. **Delete** removes the selection. The issue panel's element IDs select the corresponding element.
2. **Wall:** click two endpoints. Horizontal/vertical alignment is automatic; nearby endpoints and segments provide snap targets. Overlapping physical walls produce a blocking issue.
3. **Join endpoints:** choose two different wall endpoints. Perpendicular walls meet at their axis intersection; collinear walls meet at the selected endpoint. Parallel walls at different normal coordinates must be aligned first. A move that would tilt connected geometry is refused.
4. **Opening:** click its two endpoints. Drawing it over a physical wall cuts that span out of the wall. Choose `door` or `open_passage`, then **Approve opening**. Opening approval is separate from topology approval.
5. **Reject** removes an opening hypothesis without creating a wall. **Fill opening with wall** explicitly fills its physical gap and rejects the opening.
6. **Save draft** preserves incomplete work. **Approve topology** is enabled only when structural checks pass. After approval, **Download reviewed JSON** exports the current reviewed revision. Editing or saving a new draft prevents that draft from being downloaded as reviewed.

Mouse wheel zooms; Space/Pan drags the view; **Fit** recenters it. Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z redoes, Delete removes and Escape cancels an operation. Undo history is session-local; saved revision history is on disk. Switching drawings or leaving the page warns about unsaved changes.

Colors: teal physical walls, orange pending openings, green approved openings, amber unresolved region boundaries, purple rectangular candidates, red unsupported regions or dangling walls. A green opening does not imply approval of the whole plan.

## Approval checks

- At least one closed rectangular region must exist; L-shaped regions and holes are unsupported in v1.
- All opening candidates require an explicit `approved` or `rejected` decision. Approved openings require a known type.
- An approved opening must attach to two distinct matching physical supports and connect two rectangular regions.
- Overlapping walls, cut edges and invalid rings block approval.
- Dangling segments longer than 2 px block approval; smaller overshoots remain warnings.

These are structural checks. Users must also check missed/extra rooms, wrong openings and intended connections. Dimensions, room/corridor semantic editing, Start/Goal and gameplay reachability are outside this editor's current scope.

## Implementation and storage

- `review/server.py`: local HTTP API, exact geometry analysis, approval gates and revision storage.
- `review/uploads.py`: bounded background upload jobs, existing inference adapter, manual fallback and registration of new cases.
- `review/web/`: plain HTML/CSS/JavaScript canvas editor.

Only a new upload runs OCR/perception. Geometry edits use `build_topology(..., review_exact=True)`; perception recovery does not silently heal or move user corrections.

The background and geometry use the same `working_rotated_pixel` frame. Revisions preserve `original_to_review` and `review_to_original` transforms. Step 09 can use these transforms to associate original-frame OCR evidence with reviewed geometry. Pixel distances are never treated as centimeters.

```text
Saved/Step08/topology-review/
  uploads/
    Upload_<UTC>_<unique id>/
      source.jpeg                 # or source.png/source.jpg
      upload.json                 # job status, label, requires_review
      prediction/
        observations.json
        working.json
        topology.json
        unmasked_line_input.png
        ...                       # other inference artifacts, if available
  Data_8/                         # existing prediction case
    latest.json
    revisions/<revision id>.json
  Upload_<UTC>_<unique id>/        # uploaded case, after an explicit save
    latest.json
    revisions/<revision id>.json
```

Completed uploads reappear in the drawing selector after restart. Raw images, automatic predictions and review revisions are separate. Immutable revisions use `playablesketch-topology-review/1.0`, include parent ID, state, topology, validation, transforms, source fingerprints and server-computed changes. State and whole-revision hashes protect integrity; `latest.json` is updated atomically. Stale sources or parent revisions block saving. Existing prediction files and manual annotations remain unchanged.

A manual fallback contains empty, schema-valid original-frame observations; `working.json` marks `manual_review_required` and `training_performed: false`. Review corrections do not retrain OCR or produce measurement labels automatically.

This output is **not** `validated_layout`: `units` remains `px`, `metric_layout_created` remains `false`. Step 09 must verify a current reviewed revision and its source provenance before using it. A separate metric review and validation precede the existing Unreal importer.

## Verification

```sh
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
node --check SketchPipeline/review/web/editor.js
```

112 Python tests passed on 16 October 2026. Coverage includes exact edits, opening decisions, holes/overlaps, approval gates, immutable revisions, stale sources/parents, integrity, reviewed-only export, upload validation, bounded queue, failed-inference fallback, duplicate uploads, restart persistence and HTTP session boundaries.

Browser smoke checks used isolated `Saved/Step08/upload-smoke-review-v1` storage: a real Data_3 photo ran automatic inference and opened an unapproved review; a blank fixture opened manual review; unsaved corrections were preserved as a draft before the next upload. A rectangle drawn on the blank fixture passed graph checks and an explicit test approval enabled reviewed JSON download. These test uploads are not independent evaluation data or accepted user ground truth.

For deployment choices, roadmap boundaries and dataset planning, see [Product architecture](product_architecture.md).


## Step 09 handoff (2026-10-21)

The metric core/CLI now consumes the latest accepted revision together with linked observations and explicit measurement bindings. It rechecks source hashes and exact topology; metric output stays pending for Step 10. After approving the current topology, **Continue to metric review** opens the implemented [Step 10 screen](step10_metric_review.md). Pixel topology JSON remains separate from accepted metric JSON. See [Step 09 metric solving](step09_metric_solving.md).


## Step 11 persistent job intake (2026-10-21)

The browser now submits multipart `/jobs` uploads with stage progress and persistent failure/retry/cancel controls. Existing `/api/upload` remains for compatibility. The same topology/metric acceptance gates apply. Usage, cache/replay and Unreal actor actions: [Step 11](step11_pipeline_jobs_unreal.md).
