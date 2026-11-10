# Step 12 — Explicit collision, navigation and Pawn verification

Implemented 2026-10-21 for the v1 horizontal-floor pipeline. The canonical accepted layout remains the metric source; engine results are separate artifacts and never rewrite its `engine_geometry` or `navigation` acceptance fields.

## User workflow

1. In metric review select distinct Start/Goal rooms and accept a `gameplay` revision. A `geometry_only` revision intentionally has no room-traversal certification.
2. Import the accepted canonical layout into the Unreal actor and rebuild its current geometry.
3. Under **PlayableSketch → Navigation**, set `PawnRadiusCm`, `PawnHeightCm`, `ClearanceCm`, `ExplicitNavigationCellSizeCm` (default 25), `NavigationGridOffsetCm`, and `NavigationMaxCells`.
4. **Analyze Navigation** performs topology and physical grid analysis. `NavigationReport` lists separate results. This alone leaves Pawn `not_run`.
5. **Verify Explicit Pawn Traversal** analyzes the current scene, spawns an actual capsule Pawn and moves it through the route using swept movement. The temporary Pawn is destroyed afterwards.
6. **Export Navigation Report** repeats current analysis/Pawn verification and writes `Saved/Navigation/ExplicitNavigationReport.json`; `NavigationExportPath` gives the location. Failed/incomplete/not-applicable reports are exported too. There is no GraphAsset dependency for explicit imports.

The original `GridStepCm` remains a legacy generation setting. Explicit navigation has its own resolution, since a 50 cm grid can miss the allowable agent-center interval of a 120 cm door. Grid alignment is observable and configurable, never a reason to alter the drawing or silently move an opening.

## Physical contract

- Units cm. Agent defaults: radius 40, half-height 90 (full height 180), clearance 10, step height **0**. The test capsule expands radius by clearance and raises its top by clearance; floor lift is 0.5 cm to avoid touching the coplanar floor.
- The selected v1 movement model is **flat-floor, kinematic swept capsule Pawn**: an actual `APawn`, `UCapsuleComponent`, `UFloatingPawnMovement`, `DispatchBeginPlay`, and repeated `SafeMoveUpdatedComponent` calls of at most 5 cm. It does not certify CharacterMovement walking/gravity, stairs, jumping, a possessed player, or an AI controller. Those require a matching movement adapter and additional tests when selected by the product.
- Collision channel: `ECC_Pawn`; generated walls/lintels/floors block Pawn. World queries include external blocking props. Pawn queries ignore only the temporary Pawn itself.
- Floors are the currently published, query-enabled generated floor boxes at local z=0. Exact rectangle-union subtraction checks a conservative square support footprint and the swept support rectangle, with an engine downward trace as well. Missing or disabled floor collision cannot be bridged by the graph or grid. The square support policy can conservatively reject a circular-footprint corner route.
- Topology uses explicit opening/passage region relations. Grid uses actual engine capsule overlap/sweep queries against the published scene, not centerline room membership. Adjacent grid samples require a swept collision/support check; no diagonal corner cutting.
- `corridor_clear_widths_cm` is the nominal minimum rectangular span minus wall thickness. For the 200 cm corridor fixtures, 20 cm walls give **180 cm**, and 40 cm walls give **160 cm**. Local junction clearance and route feasibility are decided by collision queries, not this diagnostic scalar.
- All coordinates are transformed through the owning actor. Translation and yaw are supported. Tilt and nonunit scale are refused. Grid work is bounded to 250,000 cells and 2,000,000 work units (collision probes plus floor-union operations); Pawn movement is bounded to 100,000 increments. Budget exhaustion means analysis incomplete, never proven unreachable.
- Recast/NavMesh is deliberately `not_applicable`: this v1 adapter uses collision-grid routes and generated components already opt out of Recast. No NavMesh query or AI navigation certification is claimed.

## Reports and interpretation

`explicit-navigation/v1` records document/revision, agent contract, transform, origin/resolution/dimensions, path in local cm, work counters, timing, issues and independent `topology`, `geometry`, `grid`, `navmesh`, `pawn` statuses. `analysis_completed` and `reachable` are separate. `reachable` refers to the reference grid; a replayed known route can still have Pawn `passed` when a coarse grid fails.

- `passed`: that specific check succeeded.
- `failed`: that check ran and did not succeed.
- `not_run`: no successful execution of that check yet.
- `not_applicable`: not selected by this contract (NavMesh), or room traversal on geometry-only input.

A completed unsuccessful grid analysis explicitly reports collision/floor/**discretization** possibilities; it does not prove continuous-space unreachability. Issues retain `narrow_opening:<id>`, `low_lintel:<id>` and missing floor support. Movement reports identify blocking collision components or floor disconnect. Stale/invalid source geometry cannot be certified; a rejected new import retains the previous accepted geometry and can still be tested as that previous revision.

## Automated evidence

The controlled test fixtures select Start/Goal only in in-memory copies of references. Original drawings, manual annotations and accepted reference JSON files remain untouched.

- `PlayableSketch.Navigation.ExplicitPawn`: shared-wall door; case-sensitive region identifiers; removed opening; narrow door; low lintel; external-style blocking prop; larger capsule; 200 cm corridor; thicker walls with unchanged centerlines; agent too wide for corridor; removed corridor floor; translated/yaw layout; authored branching/T join; shifted grid; coarse-grid failure with independently successful Pawn replay; geometry-only floor sanity; invalid transform/work budget; rejected import, Local/Full rebuild and stale-scene gating.
- `PlayableSketch.Import.CanonicalExplicit`: existing import tests plus actual Pawn traversal after runtime BeginPlay through a controlled gameplay copy of Data_8.
- `PlayableSketch.Import.ExplicitPersistence`: actual Pawn before disk save and after real map/asset unload/reopen, with translated/yaw actor and preserved geometry values.
- `PlayableSketch.Navigation.RestartedProcess`: a **second Unreal process**, started with `-unattended -Step12Restart`, reopens the saved map and repeats Pawn traversal before rebuild, after Local, after Full and after BeginPlay. Without this explicit flag the normal suite only records the required separate-process invocation; that informational invocation is not restart evidence.

Artifacts: `Saved/Step12/physical-fixtures.json`, `unreal-report/index.json`, `unreal-tests.log`, `restart-report/index.json`, `restart-tests.log`, `restarted-pawn.json`, `verification.json`, and `build.log`.

The engine build uses the existing temporary local Xcode 27 admission wrapper; it restores the original Apple SDK configuration after building. No engine configuration change is retained. No model training, dataset edits, automatic user approval, or web-service changes are part of this step.

Step 13 was subsequently completed using these independent physical results; see [evaluation and robustness](step13_evaluation_robustness.md). Step 14 was subsequently completed for the local Mac Development package; see [packaged runtime](step14_packaged_runtime.md). The flat-floor physical contract remains unchanged.

## Verified outcome (2026-10-21)

The full engine suite has 13 successful entries and zero failures; its restart entry is a guarded informational invocation. A separate flagged Unreal process executes the actual restart test. Sixteen physical fixtures produce their expected outcomes: 8 Pawn passes, 7 correctly blocked traversals, and 1 geometry-only `not_applicable`. The coarse-grid fixture deliberately has grid `failed` with physical Pawn `passed`. The only remaining automation warnings are the existing authoring-validation negative-case warnings; the new physical tests emit none.
