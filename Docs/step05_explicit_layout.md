# Step 05 — Canonical explicit layout

The actor can now import accepted `playablesketch-layout/1.0` JSON directly. This path builds the supplied rectangular rooms, corridors, unique walls and openings without room placement, automatic door selection or corridor routing.

## Quick check in Unreal

1. Restart Unreal Editor after building so the new asset class and action are available.
2. Create a Data Asset of class **PlayableSketchImportedLayoutAsset**, for example `DA_Step05_Test`.
3. Add/select a `PlayableSketchLevelActor`. Assign the asset to **Imported Layout Asset**. Keep Scale `(1,1,1)`; Location/Rotation `(0,0,0)` make the fixture easier to inspect. A Graph Asset is not required for this path.
4. Set **Import Layout Json Path** to:

```text
/Users/pelinsukaleli/PlayableSketch/Data/ground_truth/v1/Data_3.validated.json
```

5. Click **Import Canonical Layout Json**. The existing **Import Layout Json** action still consumes the Step 04 bridge format.
6. Check **Last Import Report**: `Imported canonical ... 2 rooms, 0 corridors, 7 unique walls, 1 openings`. **Layout Source** becomes **Imported Explicit Layout** automatically.
7. Inspect two adjacent rooms, one shared wall and its door. Centerline room dimensions are 600 × 400 and 500 × 400 cm; wall thickness is 20 cm; the door clear width is 120 cm, height 220 cm and paper lower-edge offset 200 cm and derived center offset 260 cm along the shared wall. There is no added corridor.
8. Import the same file again, then use **Rebuild Local Geometry** and **Rebuild Geometry (Full)**. Geometry must not accumulate or move. **Test Rebuild Equivalence** also supports this source.
9. Save the Data Asset and the map. Reopen and rebuild; the accepted JSON and explicit source remain the basis for generation.

Next, import [Data_8.validated.json](/Users/pelinsukaleli/PlayableSketch/Data/ground_truth/v1/Data_8.validated.json). It contains two rooms and a corridor, one door and one open entrance. The left door center is y=360 cm: its paper room-corner-to-edge offset is 300 cm and its width is 120 cm, while its noded supporting wall-local center offset is **100 cm**.

Try height changes and thickness changes, then rebuild (or use Auto Rebuild). A confirmed paper edge offset can conflict with changing a derived corridor entrance width while keeping region centerlines fixed; such a settings change must be rejected pending metric reconstruction rather than rewriting that label. Centerlines stay fixed. A 200 cm centerline corridor's derived clear entrance changes from 180 to 170 cm. Confirmed door widths stay fixed. Valid changes produce a new settings revision in the asset; invalid settings retain the previous accepted source and visible geometry, marking the preview stale. Save the asset/map after accepted changes.

## Supported input and rejection

- Single rectangular/square room, including `geometry_only` with null Start/Goal.
- Rectangular rooms sharing a wall and connecting directly through a door.
- Explicit horizontal/vertical rectangular corridors, with doors or full-height open entrances.
- Noded T junctions and extra collinear region-boundary vertices.
- Multiple nonoverlapping openings on one wall; fractional cm coordinates/dimensions are preserved.
- Global configurable wall thickness/height, door height and floor thickness.

[Data_1–8](/Users/pelinsukaleli/PlayableSketch/Data/ground_truth/v1/README.md) are supported manual metric references. [Data_9.draft.json](/Users/pelinsukaleli/PlayableSketch/Data/ground_truth/v1/Data_9.draft.json) and [Data_10.draft.json](/Users/pelinsukaleli/PlayableSketch/Data/ground_truth/v1/Data_10.draft.json) are rejected because they are conflicting/incomplete drafts. Original photographs and reference JSON files are not rewritten by import.

The C++ parser rejects wrong versions/units/basis, unknown/missing fields, duplicate JSON keys/IDs, invalid types or non-finite numbers, unresolved states, broken references, invalid ownership, overlapping regions/walls/openings, unnoded intersections, reversed walls, inconsistent dimensions and invalid passage/role relations. Gameplay mode also checks logical passage connectivity.

Engine input bounds are 2 MB, 32 JSON nesting levels, 2048 total entities and absolute input coordinates/numeric settings up to 10,000,000 cm. Geometry settings and clear opening sizes must exceed 0.001 cm. Metric comparisons use 0.001 cm tolerance. These are engine import limits in addition to the v1 contract.

External observation IDs and the source image hash are retained as provenance. This self-contained engine import does not load the image/observations or certify OCR correctness. The Python contract/review gate remains responsible for external evidence validation.

## Architecture

```text
Canonical accepted JSON
  → Parse + metric/reference checks
  → Explicit layout model
  → Floors + unique-wall solid intervals + lintels
  → Check every opening against all wall/junction solids
  → Component registry staging/publication
  → Persist accepted JSON/revision and actor source/settings
```

- [PlayableSketchExplicitLayout.h](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Public/ExplicitLayout/PlayableSketchExplicitLayout.h): plain C++ model and pure `Parse`, `Build`, `ResolveSettings` operations. Failure leaves output arguments unchanged.
- [PlayableSketchExplicitLayout.cpp](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Private/ExplicitLayout/PlayableSketchExplicitLayout.cpp): strict canonical parser, metric validation, stable IDs, geometry and settings revisions.
- [PlayableSketchImportedLayoutAsset.h](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Public/ExplicitLayout/PlayableSketchImportedLayoutAsset.h): persistent canonical JSON, document/revision IDs, image hash and source enum.
- [PlayableSketchExplicitLevelActor.cpp](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Private/ExplicitLayout/PlayableSketchExplicitLevelActor.cpp): Editor import, materials, staged publication, validation and rebuild lifecycle.

The legacy importer and procedural graph remain separate source paths. Existing component registry gains canonical wall/corridor ownership tags and dirty-wall tracking. Explicit keys identify document/entity and semantic piece roles rather than array ordinals; changing array order or revision does not change logical identity. Canonical IDs and schema literals are compared case-sensitively; opaque IDs are hashed before use in Unreal FName keys.

## Geometry logic

Each room/corridor has one rectangular floor with its top at z=0 and thickness below ground. Floors cover centerline regions, including the opening thresholds; actual clear space is bounded by wall solids.

Each canonical wall is built once. For opening offset `c` and clear width `w`, its interval is `[c-w/2,c+w/2]`. The remaining intervals become full-height wall boxes. A door adds a lintel above its clear height; an `open_passage` has no lintel.

Wall ends extend by half the wall thickness to close orthogonal corner/T joins. These boxes may overlap at joins, representing their solid union. The builder checks the claimed clear opening volume against every solid, including neighboring wall caps. An opening obstructed by a junction is rejected rather than silently narrowed.

Changing settings creates a new canonical revision, recomputes resolved wall/opening heights and derived entrance widths, then revalidates before publication. Parent revision and source provenance remain recorded; configured changes are identified as `UnrealEditor-configured-settings`. Confirmed centerline dimensions and door widths are not silently changed. Reattaching a saved asset to a fresh actor restores its settings. Actors sharing an asset adopt externally updated snapshots instead of overwriting them with stale settings.

Rejected import does not alter the accepted asset, source mode or components. Invalid rebuild retains previous geometry as stale. A repeated accepted revision reuses components; Local and Full builds produce equivalent geometry/collision. BeginPlay rebuilds the explicit source without invoking the procedural generators or modifying the source asset at runtime.

## Verification and remaining boundary

Automation: `PlayableSketch.Import.CanonicalExplicit` in [PlayableSketchExplicitImportTests.cpp](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Private/Validation/Tests/PlayableSketchExplicitImportTests.cpp), plus `PlayableSketch.Import.ExplicitPersistence` in [PlayableSketchExplicitPersistenceTests.cpp](/Users/pelinsukaleli/PlayableSketch/Source/PlayableSketch/Private/Validation/Tests/PlayableSketchExplicitPersistenceTests.cpp). The disk persistence test runs with `-unattended`; it does not replace an interactive user's map.

Coverage includes all eight accepted references, negative/tampered inputs, stable identity under array reorder/revision changes, Data_8 offset rebasing, multiple openings, junction obstruction, actual door/jamb/lintel collision queries, settings revisions, one-wall opening updates, rejected-import preservation, Local/Full equivalence, source-property serialization and reconstruction on fresh actors, shared-asset synchronization, case-sensitive IDs, and BeginPlay.

Real Data Asset/map files were saved, the source package unloaded, and the map reopened in a headless Editor session under `Saved/Step05/Persistence/`. The test verifies source mode, asset reference, actor transform, settings and reconstructed geometry/collision. Interactive viewport inspection and actual Pawn traversal remain separate. Explicit agent/grid/NavMesh analysis is reserved for Step 12; the actor reports it as `Not run`. Existing procedural navigation behavior is preserved. The canonical source contract's `engine_geometry`/`navigation` fields remain `not_run`; generated-scene results are separate reports.

### Local build environment

On 15 October 2026 this machine had Xcode 27.0 / Mac SDK 27.0. UE 5.7's installed Apple SDK configuration admits Xcode only through 26.9.0, so an ordinary build stopped before compilation. Verification temporarily widened that range for the build process and restored the original engine configuration afterward. No permanent SDK/platform setting or project target upgrade was made. This verifies the local build/tests, not official Xcode 27 compatibility.

The local verification wrapper is [Saved/Step05/build_with_current_xcode.py](/Users/pelinsukaleli/PlayableSketch/Saved/Step05/build_with_current_xcode.py); it is a generated verification artifact. For ordinary supported builds use a compatible Xcode installation. Build output: [build.log](/Users/pelinsukaleli/PlayableSketch/Saved/Step05/build.log).

### Recorded verification — 2026-10-15

- Mac Development Editor build succeeded with the temporary environment override described above; engine SDK configuration was restored byte-for-byte.
- All **8** `PlayableSketch.*` Unreal automation tests passed, including canonical import, real disk persistence and the existing legacy/procedural checks. No failed or skipped tests. The existing authoring rejection case retains its expected overlap warnings.
- All **43** Python contract/export tests passed using the existing pinned requirements in an isolated `Saved/Step05/python/` environment.
- All **28** v1 reference documents still match their preserved migration sources.

[Final automation report](/Users/pelinsukaleli/PlayableSketch/Saved/Step05/final-report/index.json) and [test log](/Users/pelinsukaleli/PlayableSketch/Saved/Step05/final-tests.log).

### Opening-offset correction — 2026-10-16

Paper offsets now measure corner-to-near-opening-edge. Import the corrected references again after restarting the rebuilt Editor; an already saved imported asset retains its previous explicit snapshot until reimported. Old explicitly center-based canonical documents remain supported.

Data_5 is now a known physical negative case: interval [450,600] touches the outer corner, and wall-cap collision blocks its claimed clear width. Its metric reference remains valid, but the builder and actor reject publication. Confirmed edge offsets can also make a thickness change invalid when a derived corridor entrance width changes; height-only changes remain supported. Tests verify rejection instead of silently rewriting labels.

The Mac Development Editor build succeeded with the existing temporary Xcode verification wrapper; the original engine SDK configuration was restored byte-for-byte. All three `PlayableSketch.Import.*` automation tests passed, covering canonical import, physical rejection, source/settings persistence and the legacy importer. Logs/report: `Saved/OffsetMigration/20261016T183703Z/`. Earlier dated results above describe the pre-correction center-offset fixtures.
