# Layout Data Contract v1

**Version:** 1.0  
**Date:** 2026-10-14  
**Scope:** Step 03 — observations, metric layout representation, validation and reference fixtures. Unreal generation and image recognition are separate steps.

The contract follows [Drawing Convention v1](/Users/pelinsukaleli/PlayableSketch/Docs/drawing_convention_v1.md). Original photographs remain unchanged. The ten `0.1` manual drafts and their generated references were corrected on 2026-10-16 to use the author’s near-opening-edge offset interpretation; pre-correction copies are archived under `Saved/OffsetMigration/`. Converted fixtures live under `Data/ground_truth/v1/`.

## Documents and schemas

| Document | Schema | Purpose |
| --- | --- | --- |
| `observations` | `observations.schema.json` | What was seen/read in an image, including uncertainty |
| `draft_layout` | `draft_layout.schema.json` | Interpreted topology, dimensions and provisional cm coordinates |
| `validated_layout` | `validated_layout.schema.json` | Accepted, complete metric reference with passing validation |

`common.schema.json` contains shared definitions. Schemas use JSON Schema Draft 2020-12, strict objects (`additionalProperties: false`), and local URN references. The validator loads its schema registry from the repository; it does not fetch schemas over the network. [JSON Schema validation API](https://python-jsonschema.readthedocs.io/en/stable/validate/).

Layout version is `playablesketch-layout/1.0`; observation version is `playablesketch-observations/1.0`. Unsupported versions are rejected rather than silently migrated.

## Coordinates and measurement basis

- Observations use original-image coordinates: `u` right, `v` down, units `px`.
- `frame.original_to_frame` is an invertible 3×3 homography. Current fixtures use the original frame and identity transform. Future crop/resize/rectification must update the frame metadata.
- Pixel geometry is continuous within `[0,width_px] × [0,height_px]`, including image borders.
- Metric layout coordinates use local cm: `x` right, `y` up, `z` up. Ground floor is z=0. Intended Unreal mapping is X=x, Y=y, Z=z.
- Region boundaries and wall dimensions use **wall centerlines**.
- Opening width and height use **clear opening** dimensions.
- Wall axes are `x` for horizontal and `y` for vertical. Walls point in the positive direction of their axis.
- Unknown draft coordinates or measurements use `null`. Zero is a real coordinate, never an unknown-length placeholder.
- Numbers must be finite. Numeric schema fields are bounded to ±1,000,000,000, with positive lengths. NaN, Infinity, duplicate JSON keys, wrong types and unknown fields are rejected.

## Root metadata

Each layout has `document_id`, `revision_id`, nullable `parent_revision_id`, `algorithm_version`, `observation_document_id`, `source`, `settings`, `review`, `layout`, `issues` and `validation`.

`source` contains the image path, SHA-256 and optional legacy draft path. Paths are relative to the document file. The CLI checks the source image hash. Observation identity and image hash must match when an observation document is supplied.

IDs are opaque, unique across the entities of one layout, and stable across revisions. They are not array indices. The fixture converter assigns and deduplicates IDs during initial migration; a future editor must preserve those persisted IDs when an element moves. Do not rerun conversion to implement live edits.

Revisions identify immutable snapshots. User correction should create a new revision and invalidate the old validation result. `as_validated` returns a copy with an accepted revision and preserves its input.

## Observations

`texts` contain `id`, `raw_text`, nullable `polygon_px`, nullable `parsed_value_cm`, nullable `score` and `method`. Numeric parsed values are in cm even though image coordinates are in px.

`lines` contain pixel endpoints and an optional score. `opening_candidates` contain pixel polygons and an optional score. They are observations, not final wall/opening decisions.

`region_annotation_status` is `not_started`, `partial` or `complete`. A complete text annotation requires pixel polygons. The current fixtures contain manual numeric transcriptions with `polygon_px: null`; line regions and opening regions are not annotated. They are not detection-training ground truth yet.

Scores are model scores, not calibrated probabilities. Current manual transcriptions have `score: null`. Whitespace is normalized in their `raw_text`; no OCR was run.

## Layout entities

| Entity | Required interpretation |
| --- | --- |
| `Vertex` | ID, `[x,y]` position, evidence state and provenance |
| `Wall` | Two endpoint IDs, axis, resolved thickness/height and owning region IDs |
| `Room` | ID, name, role and cyclic boundary vertex/wall references |
| `Corridor` | A rectangular region with the same boundary representation; role is `none` |
| `Opening` | Supporting wall ID, type, center offset, clear width/height and two connected typed entities |
| `Passage` | One opening reference and its corresponding region connection |
| `Dimension` | Value, measurement basis, target span, state, label and provenance |

All entities include provenance: `method`, `evidence_ids`, and a short `note`. Evidence IDs refer to the linked observations. The acceptance function requires that observation document whenever evidence links exist. Bare metric validation without observations does not verify external evidence links.

### Boundaries and shared walls

Region boundary arrays describe a counterclockwise cycle. Wall i connects vertex i to the next vertex, with implicit closure to the first. Boundary traversal may oppose the wall's positive-axis direction.

Regions must be rectangles. Extra collinear boundary vertices are allowed to represent T junctions. Intersections are noded and owners share the same vertex/wall IDs. Overlapping room/corridor interiors, duplicate walls, reversed or diagonal walls and broken boundary references are invalid.

A shared wall is stored once. Its `region_ids` exactly match the regions referencing it. V1 supports interior openings between two rooms or between a room and a corridor. Exterior openings are not represented by a fictitious second room.

### Logical boundaries and open entrances

The room/corridor interface remains a logical wall boundary in the graph even where the passage is open. Its opening identifies what must be removed from solid geometry in Step 04–05.

For these fixtures, corridor entrances are open passages unless a door was explicitly specified. With a centerline corridor width of 200 cm and equal 20 cm boundary-wall thickness, the derived clear entrance width is 180 cm. This is not a 200 cm door measurement.

`open_passage` uses full wall height; `door` uses configured door height. A future geometry builder must implement these openings and junction joins; passing this contract does not certify that mesh output.

### Opening offsets: two distinct references

`Opening.center_offset_cm` is measured from the **supporting wall's start vertex**. The opening interval is:

```text
[center_offset_cm - clear_width_cm/2,
 center_offset_cm + clear_width_cm/2]
```

The author's paper offset is **corner-to-near-opening-edge** (corrected 2026-10-16). It is a separate `Dimension` with `basis: edge_offset`, target `opening_offset`, connected room ID, side and `reference: min_corner|max_corner`. The numeric label is preserved. Legacy explicit dimensions with `basis: center_offset` still mean center measurements; they are never silently reinterpreted.

For north/south sides, `min_corner` is the left corner; for east/west it is the bottom corner. `max_corner` uses the opposite corner. An edge measurement equals center-to-reference distance minus half the clear width. For a minimum-corner offset `s` and clear width `w`, the opening occupies `[s, s+w]` relative to that corner and its derived center is `s+w/2`. For a maximum-corner offset, the near edge lies `s` back from that corner.

Example from `Genel.png`: room widths 400/500 cm, depth 200 cm, lower edge offset 50 cm and door clear width 120 cm imply center 110 cm and upper remaining span 30 cm. This example documents interpretation; it is not automatically added to a dataset manifest.

**Data_8 example:** Left door lower edge y=300 and clear width 120 imply center y=360. Retaining prior fixture center alignment, the 200 cm centerline corridor spans y=260–460; the supporting wall-local center offset remains 100 cm. The right open entrance has clear width 180 and lower-edge offset 200 from its room corner, so that room's bottom becomes y=70. This derivation retains the recorded corridor alignment assumption; unequal clear widths must not be treated as equal-width entrances.

A wall's direction is fixed in v1. Reversing its direction requires an explicit migration of offsets; the validator rejects reversed walls.

### Dimension targets

- `region_span`: region ID and axis; measures the full bounding width/depth. Opposite rectangle sides target the same geometric span; `span_label` retains which label was read.
- `wall_chain`: ordered, contiguous, collinear wall IDs; measures the total chain length.
- `opening_width`: opening ID; measures clear width.
- `opening_offset`: opening ID, connected room ID, side and reference; measures the corner-to-near-edge offset for `basis: edge_offset`, or an explicitly retained center measurement for `basis: center_offset`.
- `opening_separation`: ordered `from_opening_id` and `to_opening_id` on the same supporting wall; `basis: edge_offset` measures the solid span between their facing clear-opening edges. For Data_15, this is 150 cm, not the cumulative upper-door start of 380 cm. Python and Unreal validate the same scope.
- `unassigned`: draft-only target when association cannot yet be resolved.

No averaging is performed for conflicting confirmed dimensions. An unassigned target blocks acceptance. Values and evidence remain available for correction.

## States and acceptance

| State | Meaning |
| --- | --- |
| `confirmed` | Explicitly accepted measurement or interpretation in the reference annotation |
| `derived` | Computed from accepted dimensions, relations or configured settings |
| `inferred` | A proposal requiring review |
| `missing` | Unresolved; nullable data is retained |
| `conflicting` | Requires correction before acceptance |

Configured defaults are identified by provenance, not described as image measurements.

Draft status is `draft`, `needs_review` or `conflicting`. A draft may have correct metric geometry and still be non-exportable. `as_validated(draft, reviewer, observations)` requires a named reviewer, passing checks and resolved evidence; it creates a separate accepted document.

Validated schema requires complete coordinates, resolved measurements, confirmed/derived states, no issues, accepted review and passing metric validation metadata. The validator recomputes metric validity; a claimed `status: validated` or cached `validation.metric: passed` cannot bypass checks.

The first eight accepted files are **manually prepared metric reference fixtures** produced by this conversion step. They are not user-approved OCR predictions, Unreal mesh results, or proof of physical playability.

## Settings and gameplay

V1 uses global wall thickness/height, door height and floor thickness. Resolved walls/openings must agree with those settings. After changing defaults, recompute resolved values and derived entrance clear widths, then revalidate. Do not silently change centerline dimensions.

`geometry_only` allows null Start/Goal, including single-room fixtures. `gameplay` requires different existing Start/Goal rooms, consistent room roles, and passage connectivity from Start to every room. Adjacency without an opening is not a passage.

Metric validation covers schema, IDs/references, orthogonal rectangular boundaries, ownership, overlap, noding, opening intervals/heights, dimension consistency and topology. It does **not** validate generated wall solids, agent clearance, collision, Recast/grid navigation or Pawn movement. Those checks remain `not_run`.

## Current fixtures and negative examples

`Data/ground_truth/v1/` contains 10 observations, 10 drafts and 8 accepted metric references. Source numbers and original images are preserved.

- Data_9 keeps 600 and 450 cm opposite horizontal measurements targeting the same rectangle width. It has a dimension conflict and unresolved geometry, with no accepted export.
- Data_10 keeps corridor width and both right-room dimensions null. Its entrance-offset labels remain unassigned until the unresolved boundary geometry can be constructed. It has no accepted export.
- Pixel polygons, line observations and detailed original-image associations remain future annotation work, explicitly marked `not_started`.

## Running the checks

From the repository root, create an isolated environment and install only the contract dependencies:

```sh
python3 -m venv SketchPipeline/.venv
SketchPipeline/.venv/bin/python -m pip install -r SketchPipeline/requirements.txt
SketchPipeline/.venv/bin/python -m unittest discover -s SketchPipeline/tests -v
SketchPipeline/.venv/bin/python -m SketchPipeline.validation.validate Data/ground_truth/v1/Data_3.validated.json
SketchPipeline/.venv/bin/python -m SketchPipeline.fixtures.build_references --check
```

On Windows use `py -m venv SketchPipeline/.venv` and `SketchPipeline/.venv/Scripts/python.exe` in place of the executable above.

CLI exit 0 means no reported validation/source errors; it does not mean a draft is exportable. Read `exportable` in the report. Data_9 and Data_10 intentionally return nonzero with actionable issues.

Fixture conversion refuses to replace existing outputs by default. `--check` compares without writing; `--overwrite` explicitly rebuilds generated v1 references from the author-corrected `0.1` source drafts. It must not be used to overwrite future user-edited production layouts.
