# Data_31–40 drawing brief

Prepared 2026-10-16. **Drawing instructions only: not annotations, ground truth, generated drawings, or training input.** Actual uploaded images and visible measurements will override every recipe below.

## Basis and current project state

Read together: [handoff](chat_handoff_data_31_40.md), [Drawing Convention v1](drawing_convention_v1.md), [11–20 review](../Data/annotation_review_11_20.md), [21–30 review](../Data/annotation_review_21_30.md), [annotation README](../Data/annotations/v1/README_tablet_21_30.md), [product architecture](product_architecture.md), [roadmap](SketchToLevel_Implementation_Guide_TR.md), and [previous brief](data_21_30_drawing_brief.md). The roadmap's 16 October implementation note takes precedence over older status paragraphs: topology review exists; Step 09 metric solving and metric review/integration remain principal next work. These examples expand reference/evaluation coverage; they do not promise automatic detector success. Data_1–30 remain in `Data/annotations/v1/manifest_all_30.json`; this brief does not modify that manifest.

## Rules applying to every drawing

- Make one image per Data number. Use dark strokes, a light background and generous whitespace. Draw natural approximate proportions; the written numbers determine metric geometry. All written dimensions have a space and `cm`.
- Each room and each corridor is rectangular. Width is horizontal, depth vertical. Draw one centerline per physical wall and each shared wall only once. An interrupted boundary is still logically rectangular. Do not draw dimension lines as extra physical walls.
- A door is a gap with two short perpendicular endpoint ticks. Write its **clear width** beside the gap, parallel to it. No swing arcs. Offsets end at the **near opening edge**, never the center. A top/down offset ends at the upper edge; a right/left offset ends at the right edge.
- A corridor entrance is an open passage spanning its two boundary centerline junctions. Do not draw a closing wall across it or add door ticks/door widths. The logical region interface continues across the opening. Write corridor **centerline width**, not clear width. Corner-to-corridor spans terminate at centerline T junctions.
- For partial spans, draw a separate dimension rail with endpoint ticks/extension lines identifying both targets. Keep its ink clear of walls. Between two doors without an intervening junction, a solid-wall label is edge-to-edge. With an intervening room boundary, use the local junction instead.
- Room IDs A–F and corridor IDs H/V are explanatory only: **do not write IDs, coordinate axes, coordinate tables, equations, status words, or check values on the drawing**. No wall thickness/height, Start or Goal labels. Those are settings/review choices.
- **Standard room-label placement:** for every room in a size table, write its width on a horizontal dimension rail just inside the bottom of that room, extending to its full left/right boundary centerlines. Write its depth on a vertical rail just inside its left side, extending to its full bottom/top centerlines. These rails measure the full room even if an endpoint wall contains a gap or T junction. Rotate the entire vertical label; do not stack its digits. Move the rail farther into that room when needed to avoid door/local-span labels. Every table row requires both labels, including repeated values.
- **Standard corridor-label placement:** for a horizontal corridor, write length on an external horizontal rail just below its lower boundary, from room interface to room interface; write width across the corridor near its midpoint on a vertical rail between boundary centerlines. For a vertical corridor, write length just left of its left boundary on a vertical rail between room interfaces; write width across its midpoint on a horizontal rail. Keep rails detached from physical walls. Data_40 deliberately omits only its corridor length.
- Every number listed in a **Write** instruction is a paper label, once at that target. Values in **Check only** and coordinate tables are exclusively drafting/audit aids. Do not add derived remaining spans unless explicitly requested.
- Coordinates below use x right and y up, in cm. Bounds are wall centerlines, not faces. They demonstrate consistency; they are **not a coordinate transcription task**. Alignment means visibly coincident corners/collinear walls as instructed, not approximate equality guessed from image proportions.
- The eight valid cases are fully constrained up to an arbitrary global origin. No door or corridor uses an unstated centering assumption. At reference wall thickness 20 cm, the corridor clear widths below are centerline width minus 20. Those are checks, not paper labels or a playability certificate.

## Data_31 — three-room ascending stagger, two direct doors

### 1. Layout and drawing order

1. Draw tall A on the left.
2. Attach shorter B to the middle of A's right wall. B's bottom starts **120 above A's bottom**, marked by a T junction; B's top stops below A's top.
3. Attach C to B's right wall. C's bottom starts **80 above B's bottom**; C's top extends above both other tops. The outline steps upward.
4. Draw one door in A–B and one in B–C; no corridor. Preserve solid wall outside each shared interval.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 480 × 600 cm |
| B | 360 × 420 cm |
| C | 560 × 500 cm |

### 3–6. Connections and exact local labels

| Target | Write | Exact reference and label location |
|---|---|---|
| B placement on A right | `120 cm` | A bottom-right corner upward to B bottom-left T junction; beside that solid span |
| C placement on B right | `80 cm` | B bottom-right corner upward to C bottom-left T junction; beside that solid span |
| A–B door clear width | `110 cm` | Beside gap on their vertical shared wall |
| A–B door location | `120 cm` | B bottom-left junction upward to lower door edge; rail on B side of wall |
| B–C door clear width | `130 cm` | Beside gap on their vertical shared wall |
| B–C door location | `150 cm` | C bottom-left junction upward to lower door edge; rail on C side |

No corridor labels. The placement `120` and door-offset `120` are two distinct labels with different endpoints.

### 7. Check only — do not write

| Region | x interval | y interval |
|---|---|---|
| A | 0–480 | 0–600 |
| B | 480–840 | 120–540 |
| C | 840–1400 | 200–700 |

A–B shared span y=120–540, length 420: 120 solid + 110 opening + 190 solid. Door y=240–350, center 295. A right wall below/above B: 120/60.

B–C shared span y=200–540, length 340: 150 solid + 130 opening + 60 solid. Door y=350–480, center 415. B right below C: 80; C left above B: 160. Room interiors do not overlap.

### 8. Expected result

**Valid, fully constrained:** A–B–C connected by two direct doors. Relative vertical positions follow the local placement labels, not sketch scale.

## Data_32 — four-room branching hub and local T-junction offsets

### 1. Layout and drawing order

1. Draw hub A. Attach B to the lower part of its right side, with B's bottom collinear with A's bottom.
2. Attach C above B, sharing B's entire top side. C's top is collinear with A's top. C extends farther right than B. The B/C boundary terminates at A's right wall as a T junction.
3. Place D on A's top side, inset **100 from A's top-left corner**, leaving room on the right too.
4. Add A–B, A–C and A–D doors. The B–C shared horizontal wall stays solid: touching rooms need not connect.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 700 × 800 cm |
| B | 420 × 320 cm |
| C | 560 × 480 cm |
| D | 500 × 360 cm |

### 3–6. Connections and local labels

| Target | Write | Exact reference and placement |
|---|---|---|
| D placement | `100 cm` | A top-left corner rightward to D bottom-left T junction, above A's top-left solid span |
| A–B width / offset | `100 cm`; `80 cm` | Gap width; then A/B common bottom corner upward to lower gap edge, beside lower shared wall |
| A–C width / offset | `120 cm`; `160 cm` | Gap width; then B/C/A T junction upward to lower gap edge, on C side |
| A–D width / offset | `130 cm`; `110 cm` | Gap width; then D bottom-left T junction rightward to left gap edge, inside D near its bottom |

Do not replace the `160 cm` local offset with an A-bottom cumulative offset or a door-to-door distance across the B/C boundary. No corridors.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–700 | 0–800 |
| B | 700–1120 | 0–320 |
| C | 700–1260 | 320–800 |
| D | 100–600 | 800–1160 |

A–B: y=80–180, center 130; shared 320 = 80+100+140. A–C: y=480–600, center 540; shared 480 = 160+120+200. A–D: x=210–340, center 275; shared 500 = 110+130+260. A top outside D: 100 left, 100 right; this symmetry follows labels/widths. B/C share x=700–1120 (420), with no opening. No interior overlap.

### 8. Expected result

**Valid, fully constrained:** hub A branches to B, C and D. B–C adjacency does not add a fourth connection.

## Data_33 — horizontal corridor and an upper direct-door branch

### 1. Layout and drawing order

1. Draw A left and taller B right, separated horizontally.
2. Draw rectangular H between A's right and B's left, with open entrances. Its lower junction is **170 above A's bottom**, **260 above B's bottom**. B's bottom is therefore lower than A's; its top is slightly higher.
3. Attach D above A with their left outer walls forming one continuous vertical line; D is narrower, leaving an exposed part of A's top on the right.
4. Add A–D door; no doors at H entrances.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 520 × 640 cm |
| B | 680 × 740 cm |
| D | 400 × 360 cm |

### 3–6. Connections, corridor and paper labels

- H: write **`300 cm` length**, **`200 cm` centerline width**, using standard corridor rails. Connections: A–H and H–B, both open passages.
- Write **`170 cm`** along A right wall from its bottom-right corner upward to H's **lower centerline T junction**.
- Write **`260 cm`** along B left wall from its bottom-left corner upward to H's lower centerline T junction.
- A–D: write **`110 cm`** beside horizontal door gap; write **`140 cm`** from their common left corner rightward to the gap's left edge, on D's bottom side.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–520 | 0–640 |
| H | 520–820 | 170–370 |
| B | 820–1500 | −90–650 |
| D | 0–400 | 640–1000 |

A corridor-side chain: 170+200+270=640. B: 260+200+280=740. B is 90 lower, 10 higher at top. H clear width at t=20: 180. A–D shared span 400 = 140+110+150; door x=140–250, center 195. A top right exposed span 120. No overlap; H does not touch D.

### 8. Expected result

**Valid, fully constrained:** B–H–A–D. H is neither centered in A nor positioned by clear-edge offsets.

## Data_34 — vertical corridor with horizontal stagger and a side room

### 1. Layout and drawing order

1. Draw wide A below and narrower B above, with vertical separation.
2. Draw rectangular V from A top to B bottom. Its left junction is **430 right of A's left side**, **180 right of B's left side**. B starts to the right of A and extends past A's right edge.
3. Attach C to B's right side; their top walls meet collinearly at a common corner. C is shallower than B.
4. Leave V entrances open; add one B–C door.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 760 × 360 cm |
| B | 600 × 540 cm |
| C | 420 × 420 cm |

### 3–6. Connections, corridor and paper labels

- V: **`290 cm` length**, **`200 cm` centerline width**, standard vertical corridor rails. A–V and V–B are open passages.
- On A top, write **`430 cm`**, A top-left corner rightward to V left centerline T junction.
- On B bottom, write **`180 cm`**, B bottom-left corner rightward to V left centerline T junction.
- B–C: write **`110 cm`** beside the vertical gap. Write **`90 cm`**, common top corner **downward to upper opening edge**, alongside the upper solid wall on C side.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–760 | 0–360 |
| V | 430–630 | 360–650 |
| B | 250–850 | 650–1190 |
| C | 850–1270 | 770–1190 |

A top: 430+200+130=760. B bottom: 180+200+220=600. B left displacement 250. V clear width 180 at t=20. B–C shared y=770–1190, length 420: bottom 220 + opening 110 + top 90. Door y=990–1100, center 1045. B's right wall below C is 120. No overlap.

### 8. Expected result

**Valid, fully constrained:** A–V–B–C. Vertical corridor position follows two local horizontal spans.

## Data_35 — four-room cycle with unequal upper depths

### 1. Layout and drawing order

1. Draw bottom A left, B right, bottoms/tops aligned. Draw their shared wall once.
2. Put C directly above A with the same left/right boundary lines. Put D directly above B with the same left/right boundary lines. The C/D bottom line is the A/B top line.
3. Make C taller than D, producing an upper step. The central vertical wall passes through a four-way junction at the common row boundary; D's top terminates against C as a T junction.
4. Add four doors A–B, B–D, D–C and C–A. They form a genuine cycle. Keep all junctions clear of gaps.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 450 × 380 cm |
| B | 650 × 380 cm |
| C | 450 × 540 cm |
| D | 650 × 460 cm |

### 3–6. Direct-door labels

| Door | Clear width to write | Offset to write; endpoints/direction |
|---|---|---|
| A–B | `100 cm` | `100 cm`: bottom shared corner upward to lower edge |
| B–D | `120 cm` | `250 cm`: B top-left central junction rightward to left edge |
| D–C | `120 cm` | `100 cm`: D top-left T junction downward to upper edge |
| C–A | `100 cm` | `160 cm`: common left corner rightward to left edge |

Write each offset beside its own solid span on the named room side; write each width beside its gap. No corridors. In particular D–C is referenced to D's top junction, not C's higher top.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–450 | 0–380 |
| B | 450–1100 | 0–380 |
| C | 0–450 | 380–920 |
| D | 450–1100 | 380–840 |

A–B shared 380: 100+100+180; y=100–200, center 150. B–D shared 650: 250+120+280; x=700–820, center 760. C–D shared 460: 240+120+100; y=620–740, center 680. A–C shared 450: 160+100+190; x=160–260, center 210. C extends 80 above D. All four regions are disjoint in their interiors. Cycle A→B→D→C→A has no corridor or missing connection.

### 8. Expected result

**Valid, fully constrained**, one four-room cycle. No rule requires the complete outline to be rectangular.

## Data_36 — four rooms, two separate horizontal corridors and a branch

### 1. Layout and drawing order

1. Draw A left, B middle and C right, with two separate horizontal gaps between rooms. B and C have different bottom/top levels from A.
2. Connect A to B through lower H1, and B to C through higher H2. Each is its own rectangular region. Do not join them into an L-shaped corridor inside B; B is the connecting room.
3. Attach D to B's top with its left edge **50 right of B's left edge** and add B–D door.
4. Draw all four corridor entrances open.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 500 × 650 cm |
| B | 600 × 700 cm |
| C | 460 × 720 cm |
| D | 400 × 370 cm |

### 3–6. Corridor, placement and door labels

| Target | Write | Location/endpoints |
|---|---|---|
| H1 | `300 cm` length; `200 cm` width | Standard horizontal corridor rails |
| A→H1 lower junction | `150 cm` | A bottom-right corner upward to lower centerline junction |
| B→H1 lower junction | `100 cm` | B bottom-left corner upward to lower centerline junction |
| H2 | `380 cm` length; `240 cm` width | Standard horizontal corridor rails |
| B→H2 lower junction | `350 cm` | B bottom-right corner upward to lower centerline junction |
| C→H2 lower junction | `180 cm` | C bottom-left corner upward to lower centerline junction |
| D placement | `50 cm` | B top-left corner rightward to D bottom-left junction |
| B–D door | `110 cm` clear width; `90 cm` offset | Width beside gap; offset from D bottom-left junction rightward to left edge |

Connections: A–H1–B–H2–C and B–D. No other doors.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–500 | 0–650 |
| H1 | 500–800 | 150–350 |
| B | 800–1400 | 50–750 |
| H2 | 1400–1780 | 400–640 |
| C | 1780–2240 | 220–940 |
| D | 850–1250 | 750–1120 |

H1 wall chains: A 150+200+300=650; B 100+200+400=700. H2: B 350+240+110=700; C 180+240+300=720. Clear widths at t=20: 180/220. B top: 50+400+150=600. B–D shared 400: 90+110+200; door x=940–1050, center 995. Region interiors do not overlap; D does not touch either corridor or C.

### 8. Expected result

**Valid, fully constrained:** two corridor rectangles at different heights and a direct-door branch at B.

## Data_37 — five rooms and two parallel vertical corridor branches

### 1. Layout and drawing order

1. Draw broad hub A below. Draw two separate vertical corridors above it, V1 left and V2 right, with solid wall between their entrances.
2. V1 leads to B; V2 leads to C. B's left side aligns with A's left side. C starts well to the right of B and higher than B. Do not connect B and C across the empty gap.
3. Attach D to A's left side, its bottom **80 above A's bottom**.
4. Attach E to C's right side with collinear top walls; E is shallower. Add A–D and C–E doors. All corridor entrances remain open.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 900 × 500 cm |
| B | 420 × 420 cm |
| C | 600 × 520 cm |
| D | 400 × 340 cm |
| E | 360 × 400 cm |

### 3–6. Corridor, junction and door labels

| Target | Write | Exact endpoints/location |
|---|---|---|
| V1 | `280 cm` length; `200 cm` width | Standard vertical rails |
| V1 on A top | `120 cm` | A top-left corner rightward to V1 left centerline junction |
| V1 on B bottom | `120 cm` | B bottom-left corner rightward to V1 left centerline junction |
| V2 | `360 cm` length; `220 cm` width | Standard vertical rails |
| V2 on A top | `260 cm` | V1 **right** centerline junction rightward to V2 **left** centerline junction; beside intervening solid wall |
| V2 on C bottom | `80 cm` | C bottom-left corner rightward to V2 left centerline junction |
| D placement | `80 cm` | A bottom-left corner upward to D bottom-right junction |
| A–D door | `100 cm` width; `100 cm` offset | Gap width; D bottom-right junction upward to lower edge |
| C–E door | `120 cm` width; `80 cm` offset | Gap width; common top corner downward to upper edge |

The `260 cm` corridor-to-corridor solid span ends at **centerline junctions**, not clear entrance edges. It is not a door-to-door measurement. Connections: D–A–V1–B and A–V2–C–E.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–900 | 0–500 |
| V1 | 120–320 | 500–780 |
| B | 0–420 | 780–1200 |
| V2 | 580–800 | 500–860 |
| C | 500–1100 | 860–1380 |
| D | −400–0 | 80–420 |
| E | 1100–1460 | 980–1380 |

A top: 120+200+260+220+100=900. B bottom: 120+200+100=420. C bottom: 80+220+300=600. V1/V2 clear widths 180/200 at t=20. B and C have an 80 horizontal gap and no overlap; V2 misses B by 160. A–D shared 340: 100+100+140; y=180–280, center 230. A left below/above D: 80/80. C–E shared 400: 200+120+80; y=1180–1300, center 1240. C right below E: 120. All interiors disjoint.

### 8. Expected result

**Valid, fully constrained**, five rooms and two distinct rectangular vertical corridors. The second corridor position is fixed by a local T-to-T solid span, not centering.

## Data_38 — six rooms and three doors on one uninterrupted shared wall

### 1. Layout and drawing order

1. Draw A left and narrower B right, equal depth, common top/bottom lines.
2. Put C above A, left edge aligned with A. Put D above A's right part, right edge aligned with A's right edge. Leave an exposed top-wall span between C and D; they do not touch. D is taller than C.
3. Put F above B, right edge aligned with B. F is narrower than B. Leave an exposed top-wall span between D and F.
4. Attach E to B's right side, its bottom **120 above B's bottom**.
5. Add **three A–B doors**, plus A–C, A–D, B–E and B–F doors. No corridors. The A–B wall has no intermediate room boundary between its three gaps.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 800 × 1000 cm |
| B | 440 × 1000 cm |
| C | 350 × 420 cm |
| D | 350 × 500 cm |
| E | 460 × 400 cm |
| F | 360 × 380 cm |

### 3–6. Door chains and local paper labels

Along the A–B vertical wall, **bottom to top**, draw/write exactly this chain, each number beside its own span:

1. **`100 cm`** solid: common bottom corner upward to lower door's lower edge.
2. **`90 cm`** clear width of lower door.
3. **`160 cm`** solid: lower door's upper edge upward to middle door's lower edge.
4. **`110 cm`** clear width of middle door.
5. **`180 cm`** solid: middle door's upper edge upward to upper door's lower edge.
6. **`130 cm`** clear width of upper door.
7. **`230 cm`** solid: upper door's upper edge upward to common top corner.

Do not label cumulative middle/upper door offsets. The 160 and 180 are edge-to-edge solid wall spans.

| Other target | Write | Exact endpoints/location |
|---|---|---|
| A–C | `100 cm` width; `100 cm` offset | Width at gap; common left corner rightward to left edge |
| A–D | `120 cm` width; `80 cm` offset | Width at gap; D bottom-left junction rightward to left edge |
| E placement | `120 cm` | B bottom-right corner upward to E bottom-left junction |
| B–E | `110 cm` width; `100 cm` offset | Width at gap; E bottom-left junction upward to lower edge |
| B–F | `110 cm` width; `90 cm` offset | Width at gap; B/F common right corner leftward to right edge |

C/D/F alignments are actual shared collinear walls/corners, not assumed centering. Their widths determine their horizontal placements; do not add optional gap labels.

### 7. Check only

| Region | x interval | y interval |
|---|---|---|
| A | 0–800 | 0–1000 |
| B | 800–1240 | 0–1000 |
| C | 0–350 | 1000–1420 |
| D | 450–800 | 1000–1500 |
| E | 1240–1700 | 120–520 |
| F | 880–1240 | 1000–1380 |

A–B: 100+90+160+110+180+130+230=1000. Intervals y=100–190, 350–460, 640–770; centers 145/405/705. No junction intervenes between these doors.

A–C shared 350: 100+100+150; x=100–200, center 150. A–D shared 350: 80+120+150; x=530–650, center 590. B–E shared 400: 100+110+190; y=220–330, center 275. B–F shared 360: 160+110+90; x=1040–1150, center 1095. B right below/above E: 120/480. C–D horizontal gap 100; D–F gap 80; B top exposed left span 80. No unintended contacts or overlaps.

### 8. Expected result

**Valid, fully constrained:** six rooms, seven doors, with three separate passages between A and B. Preserve parallel door connections; do not merge them into one large gap.

## Data_39 — deliberate three-room total-width conflict

### 1. Layout and drawing order

1. Draw three rooms A, B, C left to right, with common bottom/top lines and two shared vertical walls.
2. Add one A–B and one B–C door.
3. Below the entire outline, draw a separate full-width dimension rail. Its extension lines must reach **A's outer bottom-left corner and C's outer bottom-right corner**. Write the deliberately conflicting total. Keep this rail separate from individual room-width rails.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 450 × 500 cm |
| B | 550 × 500 cm |
| C | 380 × 500 cm |

### 3–6. Door and conflict labels

- A–B: **`100 cm`** clear width; **`90 cm`** from common bottom corner upward to lower opening edge. Put offset beside lower solid shared wall.
- B–C: **`110 cm`** clear width; **`120 cm`** from common top corner downward to upper opening edge. Put offset beside upper solid shared wall.
- Full outer bottom width: deliberately write **`1420 cm`** on the full-width rail described above. Do not write the correct sum on paper and do not mark the total as a question.
- No corridors or further redundant measurements.

### 7. Check only

Using only the partial widths, A x=0–450, B x=450–1000, C x=1000–1380; all y=0–500. These are a **provisional audit configuration, not an accepted solution**. No overlap.

A–B: y=90–190, center 140; 90+100+310=500. B–C: y=270–380, center 325; 270+110+120=500. Shared spans both 500. Width parts 450+550+380=1380, whereas full rail says 1420: **40 cm incompatible residual**. All door/location constraints are otherwise complete.

### 8. Expected result

**Conflicting**, specifically dimension inconsistency rather than missing topology. Retain all four width observations; do not average, stretch a room or discard a label. No accepted metric export before review correction.

## Data_40 — three rooms, known corridor width but missing corridor length

### 1. Layout and drawing order

1. Draw A left and B right with a clearly visible horizontal separation.
2. Connect them with rectangular horizontal H. Place its lower junction **160 above A's bottom**, **100 above B's bottom**. B's bottom is above A's bottom, and its top is higher.
3. Attach C to B's right side, with their top walls collinear; C is shallower.
4. Add a B–C door. H entrances are open.
5. Deliberately omit H's length. Draw it comfortably long for readability, but do not derive a metric length from that appearance.

### 2. Room sizes and standard labels

| Room | Width × depth; write both |
|---|---|
| A | 540 × 620 cm |
| B | 680 × 760 cm |
| C | 420 × 540 cm |

### 3–6. Known labels and deliberate omission

- H: write only **`200 cm` centerline width**, vertically across its midpoint. **No horizontal length label, no numbered dimension rail for that length, no global outer width, and no alternate horizontal span that determines A–B separation.** Leave this measurement absent rather than writing a question mark or guessed value.
- A right wall: **`160 cm`**, bottom-right corner upward to H lower centerline T junction.
- B left wall: **`100 cm`**, bottom-left corner upward to H lower centerline T junction.
- B–C door: **`120 cm`** clear width beside gap; **`100 cm`** from B/C common top corner downward to upper edge, on C side.
- Connections A–H, H–B, B–C. There are no missing door offsets.

### 7. Check only

Let **L be the unknown positive corridor length**. This symbol and these bounds are not paper labels.

| Region | x interval | y interval |
|---|---|---|
| A | 0–540 | 0–620 |
| H | 540–(540+L) | 160–360 |
| B | (540+L)–(1220+L) | 60–820 |
| C | (1220+L)–(1640+L) | 280–820 |

A corridor-side chain: 160+200+260=620. B: 100+200+460=760. Clear H width 180 at t=20. B–C shared 540: 320+120+100; door y=600–720, center 660. B right below C: 220. For any positive L, region interiors are disjoint; choose a visibly separated drawing, but no numeric L is supplied. All vertical positions and all door properties are fixed; horizontal translation of B+C relative to A remains one internal degree of freedom.

### 8. Expected result

**Incomplete**, specifically missing H length / A–B horizontal separation. Keep it unknown. Sketch proportions, apparent corridor centering and room size do not recover it. No accepted complete metric export until a real dimension is supplied during review.

## Batch audit and use

| Data | Rooms | Corridor rectangles | Doors | Intended result / distinctive coverage |
|---|---:|---:|---:|---|
| 31 | 3 | 0 | 2 | Valid; rising stagger, partial shared spans |
| 32 | 4 | 0 | 3 | Valid; branching hub, local junction offsets, solid adjacency |
| 33 | 3 | 1 horizontal | 1 | Valid; unequal vertical alignment plus direct branch |
| 34 | 3 | 1 vertical | 1 | Valid; unequal horizontal alignment, top-reference door |
| 35 | 4 | 0 | 4 | Valid; cycle, four-way junction and upper T junction |
| 36 | 4 | 2 horizontal | 1 | Valid; separated corridor levels and direct branch |
| 37 | 5 | 2 vertical | 2 | Valid; parallel branches, centerline T-to-T span |
| 38 | 6 | 0 | 7 | Valid; three doors on one uninterrupted wall |
| 39 | 3 | 0 | 2 | Conflicting; full-width total differs by 40 |
| 40 | 3 | 1 horizontal | 1 | Incomplete; exactly one missing internal metric degree of freedom |

Audit basis: room sizes and local placement spans determine the displayed coordinate bounds; each interior is disjoint; every door fits the intersection of its two supporting boundaries with positive remaining solid spans; corridor entrances exactly match the appropriate room boundary spans. Corridor clearances were checked at reference t=20, and door edges remain away from adjacent junction caps. This is a metric recipe check, not execution of the future solver or physical Pawn validation. The conflict and free length are intentional and isolated.

After uploads arrive, inspect actual pixels, handwritten values, tick endpoints and topology first. Preserve deviations, omissions and contradictions as evidence. Do not create future annotations/ground-truth JSON from this document, and do not add these examples to manifests or train weights merely because the brief exists. Keep eventual crops/recaptures of each actual plan grouped together; writer diversity and a frozen independent holdout remain separate dataset needs.
