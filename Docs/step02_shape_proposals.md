# Shape-first Step 2 — Local learned proposals and development pilot

> **4 Kasım 2026 ölçüm düzeltmesi:** Önceki insan opening paydası incidental bir kırığı da içeriyordu. Aynı altılıda 18 yerine 17 gerçek geçiş var. Eski deney kayıtları korunuyor; [düzeltme notunu](shape_opening_metric_correction_2026_11_04.md) esas al.

22 October 2026. Engineering and development-pilot delivery for Step 2 of
[the shape-first guide](ShapeFirst_Implementation_Guide_TR.md).

**Result:** a real local segmentation model now produces editable shape-authoring
v2 proposals without numeric OCR. The synthetic development targets passed. The
selected model failed to recover usable region/topology geometry on the six human
drawings in this pilot. It is therefore a development proposal backend, with a
working manual correction path, **not a validated human-sketch automation solution**.
No new upload default, physical sizing, Unreal export or production-readiness claim
is made. Step 3 can use manually corrected topology as specified in the guide.

## What runs

`SketchPipeline/shape_authoring/` contains:

- `synthetic.py`: new clean/wavy/grid/stray/broken renders with exact wall,
  room/corridor interior, tick, junction and open-interface masks. No human
  approximate polygon is treated as dense foreground/background supervision.
- `model.py`, `train.py`: a project-authored six-head U-Net, trained from scratch,
  and a real PyTorch inference adapter. Both candidates were actually trained.
- `models/shape-unet-v1.pt`, `models.lock.json`: selected 1.1 MB weights and
  pinned SHA-256, architecture, training protocol and proposal configuration.
- `decoder.py`, `proposals.config.json`: structural proposals and bounded
  deterministic regularization; no physical units inferred from the image.
- `propose.py`: shape-only CLI/function producing `authoring.json`, `proposals.json`,
  raw `model-masks.npz`, working/cleaned images and the grid-suppression mask.
- `jobs.py`, `server.py`, `review.html`: opt-in local job API and a minimal real
  geometry correction tool, separate from the planned professional Step 4 UI.
- `pilot.py`: persisted predictions, scoring and annotated comparison gallery.

The previous Qwen model is not loaded. All model training/inference occurred locally;
no source image was submitted to a cloud model. Only the new procedural masks were
used for training, with no external pretrained weights. The architecture and weights
are project-authored; this repository currently declares no redistribution license,
so no new permissive model license is asserted. PyTorch is a third-party runtime
with its own [license](https://github.com/pytorch/pytorch/blob/main/LICENSE).

## Run locally

The existing isolated training runtime already contains the required packages.
`requirements.txt` records the versions used. This runtime does not need OCR for the
new path; the existing OCR environment remains unchanged.

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.server --port 8766
```

Open [the local review workspace](http://127.0.0.1:8766/). Upload a PNG/JPEG. Proposals
are never automatically confirmed. Draw rooms/corridor rectangles, move/resize them,
change their type, add a door/open interface on a shared wall, select/delete an
opening, undo/redo, save a draft and reopen it. Manual mode is available under
Advanced details. Model failure or timeout automatically retains the image and opens
an empty editable plan. The Download button returns authoring JSON, not validated
Unreal geometry. A resize that detaches an opening preserves its draft input and
reports the unresolved attachment; it cannot become a new connection silently.

One-shot inference:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.propose \
  --image Data/Data_18.png --output Saved/ShapeFirst/example-run
```

Use a new output directory for each run. `--backend classical` explicitly selects the
CV-only comparison path; it is never reported as a trained model. `--backend manual`
creates the same shape contract without inference. No observation document or fake
text record is produced by any of these shape-only modes.

The default worker timeout is 45 seconds. A failed model load, checksum mismatch,
missing runtime, timeout, cancellation or empty detection yields a manual plan with
the failure and actual elapsed time recorded. A classical result is never substituted
and labeled AI. Retry retains the original attempt. Retrying a manually edited job
is rejected to preserve the edits; start a separate job instead.

## Proposal contract and decoder

The existing preprocessing code preserves EXIF/original↔working transforms. A bounded
axis-angle estimate deskews only when multiple long strokes support a small global
rotation. Faint periodic grid suppression reuses the conservative structural code:
raw and cleaned images are retained; dark crossings are protected; uncertain grid
families are left intact. The working image has maximum side 256 for this pilot.
This resolution and the limited synthetic training distribution are material
limitations, particularly for photographs and small details.

The model predicts six actual probability maps. Logical wall boundaries are distinct
from physical ink: a virtual closure requires learned paired ticks, collinear wall
support and a blank interval, or a separately learned open-interface response. Large
unsupported gaps are not joined solely to close a rectangle. Raw candidate masks
and failed interpretations remain available in the output.

Region contours are checked for rectangular fill/aspect and fitted with local
structural ink using robust medians. Snapping is bounded by stroke scale and image
size. Overlapping proposals are withheld rather than repaired into invented valid
geometry; the raw maps and threshold alternatives retain the ambiguity. Boundaries
are noded at shared corners/T junctions and stored once with their owners. Every
promoted opening must have two attached rectangular regions. Doors additionally
require a real gap, perpendicular ink extending on both sides at both ends, and
learned tick support. A single tick, accidental gap, overlap or proximity does not
create a door. Open interfaces require learned interface support.

Thresholds 0.5/0.4/0.6 provide alternate complete interpretations in `proposals.json`;
only the primary is seeded into the minimal review tool. Shared-wall multi-doors keep
separate IDs and intervals; corridor bends keep separate rectangles and an explicit
open interface. All geometry is proposed/unconfirmed, physical values are empty,
acceptance is pending, and no cm scale or calibrated confidence is claimed.

Manual edits preserve region/opening IDs and unambiguous wall/junction identities.
Splits with ambiguous identity receive new IDs. Unchanged model proposals retain
their provenance; user edits use `user`. Draft writes check the exact base revision
and reject stale saves. This is minimal geometry persistence for Step 2, not the
complete accepted-snapshot/export lifecycle of Step 5.

## API

The server binds only `127.0.0.1`. Bootstrap returns the local session token; mutation
requires `X-Shape-Token` and validates the Origin when supplied. No authentication or
hosted SaaS is added.

| Request | Meaning |
| --- | --- |
| `GET /api/bootstrap` | Session token and saved jobs |
| `POST /shape-jobs` | Raw PNG/JPEG bytes, `X-File-Name`, optional `X-Shape-Backend` |
| `GET /shape-jobs/{id}` | Job status, elapsed time, source hash, attempt |
| `GET /shape-jobs/{id}/proposals` | v2 authoring document, alternatives, model/config provenance, diagnostics |
| `GET /shape-jobs/{id}/image` | Retained working-image PNG |
| `POST /shape-jobs/{id}/cancel` | Cancel inference and make manual state available |
| `POST /shape-jobs/{id}/retry` | New attempt; refuses to overwrite manual edits |
| `POST /shape-jobs/{id}/edit` | Base revision + rectangles/opening edits; validated draft + unresolved items |
| `GET /pilot/` | Annotated development comparison gallery |

The job queue is bounded, inference runs in a killable subprocess, and output is
separate from source images. Restart reopens finished jobs/drafts and identifies
interrupted work. There is no canonical-layout download endpoint in this server.

## Frozen development comparison

`Saved/ShapeFirst/v1/protocol.json` was written before training and comparison.
The configured targets were region P≥0.80/R≥0.70, opening P≥0.80/R≥0.70 and exact
topology≥0.50. They apply to the synthetic development set; they do not establish
human drawing readiness. The same targets must not be relabeled as a human benchmark.

Training used 96 new parent seeds × four styles = 384 images, 20 epochs, batch 12,
seed 220126. Candidate widths 12 and 20 were trained on Apple MPS in approximately
67 and 140 seconds, excluding dataset preparation. Model selection used synthetic
exact topology, then opening F1, region F1 and lower latency. Both arms had identical
training inputs and fixed epochs, with no validation early stopping. There are 12
different development parent seeds × five styles = 60 synthetic images. No parent
seed crosses these sets. This is template-family development testing, not an
independent family or writer evaluation.

Six existing human drawings (Data 3, 8, 18, 31, 41, 45) are additional development
checks. Writers are not known to be independent. Human annotations are approximate;
Data 3/8 have no region traces, so region metrics cover the remaining four images
(15 regions). Existing structural labels were inspected in the saved
`human-reference-audit.jpg`; they were not retraced, made pixel-perfect or used for
training. Human opening localization covers 18 labeled openings. Attachment labels
from polygon proximity are diagnostic only; human exact topology is deliberately
unscored. No physical dimension label enters inference.

Decoder development used one `2000_wavy` preflight before the full comparison. This
is explicitly adaptive development evidence, not a fresh holdout. The full comparison
froze source/config/model hashes before prediction and read each geometry reference
only after that prediction was persisted. Every outcome, including empty/incorrect
predictions, remains in the report.

| Arm, 60 synthetic images | Region P/R | Opening P/R | Exact topology |
| --- | --- | --- | --- |
| CV-only at 256 px | 1.7% / 7.2% | undefined / 0% | 0/60 |
| U-Net width 12, selected | 90.9% / 94.4% | 100% / 88.1% | 43/60 |
| U-Net width 20 | 95.2% / 100% | 100% / 83.1% | 33/60 |

The CV arm is an OCR-free low-resolution ablation using the existing structural
line/topology code plus the conservative opening gate. It does not reproduce the
old OCR-assisted 1600-pixel production baseline. Its weak results do not establish
superiority over a well-tuned high-resolution baseline or any external model.

Selected-model synthetic region matching: 170/187 predictions against 180 references
at IoU≥0.5. All 170 matched regions also had the correct room/corridor type in a
separate check. Opening localization: 141/141 against 160 references, with matching
type and endpoint error ≤4% of maximum image side. Door-only: 112/112 against 130.
All 141 matched openings had correct region attachment; false/duplicate connections
were zero in this synthetic set. Exact topology requires all regions/openings and
the correct multiplicity of connections; loose region IoU alone is insufficient.

| Scenario, selected model | Exact topology |
| --- | --- |
| Clean | 10/12 |
| Wavy | 10/12 |
| Grid + stray/digit distractors | 9/12 |
| Stray marks + digit distractors | 8/12 |
| Broken strokes without extra door labels | 6/12 |
| Shared-wall two-room family | 9/10 |
| Shared wall with two doors | 8/10 |
| Branching/T family | 10/10 |
| Four-room cycle | 10/10 |
| Corridor bend | 3/10 |
| Staggered outline | 3/10 |

Rows group the same 60 images by style or topology family, so they must not be added.
Failures in bends/staggered plans remain visible; these are not universally solved.

**Human outcome:** width 12 matched **0/4 predicted regions against 15 references**
and **0 openings against 18 references**. Two of six images had empty detection;
others contained incorrect proposals and still need manual correction. Width 20
matched 1/3 regions against 15 and zero openings. The CV arm matched 2/3 regions
against 15 and zero openings. This pilot does not demonstrate human automation,
numbered→unnumbered human invariance, new-writer recovery or broad photo robustness.

Selected synthetic inference/preprocessing/decoder elapsed p50/p95 was 0.102/0.135 s
in the in-process CPU comparison. Human p50/p95 was 0.087/0.118 s. These include model
load in that process, but exclude process startup, upload, scoring and correction.
Job elapsed time separately includes worker startup; training/model initialization
are also recorded. These are local observations, not hardware performance promises.

**Human correction time remains null.** The UI records actual review-session wall and
visible time, but the agent's browser test is not a human correction benchmark.
Independent unseen-writer data is unavailable; generalization remains unknown.

## Evidence and verification

Artifacts under `Saved/ShapeFirst/v1/`:

- `protocol.json`, `comparison-freeze.json`, `environment.freeze.txt`.
- Both candidate checkpoints, training reports, losses and logs.
- All 198 comparison records (66 images × 3 arms), raw model masks, proposals,
  metrics, annotated previews, `report.json` and `gallery.html`.
- `human-reference-audit.jpg`, `manual-review-browser.jpg`, `verification.json`.
- `regression.log`, `final-targeted-tests.log`, cancellation/retry evidence.

The selected packaged checkpoint hash is:

```text
e8f6637b5be5f2b399f43f1417944e41105a4afbe58008331330d088b8affbde
```

All 4,961 protected `Data/` files were hash-checked unchanged after the pilot and
again after the regression suite. Source images, annotations and accepted v1 files
were not overwritten. Default inference from the packaged checkpoint reproduced
the pilot topology in a fresh output directory. Runtime checksum protection was
added after comparison; the comparison's explicitly pinned checkpoint path and
recorded prediction outputs remain unchanged.

281 Python regression tests completed successfully (one real-PyTorch test skipped
in the OCR environment). A separate 60-test run in the PyTorch environment passed,
including actual model inference and checksum rejection. Additional checks cover
no-OCR imports, manual/blank inputs, missing checkpoint/runtime, timeout, paired
versus single ticks, multi-door representation, stale saves, preserved IDs, restart,
HTTP token checks and conflict preservation. Cancellation→manual recovery→retry was
also exercised with real processes. JavaScript syntax passed `node --check`.

In the browser, the learned output was opened and a region type was edited/saved.
A separate manual start on the real Data 18 image created three rooms and two doors,
saved a valid shape-authoring draft and displayed no unresolved attachments. That
manual result is separate from the unsuccessful AI prediction. The saved screenshot
and revision provide the interaction evidence.

To reproduce training and comparison, choose a NEW experiment directory and keep all
previous outcomes. Generate fixtures, train both frozen candidates, then compare:

```sh
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.synthetic --output Saved/ShapeFirst/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.train --width 12 --output Saved/ShapeFirst/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.train --width 20 --output Saved/ShapeFirst/reproduction
Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.pilot --output Saved/ShapeFirst/reproduction
```

The pilot writes its selected-model lock; keep the prior lock/checkpoint if retaining
the current packaged model. Seeds do not promise bit-identical training across
hardware/framework versions; see [PyTorch reproducibility guidance](https://docs.pytorch.org/docs/stable/notes/randomness.html).
Do not tune the preserved comparison and present it as unseen evaluation.

## Readiness

The real-model adapter, conservative decoder, proposal API, raw evidence, editable
failure path and measured gallery are delivered. Synthetic development targets are
met; human drawing automation quality is not. Improving that quality needs broader
procedural capture/ink variation and separately reviewed human geometry/keypoint
supervision, with an independent writer evaluation when available. Step 3 sizing
work may proceed from corrected/manual topology. The original measurement pipeline
remains available and the web upload default has not been changed.
