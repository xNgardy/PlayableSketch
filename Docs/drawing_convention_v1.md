# Drawing Convention v1

**Project:** PlayableSketch  
**Version:** 1.0 (opening-offset clarification: 2026-10-16)  
**Date:** 2026-10-13  
**Status:** Input specification for the planned Sketch-to-Level pipeline.

This document defines how a hand-drawn level layout should be represented on paper and how the system should interpret it. It describes the intended input contract; it does not imply that image recognition or explicit layout import has already been implemented.

The drawing provides a rough **2D rectangular layout**: room dimensions, connections, wall junctions, corridors, and door locations. The system reconstructs this layout using the written dimensions, then generates its geometry in Unreal Engine. Wall thickness and vertical dimensions remain editable settings.

The drawing does **not** need to be to scale. Written dimensions determine the intended size; the sketch provides topology and approximate relative placement.

## Supported drawings

Version 1 supports:

- A top-down view of a single floor with a horizontal floor surface.
- Rectangular and square rooms.
- Horizontal and vertical straight walls in the intended layout.
- Rectangular corridor segments with an indicated width.
- Rooms connected through corridors.
- Adjacent rooms connected directly through an opening in a shared wall, without a corridor.
- Wall corners and T junctions, provided the resulting rooms remain rectangular or square.
- Door openings marked using the convention below.

The complete level does not have to fit a single rectangle. Several rectangular rooms and corridor segments may form a larger orthogonal arrangement. An individual L-shaped room is outside the scope of v1.

Hand-drawn lines may be slightly uneven, and the photograph may be rotated. The system should recover the intended horizontal and vertical layout rather than reproduce every small stroke deviation.

Start and Goal are selected during review. They do not need to be drawn on paper.

### What the drawing communicates

| Information | Interpretation |
| --- | --- |
| Room outline | A rectangular room boundary |
| Written wall dimension | The intended length of the specified centerline span |
| Relative room placement | Approximate arrangement, subject to dimensions and review |
| Connected wall strokes | Intended wall junctions |
| Two corridor boundaries | The corridor's extent and connection to rooms |
| Door gap and perpendicular marks | The approximate location of a door opening |
| Written opening width | The intended clear opening width |

A connection does not require a corridor. Conversely, nearby rooms are not automatically connected: the drawing must show a door opening or a corridor/passable opening between them.

## Wall representation

Represent each physical wall with **one line**, interpreted as its **wall centerline**.

- Do not draw two parallel lines to represent the two faces of one wall.
- Two separate parallel lines may represent distinct walls, such as the boundaries of a corridor.
- Walls that meet should visibly share a corner or junction.
- At a T junction, the terminating wall should visibly reach the other wall.
- A shared wall between adjacent rooms is one physical wall and should be drawn once.

Small accidental breaks may be treated as recognition uncertainty. A break alone is not sufficient evidence of a door; use the explicit door markers below.

### Room boundaries at openings

A rectangular room may have a gap in one of its walls for a door or corridor connection. Its underlying rectangular boundary continues across that gap as a **logical boundary**, while the physical wall remains open there.

The system must distinguish this logical boundary from solid geometry. Reconstructing a closed room boundary must not fill a door or corridor entrance with a wall.

## Dimension units and measurement basis

### Units

Use **centimeters**, with an explicit `cm` suffix:

```text
700 cm
500 cm
120 cm
```

The preferred format is a readable positive number, a space, and lowercase `cm`. Do not omit the unit or mix units within a v1 drawing.

`px` is used only for image coordinates inside the recognition pipeline. It is not a level measurement unit. Photograph distance, cropping, and image resizing change pixel lengths without changing the intended physical dimensions.

The final layout uses centimeters internally. Support for `m`, `ft`, and `in` may be added later through explicit conversion to centimeters. Imperial annotations are outside the v1 input convention.

### Wall and room dimensions

A dimension beside a wall measures the **wall centerline span between its specified endpoints or junctions**.

For a rectangular room:

- Width is the distance between its left and right boundary centerlines.
- Depth is the distance between its bottom and top boundary centerlines.
- These are not clear interior dimensions or outer-face dimensions.

For example, a room with a centerline width of `700 cm` and two bounding walls of thickness `20 cm` has a clear interior width of approximately:

```text
700 - 20/2 - 20/2 = 680 cm
```

Changing wall thickness preserves the specified centerline layout but may change the clear interior space.

### Corridor dimensions

Use the same centerline basis for corridor dimensions:

- Corridor width is the perpendicular distance between its two boundary wall centerlines.
- Corridor length is the distance between the identified entrance and exit boundary centerlines, or another explicitly marked span.
- The clear corridor width is smaller once wall thickness is applied.

For two parallel walls of equal thickness `t`, the approximate clear width is `centerline_width - t`. The system must validate the resulting passage against the configured agent dimensions.

### Door dimensions

Door width uses a different, explicit basis: **clear opening width** between the two sides of the gap. It does not include door frames or wall thickness.

This exception is intentional: room and corridor dimensions describe the centerline layout; door dimensions describe the usable opening.

### Total spans and partial spans

A wall interrupted by an opening can still have a total centerline dimension. That total includes the opening interval; it is not merely the sum of the visible solid strokes.

If a T junction splits a wall into segments, distinguish total-span dimensions from individual segment dimensions using endpoint ticks or extension lines. Do not apply one total dimension separately to every segment.

## Dimension placement

Write each dimension:

1. Beside the relevant wall or dimension line.
2. Parallel to the direction of the measured span.
3. Approximately aligned with the midpoint of that span when practical.
4. With enough separation from wall strokes, door marks, and other annotations to remain readable.

For a vertical wall, rotate the annotation so that its reading direction follows the vertical span. For a horizontal wall, write it horizontally.

When walls are close together, or a dimension refers to only part of a wall, use short **ticks or extension lines** to identify the two measured endpoints. Keep those dimension marks outside the wall where possible.

### Endpoint references

The measured span should be identifiable as one of:

- Corner to corner.
- Corner to T junction.
- T junction to T junction.
- A total span across several collinear wall segments.
- A door opening, using the dedicated door notation.

Avoid crossing out digits or writing one value over another. Rewrite an unclear annotation in a clean location and make its target explicit.

Opposite sides of the same rectangular room must have equal total dimensions. Repeated annotations are allowed when they agree; users do not have to label every wall if the remaining dimensions are uniquely determined.

## Door representation

Represent a door using:

1. A visible gap in the wall line.
2. Two short marks perpendicular to the wall, one at each end of the gap.
3. A clear-width annotation placed in or immediately beside the gap, associated with those two marks.

For a horizontal wall, the two endpoint marks are vertical:

```text
                         120 cm
wall ----------------|             |---------------- wall
                     <--- gap ---->
```

The arrow in this diagram explains the gap; users do not need to draw it. For a vertical wall, rotate the notation by 90 degrees. Place the width text so that it remains readable without joining the wall strokes.

An optional `D` may be added to identify the opening as a door, for example `D 120 cm`. The `D` is helpful but not required when the gap and both perpendicular marks are clear.

### Door marks versus dimension ticks

Door marks sit at the two ends of an actual wall gap. Ordinary dimension ticks identify a measured span and do not create a gap.

If the distinction is unclear, the system must request review instead of silently creating a door.

### Door location

The gap identifies the approximate location. Its clear width is determined by the written measurement, not by the number of image pixels between the marks.

An exact location may be specified with a separate offset dimension from a known corner or junction to the **near edge of the opening**, measured in the indicated direction. It does not measure to the opening center. Identify both endpoints using ticks or extension lines when the span could be ambiguous.

For example, on a 200 cm vertical wall, an offset of `50 cm` from the bottom corner and a `120 cm` clear opening produce:

```text
bottom solid span: 50 cm
opening interval: [50, 170] cm
remaining top span: 200 - 50 - 120 = 30 cm
derived opening center: 50 + 120/2 = 110 cm
```

For a reference at the other end, measure back toward the opening: the near edge is the edge encountered first. The gap and the offset dimension must identify that direction. Room/corridor lengths remain centerline measurements; this clarification only changes opening-offset interpretation.

For an open corridor entrance, the same near-edge rule refers to the clear entrance. Its clear width is derived from the configured wall thickness when only a corridor centerline width is provided. A written edge offset must not be silently reinterpreted as a center offset when settings change.

A label whose endpoint is a corridor boundary T junction instead measures the solid **wall centerline span to that junction**. For Data_16/17, the 325/260 cm labels have this meaning. Do not subtract or add half the wall thickness to that observed wall span; derive the clear entrance separately from corridor width and settings.

This 2026-10-16 author correction supersedes the earlier corner-to-center interpretation for all previous photo references and new drawing briefs. The canonical internal `Opening.center_offset_cm` remains a derived coordinate; it is not the number written beside the wall.

### Wall spans between openings

A dimension written beside the solid wall between two openings on an uninterrupted room-side span measures from the first opening's end edge to the next opening's start edge. It is neither a center-to-center distance nor a cumulative offset from a room corner. If a room boundary or T junction intervenes, prefer that local corner/junction as the reference for the next opening. Use endpoint ticks or extension lines when the span could be confused with another measurement.

For Data_15, the wall sequence from bottom to top is `140 cm wall + 90 cm opening + 150 cm wall + 120 cm opening + 20 cm wall = 520 cm`. Write `150 cm` beside the wall between the doors. The upper opening's cumulative start coordinate, `140 + 90 + 150 = 380 cm`, is derived from the chain rather than written as that wall segment's label.

For Data_18, the T junction marks the upper-right room's bottom boundary. Write `210 cm` from that junction to the upper door's lower edge. This local measurement is preferred over the 250 cm door-to-door span that would cross the room boundary. Both describe different endpoints; the association stage must preserve the intended scope.

The future dimension-association/metric-solving stage must preserve the measured endpoints and compose these adjacent wall/opening spans. A total dimension still measures its explicitly marked full span; placement beside a shorter wall segment must not silently change that scope.

If no offset is supplied, the system may propose a location based on the sketch, mark it as inferred, and allow correction during review. It must not present that location as an exact measured coordinate.

### Direct room connections

For two adjacent rooms, place this notation on their shared wall. The system should create one shared wall with one opening connecting the rooms. It must not insert a corridor that was not drawn.

For a corridor connection, make its two boundaries and entrances visible. A corridor entrance may be an open passage without a door. Add the door notation only when a door opening is intended.

## Default height and thickness

The drawing describes a 2D layout. The following properties are configured in the system rather than inferred from the photograph:

| Setting | Meaning | Initial suggested default |
| --- | --- | ---: |
| Wall thickness | Wall size across its centerline | 20 cm |
| Wall height | Wall extent along the Z axis | 300 cm |
| Door height | Clear vertical opening above the floor | 220 cm |
| Floor thickness | Floor slab thickness | 20 cm |

These values are starting settings, not measurements extracted from the drawing. They remain editable and must be saved with the generated layout.

Version 1 can apply global defaults to the layout. Individual-wall overrides may be added later without changing the paper convention.

When settings change:

- Preserve room/corridor centerline dimensions, junctions, and confirmed opening locations.
- Preserve the specified door clear widths.
- Rebuild the affected geometry.
- Revalidate wall joins, clear spaces, openings, collision, and navigation.

If a larger thickness makes a corridor too narrow or a lower height invalidates an opening, report the conflict. Do not silently move walls or change confirmed dimensions to compensate.

## Unsupported cases

Version 1 does not support:

- Individual nonrectangular rooms, including L-shaped rooms.
- Intentionally diagonal or curved walls.
- Multiple floors, stairs, ramps, or changing floor elevations.
- Perspective or isometric drawings intended to represent 3D geometry.
- Double-line wall notation used to encode wall thickness.
- Mixed measurement units or annotations in `px`, `ft`, or `in`.
- Dimensions whose measurement basis is clear inside or outer face instead of centerline, unless the system first obtains an explicit correction.
- Architectural symbols that have not been defined here, such as door swing arcs or window notation, as automatic semantic input.

Unsupported or unreadable inputs should produce an actionable review issue. They must not be silently converted into a different layout.

### Missing or ambiguous information

An incomplete drawing may still be useful as a draft. The system should distinguish:

| State | Meaning | Expected behavior |
| --- | --- | --- |
| Confirmed | A dimension or interpretation has been verified | Preserve it during reconstruction |
| Derived | A value follows uniquely from confirmed geometry | Record its dependencies |
| Inferred | A value is estimated from the sketch or a proposal | Show it as editable during review |
| Missing | Required information cannot be determined | Request a dimension or user decision |
| Conflicting | Confirmed information cannot all be satisfied | Explain the conflict and request correction |

A default height/thickness is a configured value, not a detected measurement. It should be identified separately from these evidence states.

Do not assume that every missing dimension prevents reconstruction. For example, two independent dimensions can determine a rectangle. However, a drawing of two rooms and a corridor may leave corridor length or connection offsets unresolved even when both room sizes are known.

## Valid and invalid examples

### Example 1 — Single rectangular room

Draw a rectangle with a horizontal span labeled `600 cm` and a vertical span labeled `400 cm`. Keep labels parallel to their measured spans.

**Expected interpretation:** A room with centerline dimensions 600 × 400 cm. The sketch need not have the exact 6:4 aspect ratio. Clear interior dimensions depend on the configured wall thickness.

This is a valid geometry input. Start/Goal gameplay validation is separate: the current legacy Graph validator requires different Start and Goal rooms, so a single-room geometry example must not be rejected merely for lacking a second room.

### Example 2 — Square room

Draw a square and label two perpendicular spans `500 cm`.

**Expected interpretation:** A 500 × 500 cm centerline room. If opposite sides are also labeled, they must agree with those values.

### Example 3 — Two rooms connected directly

Draw two adjacent rectangular rooms sharing one wall. Label their centerline widths `600 cm` and `500 cm`, with a shared depth of `400 cm`. Put a marked gap on the shared wall and label its clear width `120 cm`.

**Expected interpretation:** Two rooms, one physical shared wall, and one door opening. No corridor is generated. If the opening's edge offset is not dimensioned, its location remains inferred until reviewed.

### Example 4 — Two rooms connected by a corridor

Draw two separate rectangular rooms, with two parallel lines defining a corridor between them. Label room dimensions and the corridor's centerline width. Label corridor length and entrance offsets when their exact placement matters.

**Expected interpretation:** Two rooms connected by the drawn rectangular corridor. The system preserves its connections and proposed relative placement. Any unresolved length or offset is derived where possible, otherwise marked as inferred or missing.

### Example 5 — T junction with total and partial spans

Draw a 700 cm horizontal wall with a vertical wall joining it 300 cm from its left endpoint. Use ticks or extension lines to mark `300 cm` on the left part and `400 cm` on the right part. Mark the total span separately if it is also shown.

**Expected interpretation:** One T junction, two horizontal wall segments, and a consistent total of 700 cm. The 700 cm total is not assigned to both segments independently. Rooms formed around the junction must remain rectangular for v1.

### Example 6 — Conflicting rectangle dimensions

Draw one rectangular room. Label the full top span `600 cm` and the corresponding full bottom span `450 cm`.

**Expected interpretation:** A dimension conflict. Both confirmed values cannot describe opposite sides of the same rectangle under the centerline convention. The system must not average them, distort the rectangle, or silently discard one value.

If OCR is uncertain, show the original annotation and alternatives before treating the numbers as confirmed.

### Example 7 — Ambiguous gap

Draw a break in a wall without perpendicular endpoint marks or a clear width label.

**Expected interpretation:** An unresolved break. It may be an accidental stroke gap, an open entrance, or a door. Request review before assigning its meaning.

### Example 8 — Reference sketch supplied for this project

[Open the supplied reference photograph](</Users/pelinsukaleli/Downloads/WhatsApp Image 2026-10-13 at 19.12.05.jpeg>).

The photograph illustrates the intended type of rough input: a left rectangular room, a right rectangular room, and a corridor-like connection between them. A visual reading suggests labels of 700 cm and 500 cm for the left room, and 800 cm and 1000 cm for the right room. These readings are illustrative and have not been produced or verified by an OCR pipeline.

For a complete v1 reference drawing:

- Write all dimension labels parallel to the measured spans, including vertical dimensions.
- Add the corridor's centerline width.
- Add corridor length and connection offsets if exact placement is required.
- Clarify whether each room entrance is an open passage or a door.
- Use the gap-and-perpendicular-marks notation and clear-width label for any intended door.

The original drawing can still serve as an incomplete draft fixture. Missing corridor dimensions or exact offsets must remain visible as unresolved information rather than becoming invented exact measurements.

## Review checklist

Before accepting a reconstructed layout:

- Room shapes are rectangular or square, with the intended orientation and connectivity.
- Every confirmed dimension has an identifiable span and measurement basis.
- Centerline dimensions and door clear widths are kept distinct.
- Shared walls exist once and connect to the correct junctions.
- Direct room connections do not acquire an unintended corridor.
- Door openings retain the intended clear width and reviewed location.
- Inferred values and configured defaults are distinguishable from confirmed measurements.
- Conflicting dimensions and unsupported geometry have been resolved.
- Current height/thickness settings are applied and geometry is revalidated.
- Gameplay requirements, collision, and navigation are checked separately from input recognition.


## Shape-first local workspace (4 November 2026)

The new default launchers do not require written dimensions or numeric OCR. Keep
using orthogonal rectangular rooms/corridor segments and gap + endpoint ticks for
doors. Suggested sizes are design choices, adjustable with locks and user overrides;
they are not measurements recovered from ink. Confirm the current saved plan before
export. Choose geometry-only delivery or Playable level with distinct Start/Goal;
Unreal remains responsible for final collision and Pawn readiness. The earlier
numeric convention still applies to the separate strict-measurement workflow.
