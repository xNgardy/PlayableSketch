# L corridor support and drawing pack

4 November 2026. The supported-corridors / corridor-passages production decoder
now runs observed parallel-wall recovery with separate segments at bends. Original
model regions are retained unchanged; new regions are appended as proposals.
The decoder diagnostic version is 2.7. Legacy, U-Net and other decoding modes
retain their existing behavior.

For interfaces involving newly recovered corridors, an additional observed-ink
check can propose an open passage without a learned interface response. It checks
92% clear coverage and an 85% continuous clear run across the shared span in a
normal ribbon. Existing door/opening proposals are preserved. A coherent crossing
wall or partially blocked span fails this fallback. This does not classify doors,
create metric scale or automatically accept a plan.

## Verification

- 35 relevant unit tests passed, including closed and obstructed interfaces,
  duplicate suppression, transformed evidence coordinates, blank images, open
  endpoints and two nonoverlapping L segments.
- The saved deneme_1 image produces 3 rooms, 3 corridor segments and 5 proposed
  open passages. All six regions are connected in the proposal graph, including
  the lower elbow and the right room entrance. Contract validation passes.
- The two upper door symbols still decode as open passages, not doors. The graph
  result is not proof of collision clearance, metric validity or runtime traversal.
- A retrospective replay of 110 cached human/synthetic cases changes only Data_7.
  Scorable region/opening/attachment metrics stay unchanged; human test region F1
  0.9286, attachment F1 0.9143, synthetic region F1 0.9063. Synthetic false
  connections remain 1. Data_7 lacks region reference; its new corridor cannot be
  counted as a verified gain. This is not a blind evaluation.
- Frozen predictions, metrics and evaluated source snapshots:
  Saved/ShapeFirst/corridor_junctions/v1/regression/.
- Target prediction: Saved/ShapeFirst/corridor_junctions/v1/deneme_1/prediction.json.

## Activation

No existing accepted job or Unreal export is overwritten. The currently running
Python server may still have version 2.6 loaded. Stop its launcher terminal with
Control-C and reopen Start Sketch Workspace.command, then analyze the drawing as
a new job. The new source is selected by the existing DINO launcher; no Unreal
rebuild is needed for this Python decoder update. Review and confirm proposals
before export as usual.

## Twenty new hand drawings

The 22-page PDF output/pdf/PlayableSketch_20_Cizim_Rehberi.pdf contains instructions,
an overview and one full page for every plan. Editable diagrams and the fixed
12/4/4 source-drawing split are in Docs/drawing_pack_20/.

The diagram coordinates are not ground truth for future photographs. Actual photos
must be traced and checked after arrival. Augmentation must transform the image
and every geometric label with the same coordinate mapping. Keep all derivatives
of one original in the same split. Planned initial augmentation: 20 variants per
training original, 240 training derivatives plus 12 original training images;
4 validation and 4 test originals stay outside training. These are variations,
not 240 independent drawings. No new user data has arrived and no training or
photo augmentation has run yet.
