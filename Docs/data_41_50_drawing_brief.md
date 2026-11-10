# Data_41–50 drawing brief

Prepared 2026-10-17 after inspecting actual Data_31–40. These are future drawing recipes, not observations or ground truth. Actual later images take precedence. Eight valid cases, one dimension conflict and one missing room-width case are intended. No image, annotation JSON or training job is created by this brief.

## Shared drawing and measurement rules

1. Units are **cm**; every number you write has ` cm`. Width is horizontal, depth vertical, on wall centerlines. Scale is optional. Keep every individual room/corridor rectangular; the outer footprint can step.
2. Draw one physical wall centerline; shared walls once. For each door leave a visible gap, add two perpendicular endpoint ticks, and **write both clear width and the specified location dimension**. No swing arcs. Corner/T-junction offsets end at the near opening edge, never at the door center. A top reference goes down to the upper edge; a right reference goes left to the right edge.
3. Corridor entrances are open passages, without door ticks. Dimension corridor centerline width/length and all specified local junction spans. Solid spans alongside a corridor end at its **centerline T junction**, not its clear entrance edge. At a corridor turn, use separate H/V rectangular regions with an open logical interface, never an L-shaped region or overlapping rectangles.
4. Standard room-label placement: write every listed room width on a full-width horizontal dimension rail inside its bottom side, and every depth on a full-depth vertical rail inside its left side. Use extension lines to full boundary centerlines. Move the rail into free space if another label is nearby. Rotate a complete vertical label rather than stacking digits. Repeat sizes when listed for separate rooms. **Only Data_50 B width is intentionally absent.**
5. Standard corridor-label placement: horizontal length on a rail below its lower boundary, width on a vertical cross-span rail near its middle; vertical length on a rail left of its left boundary, width on a horizontal cross-span rail near its middle. Length endpoints are the named room/corridor interface centerlines. Distinguish partial from total spans with endpoint ticks/extension lines.
6. In local-label tables, place the value beside the named solid span and explicitly mark its two endpoints. A door-width label belongs immediately beside the gap. Between doors without a new room boundary, write edge-to-edge solid separation, not a cumulative second-door offset.
7. A–F, H and V are explanation IDs, not paper text. Do not write coordinate tables, derived checks, equations, statuses, wall thickness/height or Start/Goal. Settings and roles are chosen in review. Leave margins around all labels.
8. Coordinate tables below are **check only**, with x right/y up. They establish nonoverlap and determinacy, not numbers to copy. All finite valid placements follow written local spans or explicit coincident/collinear boundaries. No hidden centering is used. Door centers and remaining wall values are derived and must not be added as observations.
9. At reference thickness20, corridor clear width is centerline width−20. At a side-branch entrance, clear width follows that shared interface span−20. These are check values, not extra labels. Metric consistency does not certify Pawn playability.

## Data_41 — three rooms, two doors on a partial shared wall

**Draw in order:** A left; shorter B attached to A's right with its bottom100 above A's bottom. Put C above A with their **right boundary collinear**, leaving A's top-left portion exposed. Draw two A–B doors and one A–C door. No corridors.

**Room sizes — write using standard rails:** A **600×720**, B **440×480**, C **420×380 cm**.

| Write | Target and exact endpoints/direction |
|---|---|
| `100 cm` | B placement: A bottom-right corner upward to B bottom-left T junction |
| `80 cm` | B bottom-left junction upward to lower A–B door's lower edge |
| `100 cm` | Lower A–B door clear width |
| `100 cm` | Lower door upper edge upward to upper door lower edge; uninterrupted edge-to-edge solid wall |
| `110 cm` | Upper A–B door clear width |
| `120 cm` | A–C door clear width |
| `90 cm` | A/C common right corner leftward to A–C door right edge |

**Check only:** A x0–600/y0–720; B x600–1040/y100–580; C x180–600/y720–1100. A–B shared length480 =80+100+100+110+90. Doors y180–280 and380–490, centers230/435. A–C shared420 =210+120+90, opening x390–510, center450. A right outside B100 below/140 above; A top left of C180. Interiors disjoint.

**Expected:** valid, fully constrained; two distinct A–B connections and an upper branch. Do not write the derived top remaining90 as a fourth A–B local label.

## Data_42 — four rooms, vertical then horizontal corridor

**Draw in order:** A below; V above A; B above V, extending left of A. H leads from B's right to C farther right; C starts lower than B and finishes above B. Add D on B's left, bottom100 above B bottom. V and H do not touch each other; B is between them. Add B–D door, with all corridor entrances open.

**Room sizes:** A **500×420**, B **640×520**, C **560×660**, D **360×360 cm**; write all eight labels on standard rails.

**Corridors:** V **280 length ×200 centerline width**; H **340 length ×220 centerline width**; write all four on standard corridor rails.

| Write | Local target and endpoints |
|---|---|
| `140 cm` | A top-left corner rightward to V left centerline T junction |
| `200 cm` | B bottom-left corner rightward to V left centerline T junction |
| `140 cm` | B bottom-right corner upward to H lower centerline T junction |
| `220 cm` | C bottom-left corner upward to H lower centerline T junction |
| `100 cm` | B bottom-left corner upward to D bottom-right T junction |
| `100 cm` | B–D door clear width |
| `130 cm` | D bottom-right junction upward to door lower edge |

**Check only:** A x0–500/y0–420; V x140–340/y420–700; B x−60–580/y700–1220; H x580–920/y840–1060; C x920–1480/y620–1280; D x−420–−60/y800–1160. A top140+200+160=500; B bottom200+200+240=640; B right140+220+160=520; C left220+220+220=660. Door y930–1030, center980; D shared360=130+100+130. B left below/above D100/60. Clear V/H widths180/200. No overlaps.

**Expected:** valid; A–V–B–H–C plus B–D branch.

## Data_43 — a corridor bend decomposed into two rectangles

**Draw in order:** A left, H exiting A to the right. At the **right end of H's top side**, put V upward. H and V meet along a horizontal interface; leave that interface open. B is above V. Add C above A with left edges collinear; add D right of B with top edges collinear. Add A–C and B–D doors.

**Room sizes:** A **500×600**, B **620×520**, C **380×400**, D **460×400 cm**.

**Corridors:** H **500 length ×200 centerline width**; V **380 length ×200 centerline width**. H length ends at its right boundary line, not at V's left wall. V length starts at H's top boundary line and ends at B's bottom. Write each full dimension on its standard rail.

| Write | Local target and endpoints |
|---|---|
| `150 cm` | A bottom-right corner upward to H lower centerline junction |
| `300 cm` | Along H top: A/H upper junction rightward to V bottom-left T junction |
| `180 cm` | B bottom-left corner rightward to V left centerline junction |
| `100 cm` | A–C door clear width |
| `110 cm` | A/C common left corner rightward to left door edge |
| `120 cm` | B–D door clear width |
| `100 cm` | B/D common top corner downward to upper door edge |

**Check only:** A x0–500/y0–600; H x500–1000/y150–350; V x800–1000/y350–730; B x620–1240/y730–1250; C x0–380/y600–1000; D x1240–1700/y850–1250. H top300+200=500 determines V placement; B bottom180+200+240=620; A right150+200+250=600. Three open interfaces: A–H at x500, H–V at y350/x800–1000, V–B at y730. Clear interface widths180 each at t20. A–C shared380=110+100+170, door x110–210 center160. B–D shared400=180+120+100, door y1030–1150 center1090. No corridor interior overlap; V starts where H ends vertically.

**Expected:** valid, four rooms/two rectangular corridors. A–H–V–B is the bend; neither H nor V is L-shaped.

## Data_44 — five-room hub, T junctions and a three-room cycle

**Draw in order:** A hub; B lower-right and C upper-right, sharing a horizontal boundary. B bottom aligns A bottom; C top aligns A top. Add D on A top-left, left edges aligned; E on A top-right, right edges aligned. Leave a gap between D and E. Draw A–B, A–C, B–C, A–D and A–E doors.

**Room sizes:** A **900×700**, B **400×300**, C **560×400**, D **360×420**, E **380×480 cm**. No corridor.

| Door | Clear width to write | Location label and exact endpoints |
|---|---|---|
| A–B | `100 cm` | `80 cm`: common bottom corner upward to lower edge |
| A–C | `110 cm` | `100 cm`: B/C/A T junction upward to lower edge |
| B–C | `100 cm` | `140 cm`: B top-left T junction rightward to left edge |
| A–D | `100 cm` | `90 cm`: common left corner rightward to left edge |
| A–E | `130 cm` | `80 cm`: common right corner leftward to right edge |

**Check only:** A x0–900/y0–700; B x900–1300/y0–300; C x900–1460/y300–700; D x0–360/y700–1120; E x520–900/y700–1180. Door intervals A–B y80–180 (80+100+120=300), A–C y400–510 (100+110+190=400), B–C x1040–1140 (140+100+160=400), A–D x90–190 (90+100+170=360), A–E x690–820 (170+130+80=380). Centers130/455/1090/140/755. D–E gap160. Interiors disjoint; A–B–C–A is a cycle.

**Expected:** valid, fully constrained. The B–C door must be drawn; adjacency alone would not create this cycle.

## Data_45 — six rooms, stepped upper row, two cycles

**Draw in order:** Draw A/B/C in a bottom row, with common top/bottom lines. Put D directly above A, E directly above B, F directly above C, keeping each column's boundary lines continuous. Upper depths differ: E tallest, F intermediate, D shortest. Draw all seven doors in the table. No corridors.

**Room sizes:** A **420×460**, B **580×460**, C **360×460**, D **420×360**, E **580×540**, F **360×420 cm**. Write all twelve size labels.

| Door | Clear width to write | Offset to write and reference |
|---|---|---|
| A–B | `100 cm` | `100 cm`: common bottom corner upward to lower edge |
| B–C | `120 cm` | `80 cm`: common top junction downward to upper edge |
| A–D | `100 cm` | `120 cm`: common left corner rightward to left edge |
| B–E | `140 cm` | `100 cm`: common right junction leftward to right edge |
| C–F | `100 cm` | `90 cm`: common left junction rightward to left edge |
| D–E | `100 cm` | `140 cm`: D bottom-right row junction upward to lower edge |
| E–F | `110 cm` | `100 cm`: F top-left T junction downward to upper edge |

**Check only:** A x0–420/y0–460; B x420–1000/y0–460; C x1000–1360/y0–460; D x0–420/y460–820; E x420–1000/y460–1000; F x1000–1360/y460–880. A–B y100–200, solid100/260. B–C y260–380, solid260/80. A–D x120–220, solid120/200. B–E x760–900, solid340/100. C–F x1090–1190, solid90/170. D–E y600–700, solid140/120 over shared360. E–F y670–780, solid210/100 over shared420. Door centers150/320/170/830/1140/650/725. No overlap; seven connections across six rooms yield two independent cycles. The row junctions are actual four-way wall junctions, not gaps.

**Expected:** valid, fully constrained; stepped roof and several direct connections.

## Data_46 — four rooms and a cycle through three corridors

**Draw in order:** Tall A left. Lower B to the right via H1; higher C to the right via H2. Add V between B top and C bottom. V does not intersect H1/H2 interiors. Attach D to A left with its bottom480 above A bottom. Add A–D door; all six corridor entrances open.

**Room sizes:** A **500×1400**, B **600×520**, C **540×600**, D **360×400 cm**.

**Corridors:** H1 **300 length ×200 width**; H2 **400 length ×220 width**; V **330 length ×200 width**, all centerline dimensions with standard rails.

| Write | Local target and endpoints |
|---|---|
| `160 cm` | A bottom-right corner upward to H1 lower centerline T junction |
| `160 cm` | B bottom-left corner upward to H1 lower centerline T junction |
| `640 cm` | A right wall, H1 upper centerline junction upward to H2 lower centerline junction |
| `150 cm` | C bottom-left corner upward to H2 lower centerline junction |
| `300 cm` | B top-left corner rightward to V left centerline junction |
| `200 cm` | C bottom-left corner rightward to V left centerline junction |
| `480 cm` | A bottom-left corner upward to D bottom-right T junction |
| `110 cm` | A–D door clear width |
| `120 cm` | D bottom-right junction upward to door lower edge |

**Check only:** A x0–500/y0–1400; H1 x500–800/y160–360; B x800–1400/y0–520; H2 x500–900/y1000–1220; C x900–1440/y850–1450; V x1100–1300/y520–850; D x−360–0/y480–880. A right160+200+640+220+180=1400; B left160+200+160=520; C left150+220+230=600. B top300+200+100=600; C bottom200+200+140=540. Door y600–710, center655; shared400=120+110+170. A left outside D480/520. Corridor clear widths180/200/180. Distinct interiors; cycle A–H1–B–V–C–H2–A.

**Expected:** valid. The640 is a local **centerline junction-to-junction** solid span along A, not a clear-edge door separation or an A-bottom cumulative offset.

## Data_47 — five rooms branching from the sides of one corridor

**Draw in order:** A left, B right, H between them. Put C directly above a middle section of H; D directly below a different section of H. Their whole connecting room sides are open passages. Put E above B, right boundaries collinear, connected by a door. H remains one rectangle with four open interfaces.

**Room sizes:** A **500×900**, B **600×900**, C **400×420**, D **400×400**, E **460×380 cm**.

**Corridor:** H **900 length ×200 centerline width**. Length is A right interface→B left interface, including the side-branch junctions.

| Write | Local target and endpoints |
|---|---|
| `400 cm` | A bottom-right corner upward to H lower centerline T junction |
| `300 cm` | B bottom-left corner upward to H lower centerline T junction |
| `150 cm` | H top, A/H upper junction rightward to C bottom-left centerline T junction |
| `350 cm` | H bottom, A/H lower junction rightward to D top-left centerline T junction |
| `120 cm` | B–E door clear width |
| `110 cm` | B/E common right corner leftward to right door edge |

**Check only:** A x0–500/y0–900; H x500–1400/y400–600; B x1400–2000/y100–1000; C x650–1050/y600–1020; D x850–1250/y0–400; E x1540–2000/y1000–1380. A right400+200+300=900; B left300+200+400=900. H top150+400+350=900; H bottom350+400+150=900. C/D do not overlap H: they meet its boundary. Clear A/B entrances180; clear C/D side entrances380 at t20, derived from their400 shared spans, **not** from H's perpendicular width200. B–E shared460=230+120+110; door x1770–1890, center1830. No overlap or accidental C–E contact.

**Expected:** valid, corridor-centered branching topology without an L-shaped region. Do not add door ticks to the C/D open entrances.

## Data_48 — four rooms in a tall stagger with two vertical corridors

**Draw in order:** A bottom; V1 above A; wide B above V1 extending left of A. V2 starts from B top farther right, leading to C at the top. Attach D to B left with bottom100 above B bottom. V1/V2 are separate rectangles connected through B. Add B–D door.

**Room sizes:** A **700×360**, B **900×520**, C **680×620**, D **420×340 cm**.

**Corridors:** V1 **280 length ×180 width**; V2 **310 length ×220 width**, centerline dimensions.

| Write | Local target and endpoints |
|---|---|
| `100 cm` | A top-left corner rightward to V1 left centerline T junction |
| `180 cm` | B bottom-left corner rightward to V1 left centerline T junction |
| `590 cm` | B top-left corner rightward to V2 left centerline T junction |
| `160 cm` | C bottom-left corner rightward to V2 left centerline T junction |
| `100 cm` | B bottom-left corner upward to D bottom-right T junction |
| `100 cm` | B–D door clear width |
| `70 cm` | D top-right T junction downward to upper door edge |

**Check only:** A x0–700/y0–360; V1 x100–280/y360–640; B x−80–820/y640–1160; V2 x510–730/y1160–1470; C x350–1030/y1470–2090; D x−500–−80/y740–1080. A top100+180+420=700; B bottom180+180+540=900; B top590+220+90=900; C bottom160+220+300=680. D shared340=170+100+70; door y910–1010, center960. B west below/above D100/80. Clear V1/V2 widths160/200. No overlap.

**Expected:** valid, fully constrained; a top-referenced side door and unequal corridor widths.

## Data_49 — deliberate corridor-side dimension conflict

**Draw in order:** A left and B right joined by H. C above B with left boundaries collinear, leaving B's top-right portion exposed. Add B–C door. Add the deliberately contradictory upper solid span on A's right wall. Do not mark the conflict as a question or erase a number.

**Room sizes:** A **500×800**, B **600×800**, C **400×360 cm**.

**Corridor:** H **320 length ×200 centerline width**.

| Write | Local target and endpoints |
|---|---|
| `180 cm` | A bottom-right corner upward to H lower centerline T junction |
| `240 cm` | B bottom-left corner upward to H lower centerline T junction |
| **`450 cm`** | H **upper** T junction upward to A top-right corner; deliberate conflicting solid span |
| `100 cm` | B–C door clear width |
| `130 cm` | Common B/C left corner rightward to left door edge |

**Check only:** From the lower spans alone: A x0–500/y0–800; H x500–820/y180–380; B x820–1420/y−60–740; C x820–1220/y740–1100. A remaining upper span would be420, but the observed recipe asks450:180+200+450=830≠800, conflict30. B left240+200+360=800. Door x950–1050, center1000; shared400=130+100+170. No overlap in this provisional configuration. Clear H width180. Do not write420,830 or the residual30 on paper.

**Expected:** conflicting, with topology/opening information otherwise complete. No accepted metric output; all conflicting evidence must survive review.

## Data_50 — complete openings but missing one room width

**Draw in order:** A left; B right, top walls collinear, B shallower than A. Put C above A with left boundaries collinear. Put D above B with left boundaries collinear; make D visibly narrower than B, leaving an exposed B-top-right span. C and D do not touch. Add A–B, A–C and B–D doors. No corridors.

**Room sizes to write:** A **600×600**, B **depth500 only**, C **420×380**, D **340×360 cm**. **Omit B width** and any total outer width or remaining B-top span that could determine it. Do not label a guessed width or a question mark.

| Door | Clear width to write | Offset to write and endpoints |
|---|---|---|
| A–B | `120 cm` | `100 cm`: common top corner downward to upper edge |
| A–C | `110 cm` | `90 cm`: common left corner rightward to left edge |
| B–D | `100 cm` | `100 cm`: B/D common left corner rightward to left edge |

**Check only:** Let W be the unknown B width, qualitatively greater than340. A x0–600/y0–600; B x600–(600+W)/y100–600; C x0–420/y600–980; D x600–940/y600–960. The display uses an arbitrary visual width, never a metric observation. A–B shared500=280+120+100, door y380–500 center440. A–C shared420=90+110+220, door x90–200 center145. B–D shared340=100+100+140, door x700–800 center750. A right below B100; gap C–D180. Interiors do not overlap for W>340. No value for W is derivable from the other labels.

**Expected:** incomplete with exactly one missing internal degree of freedom, B width. All door widths and local positions are supplied; do not confuse the missing width with missing door information.

## Author checklist and audit boundary

Before exporting each PNG, compare every size/local-label/door row against the page. In valid cases, verify that **every door has its clear width and its required location evidence**; Data_41's second A–B door uses the intervening solid-wall chain instead of its own cumulative offset. Verify that every corridor has both full dimensions and its local placements. Do not copy derived coordinates/check values. The interactive display's selected rail shows only one measured span at a time; its full measurement list is the completeness checklist.

All valid cases were checked for disjoint region interiors, actual shared boundary intervals, door containment, remaining wall lengths and explicit placement constraints. Minimum door clearance to a shared-span endpoint is70 in this batch. Data_43's corridor bend and Data_47's side entrances preserve rectangular regions. Data_49's30 cm conflict and Data_50's free width are intentional. These checks do not run Step09 or certify automatic perception/Unreal/Pawn behavior.

When actual Data_41–50 images arrive, annotate their visible ink and numbers, preserving changes and omissions. Do not prepopulate observation/ground-truth files or manifests from this brief. Future crops/recaptures remain grouped by their actual plan and writer; these same-author examples do not replace a frozen unseen-writer holdout.
