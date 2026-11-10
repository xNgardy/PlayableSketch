# Runtime and workspace usability update

4 November 2026, evening. The Mac runtime package has been rebuilt with the current
source. The existing drawing, approved plan, model weights and accepted canonical
JSON were preserved.

## New workflow

1. Open the workspace at `http://127.0.0.1:8772/` and reload the browser page.
2. Review/edit the drawing. Default names are Room 1, Room 2, etc.; corridors have
   their own independent sequence. Select an item to give it any custom name.
3. Choose **Review plan**. Select **Geometry only** or **Playable level** here,
   before confirmation. Playable level reveals required, distinct Start/Goal rooms.
   Settings now contains only global construction sizes.
4. Choose **Confirm plan**, then **Export for Unreal**. Changed choices disable
   export until confirmed. Choice controls are disabled while confirmation runs.
5. Close the old PlayableSketch window and reopen `Start PlayableSketch.command`.
6. Choose **Open latest plan**. The app obtains the current confirmed export from
   the local service; job/revision copying is not needed. Technical fields are
   available under Advanced options.
7. Click the level to move with **WASD or arrow keys**, or choose **Follow route to
   Goal**. Save level and Load saved level preserve the existing SaveGame behavior.

Geometry-only files remain available for the canonical Unreal Editor importer.
The runtime explains that a playable export is needed instead of making a geometry
bundle appear playable. Opening a newer plan never bypasses the existing strict
validation, collision, clearance and readiness gates.

## Drawing direction and controls

Canonical layouts use x-right/y-up; Unreal's top-down camera uses a different
coordinate basis. The runtime now adapts the parsed representation to the display
basis, including reflected region winding and wall/opening offsets. The accepted
JSON is unchanged. The opt-in runtime conversion does not alter the Editor's
canonical coordinate convention, lengths or connectivity.

A fixed overhead camera fits the complete level into the available view alongside
the smaller sidebar. The camera no longer follows the player around or presents a
portrait drawing sideways. Keyboard direction is resolved from camera right/up
vectors into the level's local movement coordinates. Existing collision sweeps and
navigation guards still determine whether movement is allowed.

## Appearance and names

The web header has a light/night-mode toggle, persisted in local browser storage.
Both the plan canvas and controls use the selected appearance; uploaded ink is not
recolored. The native runtime also has light/night controls, saved separately in
its local appearance configuration. Cosmetic appearance never changes the plan.

New proposals count rooms and corridors separately. Existing generated labels are
presented sequentially, while custom names are preserved. Re-confirming/exporting
uses these labels consistently in the authoring and canonical documents. Previously
exported immutable bundles are not rewritten automatically.

## Verification

Evidence: `Saved/RuntimeUX/v1/verification.json` and individual reports/logs.

- The rebuilt Mac Development package completed successfully; the temporary Engine
  SDK admission configuration was restored. All 87 packaged source hashes match.
- 133 non-HTTP Python tests plus four HTTP tests passed: **137 Python tests** total.
- **20 JavaScript state checks** passed, including independent room numbering,
  custom names, review-time mode selection, required Start/Goal validation, settings
  saved before confirmation, and appearance toggling.
- Real browser checks covered Room 1/Corridor 1/Room 2, playable selection and roles
  directly in review, confirmation/export, readable light/night canvases and stored
  appearance after reload. Screenshots are saved alongside the verification record.
- Cooked engine E2E used real DINO inference and explicit test-only corrections.
  Engine camera view/projection matrices verified source-right and source-down
  directions; four actual swept Pawn moves followed screen directions. The Pawn
  reached Goal; invalid-import retention, unchanged canonical content, cosmetic
  route invariance and save/load passed.
- The user's existing approved IMG_1789 plan was imported unchanged with a separate
  test save prefix. It also passed direction checks, four-direction movement,
  actual Goal traversal and canonical JSON equality with the selected export.
- A fresh cooked process reloaded the controlled save and passed the same checks.

Initial failures were retained: the first coordinate reflection reversed region
winding, which strict geometry validation correctly rejected. Region vertex/wall
ordering was corrected. A subsequent headless test could not use a window viewport;
its camera check now uses Unreal's camera projection matrix, with the method
explicitly identified in the result. Neither failed attempt is counted as success.

## Remaining verification limits

Native window automation timed out, so the rebuilt Slate UI's actual button clicks
and rendered light/night appearance were not certified through computer use. The
widget code compiled and the underlying motor path was exercised by cooked tests.

The current package's final offline rerun and stopping the isolated QA server were
not executed: automatic approval review rejected the command because its usage
limit was reached, with a retry time of 21:45 local time. The prior Step 5 offline
result is historical and is not presented as a rerun of this package. The isolated
QA service on port 8775 was left running; the normal updated workspace is on 8772.

No new model accuracy, unseen-writer result or full accessibility certification is
claimed. Existing historical screenshots/reports describe the interface at the
moment they were recorded.
