# Shape-first Step 5 — local Unreal delivery

4 November 2026. Core local delivery implemented and verified. This is the new
five-step shape-first guide, separate from the historical explicit-layout Step 05.

## Run

1. Run `Start Sketch Workspace.command`; open the printed localhost address.
2. Upload a drawing, review/edit shapes and connections, then adjust suggested
   sizes. Suggestions and overrides are design choices, not physical ink measurements.
3. For play, select Review plan → Playable level, Start room and a different Goal room.
   Geometry only remains available without promising player traversal.
4. Review plan → Confirm plan → Export for Unreal. The ZIP contains strict
   `validated-layout.json`, `authoring.json`, `manifest.json` and import instructions.
5. Run `Start PlayableSketch.command`. The current playable export is selected
   automatically; choose Open latest plan, then Follow route or use WASD / arrow keys. The browser downloads a file and the
   local launcher selects a backend snapshot; it does not write into Unreal itself.

The existing local Python environment, model files and Mac runtime package are
required. No downloads, installs, cloud hosting or model training are introduced.
For errors, inspect `Saved/ShapeFirst/delivery/sidecar-launch.log`. If the port is
occupied, stop the old service or choose PLAYABLESKETCH_PORT consistently for both
launchers. A stopped/failed analysis retains its source and supports manual authoring.
A job with manual edits refuses retry; start another job to retain that history.
After edits or a changed image/sizing/settings snapshot, review and confirm again.
A narrow route can be exported as geometry only; playable mode rejects insufficient
clearance. Final collision and actual traversal are checked by Unreal on import.

## Implemented contract

- Versioned shape-first jobs and attempt contexts record source, model configuration,
  decoder, policy and schema hashes in a deterministic analysis key. Each attempt
  has its own outputs; accepted authoring, sizing and export files are separate.
  There is no automatic cached-result reuse or training ingestion.
- Exact confirmed snapshots bind full topology, sizing result and workspace settings,
  and verify source hashes again before export/download/import. Old immutable files
  remain on disk; stale selected-revision requests reject instead of silently
  delivering a different design. Export creation uses staging and atomic pointers.
- The strict canonical validator and existing `as_validated` adapter remain the gate.
  Real authoring lineage is used; no OCR observation/evidence documents are invented.
  Manifest hashes preserve provenance separately from the canonical transport.
- POST `/shape-jobs/{id}/export` requires the exact confirmation ID. GET bundle/layout
  requires an explicit export revision. Runtime `/jobs`, status, selected layout,
  cancel/retry and `/api/bootstrap` transport is compatible with the existing package.
  The runtime alias is separate from shape-job IDs; clients need not copy IDs.
- Geometry-only and gameplay delivery are explicit settings in the confirmed snapshot.
  Gameplay applies conservative 2D inflated-wall/floor-support preflight with the
  existing capsule profile: radius 40 cm, half-height 90 cm, clearance 10 cm.
  Bundle engine geometry/navigation checks remain `not_run`: Python clearance is
  not engine certification. Unreal retains its atomic ready state, collision,
  floor support, actual Pawn and checksummed two-bank SaveGame gates.
- Both user launchers now use shape-first. The experimental DINO checkpoint is
  selected explicitly; the global model default and old measurement fixtures remain
  unchanged. No C++ change/rebuild was needed: all 87 package source hashes match.

## Verification

Evidence: `Saved/ShapeFirst/delivery/v1/acceptance-summary.json`, Python logs,
individual cooked reports, downloaded ZIPs, and browser screenshots in that folder.

- 135 unique Python tests passed: 131 non-HTTP regressions and four HTTP checks.
  This includes historical measurement/contract, shape proposals/DINO, sizing,
  workspace, exact snapshot delivery and real loopback transport tests.
- 15 in-memory JavaScript checks passed, including stale async responses and export
  without confirmation. These checks are not represented as browser tests.
- Real browser sample → Settings → Start/Goal → confirmation → Export downloaded a
  ZIP; member SHA256 values were checked. The sample is curated manual content.
- A separate real browser file chooser uploaded the generated number-free two-room
  control image. Real DINO produced two rooms/one door. Native keyboard input changed
  the first room name to Browser Start and width to 5.00 m (Custom); roles/gameplay,
  confirmation and actual ZIP download passed. This is controlled-image evidence,
  not a new accuracy benchmark. Browser automation's fill/Tab did not commit changes
  in this environment; native typing and clicking away did, and persisted values
  were checked in the downloaded artifact.
- Cooked runtime E2E: the actual executable uploaded the number-free image, real
  DINO finished, then the opt-in test driver explicitly corrected topology and
  chose a 160 cm door design override. The same downloaded canonical layout was
  imported with WITH_EDITOR=false. Actual Pawn reached Goal; rejected import
  retained the previous level; theme changes preserved layout/route; SaveGame passed.
  Corrections were test-only, with a separate save prefix, never user-data acceptance.
- A separate cooked process reloaded the saved plan and reached Goal again. With
  the test sidecar stopped, offline load retained ready geometry/Pawn and a failed
  new import left the previous ready state intact. The offline report deliberately
  has stage=failed for the new network request, with ready=true and success=true
  for the retention scenario.
- The first browser layout used the 120 cm suggested door. Python preflight passed,
  but actual Unreal grid/collision rejected readiness (geometry/topology passed;
  Pawn was not spawned). This negative engine report is preserved under
  `browser-narrow-negative`. A continuous 2D clearance pass is not a guarantee of
  discretized engine navigation. The next trial explicitly widens the door to 160 cm
  in the browser and requires new confirmation; that actual downloaded 160 cm
  bundle then passed cooked runtime import, real Pawn traversal and save/load.
  Canonical JSON matched the browser-downloaded file. This is a design edit, not an
  image measurement or a general minimum-width promise.
- Negative coverage includes narrow door/corridor, geometry-only vs gameplay,
  altered mode after confirmation, missing/stale confirmation, changed sizing/source,
  bundle corruption, repeated immutable export, service restart/selection, and ZIP
  creation failure without partial publication.

## Boundaries

This finishes core local delivery, not unseen-writer/general recognition quality.
Prior Step 2 held-out development findings and remaining passage errors are unchanged;
manual corrections are not scored as AI detections. Existing OCR/numeric accuracy
scores are not reused as shape-first success. User design edits never automatically
become image-ground-truth dimensions or training labels. Multi-floor/arbitrary polygons,
hosted accounts/payments, full responsive/accessibility certification and a distributable
Python/model installer remain outside this implementation. The package was exercised
headlessly with real engine collision/Pawn; a human interactive playthrough was not run.

Owned verification sidecars on ports 8772/8774 were stopped after QA. Reopen
the workspace with the launcher; confirmed jobs, exports and test evidence persist.


## Usability follow-up (4 November, evening)

Drawing orientation and screen-relative WASD/arrow controls, a fitted fixed overview
camera, simplified native Open latest plan, persisted light/night appearance, review-time
delivery/Start/Goal choices, and sequential editable room names were added. See
[UX verification](runtime_ux_2026_11_04.md). Earlier screenshots and Settings references
in historical experiment notes describe the previous interface.
