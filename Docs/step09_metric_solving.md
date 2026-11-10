# Step 09 — Dimension association and metric constraint solving

Implemented on 2026-10-21. Step 09 is the Python core/CLI. [Step 10 metric review](step10_metric_review.md) now provides browser editing and explicit acceptance on top of it; Step 11 orchestration/Unreal integration is also implemented; Step 12 physical/Pawn verification is next.

## Input and output

```text
Current accepted Step 08 topology revision + linked observations
    + explicit room/corridor kinds + configured settings
    + confirmed measurement bindings / explicit relations
  -> rectangular noded canonical skeleton (cm initially null)
  -> text-to-span alternatives + bounded diagnostic hypothesis search
  -> exact hard constraint solve + rank/residual report
  -> existing schema/custom metric validator
  -> draft.json + report.json + bindings.json (review pending)
```

Production reconstruction never reads `Data/ground_truth`. It requires a current accepted topology revision, rechecks revision/state digests and every source fingerprint, verifies the original image/observation identity and affine transforms, and reruns exact topology analysis. Changed sources, stale revisions, drafts and unknown room/corridor semantics are rejected. A topology edit requires rebinding measurements to its new revision.

The adapter nodes rectangular boundaries at structural T junctions, preserves one shared vertex/wall per structural interface, and attaches each approved opening to a unique logical wall. Door jambs do not become artificial metric region corners. Unsupported nonrectangular regions, holes and openings crossing a structural interface split require topology correction.

## Run locally

The existing `Saved/Step07/python/bin/python` environment has the needed packages. Fresh environments can install `SketchPipeline/requirements-metric.txt`.

```bash
Saved/Step07/python/bin/python -m SketchPipeline.metric \
  --review /absolute/path/to/case/revisions/REVISION.json \
  --observations /absolute/path/to/prediction/observations.json \
  --bindings /absolute/path/to/metric-bindings.json \
  --output /absolute/path/to/new-metric-output
```

The output directory must be new; previous results are not overwritten. `draft.json` uses the existing canonical draft contract and absolute source paths. `report.json` records review/source hashes, pixel topology for association inspection, candidates/features, search budget, equations/evidence IDs, singular values, rank/nullity, nullspace modes, per-equation residuals, solved variables and metric validation issues. `bindings.json` preserves the exact request. Metric revision IDs incorporate the bound topology revision and request digest.

A generated integration example is available at `Saved/Step09/v1/cli_demo`. Its inputs in `controlled_fixture` are a **programmatically approved unit-test topology with a blank image and synthetic OCR labels**, not user-reviewed ground truth. No actual drawing was auto-approved. Re-running its command with a fresh `--output` works while the stored sources remain unchanged; the exact reviewed revision filename is in `controlled_fixture/reviews/Data_1/latest.json`.

## Binding contract

Schema: `SketchPipeline/schemas/metric-input.schema.json`, version `playablesketch-metric-input/1.0`.

A minimal request has `schema_version`, `topology_revision_id`, `region_kinds` and `dimensions`. Empty dimensions intentionally produce an unresolved draft, not guessed centimetres. Kinds must cover every reviewed region; IDs come from that review's topology. Optional `settings` override the configured 20 cm wall/floor thickness, 300 cm wall height and 220 cm door height. Start/Goal remain unselected.

Example dimension (inside `dimensions`):

```json
{
  "id": "measurement1",
  "value_cm": 600,
  "basis": "wall_centerline",
  "target": {"type": "region_span", "region_id": "r001", "axis": "x"},
  "state": "confirmed",
  "span_label": "Left room width",
  "provenance": {
    "method": "user_correction",
    "evidence_ids": ["t001"],
    "note": "User confirmed the transcription and its target."
  }
}
```

Confirmed bindings require `user_correction` or `manual_annotation` provenance. Evidence IDs must reference linked numeric observations. Unwritten user-entered dimensions can have empty evidence IDs and an explanatory note. Missing values remain `null` with state `missing`. Other supported targets/bases follow the existing layout contract:

| Target | Basis / meaning |
| --- | --- |
| `region_span` | `wall_centerline`: full rectangular width or depth |
| `wall_chain` | `wall_centerline`: ordered contiguous positive-direction collinear walls; includes local solid spans to centerline T junctions |
| `opening_width` | `clear_opening`: clear width, independent of centerline corridor width |
| `opening_offset` | `edge_offset`: named region corner to **near clear opening edge**, from min/max corner on the named side |
| `opening_offset` | `center_offset`: only when explicitly specified; never substituted for paper edge offsets |
| `opening_separation` | `edge_offset`: facing-edge solid span of two openings on the same noded supporting wall |
| `unassigned` | Draft only; requires review |

Unknown local anchors are left for review instead of being mislabeled as a room-corner offset. Explicit `point_lock` relations can supply a verified local vertex coordinate; ordinary local solid spans use `wall_chain` dimensions. Zero is a valid point-lock coordinate; the unchanged v1 Dimension schema requires positive written measurements.

Optional confirmed `relations` are deliberately explicit:

```json
[
  {"id":"door-alignment", "type":"centered_opening", "opening_id":"door1",
   "state":"confirmed", "note":"User explicitly confirmed centering on this supporting interface."},
  {"id":"full-entrance", "type":"full_span_opening", "opening_id":"passage1",
   "state":"confirmed", "note":"User confirmed a full-span open corridor entrance."},
  {"id":"junction-lock", "type":"point_lock", "vertex_id":"mv0001", "axis":"y", "value_cm":0,
   "state":"confirmed", "note":"Verified local coordinate in the chosen origin frame."}
]
```

`full_span_opening` is restricted to `open_passage`: it centers the entrance on its supporting interface and sets clear width to interface length minus configured wall thickness (v1 equal-thickness centerline convention). A 200 cm interface with 20 cm thickness gives 180 cm clear width. It is **not applied automatically** to corridors/passages. An explicitly measured narrower passage keeps its measured width and offset. Relations may carry linked observation `evidence_ids`; a nonempty note is required.

The origin defaults to the first structural vertex at `(0,0)`; `origin_vertex_id` can name another structural vertex. Point locks use this same coordinate frame. Existing template coordinates/opening values are ignored by the solver, including manual reference values.

## Association and search

The candidate catalog covers region spans, bounded collinear wall chains, clear opening widths, min/max room-corner offsets and same-wall adjacent-opening separation. Original OCR polygons/line endpoints are transformed through `original_to_review × inverse(original_to_frame)`, then flipped into x-right/y-up coordinates.

Local costs expose normalized perpendicular distance, projection outside the span, weak text orientation evidence, perpendicular endpoint/extension evidence and a weak target-type prior. The prior is a heuristic, not a trained semantic classifier. Line evidence is optional; missing tick/extension evidence lowers confidence. Null text polygons or unparsable numbers produce no invented association. Region-span side duplicates are merged by target/basis; redundant measurements remain allowed.

Defaults: top 3 alternatives per text, 2,048 generated wall chains, beam budget 16; request limits are top_k 1–8 and hypothesis_budget 1–64. Search considers unmatched branches and combines local costs with hard-system consistency, known ordering/interval checks and custom validator results wherever geometry is determined. Budget exhaustion is explicit. It is a local beam, not exhaustive optimization. There is no automatic assignment acceptance. Branches temporarily treating OCR candidates as constraints exist only in the diagnostic report; the published draft solves **confirmed inputs only**.

## Exact solve and acceptance boundaries

Orthogonality and shared junctions define the topology. Directed axis differences, confirmed dimensions, explicit relations/locks and an origin gauge form `Aq=b`. SVD reports numerical rank and nullspace; equation count alone does not establish determinacy. Every scalar unaffected by nullspace freedom can be published; unresolved coordinates/widths remain null. Pixel ratios do not fill missing metric information.

Conflicting hard equations yield diagnostic least-squares residuals, but their averaged coordinates are **not** published as usable geometry. The first implementation conservatively nulls all solution variables on hard inconsistency. Confirmed conflicting inputs remain visible. An unconfirmed OCR mismatch requires review and cannot change a confirmed dimension.

A linearly determined solution can still have impossible wall order, overlap or opening intervals. Custom validation runs separately and must pass. `status` in the report describes the linear system; `reconstruction_status` and `validation` describe the resulting draft. An explicitly measured opening width can remain confirmed while its center is derived; full-span-derived widths remain derived and are checked against settings.

Every output is `draft_layout`, review pending, exportable false. Solver success never calls `as_validated`. Engine geometry, navigation and physical playability remain `not_run`. Step 10 now supplies metric editing, explicit acceptance and validated JSON download; [Step 11](step11_pipeline_jobs_unreal.md) now completes orchestration/Unreal integration.

## Verification and development artifacts

```bash
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
Saved/Step07/python/bin/python -m SketchPipeline.experiments.metric_regression \
  --output Saved/Step09/new-regression
```

Development regression results are in `Saved/Step09/v1/final_regression/summary.json`:

| Inputs | Expected/result |
| --- | --- |
| Data_1, Data_3 | Determined; 600×400 and shared x-lines 0/600/1100 pass metric validation |
| Data_8 | Determined **with two explicit reference premises**; local door center 100, right room bottom 70; without premises underdetermined |
| Data_9 | Inconsistent 600/450 width; no averaged geometry/export |
| Data_10 | Underdetermined; right width/depth and corridor width unresolved |
| Data_15, Data_18, Data_41 | Determined; same-wall separation, staggered boundaries, max-corner offsets pass validation |
| Data_49 | Inconsistent written spans; missing entrance premises do not hide conflict |
| Data_50 | Underdetermined missing room width |

The experiment scrambles every existing cm coordinate/opening value before solving. Data_9/10 historical fixture wall directions were generated backwards where coordinates were null; the experiment explicitly normalizes those directions from their documented SW-first CCW loops without reading numeric positions. Original fixtures remain untouched. These are **solver development regressions on known topology/associations**, not automatic perception accuracy or independent held-out performance.

Unit/integration coverage additionally includes total 600 versus parts 200+400 / 250+400, redundant equations/rank, wrong OCR branches, real shared T-junction noding, frame transforms, stale/tampered reviews, changed sources, explicit semantic kinds, narrow passages and mandatory pending acceptance.

Verification completed on 2026-10-21: **205 tests passed**, including 21 new metric solver/association/revision integration tests. Full test log: `Saved/Step09/v1/tests.log`; machine-readable verification: `Saved/Step09/v1/verification.json`.

Step 10 adds optional `ignored_texts` entries with explicit evidence IDs/reasons for nonmeasurement rejection; original observations are preserved and the same evidence cannot also be bound to a dimension.
