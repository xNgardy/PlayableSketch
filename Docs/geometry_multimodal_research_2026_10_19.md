# Geometry recognition: multimodal research and proposed experiment

Research date: 2026-10-19. Recommendation only: no detector changes, model training, remote image submission, or new accuracy claims were made in this investigation.

## Decision

Test a hybrid system combining task-specific visual evidence, OCR, a vision-language model (VLM), and deterministic graph validation. Prioritize separating structural ink from grid and dimension graphics before polygonization. Use the VLM for grounded semantic proposals and ambiguity resolution; keep exact endpoints, evidence checks, and metric solving independently inspectable.

This is both **multi-model** (specialists with different responsibilities) and **multimodal** (image, text, and structured relations). Running several generic VLMs and majority-voting their JSON is not the first recommended experiment: agreement does not establish image support, and the errors may be correlated.

## What the existing project actually shows

The completed evaluation in [data_training_evaluation_v1.md](data_training_evaluation_v1.md) reports opening precision/recall/F1 of 18.4% / 79.8% / 29.9% on all 50 human originals. These are descriptive development scores, not new-writer generalization. Exact pixel topology was recovered in 7/40 human examples with region references and 0/70 synthetic images. OCR decoder fine-tuning did not train or change geometry.

Code inspection identifies these mechanisms:

- `SketchPipeline/perception/geometry.py::line_evidence`: CLAHE, line detection, and merging precede role assignment. Sufficiently long segments become `wall_candidate`, subject mainly to text-overlap and border exclusions. There is no explicit grid or dimension-graphics classifier. CLAHE may increase faint grid visibility; its causal contribution needs an ablation.
- `geometry.py::text_mask`: OCR masking protects long strokes, which can include nonstructural rails. Short real door ticks can instead be removed with nearby text. The unmasked recovery branch is useful but can reintroduce nonstructural graphics.
- `SketchPipeline/perception/openings.py`: credible collinear supports, a gap, and perpendicular endpoint context can also be supplied by dimension graphics. Nearby numeric text does not distinguish a dimension rail from a door.
- `SketchPipeline/perception/topology.py::build_topology`: false structural candidates can propagate into polygonization, producing extra regions and incorrect connectivity. Local graph plausibility alone is insufficient: a grid also contains intersections and closed rectangles.

The following diagnostic was computed from existing saved predictions, without rerunning inference. Each style covers the same 20 synthetic parent plans:

| Style | Images | Median LSD segments in working.json | Matched / predicted / reference openings | Opening precision | Opening recall |
| --- | ---: | ---: | --- | ---: | ---: |
| ink | 20 | 58 | 76 / 280 / 92 | 27.1% | 82.6% |
| pencil, with grid | 20 | 4,318 | 69 / 433 / 92 | 15.9% | 75.0% |
| photo | 20 | 71.5 | 76 / 254 / 92 | 29.9% | 82.6% |

Sources: `Saved/Evaluation/v1/baseline/SP{001..020}_{ink,pencil,photo}/{working,metrics}.json`. These style variants also differ in stroke, font, and capture characteristics. This is evidence of a difficult rendering domain, **not a controlled estimate of the isolated grid effect**.

For SP008 specifically, the saved LSD counts are 62 ink versus 5,797 pencil. Yet topology predicts 35 regions for ink, 35 for pencil, and 31 for photo, against five reference regions. Removing grid alone cannot explain or fix all failures. Dimension graphics, duplicate structural edges, opening attachment, and region decomposition also need investigation. Do not attribute every unmatched candidate to a particular cause without a labeled error audit.

## Research findings and their limits

**Typed geometric primitives are a useful direction.** GLSP predicts junctions and categorized line segments with a graph neural network. It supports learning what a segment represents, rather than treating line detection as wall recognition. Its architectural floorplan domain does not establish performance on our single-line gap/tick convention. [GLSP paper](https://arxiv.org/html/2303.03851v1).

**VLM parsing is feasible, but published tasks differ.** Vision Language Models Can Parse Floor Plan Maps demonstrates navigation planning from maps. Its method manually removes extraneous architectural markings and adds labels/door indicators. Its navigation success is not raw-sketch endpoint accuracy and does not demonstrate that a VLM will solve our annotation-versus-door problem unaided. [Primary paper](https://arxiv.org/html/2409.12842v1).

**Recent VLM vectorization is promising but data intensive.** FloorplanVLM generates structured walls, openings, and room references using Qwen2.5-VL-3B. The authors describe progressive training on Floorplan-2M and HQ-300K with 32 H200 GPUs. Their external-wall IoU is a different task/metric from our opening F1; it cannot be transferred to our drawings. Treat the shared-wall representation as a useful design reference, not a training recipe to reproduce on this Mac. Usable author weights and their input-domain suitability were not established here. [FloorplanVLM paper, especially Sections 3 and 5.1](https://arxiv.org/html/2602.06507v1).

**Evidence-gated local revision closely matches our needs.** The September 2026 SALI-FP preprint separates model proposals, deterministic admission checks, recoverable revisions, and reviewable geometry. This supports an auditable hybrid design. Its corpus output validity is not drawing-recognition accuracy, and it does not validate our custom symbols. We have not reproduced its results. [SALI-FP paper](https://arxiv.org/html/2609.25615v1).

**Human review remains useful.** Sketch2BIM studies unscaled hand-drawn plans with multimodal extraction and feedback. Its ten-plan, feedback-assisted experiment supports testing a review loop; its convergence results do not establish unattended performance on our data. [Sketch2BIM paper](https://arxiv.org/abs/2510.20838).

**Ready-made floorplan models require domain checking.** CubiCasa5K provides 5,000 densely annotated architectural plans, but its released implementation targets an older Python/PyTorch/CUDA environment. HEAT's indoor task uses point-density images and its repository includes compiled attention operations and research-use restrictions. Neither is the first drop-in replacement for our Mac-based sketch pipeline. [CubiCasa5K authors' repository](https://github.com/CubiCasa/CubiCasa5k), [HEAT authors' repository](https://github.com/woodfrog/heat).

## Proposed system

```text
Untouched RGB source + reversible working-image transforms
  |-- background/grid evidence
  |-- structural visual model: wall ink, door ticks, dimension graphics
  |-- OCR detection + alternative readings
  |-- VLM: global interpretation and selected ambiguous local regions
                 |
     Evidence fusion: typed primitives and competing hypotheses
                 |
     Shared-wall graph + opening attachment + region checks
                 |
     Existing topology review
                 |
     Step 09 dimension association and cm constraint solving
```

### 1. Conservative grid suppression

Estimate repeated line families using direction, spacing periodicity, color, contrast, and page-wide repetition. After perspective, spacing need not be globally constant; rectify a confident paper plane or use local evidence with recorded transforms. Repeated room dimensions must not be mistaken for a grid.

Generate a grid-likelihood map and an alternative geometry input. Keep original RGB for OCR/VLM and local structural recovery. Suppress only sufficiently supported background evidence; do not erase every horizontal/vertical line or replace ambiguous intersections irreversibly. Dark gray grids overlapping faint pencil walls need an uncertainty path.

OpenCV provides horizontal/vertical morphology primitives, but line extraction is not semantic separation. A blind horizontal/vertical subtraction would remove our real walls too. FFT/notch filtering may be an ablation for regular grids, not the default destructive operation. [OpenCV morphology example](https://docs.opencv.org/4.13.0/dd/dd7/tutorial_morph_lines_detection.html).

### 2. Learn structural versus annotation graphics

First test a lightweight candidate classifier using local image crops, segment features, nearby OCR, and graph context. Classes should distinguish wall, door tick, dimension rail/extension/tick, grid, text, and unknown. Neither thickness nor OCR proximity should act as an absolute rule: human walls and labels share ink, and real doors often have adjacent width text.

For broader recovery, compare a compact U-Net-style segmentation model with separate junction/endpoint heads. Predict overlapping evidence channels where layers cross; a door opening is primarily an interval/keypoint relation, not a visible foreground class to paint over. Preserve separate `door_like`, `open_passage_like`, and ambiguous hypotheses. A corridor entrance need not have door ticks. [U-Net architecture reference](https://arxiv.org/abs/1505.04597).

### 3. Give the VLM a bounded, useful role

Inputs: original full image, selected high-resolution contextual crops, candidate-ID overlays, OCR alternatives, and the explicit drawing convention. Crops need enough context to see whether a stroke separates spaces or belongs to an annotation. The model should propose typed candidate relations, disputed regions, and missing-feature search regions.

For example, request a record containing candidate ID, proposed class, associated wall/region IDs, evidence crop coordinates, and an uncertainty flag. Do not require a confident answer when strokes are ambiguous. Self-reported confidence is not a calibrated probability.

Do not restrict the entire system to accepting/rejecting existing proposals: that would cap recall at the current detector. Let an independent VLM pass or segmentation branch propose a missed-opening search region, then local image processing must verify endpoints and support. New proposals remain distinct from reviewed geometry.

Use a full-image VLM-only baseline to measure whether direct parsing is already better; compare it against candidate-assisted VLM inference. Select an exact model/version only after measuring localization, latency, memory/cost, and repeatability. A small local VLM is an experimental option; fitting weights in memory alone does not establish practical high-resolution inference on this 16 GB Mac. Hosted inference is an optional deployment choice, not a requirement. No project images were submitted to a remote model during this research.

### 4. Validate topology without inventing intent

Use typed junctions, support continuity, opening-to-wall attachment, shared boundaries, and room/corridor decomposition. Preserve multiple openings on one wall and cycles. An opening may connect a room to the exterior; an open corridor may connect interior regions without ticks. The combined outer boundary need not be rectangular.

Logical room/corridor regions are rectangular in our convention, but their raster strokes are approximate. A connected traversable area can contain several intended rectangular regions. Do not treat each polygonized face as a room automatically or force the entire connected space into a single rectangle.

Keep image topology validation separate from metric consistency. Step 09 should preserve intentional conflicting or missing dimensions, never repair them to make the model appear correct. Enforce near-opening-edge offsets, edge-to-edge wall spans, centerline junction spans, and no pixel-to-cm proportional inference. Wall thickness/height remain settings.

## Data work required before geometry training

There are 720 images but only 80 parent-plan groups (50 human + 30 synthetic geometries), and the human originals do not provide 50 independent writers. Derivatives must inherit their parent/family split.

The renderer already constructs `wall_mask`, `tick_mask`, `rail_mask`, and `text_mask`, but currently exports only walls, door_ticks, and text. Grid is painted directly on the background. **Dimension rails and grid do not currently have exported dedicated masks.** Export them in a versioned future dataset instead of silently relabeling existing background as verified negatives. At crossings, retain layered coverage and the visibility/compositing semantics.

Human sidecars contain approximate traces and opening endpoints, not complete pixel-perfect masks. Rasterized traces can provide weak supervision with explicit uncertainty/ignore bands; do not advertise them as dense GT. Review an initial subset of genuine wall/tick/annotation confusions for stronger labels, using training groups only.

Generate paired renders with geometry and stroke realization held fixed while varying grid presence/color/strength, annotation rails, shadows, and pencil contrast. The current ink/pencil/photo style comparison is confounded. Vary real wall versus dimension-line thickness independently so the model cannot learn only the synthetic renderer's color shortcut. Include hard negatives: dimension tick pairs, digits, incidental stroke breaks, and grid intersections. Also include short real wall remainders, faint real doors, and open corridors to prevent an easy precision gain through recall collapse.

Collect fresh plans from additional writers for external evaluation. A practical initial collection target is 20–30 drawings from 3–5 additional writers, with writer-separated scoring; these are proposed collection sizes, not statistically guaranteed sample requirements. VLM-assisted labels remain proposals until reviewed.

## Experiment order and selection

| Experiment | Change | Question |
| --- | --- | --- |
| E0 | Frozen current baseline | What errors exist before intervention? |
| E1 | Grid likelihood/suppression branch | How much grid contamination can be removed without losing structures? |
| E2 | E1 + typed candidate classifier | Can annotation false positives be reduced cheaply? |
| E3 | OCR + VLM-only parsing, original image | How strong is direct multimodal parsing on this convention? |
| E4 | E2 + grounded VLM proposals/audit | Does multimodal fusion improve topology over either branch alone? |
| E5 | Learned segmentation/keypoints + the same fusion | Is a denser visual model worth the additional labeling and training? |

Freeze preprocessing, matching thresholds, model snapshots, prompts, and grouping. Select thresholds and architecture on validation only. The previous test images have now been inspected for this research: subsequent comparisons on them must be labeled retrospective development results. Keep fresh external writer data untouched until choices are fixed.

Report wall length coverage, wall/annotation confusion on reviewed labels, opening precision/recall/F1 and endpoint error, region F1, exact region/connectivity topology, and false positives per image by cause. Add actual reviewer edits/time, p50/p95 latency, failed/unknown output rate, and memory/API cost where applicable. Empty/error outputs remain in denominators. Report real and synthetic cohorts separately. Use parent-plan uncertainty intervals; new-writer results require writer-level separation. Good JSON/schema validity does not count as correct geometry.

Provisional adoption gates: improve opening precision and exact topology on validation; predeclare a maximum two-percentage-point opening-recall loss, inspect uncertainty and all newly missed real doors/corridors; preserve OCR numeric accuracy; and reduce measured review effort within the selected runtime budget. These are engineering targets, not measured outcomes or a claim that small-sample changes are significant.

**Recommended next implementation:** instrument and label error causes, add reversible grid evidence, then run the typed-candidate and grounded-VLM pilot side by side. Use the results to decide whether to train dense geometry heads. Preserve the current baseline and mandatory topology review throughout.
