# Step 07 — OCR, wall centerlines and opening evidence

Implemented on 2026-10-15. An image now produces independent, unreviewed observations in the original pixel frame. Manual annotations are used only after prediction to measure the result. No training, metric reconstruction or Unreal changes are included.

## Run

From the repository root, use a separate environment for OCR dependencies:

```sh
python3 -m venv Saved/Step07/python
Saved/Step07/python/bin/python -m pip install -r SketchPipeline/requirements-perception.txt
Saved/Step07/python/bin/python -m SketchPipeline.perception.run --dataset --output Saved/Step07/my-review
```

Open `Saved/Step07/my-review/index.html`. Left is the manual reference; right is the independent prediction. Each sample links to Hough/LSD line overlays, metrics, observations and the working artifact. Choose a new output directory for each run. A failed run removes its staging directory instead of publishing a partial result.

For a new image without any manual reference:

```sh
Saved/Step07/python/bin/python -m SketchPipeline.perception.run --image Data/Data_3.jpeg --output Saved/Step07/my-image
```

Optional flags: `--detector lsd` (default), `--detector hough`, `--max-side 1600` (default), and `--manifest path/to/manifest.json` for a dataset run. Both line detectors are always measured in dataset mode; the selected detector supplies the exported lines and gap evidence. Missing/corrupt/blank inputs follow Step 06's input policy.

## Architecture and reasoning

`perception/run.py` coordinates existing Step 06 preprocessing with four separate jobs:

| Module | Responsibility |
| --- | --- |
| `ocr.py` | Detect text polygons, rectify crops, recognize four rotations and retain alternatives; join nearby number/unit fragments |
| `numeric.py` | Parse explicit cm labels without repairing ambiguous OCR digits or converting units |
| `geometry.py` | Detect lines with Hough/LSD, merge candidate edges/fragments, protect crossing walls during text masking, and gather gap/context evidence |
| `evaluate.py` | Compare completed predictions with manual original-frame references; report development metrics |

`predict(image, adapter, ...)` accepts image pixels and fixed configuration. It has no ground-truth or metric-layout argument. Dataset mode completes prediction before loading manual observations or annotation sidecars. It does not use annotated crops, expected dimensions, reference wall endpoints, or reference openings to produce predictions.

### OCR: location and reading are separate

The baseline uses **RapidOCR 3.10.0**, its bundled **PP-OCRv6 small detection and recognition ONNX models**, and **ONNX Runtime 1.31.0** on CPU. The detector returns polygons. The recognizer separately reads rectified crops at 0°, 90°, 180° and 270°. When a substantial tall polygon suggests vertical text, detection also runs once at 90° and maps proposals back to the working frame; contained duplicate proposals are suppressed. This is an image-level fallback, not a full-page rotation for every label. Original detector proposals and matrices remain in `text_detection`. If the first pass finds no text or no qualifying tall hint, the fallback does not run; difficult vertical handwriting can still be missed. These stages can be replaced independently later. The pinned package's separate stage interfaces were smoke-tested on this Mac; this is not a claim that the model is specialized for handwritten floor plans. [RapidOCR stage outputs and usage](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/).

`models.lock.json` records the expected model filenames and SHA-256 hashes. Startup checks package version and both model hashes, then uses explicit local model paths. It never silently substitutes a different model or downloads missing model weights during inference. The run records resolved configuration, hardware/platform, runtime versions and actual ONNX session providers. Installation obtains the bundled models through the package; prediction runs locally without sending photos to a service.

The pinned detector implementation sorts boxes separately from its score array. The adapter deliberately does not attach those possibly reordered detection scores to polygons. Observation `score` is the selected **recognition** score; it is neither text detection probability nor geometry confidence. Wall/opening scores remain `null`.

Each crop has `working_to_crop` and `crop_to_working` matrices. With Step 06's transform, it also records `original_to_crop` and `crop_to_original`. Four saved crop images make orientation choices inspectable. All exported polygons and line endpoints are back-projected to the encoded original frame.

A valid cm reading with score at least 0.45 is preferred over nonnumeric rotation results; otherwise the strongest raw reading is retained. Different valid numeric readings within 0.12 of the selected score produce `SKETCH_NUMBER_AMBIGUOUS` and a null exported value. Scores below 0.45 remain unknown. These thresholds are baseline heuristics, not calibrated probabilities; other rotation readings remain in the working artifact even when they fall outside that ambiguity window.

For multiline writing such as `400` above `cm`, a bare number can join one nearby standalone `cm` fragment to its right or below. The original fragment IDs, readings, polygons and transforms remain available. Grouped `raw_text` joins recognized fragments with a space; it is not a manual replacement. Spatial grouping can be wrong and requires downstream review.

### Numeric policy

Accepted examples: `700 cm`, `700cm`, `D 120 cm`, `120.5 cm`, `120,5 cm`. Unit matching is case-insensitive. Values must be positive and at most `1e9`. A single dot or comma is a **decimal separator**; thousands separators are not supported. A comma is never stripped to turn `1,000` into 1000.

Unitless `700`, meters (`2.5m`), imperial units (`10 ft`), negative/zero values and malformed strings raise explicit review issues. The parser never changes handwritten-looking OCR substitutions such as `h00cm` into `400 cm`. `600/800 cm` is an explicit alternative, with no selected numeric value. A parsed value is only a candidate measurement; it is not a confirmed dimension or a wall association.

### Lines and centerlines

Both detectors run on the same mildly enhanced gray input. Hough uses Canny edges followed by probabilistic line voting; LSD uses local line/gradient evidence. Their raw segments are not semantic walls. [OpenCV detector APIs](https://docs.opencv.org/4.13.0/dd/d1a/group__imgproc__feature.html).

Text masking operates on a separate detector input. Long structural strokes are protected where they cross a text polygon. Removed text is replaced with estimated local paper background, rather than white, which would invent rectangle edges around OCR boxes. Original color and gray images remain unchanged. Some text or crossing wall evidence can still survive imperfect masking; the retained masks explain these cases.

A weighted median of long axis-like segments estimates small global rotation. Overlapping nearby parallel edges and short collinear fragments can merge into approximate centerline candidates. Larger gaps remain open. Configuration records angle, distance, gap and length thresholds. This cleanup does not orthogonalize a room, close passages or solve junction topology.

Candidate roles are `wall_candidate`, `tick_candidate` or `unknown`; dimension lines are not reliably separated in this baseline and can remain unknown or be misclassified. Border-like and mostly text-overlapping segments are kept as unknown. Double edges can remain on bent or thick strokes; downstream code must not assume every exported line is a separate physical wall.

LSD is the default because its development coverage was substantially stronger on these photographs. Hough remains available for reproducible comparison; this choice has not been validated on independent writers or plans.

### Gaps and openings

Opening detection now combines two line-evidence branches. Text-masked lines provide cleaner wall support; lines detected on the original enhanced image can recover short endpoints and fragments removed by masking. Recovery lines retain their `unmasked` source and are used locally. A short segment with role `unknown` may support a gap proposal when nearby structural evidence supports it; this does not promote that segment to a wall globally. A local endpoint-attachment check also tests whether perpendicular context touches the finite segment or only its infinite extension. The latter is kept as unresolved evidence.

The detector records each plausible pair and its rejection reasons, including alignment, small break, missing structural support, missing endpoint context, a wall blocking the gap, continuous ink through the gap, or duplicate proposal. For each pair it also stores the supporting line IDs and roles, masked/unmasked provenance, endpoint context, nearby OCR evidence, robust support-line fit, residual, and gap ink fraction. These diagnostics explain why a hypothesis was retained or rejected.

An opening shorter than 2.3% of the working image's long side, or without endpoint attachment evidence, remains `unresolved_gap` for review. This is a visual heuristic tuned on the ten development photos; it can reject small real openings in differently framed sketches and must be checked on new plans. A retained `opening_candidate` is still an unreviewed hypothesis, not a confirmed door or passage. Several candidates can describe the same room/corridor topology or be incidental breaks, so the user must review them. `door_like` and `passage_like` are visual evidence labels, not semantic certainty. Nearby text is not automatically the opening width. Every `width_cm` remains `null`; pixel gap length never becomes centimeters. The detector does not fill an opening from the manual annotations.

## Output contract

| Artifact | Contents |
| --- | --- |
| `observations.json` | Existing observations/1.0 schema: original-frame texts, lines and opening polygons; `method: ocr`; `region_annotation_status: partial` |
| `working.json` | OCR fragments, all rotation readings, numeric alternatives, crop transforms, both line-evidence branches, line provenance, retained and rejected opening proposals with reasons, model/configuration provenance and timing |
| `crops/fNNN-rANGLE.png` | Actual recognized crop for each orientation |
| `prediction_original.png`, `prediction_working.png` | Predicted evidence overlays in the two frames |
| `hough_lines.png`, `lsd_lines.png` | Cyan wall candidates and amber unknown/tick evidence |
| `wall_input.png`, `text_mask.png`, `protected_strokes.png` | Debug detector inputs and masking decisions |
| `metrics.json`, `reference.png`, `comparison.png` | Dataset-only evaluation and manual/predicted comparison |
| `report.json`, `index.html` | Dataset-level metrics, provenance and review page |

Extra candidate fields live in a versioned working artifact, not as undocumented fields in the strict observation schema. Observation document IDs derive from the source image hash; revision IDs include the detector/configuration fingerprint. Relative image paths are rebased to the final run directory before publishing. Predictions are stored under `Saved/Step07/`; the manual annotations and existing metric references remain unchanged.

## Measured development result and limitations

**2026-10-19 update:** The 720-image dataset baseline and an isolated TrOCR recognition fine-tuning experiment are measured in [dataset evaluation and OCR fine-tuning](data_training_evaluation_v1.md). That report separates human/synthetic sources, parent-group development tests, numeric F1 and topology failures. The table below remains the historical result on the original ten photos; it is not the score on the expanded dataset. The local UI still uses pinned RapidOCR weights.

The conservative baseline remains at `Saved/Step07/final-review-v1/`. The initial recovery review remains at `Saved/Step07/opening-improvement/full-review-v1/`; the latest endpoint-validation run is `Saved/Step07/opening-improvement/full-review-v4/`. These ten photos informed the implementation, so the results measure **development fixtures**, not unseen-plan accuracy.

| Stage | Result | Meaning |
| --- | --- | --- |
| Text detection | 56/56 reference labels matched; 65 predicted groups | Precision 86.2%, recall 100% at polygon IoU ≥ 0.30; extra groups remain visible |
| Numeric exact | 40/56, **71.4%** | Matched polygon and exact parsed cm value; wrong digits, missing units and ambiguity count as failures |
| LSD walls | Precision coverage 94.2%, recall coverage 93.6% | Length-weighted sampled coverage against manual wall strokes |
| Hough walls | Precision coverage 85.5%, recall coverage 22.4% | Same coverage definition and tolerance |
| Opening candidates, before endpoint validation | 9/11 found, **81.8% recall**; 9/23 matched (39.1% precision) | Contextual recovery raised recall but left many false candidates |
| Opening candidates, endpoint validation | 11/11 found, **100% recall**; 11/16 matched (68.8% precision) | Finite-segment endpoint attachment and small-gap review reduced unmatched candidates from 14 to 5 |

Text matching is one-to-one, with duplicate predictions receiving no extra credit. Wall coverage samples segment length every 4 px and checks nearby, similarly oriented reference strokes; tolerance is 12 px at original long side 1600, scaled by source size with a 6 px minimum, and angle tolerance is 15°. This accommodates approximate manual polyline tracing and different detector fragmentation; it is not a count of correctly reconstructed walls or rooms. Opening matching is one-to-one with both endpoints within 2% of the original long side (minimum 12 px). Empty denominators are `null`.

The latest run matches every annotated opening in these ten photos, including the baseline's Data_3 opening, and emits five unmatched candidates in Data_6, Data_7 and Data_8. Per-image metrics and IDs are in `metrics.json`; each pair's evidence and rejection reasons are in `working.json`.

This is an improved development result, but 100% recall here does not establish general accuracy: the same ten photos guided the threshold choice, five candidates remain unmatched, and differently framed sketches may behave differently. Keep all candidates reviewable before automatic level generation. Wall and OCR results remain unchanged from baseline. Data_9's dimension conflict is still unresolved, and Data_10's missing measurements remain unknown. Step 08 can consume these as uncertain evidence; it must not treat every candidate as a confirmed opening.

OCR mistakes remain in their original crops and alternatives. Data_9's written conflict is not solved or corrected here; Data_10's missing dimensions are not invented. Step 08 handles connectivity candidates, and Step 09 handles dimension association/conflict solving. This baseline is ready to feed those stages as **uncertain evidence**, not to automatically publish a reliable playable level.

## Verification

```sh
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -v
Saved/Step07/python/bin/python -m SketchPipeline.fixtures.build_references --check
Saved/Step07/python/bin/python -m SketchPipeline.preprocessing.dataset
```

The preceding perception revision passed **80 Python tests**; all **28** preserved migration fixtures matched; all **10** manual pixel reference audits passed. The current endpoint-validation change was run end to end on all ten photos and produced schema-valid review artifacts, but the 80-test suite was not rerun after this change. A separate printed `700 cm` smoke test passed in both horizontal and 90° orientations (`Saved/Step07/rotation-smoke.json`); this does not establish rotated handwriting accuracy. The earlier tests cover numeric policy/ambiguity, rotation raster mapping and perspective crop transforms, text masking near walls, no artificial masking rectangles, double-edge merging, opening evidence, both line detectors, evaluation matching, independence from manual labels, model hash rejection, atomic output paths and failure cleanup.

`Saved/Step07/tests.log`, `final-run-v1.log` and `environment.txt` record local verification. No Unreal build was needed because this step changes only Python perception code, dependencies and documentation.

## Geometry pilot update — 2026-10-19

The perception API and CLI now offer opt-in `grid` and `structural` geometry profiles (`--geometry-profile`). The default remains `baseline`; source RGB and OCR behavior are preserved. The 19-original validation pilot also compares offline local VLM-only and bounded hybrid inference. Results, recall tradeoffs, timing scope and pending human correction-time measurement are documented in [geometry pilot results](geometry_multimodal_pilot_results_2026_10_19.md). This does not implement Step 09 or accept metric geometry.

