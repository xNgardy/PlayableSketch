# Opening-offset correction — 16 October 2026

The author clarified that offsets in all previous drawings measure from the stated corner/junction to the near opening edge. This supersedes the 14 October corner-to-center clarification. Original images and all 56 visible numeric transcriptions are unchanged.

## Rules

For a minimum-corner edge offset `s` and clear opening width `w`:

```text
opening interval = [s, s+w]
derived center = s+w/2
remaining span = wall length - s - w
```

For a maximum-corner reference, measure back toward the first opening edge. Metric dimensions now carry `basis: edge_offset` and target `opening_offset`; `reference` accepts `min_corner` or `max_corner`. Python and Unreal validate both directions. Existing explicit `basis: center_offset` dimensions retain their old meaning for backward compatibility. Basis is included in conflict signatures so an explicit center measurement is not confused with an edge measurement.

Canonical `Opening.center_offset_cm` remains the derived center relative to the supporting wall start. This avoids changing the geometry-builder representation and existing explicit snapshots. A paper corner offset is never copied into that field without conversion and wall-local rebasing.

## Corrected references

| Case | Written edge offset | Clear width | New opening interval / center |
| --- | ---: | ---: | --- |
| User's Genel.png example | 50 | 120 | interval [50,170], center 110, upper remaining span 30 on a 200 cm wall |
| Data_3 | 200 | 120 | interval [200,320], center 260 |
| Data_4 | 150 | 180 | interval [150,330], center 240 |
| Data_5 | 450 | 150 | interval [450,600], center 525; physical corner obstruction |
| Data_6 | 250 at both entrances | 180, derived | aligned entrance centers y=340; room minima remain aligned |
| Data_7 | 300 from left corners | 180, derived | aligned entrance centers x=390 |
| Data_8 | left 300; right 200 | left door 120; right passage 180 | inherited center alignment gives y=360; right room min_y=70; wall-local door center remains 100 |
| Data_10 | 250 at both entrances | unknown | transverse center remains null; missing measurements stay unresolved |

Corridor centerline widths remain 200 cm in Data_6–8. At the reference thickness of 20 cm, an open entrance has derived clear width 180 cm. Edge-offset conversion uses the clear width, not the corridor centerline width. The previous fixture interpretation of aligned entrance centers is retained and explicitly documented; it is not a new claim inferred from pixel scale.

Data_5 is dimensionally consistent but physically blocked by a neighboring wall cap. It remains an accepted **metric reference**, with a recorded expected geometry issue; Unreal refuses generation rather than shifting the opening or narrowing its clear width. A thickness change may similarly conflict with a confirmed edge offset when a derived entrance width changes. Such settings changes require reconstruction/review rather than silently changing the written measurement.

## Updated artifacts

- Drawing convention, contract explanation, implementation guide and Data_11–20 drawing brief.
- Data_1–10 source metadata; affected door/corridor positions and offset fields.
- All 28 generated reference documents, revisions `manual-edge-2`, converter version `manual-fixture-conversion/1.1`.
- Eleven interpreted pixel offset spans now end at their near annotated gap endpoint. Text polygons, wall traces, gap endpoints and original photos are unchanged.
- Python schema/metric validation and Unreal parser; regressions cover preserved values, near/far corner directions, mixed explicit center/edge measurements and unequal entrance widths.

Existing `Saved/Step06–08` runs and topology-review revisions were not overwritten. They are historical artifacts; topology review uses px geometry and does not convert written offsets. Previously imported Unreal assets retain their explicit stored geometry until the corrected reference is reimported. New Data_11–14 PNGs already present in `Data/` were not modified or assumed to match the requested brief; they still need inspection/annotation from their actual content.

## Verification and recovery

- 117 Python tests passed.
- All 28 generated references passed reproducibility checks.
- Dataset audit passed: ten samples, 56 text regions.
- All ten original photo hashes and all 56 manual numeric transcriptions match the pre-correction snapshots.
- Mac Development Editor build succeeded. The existing temporary Xcode compatibility wrapper was used and engine SDK configuration was restored byte-for-byte.
- Three Unreal import automation tests passed, zero failures/skips: canonical explicit import, explicit disk persistence and legacy JSON import. Physical Data_5 rejection and edge-offset/settings conflicts are expected test cases.

Pre-correction snapshots, source image hashes, pixel-span changes, build log and Unreal report are under `Saved/OffsetMigration/20261016T183703Z/`. Earlier dated verification reports describe the original center-based interpretation and were preserved.
