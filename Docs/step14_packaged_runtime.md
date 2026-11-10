# Step 14 — Local Mac packaged runtime

Implementation date: 2026-10-21. Initial target: this Mac, arm64, Unreal Engine 5.7 Development build. The Python image pipeline remains an external loopback sidecar. Runtime play uses the Step 12 flat-floor capsule contract. Model accuracy and general-release restrictions from Step 13 remain unchanged.

Final packaged verification is recorded separately in `Saved/Step14/verification.json`.

## Start and use

Double-click `Start PlayableSketch.command`, or run:

```bash
python3 Scripts/start_runtime.py
```

The launcher finds `Saved/Step14/package/Mac/PlayableSketchRuntime.app`, checks the local service, starts the existing project Python sidecar if required, and opens the app in a 1440 × 900 window. The app can also be opened directly when the sidecar is already running.

1. Keep the service at `http://127.0.0.1:8768` unless you deliberately start a different loopback port.
2. **Open browser upload / review** provides the existing web file picker and correction interface. For a file already readable inside the Mac app sandbox, alternatively enter its PNG/JPEG path in the app and press **Upload image from path**. Uploads are limited to 20 MB; inference runs asynchronously in the sidecar.
3. Review topology and measurements in the browser. Select **gameplay**, distinct Start/Goal rooms, and explicitly accept a metric revision. No runtime client action automatically approves a user drawing.
4. If upload began in the app, its Job ID is filled automatically. If upload began in the browser, paste that Job ID into the app. **Refresh job / accepted revision** displays processing/review status and supplies the current accepted metric revision when none is selected.
5. **Import selected revision and prepare level** fetches exactly that accepted revision. Geometry, collision and reference-grid readiness must pass before the active level is replaced and a playable Pawn is spawned.
6. Buttons also support **Tab** focus and **Enter** activation. **Play route to Goal / WASD** follows the route with an actual runtime Pawn. Click the view/use WASD to explore; click the panel to edit fields again. This is top-down flat-floor movement, not CharacterMovement gravity/stairs or NavMesh AI.
7. **Save runtime / Load runtime** preserve the accepted source, document/revision/settings, job/service metadata and committed theme seed. Loading does not require the sidecar; it rebuilds and validates the stored canonical snapshot.

A geometry-only revision remains a valid browser/geometry workflow, but this runtime's **play** action explicitly requires gameplay Start/Goal. It does not invent roles or certify geometry-only input as a Start-to-Goal playtest.

**Mac sandbox:** use the browser file picker for normal project/Desktop/Downloads images. Typing an arbitrary filesystem path does not grant the native app file access. App Sandbox remains enabled; no extra filesystem entitlement or security bypass is required. Runtime SaveGame files live under `~/Library/Containers/com.YourCompany.PlayableSketchRuntime/Data/Library/Application Support/Epic/PlayableSketch/Saved/`.

The local package is a Development prototype built on this machine, not a notarized redistribution installer. It does not include Python/model weights inside Unreal; the launcher relies on this repository and its existing `Saved/Step07/python` sidecar environment. Starting the external service does not require Unreal Editor or its Python plugin.

## Runtime boundary

- `FPlayableSketchExplicitLayoutBuilder` remains the canonical parser/builder used by both Editor and runtime. No alternate coordinate or opening-routing implementation was introduced.
- `ImportRuntimeCanonicalJsonText` is game-world-only and publishes a transient source object. Existing Editor import actions remain Editor authoring operations.
- `APlayableSketchRuntimeController` owns HTTP orchestration, readiness, the active runtime level/Pawn and SaveGame persistence. It neither modifies a user's GraphAsset nor writes Editor Data Assets/maps.
- `APlayableSketchRuntimeGameMode` and the Slate panel provide the runtime client. The browser is the explicit review surface; there is no embedded Editor Python or WebBrowser-plugin dependency.
- The runtime target has no `UnrealEd` link dependency. Editor-only code/dependencies remain under `WITH_EDITOR` / `Target.bBuildEditor`. Cooked acceptance additionally records `with_editor=false` from the actual executable.

## Atomic readiness and failures

A candidate actor is built at a staging transform away from the active level. Its real generated collision and actual temporary capsule-Pawn traversal are verified. The previous level and Pawn remain intact during this phase.

Before publication, the candidate is moved to the destination, previous level/Pawn collision is temporarily disabled, and destination collision-grid readiness is rechecked. Failure restores the previous level. A playable Pawn is spawned only after successful publication checks. A rejected canonical JSON, narrow route, invalid role selection, missing cooked dependency, cancelled request, service error or stale HTTP response cannot publish a partial level.

Requests capture a sequence plus service/job/selected-revision identity. Local cancel, changed selection, runtime load and controller teardown invalidate old callbacks. **Cancel request** stops local publication; **Cancel job** stops remote work when that job's state allows it. **Retry job** starts a new traceable job. Status/error text remains visible while a prior ready level can remain playable.

## Cooking and packaging isolation

```bash
python3 Scripts/package_runtime.py
```

The packaging script creates an owned project snapshot under `Saved/Step14/package-project`, verifies its C++ source hashes, and builds the dedicated `PlayableSketchRuntime` Game target. Only this snapshot switches the default map to Engine Entry and the runtime GameMode. The original Editor startup map, original Content assets and procedural configuration are preserved.

An idle CameraActor supplies the initial view before accepted geometry exists. The small local prototype Slate panel repaints its widget cache each frame on Mac Metal (except during mouse capture); buttons support keyboard focus. This deliberately favors predictable drawing over UI-cache performance. No playable Pawn is spawned until ready-state checks pass.

The snapshot uses a simple Metal SM5 rendering profile suitable for the generated boxes. Cube and BasicShapeMaterial have hard runtime references, and the cooker explicitly includes BasicShapes. The app ships its cooked geometry dependencies; it never depends on a user reference image/annotation file being available to generate metric walls.

`package-source-hashes.json`, `package-command.json` and `package.log` record what was built. The existing local SDK-admission workaround temporarily permits the installed Xcode 27 SDK during build/cook and restores the original engine Apple SDK configuration afterwards. No permanent engine SDK policy change is required.

## Runtime persistence

Persistence uses `USaveGame` and `UGameplayStatics`, not Editor save APIs. Two banks (`PlayableSketchRuntime_A/B`) retain a prior intact snapshot. Each snapshot has a generation and a portable **BLAKE3** content checksum covering canonical JSON plus metadata. Fresh sessions continue above both intact banks even when the user saves before pressing Load. A damaged newest bank falls back to an intact older bank. Loaded source still passes canonical, physical and readiness checks before publication.

The checksum detects accidental alteration; it is not a signature or proof of human acceptance. Acceptance remains a named browser-review action plus the strict canonical import contract. Current UI selection fields do not rewrite the provenance of an already published level when saving it.

## Optional procedural layer

The initial optional layer is cosmetic seeded material selection and Start/Goal floor colors. It introduces no props, collision obstacles, room repositioning or changed openings. The exact canonical JSON and navigation route are checked across theme seeds. Confirmed walls/dimensions/openings remain locked. PCG, prop placement and broader gameplay systems are not prerequisites or silently added scope.

## Verification and artifacts

- `PlayableSketch.Runtime.AtomicReadySaveAndPlay` covers game-world import, deferred Pawn publication, actual Pawn tick movement to Goal, invalid import retention, geometry-only play rejection, locked geometry across seeds, two-bank fallback, a fresh session saving above existing generations and agent-clearance behavior.
- A generated orthogonal test image is uploaded by the runtime HTTP client. Image-only inference finishes before the test driver enters explicit topology/measurement corrections and named acceptance. This is controlled automation, not approval of a real user drawing or a claim of automatic reconstruction accuracy.
- Editor `-game` evidence is stored in `editor-e2e/` and labeled `with_editor=true`; it does not substitute for a cooked test.
- Cooked executable evidence belongs in `verified-e2e/`, with separate fresh-process restore in `verified-restart/` and service-unavailable retention in `verified-offline/`. Only actual `with_editor=false` results count as packaged acceptance.
- Runtime test save prefixes are separate from the normal user's SaveGame banks. No original drawings, accepted references or ML weights are modified.

Supporting scripts: `Scripts/runtime_fixture.py` creates only the controlled test image/review; `Scripts/test_runtime.py` drives the explicit smoke harness. The default runtime never executes that automation or auto-accepts a drawing.

### Recorded acceptance (2026-10-21)

All 14 Unreal automation tests passed. `verified-e2e/runtime-report.json` records successful controlled upload → image-only inference → explicit corrections/acceptance → import → actual Pawn Goal, invalid-import retention, locked geometry across cosmetic seeds and save/reload. `verified-restart/runtime-report.json` records a fresh executable restoring the same canonical snapshot and reaching Goal. `verified-offline/runtime-report.json` records failed service access with the ready level/Pawn retained. All three executable reports contain `with_editor=false` and `success=true`. These test drawings are controlled fixtures, not held-out perception accuracy evidence.

To respect the sandbox, packaged test images/reports were written under the app container’s `Data/Documents/Step14/` directory, then copied into the above project evidence folders. Normal user SaveGame slots were not used.

Test driver example (use the project sidecar environment, which includes NumPy/Pillow):

```bash
Saved/Step07/python/bin/python -m Scripts.test_runtime --executable /absolute/path/to/PlayableSketchRuntime.app/Contents/MacOS/PlayableSketchRuntime --output /absolute/new/path/inside/app/container --prefix Step14_Control
```

### Native UI check

The final rendered app was inspected before import, after editing fields, after accepted import, and after an actual Pawn reached Goal. Import and Play were activated through Tab/Enter, and `Saved/Step14/runtime-ui.png` records the visible Goal result. Native pointer injection did not reliably activate Slate buttons on this host; automated mouse activation is not certified by this check and remains a manual QA item. The verified keyboard path is available in the app. No normal user SaveGame slot was written during this UI check.
