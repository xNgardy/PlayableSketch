# Shape-first Step 4 — workspace implementation

Date: 4 November 2026. Initial Step 4 checks were backend-only because of a browser usage limit. **Follow-up during Step 5:** that limit reset; a real browser sample settings/roles/confirmation/export/download and separate real image upload to the DINO workspace were checked. Screenshot and downloaded ZIP evidence are in `Saved/ShapeFirst/delivery/v1`. The original scope notes below describe the initial run; a complete accessibility/device certification is not claimed.
This is the local PlayableSketch application, not a hosted Site.

## Run locally

Run `Start Sketch Workspace.command` from this repository. It uses the existing
`Saved/Training/v1/python/bin/python`, explicit DINO checkpoint + checksum,
`refined-full`, ink normalization and port 8772. Open the printed local address
in your browser. Override the port with PLAYABLESKETCH_PORT if needed. Jobs persist
under `Saved/ShapeFirst/workspace/jobs`. The launcher does not install packages,
download weights or change the global model default. It does not automatically
open a browser. The temporary verification server has been stopped.

## Implemented experience

- English PlayableSketch branding, editorial olive/paper design and an upload
  landing page. Drag/drop or file selection, PNG/JPG and 20 MB guidance, optional
  drawing convention, recoverable upload errors and saved drawings.
- Use a sample creates a clearly curated **manual** sample with two rooms, one
  corridor and two doors. This is not represented as an AI detection success.
- Real inference jobs show analyzing/cancel/manual continuation/retry states.
  Failed/empty detection retains the image and opens manual tools.
- One workspace contains the source image, clean generated plan, Sketch / Plan /
  Compare, selection in both panes, zoom/pan/fit, entity lists and inspector.
  Plan size editing changes the metric design; sketch geometry remains separately
  visible. Geometry tools switch to the sketch when necessary.
- Move, draw room/corridor rectangles, pointer corner resizing, keyboard resizing,
  delete, add door on a shared boundary, move/resize a connection along its current
  support and Connect for a shared interface or nearby aligned corridor end.
  Connection owners are never silently retargeted by a move.
- Unsupported/deformed attachments remain in edit state and appear in Needs
  attention; save diagnostics cannot be hidden by confirmation. Clicking an issue
  selects its related item. No pixel-coordinate prompts or schema names appear in
  the ordinary flow; technical model information is in Advanced details.
- Names/types, room width/depth, corridor length/width, door width/near-edge
  position, Suggested / Custom badges, Keep proportions, locks and reset use the
  real sizing API. The position reference junction is highlighted separately from
  the opening interval.
- Size changes are serialized, carry topology/sizing revisions and render the
  currently selected inspector. Old-job responses and old geometry saves cannot
  overwrite a newly opened job. Conflict retains the previous valid preview.
- Topology changes invalidate size bindings. Update suggested sizes explicitly
  resets them; if user overrides/locks exist the UI explains that they remain in
  saved history before asking to replace the bindings.
- Undo/redo tracks geometry, sizes and metadata. Save/dirty/pending state and
  unload protection are present. Names/Start/Goal choices persist independently
  of raw AI proposals and size values.
- Settings expose wall/floor/door heights and wall thickness in metres. Start and
  Goal are saved for later gameplay setup; player traversal is not certified here.
- Review plan shows counts and unresolved state. Confirm plan records a separate
  immutable reviewed snapshot, with its own authoring revision and current value
  bindings. Any topology, sizing or metadata change invalidates the current
  confirmation. The underlying proposal and sizing draft remain pending.
- Export for Unreal is visibly disabled with an explanation. Step 5 still owns
  accepted canonical delivery, gameplay clearance, import/play and persistence
  acceptance. No unvalidated JSON is presented as a usable Unreal export.
- Responsive CSS, visible focus, native forms, keyboard shortcuts, entity-list
  selection, canvas keyboard tools, modal Escape behavior and non-colour status
  text are implemented. Actual responsive/a11y/visual acceptance is not verified.

## Backend additions

`workspace.py` supplies:
- GET/POST `/shape-jobs/{id}/workspace` — names and optional room roles, optimistic
  topology/workspace revisions, immutable metadata history.
- POST `/shape-jobs/{id}/confirm` — checks the exact topology, sizing and workspace
  revisions, unresolved saved attachments and strict metric preview validity.
  It saves an accepted authoring snapshot but returns delivery_ready=false.
- POST `/api/sample` — curated local editable sample, no inference claim.

`server.py` serves the local workspace JS/CSS and strictly checks JSON object
bodies for sizing/workspace/confirmation. All mutation endpoints retain the local
session token/origin checks. No cloud service, hosting or external assets are used.
`ShapeJobs` keeps the previous Step 2–3 methods and uses the workspace mixin.
Removed entity names/roles are filtered from the current view while their old
records remain in history; an orphan name cannot prevent later saves.

## Verification completed

- **122 unique Python tests passed:** 119 related regression/core tests plus 3
  isolated HTTP tests. The 8 new workspace tests cover curated sample sizing,
  metadata/restart, new exact confirmation snapshot, confirmation invalidation,
  invalid roles, deleted metadata and unresolved attachment gating. The HTTP test
  covers token rejection, asset serving, confirmation and malformed JSON.
- **13 in-memory JavaScript state checks passed.** They test shared boundary door
  insertion/overlap suppression, deletion/undo, invalid attachment detection,
  corridor connection, selected-inspector preservation, old-job sizing response
  rejection, size undo payloads, keyboard/modal behavior, keyboard room insertion,
  new-region naming, old-job geometry save rejection, old-job metadata response
  rejection and metadata undo/redo. These use a minimal mocked DOM and fake API;
  they are not a real DOM/browser/render/accessibility test.
- Separate backend acceptance exercised sample → automatic sizes → custom width
  8 m → conflicting depth 20 cm retains previous preview → reset → names/roles →
  explicit test confirmation → restart/reopen. All passed using real job storage.
- A separate real DINO upload of Data 25 produced 2 rooms and 2 doors, then a
  metric-valid pending size preview. Model SHA was unchanged, decoder 2.6, OCR off.
  No reference labels entered inference. This validates backend wiring, not new
  perception/generalization quality.
- JS syntax, launcher shell syntax and literal UI element references were checked.
- The model, global default lock, source images, accepted Data files and unrelated
  Unreal/C++ edits were not changed. QA confirmation snapshots are in new Saved
  test jobs, not original accepted designs.

## Browser acceptance blocker

The attempted `cua.createBrowserTab` navigation to `http://127.0.0.1:8772/` was
rejected by automatic approval review because the service hit its usage limit.
The browser action was not executed. No alternate browser, CDP, screenshot tool,
headless browser or indirect browser path was used to bypass this rejection.

As a result, real upload interactions, drag/resize pointer behavior, Compare,
responsive layout, keyboard focus, modal usability and before/after screenshots
still require browser verification when approval service access is available.
**The guide's full Step 4 finish condition is not yet established.** No screenshot
mock is substituted for a running product test.

## Artifacts

`Saved/ShapeFirst/workspace/v1/verification/`:
- verification.json — completed checks, source hashes and explicit browser blocker.
- python-tests.log / http-tests.log / javascript-state-tests.log.
- source_snapshot/ — exact implemented source and launcher.

`Saved/ShapeFirst/workspace/v1/backend-acceptance/`:
- backend-acceptance.json — real persisted backend flow and real DINO upload.
- jobs/ — isolated sample and real-upload test artifacts.

The previous technical review surface was replaced in source. Before/after browser
screenshots are absent because of the approval blocker. Step 5 has not been marked
complete and Unreal export remains unavailable.
