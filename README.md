# PlayableSketch

An Unreal Engine C++ prototype that turns a spatial graph into room floors, doors,
orthogonal corridors and wall geometry. It supports saved room placements, validated
edits, component-preserving local rebuilds and grid-based navigation analysis.

The repository includes a fixed experiment manifest, a headless runner and raw results
including generation failures. Geometry validation passed for **10 of 30** cases;
none was reachable in the navigation analysis. The Local/Full benchmark
passed equivalence checks for **10 distinct edits**.

## Environment and build

Verified on Windows with Unreal Engine **5.7.4**, Visual Studio 2022 / MSVC
**14.44.35229**, Windows SDK **10.0.22621.0** and an AMD Ryzen 5 5600X.
Python **3.10+** is needed for experiment validation and CSV/statistics export;
the scripts use only its standard library. Git is optional for running experiments;
when available, its revision and working-tree status are recorded.

1. Clone your fork with its `Source`, `Config`, `Content`, `Scripts`, `Experiments`
   and `PlayableSketch.uproject` files. Keep World Partition external actors/objects
   with the sample map.
2. Install UE 5.7 and the Visual Studio C++/Unreal build tools. The project enables
   the engine's Modeling Tools Editor Mode plugin.
3. Generate Visual Studio project files from `PlayableSketch.uproject`, then build
   `PlayableSketchEditor`, `Development Editor`, `Win64`.
4. Open `PlayableSketch.uproject`. The sample map is `/Game/PlayableSketch` and the
   sample graph asset is `/Game/PlayableSketch/Data/DA_ThreeRooms`.

A command-line build from the repository root is also possible:

```powershell
$Project = Join-Path (Get-Location) 'PlayableSketch.uproject'
New-Item -ItemType Directory -Force Saved\BuildLogs | Out-Null
& 'C:\Program Files\Epic Games\UE_5.7\Engine\Build\BatchFiles\Build.bat' `
    PlayableSketchEditor Win64 Development "-Project=$Project" `
    -WaitMutex -NoHotReloadFromIDE -NoUBA "-Log=$PWD\Saved\BuildLogs\build.log"
```

The recorded verification used this working checkout. A fresh clone, packaged build
and interactive playthrough have not been verified by this experiment run.

## Authoring and editor controls

Place/select a `PlayableSketchLevelActor` and assign a `PlayableSketchGraphAsset` in
its Details panel. Edit the graph asset's room/connection arrays; stable GUIDs identify
elements. Rooms define dimensions, type, role and Auto/Locked positioning. Connections
define endpoints, corridor/door widths and optional manual door positions. Set Start
and Goal room IDs to existing, different rooms.

Use the actor's Details buttons:

| Control | Behavior |
| --- | --- |
| Validate Graph / Validate Current Design | Report structured input/geometry issues. |
| Generate Layout | Place Auto rooms, generate geometry and save room placements in the graph asset. |
| Rebuild Geometry (Full) | Rebuild from saved/Locked positions and replace generated components. |
| Rebuild Local Geometry | Recompute the candidate and retain/update unchanged/key-matched components. |
| Auto Rebuild Geometry | Refresh geometry after graph/settings edits. |
| Clear Floors | Remove generated preview geometry and its navigation result. |
| Analyze Navigation | Analyze the current floor/wall geometry from Start to Goal. |
| Export Navigation Report | Export the current navigation sample under `Saved/Navigation`. |
| Run Navigation Examples | Export the five fixed navigation fixtures. |
| Show Navigation Grid / Show Blocked Navigation Cells | Draw the analyzed cells and route in the viewport. |

Validation failures invalidate the preview and remove outdated generated collision.
Local rebuild can fall back to Full when the initial snapshot is missing, global
settings/seed/asset change or the component registry is unhealthy; inspect
`LastRebuildReport` for the actual mode and reason. Save the asset/map through the
editor after authoring changes.

## Repeat the experiments

Close the editor before rebuilding. From the repository root:

```powershell
.\Scripts\run_experiments.ps1 `
    -EngineRoot 'C:\Program Files\Epic Games\UE_5.7' `
    -PythonExe python
```

The script validates the manifest SHA-256 lock, records source hashes, builds the
editor target, runs all `PlayableSketch.` automation tests in a transient world with
`-NullRHI`, validates the output and writes a new timestamped directory under
`Experiments/runs/`. Logs, DDC and the automation report stay under
`Saved/Experiments/runs/`. It restores the process DDC environment variables on exit.

Use `-OutputDirectory <unused-path>` to choose the result directory. The script refuses
to overwrite an existing directory. `-SkipBuild` is only appropriate when the binary
already matches the current source. Run one experiment process at a time because the
engine initially exports to `Saved/Experiments/raw_results.json`.

The engine automation entry point is `PlayableSketch.Experiments.Run`. The PowerShell
wrapper adds the manifest/source checks and CSV/statistical exports. Expected generation
failures are data; the automation test fails for a broken harness or a Local/Full
equivalence failure. Fresh raw results are retained when automation reports a failure.

`Scripts/create_manifest.py` documents how the committed inputs were constructed.
**Do not regenerate or tune the manifest after looking at outcomes.** A changed protocol
needs a separately identified manifest/run and must retain its failures.

## Fixed protocol

[`Experiments/manifest.json`](Experiments/manifest.json) was written before the first
run. Its SHA-256 is:

```text
06f45534f232d33e21d6e47cd22c36d87c69f40bacb314a6cc77f4dc5ddf0ca8
```

It fixes full graphs, GUIDs, seeds, schema/algorithm versions and all generation,
geometry and navigation settings. The generation group contains 10 chain, 10 binary
branching and 10 ring graphs. Each family uses room counts
`5, 10, 20, 5, 10, 20, 5, 10, 20, 5`; seeds and IDs are fixed per case. Every room in
this group uses Auto placement, 200 cm corridors and 150 cm doors. For zero-based case
index `i` within a family, room index `r`, and family index `f`, dimensions are fixed as
`width = 600 + 50*i + 50*(r%3)` and `depth = 600 + 50*((r+i+2*f)%4)` cm.
The recorded output contains **30 different room-bound arrangements even after
removing GUIDs**.
There is one generation attempt per case with a 128-attempt placement bound; no retry,
replacement or success-only filtering is performed.

This is input set version 2 (`varied-dimensions`). The first, uniform-dimension input
set only varied seeds/IDs within repeated room counts. Inspection showed that the
current placement implementation does not consume Seed, so that set was inadequate
for geometric diversity. Its full manifest and results remain in
[`Experiments/archive/uniform-inputs`](Experiments/archive/uniform-inputs). The second
set varied dimensions by the formula above, was locked before its own run, and retained
all of its outcomes. The generation algorithm was unchanged. The headline results
below use only version 2; the earlier run is not pooled into them.

The benchmark group is separate from the generation group. It uses a known valid
four-room Locked ring and ten predefined before/after graph pairs: hub material,
display name, room width, room depth, room position, door width, corridor width,
connection deletion, room deletion and array reordering. Display-name and array-order
edits intentionally test changes that should leave geometry unchanged. These fixtures
do not demonstrate successful automatic generation of branching/ring layouts.

For each pair, the runner performs one warmup and five measured repetitions. Before
**every** repetition, both actors receive the same baseline graph and a Full rebuild.
Their starting plans and actual scene values must match. Both then receive the exact
same edited graph; one uses Local and the other Full. Execution order alternates.
Baseline setup, comparison and JSON/CSV export are outside the measured rebuild call.
Warmups remain in the raw records and are excluded from timing summaries.

Equivalence checks cover canonical room bounds, door endpoints and corridor footprints;
actual component keys, transforms, mesh/material assignments and collision settings;
registry health/current source signatures; navigation metrics, ordered paths and
walkable cell sets. Raw records include plans, canonical scene values, baseline
fingerprints, update counts and the actual mode/reason. A Local fallback is not accepted
as a successful Local comparison. Artifact hashes are identifiers; equality checks also
compare the underlying values directly.

## Recorded results

[`Experiments/results`](Experiments/results) contains the run from **2026-10-11 UTC**:

| Generation family | Cases / valid inputs | Room placement succeeded | Valid geometry | Navigation reachable | Failed pipeline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chain | 10 / 10 | 10 | 10 | 0 | 0 |
| Branching | 10 / 10 | 10 | 0 | 0 | 10 |
| Ring | 10 / 10 | 10 | 0 | 0 | 10 |
| **Total** | **30 / 30** | **30** | **10** | **0** | **20** |

The 20 failures occurred during door generation: the automatically selected openings
overlapped. They have `failure_stage="doors"`, `error_code="EXPERIMENT_DOORS"` and the
original error text identifying the conflicting connection IDs. Their later geometry
validation/navigation fields are **null/not computed**, rather than successful or
measured zero. Thus room placement is 30/30 and geometry acceptance is **10/30 (33.3%)**.
Navigation analysis completed on all ten valid geometries, but every result was
unreachable: navigation success is **0/30**, or **0/10 conditional on valid geometry**.
These ten records have `status="completed"` because analysis completed; that field
does not mean the navigation was successful. Agent radius is 40 cm, clearance 10 cm,
agent height 180 cm and grid cell size 50 cm. The conservative grid/discretization is
a relevant limitation; this experiment does not establish a single cause for every
unreachable case.

All ten benchmark pairs passed, including the warmups: 20 warmup records and 100 measured
records (50 Local, 50 Full). There were no Local fallbacks. Benchmark validity means
accepted geometry, completed navigation analysis and equal Local/Full outcomes;
it does not require the edited layout to be reachable. The pooled observed times are:

| Rebuild measurement | Local median / P95 (ms) | Full median / P95 (ms) | Samples per mode |
| --- | ---: | ---: | ---: |
| Entire rebuild call | 1.667 / 3.126 | 6.089 / 7.533 | 50 |
| Component apply | 0.163 / 0.925 | 4.650 / 5.772 | 50 |
| Navigation | 1.318 / 1.865 | 1.372 / 1.815 | 50 |

Per-edit Full/Local median-time ratios range from **2.53 to 3.92** on these small
fixtures. This is a single-machine CPU/editor observation, including two geometry
no-op edits, rather than a general performance guarantee. There are only five measured
repeats per edit; their nearest-rank P95 is the maximum of those five samples. Pooled
statistics combine different edits. No GPU/frame-time, packaged-runtime or large-layout
benchmark was performed.

`total_ms` measures the existing rebuild method including validation, planning,
component updates, navigation and reporting. `plan_ms`, `validation_ms`, `dirty_ms`,
`apply_ms` and `navigation_ms` are the existing internal measurements and do not form
an exhaustive additive partition of total time. Local still recomputes candidate
geometry and navigation globally; the measured saving primarily comes from component
reuse. Generation `geometry_pipeline_ms` covers pure door/routing/wall/validation work
up to completion or failure and does not include scene component creation. Its pooled
summary includes the 20 early failures and must not be interpreted as successful-build
latency. Every timing summary includes its own non-null sample count.

| Artifact | Contents |
| --- | --- |
| [raw_results.json](Experiments/results/raw_results.json) | Full consumed manifest, all 30 generation outcomes, all 120 benchmark records, snapshots, errors and navigation output. |
| [generation.csv](Experiments/results/generation.csv) | All generation cases, input graphs/settings, stage outcomes and timings. |
| [benchmark.csv](Experiments/results/benchmark.csv) | Warmups and measured repeats, before/after graphs, mode/reason, equality flags and timings. |
| [summary.json](Experiments/results/summary.json) | Denominators, family outcomes, per-edit and pooled median/P95 values. |
| [timing_summary.csv](Experiments/results/timing_summary.csv) | Per-edit/per-mode/per-metric sample counts, median and P95. |
| [provenance.json](Experiments/results/provenance.json) | Engine/compiler context, OS/CPU context, Git revision/dirty status, source SHA-256 values and automation outcomes. |

CSV empty cells represent JSON null. Nested arrays/objects are JSON-encoded CSV fields.
P95 is nearest rank `ceil(0.95*n)`; median uses the conventional sample median. The
recorded checkout had uncommitted source changes; its exact source hashes are provided
instead of implying the Git HEAD alone reproduces the run.

## Automated verification

The recorded build succeeded and all five automation tests returned `Success`:

- `PlayableSketch.Authoring.Validation`
- `PlayableSketch.Geometry.LocalRebuild`
- `PlayableSketch.Navigation.GridAndMetrics`
- `PlayableSketch.Navigation.ActorLifecycle`
- `PlayableSketch.Experiments.Run`

Harness/test success does not imply that all 30 generated designs succeeded. The raw
generation failures above remain part of the result and denominator.

## Current limitations

- Automatic placement/door selection does not jointly solve the complete graph;
  branching/ring failures in this manifest expose that limitation. Corridor routing
  uses bounded orthogonal candidates rather than unrestricted global backtracking.
- Navigation is a conservative, four-neighbor horizontal occupancy grid with finite
  cell/work budgets. It reports reachability, route length, physical dead ends,
  alternative route existence and unreachable rooms. It is not a Recast NavMesh or
  an actual pawn movement test; discretization/agent clearance can reject narrow paths.
- Generated layout coordinates are local centimeters. Navigation assumes horizontal
  floors and unit actor scale; stairs and general 3D traversal are outside this prototype.
- Local rebuild preserves components but still plans/validates the complete candidate
  and rebuilds the navigation analysis.
- The fixed benchmark covers ten edits on small, valid fixtures. It does not establish
  scalability or compensate for failed automatic-generation cases.


