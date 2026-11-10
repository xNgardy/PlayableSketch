# Shape-first Step 1 — Contract and sizing policy

Implemented: 22 October 2026. Scope: Step 1 of `ShapeFirst_Implementation_Guide_TR.md`.
This is an authoring contract, not an implemented inference, joint sizing solver,
web workspace or Unreal delivery flow. The existing upload default is unchanged.

## Files and checks

- `SketchPipeline/schemas/shape_authoring.schema.json`: strict Draft 2020-12 schema,
  version `playablesketch-shape-authoring/2.0`.
- `SketchPipeline/shape_authoring/sizing_policy.v1.json`: deterministic product
  starting points and constraint policy, version `shape-sizing/1.0`.
- `SketchPipeline/shape_authoring/contract.py`: offline structure/reference validation,
  immutable acceptance and stale-binding helpers, tested near-edge conversion.
- `SketchPipeline/shape_authoring/fixtures/`: empty manual-start document and
  multi-door/corridor-bend document. These are synthetic contract examples, with
  placeholder image paths/hashes, not accepted metric layouts or perception results.

Run with the repository environment:

```sh
Saved/Step07/python/bin/python -m unittest SketchPipeline.tests.test_shape_authoring SketchPipeline.tests.test_contract -q
```

`validate_authoring` returns errors. An empty error list only means structural
conformance. It does not establish rectangle validity, non-overlap, opening fit in
cm, complete sizing, physical gameplay readiness, source file/hash integrity or export
permission. The future solver/export boundary must separately perform those checks.
The strict JSON loader in `SketchPipeline.validation.validate.load_json` should be
used for persisted documents to reject duplicate JSON keys and NaN/Infinity tokens.
No OCR, numeric parsing, dimension association, model or network is used here.

## Three independent layers

`image_evidence` preserves source identity and original dimensions, structural evidence,
working image dimensions, two inverse 3×3 homographies, and normalization bounds.
Evidence item points are in original image pixels. Topology geometry `points_px` are
in working image pixels, u right/v down. `points_normalized` use the working
normalization bounds: `[(u-x0)/(x1-x0), (v-y0)/(y1-y0)]`. Empty point arrays represent
an unresolved interpretation; state must communicate uncertainty. No text or numeric
OCR fields exist. Numbered and unnumbered sketches use the same contract and policy.

Normalization bounds frame the same retained structural content after crop/resample;
never infer a physical scale from pixel count, image DPI or written numbers. A crop
that removes structural content requires new interpretation/review. Matrices preserve
original↔working mapping; a new capture requires its own source hash. Step 3 must
verify suggestion invariance under these transforms; Step 1 only supplies the fields
and representation test, not an implemented suggestion engine.

`topology` contains stable opaque IDs for rooms and rectangular corridor segments,
wall/interface segments, junctions, openings and connections. IDs survive edits and
are never reused for a replacement entity. Each boundary wall is stored once with
one or two owners. Node T junctions into wall segments. Supporting interfaces are
logical boundaries even when physically open. A bend uses separate rectangular
corridor segments with an `open_passage` at their interface. Connections describe
pairs of neighboring regions and reference all their separate openings; two doors
between the same rooms remain two opening IDs. A path across multiple corridor
segments is represented by multiple neighboring connections.

Each opening specifies its supporting wall/interface, two owners, and a reference
junction plus direction. Its normalized interval is `[lo,hi]` along the wall's
start→end direction. Near-edge position is `lo` from the start, or `1-hi` from the
end. The junction must be an endpoint of this noded segment; a local T reference
therefore does not silently refer to an unrelated room corner. Connection
`shared_span_normalized` is the shared part of that supporting segment in the same
parameterization, or null if unknown. It is not permission to open a passage.

Geometry provenance is `model / regularized / user`; interpretation state is
`proposed / confirmed / unknown / ambiguous / stale`. These states express review
needs, without a fabricated confidence percentage. Explicit passage evidence or a
user decision is required; proximity/intersection alone is insufficient.

`physical_design` is independent of pixel coordinates. It holds cm units, an anchor
junction and physical translation, an orthogonal global orientation, adjustable
values and separate acceptance. Orientation describes the physical design relative
to the local x-right/y-up frame; converting image v-down is not a second rotation.
The solver must provide a complete canonical layout in this physical frame.

Every adjustable has a stable ID, target, parameter, nullable value, origin,
lock, previous suggestion, authoring revision and binding revision. Origins are
`preset / proportion_suggestion / user_override`; accepting a preset does not
change that origin. `previous_suggestion` retains its value/origin/revision after
an override. A null value requires `unknown`. Lengths are positive; near-edge
offset may be zero. `global` is the reserved target for global settings.

The presets are room 500×400 cm; corridor length 400/centerline width 200 cm;
door clear width 120/height 220 cm; wall thickness 20/height 300 cm. These are
product choices, not architectural standards or image measurements. Floor thickness
must be explicitly configured using the existing runtime settings; Step 1 adds no
new implicit floor preset. Presets must not be copied independently onto every
entity and then declared valid. Relative shape/spacing and presets are soft
preferences; user locks and valid structural relationships are hard constraints.
An infeasible combination retains the draft and last valid preview.

`invalidate_bindings` creates a new revision, clears acceptance and marks affected
geometry/values stale while retaining user overrides, locks and old suggestion
bindings. Its caller supplies the dependency closure (including adjacent walls,
openings and connections); until Step 3 supplies dependency analysis, conservatively
invalidate all dependent targets. Unaffected bindings may advance to the new revision.
Never reattach a stale opening just because an old ID still exists.

`accept_revision` records a named user's acceptance of the exact revision on a copy.
It rejects unresolved/stale interpretation and values. It does not validate physical
geometry and must not be used as an export gate by itself. Any edit/recompute needs
a new revision and clears confirmation. Immutability of saved revisions, storage and
concurrent-edit enforcement are Step 5 work; helpers do not implement persistence.

## Authoring → canonical v1 adapter mapping

Step 1 defines this mapping; the executable joint-layout adapter belongs to Step 3,
with confirmation/export integration in Step 5. Do not feed v2 directly into Unreal.

| Authoring | Canonical `playablesketch-layout/1.0` |
| --- | --- |
| Source path/hash | `source.image_path/image_sha256`; `legacy_draft_path: null` |
| Authoring document/revision | Stable canonical `document_id/revision_id`, parent revision; mapping retained in sidecar |
| No OCR document | Required `observation_document_id` receives the real authoring document ID as linkage; notes explicitly identify it as shape-authoring, not observations; never fabricate an observations file |
| Physical anchor/orientation + jointly solved positions | `layout.vertices[].position_cm` in local x-right/y-up; no px→cm measurement claim |
| Noded wall/interface | Positive-axis v1 `walls` with canonical endpoints and actual owner IDs, global thickness/height |
| `room` | v1 room with cyclic counterclockwise boundary references |
| `corridor_segment` | v1 corridor with its own rectangular boundary; never merge a bend into an L polygon |
| Door/open interface | v1 opening with `wall_id`, typed owners (`corridor_segment` becomes `corridor`), clear width/height |
| Near-edge placement | `center_offset_cm = reference_from_wall_start_cm + direction × (near_edge_cm + clear_width_cm/2)` |
| Connection with N openings | N v1 passages, one per opening; no deduplication by entity pair |
| Explicit accepted design sizes | Optional v1 dimensions with truthful `configured` provenance and descriptive labels; derived coordinates/offsets use `derived`; `evidence_ids: []` |
| Accepted user geometry edits | `user_correction` provenance when directly corrected; computed geometry remains `derived`; evidence stays in authoring sidecar |
| Unaccepted proposals | Draft only; `inferred` state and `needs_review`, no accepted/validated claim |
| Snapshot acceptance | v1 review via existing `as_validated` only after complete geometry/metric validation and current revision confirmation |
| Full provenance / policy / locks / transforms / origin | Separate authoring sidecar and canonical `notes` pointer; no new unknown v1 fields |

For positive-axis wall length 400, near edge 50, clear width 120: a start reference
gives center 110; an end reference gives 290. A T reference 200 from wall start,
heading toward start, gives center 90. `near_edge_to_center` implements and checks
this arithmetic; joint containment, shared interfaces and non-overlap still require
the existing metric validator after solve. Split wall offsets must be local to the
specific supporting segment, not the full unsplit room edge. A zero edge offset need
not be emitted as a v1 Dimension (v1 dimension values must be positive); the opening
center itself still represents it correctly.

V1 `observation_document_id` is a required nonempty ID in both Python and Unreal;
there is no requirement to fabricate OCR links when all canonical evidence IDs are
empty. Supplying a v2 document as the optional `observations` argument would fail;
the adapter must leave that argument absent. External evidence verification remains
in the v2 sidecar. The existing v1 validators and parser must not be weakened.
Settings still use `source: configured`; accepted default sizes remain configured,
never `ocr` or `manual_annotation` image ground truth. All v1 field sets, dimensions,
review metadata and `validation` fields must pass existing strict checks. Engine
geometry/navigation remain `not_run` until actually checked.

## Compatibility and next steps

No original images, annotations, accepted v1 fixtures, parser fields, existing job
modes or uploads are migrated/overwritten. Existing exact measurement code remains
available. Unsupported v2 fields are rejected by v1 rather than ignored. V2 authoring
is not training ground truth for image dimensions. User corrections are only future
geometry/topology curation candidates with explicit review.

Step 2 can consume this contract for proposals, including empty/manual fallback.
Step 3 must add complete per-entity sizes, joint geometric consistency, deterministic
suggestions and a working canonical adapter. Step 4 supplies editing UI. Step 5
supplies persistence, exact-snapshot export gating and runtime acceptance. No model
accuracy, suggested-size quality, browser workflow or Unreal runtime success is
claimed by the Step 1 contract checks.
