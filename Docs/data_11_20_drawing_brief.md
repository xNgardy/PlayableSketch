# Data_11–Data_20: tablet drawing brief

These are requested drawings, not annotations of images already received. Ground truth must later describe the actual uploaded images; do not replace visible values with this brief if the drawing differs.

## Shared drawing rules

- One plan per image. Save under `Data/Data_11.png` through `Data/Data_20.png`; JPEG is also accepted. Use the same case-sensitive `Data_` naming as the existing images.
- Export the drawing directly from the tablet as an opaque PNG where possible, without app controls. Use a light gray, pale beige or pale blue background with dark strokes. Keep this batch's background and pen style consistent; a dark background with light strokes should be tested separately.
- Draw by hand. Disable straight-line/shape correction and use handwritten labels rather than typed text. Small natural imperfections are useful; do not deliberately make labels illegible.
- Intended walls are horizontal/vertical, single centerlines. Shared walls are drawn once. Leave space outside the plan for dimensions; omit grid lines, decorative text and color-coded semantics in this batch.
- All numbers on the drawing include `cm`. Place dimensions parallel to the measured span. Width means horizontal extent; depth means vertical extent. Room/corridor dimensions use boundary-centerline spans, not clear interior sizes.
- Draw doors as physical gaps with short perpendicular marks at both ends; label clear width, preferably `D 110 cm`. Location labels describe the adjacent solid wall span: corner/junction to the near opening edge, or one opening's end edge to the next opening's start edge. Identify both endpoints with clear dimension/extension marks outside the wall when possible. A label between two openings measures their edge-to-edge separation, not a cumulative distance from a room corner.
- Corridors in Data_16 and Data_17 have open entrances, not doors. Draw the room walls interrupted across each entrance and the corridor's two side boundaries. Label corridor centerline width; do not label it as a door clear width or add door endpoint marks there.
- Sketch proportions do not need to match cm values. Topology, shared junctions and intended alignments must remain clear. No Start/Goal or height/thickness labels are needed.
- A/B/C below explain the brief; they do not need to be written inside the drawing.

## Data_11 — one rectangle, repeated measurements

- One room: **470 cm wide × 680 cm deep**. No opening.
- Write `470 cm` beside both horizontal walls and `680 cm` beside both vertical walls.
- Purpose: repeated, consistent dimensions; vertical text recognition; one closed region.

## Data_12 — proportions intentionally different from measurements

- One room: **930 × 560 cm**. No opening.
- Draw its outline nearly square despite these dimensions.
- Write `930 cm` above the top span and `560 cm` beside the right span. Leave opposite walls unlabeled.
- Purpose: metric measurements must come from text, not image aspect ratio.

## Data_13 — adjacent rooms, off-center door

- A on the left: **650 × 480 cm**. B on the right: **390 × 480 cm**. Align their top and bottom boundaries.
- Their single shared vertical wall contains a **110 cm clear-width door**.
- Lower door edge: **175 cm above the bottom shared corner**. Opening interval [175, 285] cm; derived center 230 cm.
- Label each room's width, the common depth, door width and edge offset.
- Purpose: shared-wall deduplication, vertical opening and explicit edge-offset association.

## Data_14 — vertically stacked rooms

- A below: **840 × 350 cm**. B above: **840 × 570 cm**. Align left and right boundaries.
- Shared horizontal wall: **130 cm clear-width door**, near edge **610 cm from its left corner**. Opening interval [610, 740] cm; derived center 675 cm.
- Label `840 cm` at the bottom and top outer spans; label the two depths separately, then the door width/offset.
- Purpose: horizontal opening, vertical room arrangement and unequal depths.

## Data_15 — two doors in one shared wall

- A left: **760 × 520 cm**. B right: **440 × 520 cm**. Align top/bottom.
- Shared vertical wall has two separate doors:
  - Lower: width **90 cm**, near edge **140 cm from the bottom shared corner**; interval [140, 230], derived center 185.
  - Upper: width **120 cm**, with **150 cm of solid wall between the lower door's upper edge and the upper door's lower edge**. Its derived interval is [380, 500] and center is 440; do not write the cumulative 380 cm as the intervening wall label.
- Label the bottom solid span `140 cm`, lower opening `90 cm`, intervening solid span `150 cm`, upper opening `120 cm`, and top remaining span `20 cm`. These sum to the room depth of 520 cm.
- Purpose: two different openings connecting the same room pair, without merging them.

## Data_16 — horizontal corridor with open entrances

- A left: **450 × 650 cm**. B right: **600 × 650 cm**. Align room tops and bottoms.
- A rectangular horizontal corridor connects them: **350 cm long × 200 cm centerline width**.
- Each near clear-entrance edge is **325 cm from the bottom corner of its room's connecting wall**. With the reference 20 cm thickness, clear entrance width is 180 cm, derived center y=415 cm and corridor centerline bounds y=315–515 cm. The corridor is not centered vertically.
- Both entrances are open passages. No doors or door-width annotations.
- Label both room widths, room depth, corridor length/width and entrance edge offsets.
- Purpose: three regions, two passage connections; corridor width distinct from a door clear width.

## Data_17 — vertical corridor, shifted right

- A below: **620 × 410 cm**. B above: **620 × 730 cm**. Align left/right boundaries.
- Vertical rectangular corridor: **280 cm long × 180 cm centerline width**.
- At both room interfaces, the near clear-entrance edge is **260 cm from the left corner**. At reference thickness 20 cm, clear width is 160 cm and the derived entrance center is x=340 cm. The corridor is right of the rooms' horizontal midpoint; its side centerlines are x=250 and x=430 cm.
- Both entrances are open passages. No doors.
- Label room widths/depths, corridor length/width and the entrance edge offsets.
- Purpose: vertical corridor and placement independent of room centers.

## Data_18 — T junction, total and partial dimensions

- Start with an outer rectangle **900 × 700 cm**.
- A full-height internal vertical wall lies **360 cm from the left boundary**.
- In the right part, draw a horizontal partition **280 cm above the bottom boundary**, ending at the internal vertical wall. This makes a T junction.
- Regions: left A **360 × 700**, lower-right B **540 × 280**, upper-right C **540 × 420** cm.
- Door A–B: **100 cm** wide, near edge **140 cm above the bottom shared corner**; interval [140, 240] cm.
- Door A–C: **120 cm** wide, with its lower edge **210 cm above the T junction**, which is the upper-right room's bottom boundary. Write `210 cm` on that local wall span. The opening occupies y=490–610 cm above the outer bottom boundary; derived center y=550 cm. The intervening room boundary makes the junction the natural reference; do not replace this local measurement with a cumulative span across the junction.
- Label top partial widths `360 cm` and `540 cm`; bottom total width `900 cm`; left total depth `700 cm`; right partial depths `280 cm` and `420 cm`. Use ticks/extension lines to show each measured span. Add door widths and offsets.
- Purpose: three rectangular regions, two connections and consistent total/partial constraints (360+540=900; 280+420=700).

## Data_19 — deliberate dimension conflict

- One rectangle; no opening.
- Top full span: **720 cm**. Bottom full span: **690 cm**. Both vertical full spans: **460 cm**.
- Preserve this contradiction deliberately. Do not change the outline to a trapezoid.
- Expected result: topology can contain one rectangle, but no rectangular metric layout satisfies all labels; dimension conflict requires correction.

## Data_20 — one missing independent dimension

- Two adjacent rectangular rooms, aligned at top/bottom. A left: **530 × 470 cm**.
- Leave B's horizontal width unlabeled. Do not write overall plan width or another dimension that would determine B's width.
- Shared vertical wall: **100 cm clear-width door**, near edge **235 cm above the bottom shared corner**; interval [235, 335] cm, derived center 285 cm.
- Label A's width/depth and the door width/offset. B's depth is implied by the shared aligned boundaries; its width remains unresolved.
- Expected result: two connected regions, missing B width; no invented confirmed width from pixel proportions.

## How this batch will be used

First measure the frozen current pipeline on these new images, before tuning it on them. Evaluate text detection, text recognition, geometry and association separately. Manual text crops can diagnose recognition; complete-image inference is still required to measure detection/end-to-end behavior.

These ten tablet drawings from one writer do not establish generalization to other writers or photographed paper. If they later enter training or repeated tuning, treat them as development data and retain a different real holdout. Keep a plan's crops, recaptures and augmented variants together in one split.

Use each image for multiple labels: text polygons/transcripts for OCR; walls/junctions/openings/regions for geometry; verified text-to-span associations for the metric stage. Do not infer OCR labels from the requested values in this document without checking the image.

## Actual uploaded batch review — 2026-10-16

The source images are now annotated. Their 325/260 cm corridor-side labels terminate at T junctions and are recorded as solid wall centerline spans. This supersedes the clear-entrance-edge interpretation in the requested Data_16/17 recipes above. Data_18 actually labels the lower-right width as 540 cm, not an outer total of 900 cm. Actual images and explicit endpoint scopes determine the references; see `Data/annotation_review_11_20.md`.
