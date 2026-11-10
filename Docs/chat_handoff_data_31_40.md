# Chat handoff — prepare Data_31–40

Updated: 2026-10-16. Repository: `/Users/pelinsukaleli/PlayableSketch`.

## Current state

The user is building a sketch-to-Unreal authoring pipeline. Current architecture: local English web UI, local Python processing, mandatory topology review after every upload, then planned metric reconstruction/review and existing Unreal JSON import. Pretrained OCR and geometry heuristics are in use; this project has not trained OCR or wall/room model weights. Dataset curation does not automatically train anything.

Step 08 topology and correction UI are implemented. Step 09 dimension association/constraint solving and metric-review integration remain the next principal implementation work. The roadmap continues through Step 14; some Step 10/11 interaction and upload infrastructure was implemented early. Read `Docs/product_architecture.md` and the roadmap's dated implementation note before interpreting older status paragraphs.

The present request is to describe the next ten drawings, not to implement a new model or change the pipeline. The user will draw them and provide actual files later.

## Read these first

1. `Docs/drawing_convention_v1.md` — authoritative measurement and notation rules.
2. `Data/annotation_review_11_20.md` and `Data/annotation_review_21_30.md` — actual-image interpretations override requested recipes.
3. `Data/annotations/v1/README_tablet_21_30.md` — files, commands, annotation limitations.
4. `Docs/product_architecture.md` and `Docs/SketchToLevel_Implementation_Guide_TR.md` — current architecture, stage boundaries and roadmap.
5. `Docs/data_21_30_drawing_brief.md` — an earlier request, not ground truth. In particular Data_25/27/29 differ in the uploaded images.

For later annotation work, inspect `tablet_11_20.source.json`, `tablet_21_30.source.json`, `manifest_all_30.json`, `SketchPipeline/fixtures/build_tablet_references.py`, `build_tablet_21_30_references.py`, `export_ocr_crops.py` and schemas under `SketchPipeline/schemas/`.

## Dataset state

- Original images Data_1–30 are present in `Data/`; Data_30 is `Data/Data_30.png`, not its stale Downloads path.
- Manual observations and pixel sidecars live in `Data/annotations/v1/`. Metric observations/drafts/accepted references live in `Data/ground_truth/v1/`.
- `manifest_all_30.json`: 30 images, 178 visible text regions, development-only. Older manifests were preserved; the default `manifest.json` still selects the original ten photos. Pass the combined manifest explicitly.
- Data_21–30: 61 texts, 11 openings, 21 region polygons; 8 complete metric references (21–28), Data_29 conflicting and Data_30 incomplete. OCR curation export: 61 crops, 49 single-line TSV rows, 12 multiline blocks. No training performed.
- Actual Data_25 bottom-to-top sequence: solid 140, opening 85, solid 175, opening 105, solid 95, total 600.
- Actual Data_27 lower spans: left 240, right 210. With left bottom y=0, right bottom is y=30. Do not replace the 240 label with the old brief's 210.
- Data_28's numbers imply right bottom 120 below left and right top 60 above left, irrespective of pixel proportions.
- Actual Data_29 has no opening, only widths 300/500, common depth 600 and conflicting outer width 850. The overtraced shared-wall patch is not a door.
- Data_30 has complete room sizes and door width 120 but no written location. Opening center and missing edge offset remain null; do not use visual centering to fill them.
- Earlier negatives: Data_9/19 conflicting; Data_10/20 incomplete. Data_5 is metrically consistent after the author's edge-offset correction but physically corner-blocked; metric acceptance is not a playability guarantee.
- Tablet images are from the same author. Different backgrounds/digit combinations add coverage, not an independent unseen-writer holdout. Keep each plan, its crops and recaptures together across splits.

## Rules for future drawings

- Each room/corridor segment is rectangular; overall footprint may be orthogonal and nonrectangular. Multiple rooms and different alignments are allowed. Avoid individual L-shaped rooms, diagonals, true curved walls, stairs or multiple floors in v1.
- Single wall centerlines; shared walls drawn once. Room sizes, corridor widths/lengths and corner-to-T-junction spans use centerline measurements. Door width is clear opening width.
- Paper offsets are corner/local T junction → near door edge, never center. Specify which corner/junction and direction. The internal center field is derived from the edge offset and half the clear width only when the constraints determine it.
- Between two openings on one uninterrupted room side, write the edge-to-edge solid wall length. If a new room boundary/T junction lies between them, prefer local junction-to-opening spans.
- Corridor-side solid spans end at centerline junctions, not at the clear entrance edge. Derive clear entrance width from corridor centerline width minus configured wall thickness.
- Use explicit `cm`. Sketches need not be to scale, but arrange the drawing to agree qualitatively with the requested relative positions where practical. Include full width/depth and enough local spans to uniquely determine intended placements and openings in valid cases.
- Use ticks/extension lines to disambiguate partial/total spans and offsets. Separate label text from walls and door marks. If asking for vertical text, explain that the whole label can be rotated; avoid accidentally requesting stacked multiline text for a single-line OCR case.
- Heights/thickness are settings; Start/Goal chosen during review. Do not write them on these drawings.
- Keep openings away from corners and adjacent T-junction wall caps; clear widths should remain usable at the reference 20 cm thickness. Every intended connection needs a visible marked door or explicit open corridor entrance.
- Never fabricate future labels/ground truth before actual images arrive. Actual images override any recipe, preserving missing/conflicting data.

## Desired Data_31–40 coverage

Give ten concrete, distinct drawing recipes in clear Turkish with English technical terms. Include 3–6 rooms in several examples, direct shared-wall connections, horizontal and vertical corridors, multiple rectangular corridors, unequal room sizes and staggered alignments. Include branching layouts, T junctions, multiple openings on a shared wall and a cycle if it can be drawn within rectangular-region rules without ambiguity. Do not turn corridor bends into an unsupported L-shaped region; decompose them explicitly if used.

Most cases should be valid and fully constrained. One clearly identified dimension-conflict case and one missing-dimension case can exercise review. Avoid repeated near-identical two-room plans. Difficulty should grow gradually, with enough spacing to keep dimensions readable. Geometric variety does not imply the present automatic detector will recover every new layout; these are reference/evaluation coverage for future improvements.

For each case explain the layout, room width×depth, exact connection pairs, door clear widths, offset reference/direction, corridor dimensions, local corner/junction spans and where each label goes. A compact coordinate table or ASCII plan can help the author draw; derived checks/coordinates must be clearly distinguished from numbers to write. Check all totals, offsets, room overlaps, shared spans, connection widths and remaining wall lengths before proposing the recipe. Never assume an unlabelled door or corridor is centered in order to make a valid case solvable.

The immediate deliverable is a drawing brief, optionally saved as `Docs/data_31_40_drawing_brief.md`, and a readable explanation to the user. Preserve existing images, annotations, UI, user drafts, maps and unrelated code.

## Verification commands for later work

```sh
Saved/Step07/python/bin/python -m SketchPipeline.fixtures.build_tablet_references --check
Saved/Step07/python/bin/python -m SketchPipeline.fixtures.build_tablet_21_30_references --check
Saved/Step07/python/bin/python -m SketchPipeline.preprocessing.dataset --manifest Data/annotations/v1/manifest_all_30.json
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
```

Latest review is `Saved/Annotations/tablet-21-30-v1/final-review/index.html`; OCR crops are `final-ocr/`. Final verification: 135 Python tests, four Unreal import automation tests and Mac Development Editor build passed; all 144 protected pre-existing images/JSON files remained unchanged. Results and logs are under the same batch directory. Runtime NumPy determinant warnings were observed in OCR crop rectification; exported homographies are finite and crops were visually checked. Do not reinterpret this warning as a reason to alter labels or image content.
