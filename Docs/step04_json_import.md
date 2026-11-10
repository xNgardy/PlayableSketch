# Step 04 — JSON to Unreal legacy import

The Editor actor now provides `Import Layout Json Path`, `Import Layout Json` and `Last Import Report`. Import uses a preflighted legacy adapter; it does not run automatic room placement.

## Supported input

This step supports **two rectangular rooms, one straight horizontal/vertical corridor, and a door at each entrance**. Both doors must have the same clear width because the current `Connection` stores one door width.

Shared-wall room connections, single-room geometry, open corridor entrances, unequal door widths and arbitrary corridor paths require the Step 05 explicit builder. They are rejected rather than approximated. Consequently, the ten photographed fixtures are preserved for the explicit pipeline; none is silently changed to fit the legacy builder.

The supplied [synthetic reference](/Users/pelinsukaleli/PlayableSketch/Data/import_examples/legacy_two_rooms.svg) is an additional manually specified example, not a reinterpretation of a user photograph.

## Try the ready example

1. Build `PlayableSketchEditor` and open the project.
2. Create a new Data Asset of class `PlayableSketchGraphAsset` and assign it to a `PlayableSketchLevelActor`. Use a new asset for the example, since a successful import replaces the assigned asset's graph and saved placements.
3. Keep actor scale `(1,1,1)`.
4. In **PlayableSketch → Import**, set `Import Layout Json Path` to:

```text
Data/import_examples/legacy_two_rooms.legacy-import.json
```

5. Click **Import Layout Json**. Project-relative and absolute file paths are accepted.
6. Read **Last Import Report**, **Preview Status**, and **Navigation Report** separately. A successful geometry import does not imply a reachable navigation result.
7. Save both the Data Asset and the map to persist the graph, settings and actor assignment. Rebuild Geometry and BeginPlay use the imported Locked rooms and manual doors.

Expected example values:

| Quantity | Canonical centerline layout | Legacy clear-inside adapter |
| --- | --- | --- |
| Left room width | 455 cm | **435 cm**, retained without grid rounding |
| Left room depth | 600 cm | 580 cm |
| Right room width/depth | 600 × 600 cm | 580 × 580 cm |
| Left room minimum | (0,0) | (10,10) |
| Corridor width | 220 cm | 200 cm |
| Corridor length | 600 cm | 620 cm including wall thresholds |
| Door clear width | 150 cm at both entrances | 150 cm |
| Door center from bottom corner | 300 cm | 290 cm from clear-inside minimum |

The room wall solid is built outward from the clear boundary, so its centerline returns to the specified canonical wall location. The corridor floor extends through the room-wall thresholds to connect the room clear interiors. These extensions are deliberate basis conversion, not a new corridor route.

## Export another supported v1 layout

Use the Python environment from Step 03:

```sh
SketchPipeline/.venv/bin/python -m SketchPipeline.import_bridge.export_legacy \
  Data/import_examples/legacy_two_rooms.validated.json \
  --observations Data/import_examples/legacy_two_rooms.observations.json \
  --output Saved/SketchImports/example.legacy-import.json
```

On Windows replace the Python executable with `SketchPipeline/.venv/Scripts/python.exe`.

The exporter requires an accepted v1 metric layout, matching observations and explicit Start/Goal rooms. It checks the Step 03 contract and supported topology, converts centerline geometry to clear-inside bounds, and writes `playablesketch-legacy-import/1.0`. Existing output files are not overwritten.

The C++ importer consumes this narrow bridge format, **not** the complete canonical v1 schema. It validates its fields, version, cm units, clear-inside basis, references, finite numbers and integer dimensions, then runs the existing graph/door/routing/wall/geometry validation. The source layout hash is provenance, not an authentication signature or a C++ revalidation of the original canonical document.

The current legacy model stores dimensions as `int32`. Fractional clear dimensions are rejected without truncation, rounding or grid snapping. Positions and door offsets remain floating-point values.

## Publication and persistence

- Parsing and geometry preflight do not mutate the actor or assigned asset.
- The candidate uses `Locked` rooms, manual door sides and offsets.
- The routed corridor must match the expected converted straight footprint within 0.001 cm; otherwise import is rejected.
- The component registry publishes the candidate before the original asset is written.
- Normal rejected inputs retain the prior asset and preview. If component publication itself fails, the prior components remain and the preview is explicitly stale.
- Editor transaction records actor settings and asset changes. Save remains an explicit Editor action.
- Source document ID, revision and hash are stored on the graph asset.
- Room/connection GUIDs derive deterministically from document ID, entity kind and external ID, excluding revision. Reimport keeps logical identity and does not accumulate components.
- The import action is Editor-only. This step does not add packaged runtime upload or persistence.

The existing rebuild lifecycle and procedural generation behavior remain in use. Import does not introduce the shared-wall builder or change existing navigation algorithms.

## Verification

Python tests cover basis conversion, the off-grid 435 cm dimension, unchanged input documents, unsupported photo layouts, missing/invalid measurements and missing roles.

Unreal automation test: `PlayableSketch.Import.LegacyJson`. It covers strict parsing and duplicate-key rejection, stable IDs, geometry preflight, exact corridor footprint, actor publication, reimport component count, rejected-import preservation and full rebuild without grid rounding.

```sh
SketchPipeline/.venv/bin/python -m unittest discover -s SketchPipeline/tests -v
```

For macOS builds, if the active developer path points to Command Line Tools, select the installed Xcode only for the build process:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  '/Users/Shared/Epic Games/UE_5.7/Engine/Build/BatchFiles/Mac/Build.sh' \
  PlayableSketchEditor Mac Development '/Users/pelinsukaleli/PlayableSketch/PlayableSketch.uproject' \
  -WaitMutex -NoHotReloadFromIDE -NoUBA
```

This does not change the system-wide `xcode-select` setting. Interactive viewport inspection, an actual save/reopen session and Pawn traversal are separate from the headless checks.

### Recorded verification — 2026-10-14

- macOS Development Editor build succeeded with installed Unreal Engine 5.7.2 and Xcode's Mac SDK 26.5.
- All 43 Python contract/export tests passed.
- All six `PlayableSketch.*` Unreal automation tests completed successfully, including the new horizontal/vertical import checks and existing authoring, Local rebuild, navigation and experiment tests.
- The existing authoring rejection test recorded two expected overlapping-room warnings; the automation report contains zero failed or skipped tests.
- The original 28 v1 photo-reference documents still match their preserved migration sources.

[Unreal automation report](/Users/pelinsukaleli/PlayableSketch/Saved/Step04/final-report/index.json) and [engine test log](/Users/pelinsukaleli/PlayableSketch/Saved/Step04/final-tests.log) are local generated verification artifacts.
