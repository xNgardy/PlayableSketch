# Step 06 — Pixel references and image preprocessing

Implemented on 2026-10-15. This step prepares measurable image evidence for Step 07. It does not run OCR, detect walls automatically, solve metric coordinates or generate a new Unreal layout.

The ten photographs now have 56 manually annotated text regions, 233 wall/tick line segments and 11 intended opening regions. A separate sidecar contains stroke classes, approximate junctions, incidental gaps and text-to-measured-span associations. The original photos, metric references and Unreal code remain unchanged. Data_9 is still conflicting; Data_10 still lacks measurements.

## Install and run

Run from the repository root. Python 3.13 was used for verification. Image dependencies are separate so the existing contract/import tools can keep their lighter environment.

```sh
python3 -m venv Saved/Step06/python
Saved/Step06/python/bin/python -m pip install -r SketchPipeline/requirements-image.txt
Saved/Step06/python/bin/python -m SketchPipeline.preprocessing.dataset
Saved/Step06/python/bin/python -m SketchPipeline.preprocessing.dataset --output Saved/Step06/my-review
```

The first command audits all references without writing images. The second produces a local review page at `Saved/Step06/my-review/index.html`. Existing run directories are rejected. A failed run removes its staging directory and never publishes a partial result as complete.

Prepare an individual photograph without annotations:

```sh
Saved/Step06/python/bin/python -m SketchPipeline.preprocessing.prepare Data/Data_1.jpeg Saved/Step06/single-image
```

Optional `--config path/to/config.json` accepts `max_side`, `crop`, `deskew_degrees`, `page_corners` and `page_aspect_ratio`. Defaults retain the full image and downsize only when the longest side exceeds 1600 px. Manual crop coordinates are integer `[left, top, right, bottom]` in the EXIF-upright image; right/bottom are exclusive. Manual deskew uses OpenCV's positive counterclockwise angle, at most ±45°, on an expanded white canvas. Crop precedes deskew; resize follows both.

Page rectification requires four **upright** corners ordered TL/TR/BR/BL and a known page width/height ratio. It cannot be combined with crop/deskew. For example, `page_aspect_ratio: 0.7070707` is appropriate only if the visible page is known to be portrait A4. No page format or corners are inferred by this implementation. None of the ten current photos exposes a complete page rectangle, so their default runs apply no page homography.

## Processing and coordinate contract

`SketchPipeline/preprocessing/prepare.py` implements this sequence:

1. Accept JPEG/PNG contents with JPG/JPEG/PNG extensions, at least 16×16 px, at most 40 MP and 20 MB. Reject corrupt, missing or nearly uniform blank inputs with an explanatory error. Composite transparency onto white.
2. Preserve the encoded image as `original.png`; apply all eight EXIF orientations to obtain an upright RGB image. Record the original-to-upright matrix.
3. Apply optional manual page homography, or optional crop and manual deskew. Page geometry corrects perspective; it never determines the level's cm scale.
4. Resize while recording the actual rounded output dimensions. OpenCV resize uses pixel centers: `dst = (src + 0.5) * scale - 0.5`; matrices include that half-pixel translation.
5. Retain color, gray, mild Gaussian-denoised gray and adaptive threshold variants. Thresholding does not classify text versus walls and can lose faint strokes; the color/gray alternatives remain available.
6. Save the composed transform, its inverse, parameters, source hash, runtime versions and quality report. Validate point round trips within `1e-6 px`.

For column vectors, `p_work ~ H * p_original`. Each new operation multiplies on the left. Back-project working detections with `working_to_original` before creating Step 07 observations. The canonical manual evidence stays in the original encoded frame; do not compare a working-frame box directly with an original-frame label. There is no pixel-to-cm scale in this stage.

All coordinates refer to zero-based pixel centers, with `u` right and `v` down. Image corners for transforms are `[0,0]` through `[width-1,height-1]`. Fractional coordinates near the image boundary after resizing are normal. A crop can put some original annotations outside the working frame; their original evidence remains intact.

## Files and review

Versioned references are under `Data/annotations/v1/`; the README defines annotation precision and provenance. These are manually authored approximate traces and enclosing polygons, not predictions or dense segmentation masks. The original 28 metric migration fixtures still reproduce exactly. Stable evidence IDs let those layouts validate against the new annotated observation revision too.

A generated sample directory contains:

| File | Purpose |
| --- | --- |
| `original.png`, `color.png` | Encoded original and prepared working color |
| `gray.png`, `denoised.png`, `adaptive.png` | Alternative inputs for downstream recognition |
| `original_overlay.png`, `working_overlay.png` | Pink text polygons, cyan wall/tick strokes, orange intended openings |
| `comparison.png` | Side-by-side original and working overlays |
| `original_details.png`, `working_details.png` | Purple measured spans with text→dimension IDs; green approximate junctions; brown explicitly noted incidental gaps |
| `preprocessing.json` | Matrices, parameters, hash, counts, quality issues and round-trip errors |

The dataset run also writes `report.json` and `index.html`. `dataset.py` audits source hashes/paths/sizes/orientations, schemas, bounds, annotation counts, line classifications, gap/opening coverage, dimension/evidence associations and metric status before generating artifacts. It checks every annotated point's round trip, including sidecar spans and junctions.

To inspect the result:

1. Open `index.html` and check all labels are enclosed; wall/tick traces follow visible ink, and orange regions occur only at intended passages.
2. Open each measured-span view. Offset spans must reach the opening **center**, especially Data_8; they must not stop at the door edge. Data_9's opposing horizontal spans keep their different values.
3. Compare `gray.png` and `adaptive.png`, especially Data_7. Threshold output is an alternative, not a replacement for the original evidence.
4. Inspect `preprocessing.json`: no fabricated page homography, invertible matrices, round-trip error below `1e-6 px`, and separate annotation completeness versus metric status.

Quality warnings are heuristics, not calibrated recognition scores. Laplacian variance is measured after resolution normalization; paper texture and handwriting can affect it. Data_7's known softness is recorded as `BLUR_OR_FAINT_STROKES_VISUAL_REVIEW` in manual issues even when the automatic blur heuristic does not fire. Softness never deletes a wall. Homography also cannot repair arbitrary bent paper or lens distortion.

## Verification

```sh
Saved/Step06/python/bin/python -m unittest discover -s SketchPipeline/tests -v
Saved/Step06/python/bin/python -m SketchPipeline.fixtures.build_references --check
```

Verified: **59 Python tests passed** (43 existing, 16 added); all **28** preserved migration fixtures still match. Tests cover all eight EXIF orientations against actual raster pixels, crop after EXIF, half-pixel resizing, composed deskew, independently expected homography corner positions, missing page geometry, invalid/corrupt/blank inputs, transparency, input limits, annotation integrity, preserved outputs and failed-run cleanup. Original and working overlays for all ten samples were visually checked. Annotation round-trip error was at most `4.55e-13 px`; this is numerical transform accuracy, not manual annotation accuracy.

The verified review artifacts are in `Saved/Step06/final-review/`; the test log is `Saved/Step06/tests.log`. They can be reproduced with the commands above. This step changes only image pipeline code, annotation data and documentation; no Unreal rebuild is required.

Next: Step 07 will produce independent OCR/line/opening predictions and compare them with these manual references in the same coordinate frame. The ten existing photos remain a development set; an independent held-out dataset is still needed for generalization claims.
