from collections import Counter
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from SketchPipeline.experiments.geometry_study import OUT, BASE, ARMS, MANIFEST, samples, summary
from SketchPipeline.experiments.geometry_review import build
from SketchPipeline.synthetic.augment import ROOT, read, write, sha


def count_f1(records):
    tp = sum((r["metrics"]["openings"]["true_positive"] for r in records))
    p = sum((r["metrics"]["openings"]["predicted"] for r in records))
    t = sum((r["metrics"]["openings"]["reference"] for r in records))
    return 2 * tp / (p + t) if p + t else 0.0


def paired_intervals(records):
    result = {}
    rng = np.random.default_rng(20261019)
    for cohort in ["all", "human", "synthetic"]:
        selected = [s for s in samples() if cohort == "all" or s["origin"] == cohort]
        groups = sorted({s["base_plan_id"] for s in selected})
        ids = {g: [s["id"] for s in selected if s["base_plan_id"] == g] for g in groups}
        deltas = {arm: [] for arm in ARMS[1:]}
        for _ in range(2000):
            chosen = [sid for g in rng.choice(groups, len(groups), replace=True) for sid in ids[g]]
            baseline = count_f1([records["baseline"][sid] for sid in chosen])
            for arm in deltas:
                deltas[arm].append(count_f1([records[arm][sid] for sid in chosen]) - baseline)
        result[cohort] = {
            arm: dict(
                delta_f1_95_percentile_interval=np.percentile(v, [2.5, 97.5]).tolist(),
                parent_groups=len(groups),
                replicates=2000,
                scope="Conditional retrospective validation-plan bootstrap; not unseen-writer uncertainty.",
            )
            for arm, v in deltas.items()
        }
    return result


def run(reuse_integrity=False):
    records = {
        arm: {s["id"]: read(OUT / arm / s["id"] / "metrics.json") for s in samples()}
        for arm in ARMS
    }
    report = summary()
    for arm in ARMS:
        for cohort, value in report[arm].items():
            op = value["openings"]
            den = op["predicted"] + op["reference"]
            op["f1"] = 2 * op["true_positive"] / den if den else None
    intervals = paired_intervals(records)
    integrity = {}
    if reuse_integrity:
        prior = OUT / "before-noop-fix/final_report.json"
        integrity = read(prior)["verification"]
        integrity["source_integrity_check_reused"] = True
        integrity["source_integrity_as_of_utc"] = datetime.fromtimestamp(
            prior.stat().st_mtime, timezone.utc
        ).isoformat()
        integrity["source_integrity_reuse_reason"] = (
            "Raw-image reads later returned OS PermissionError; postprocessing replay consumed only stored predictions, with no source writes."
        )
    else:
        manifest = read(MANIFEST)
        integrity["all_720_source_images_unchanged"] = all(
            (
                sha((MANIFEST.parent / s["image_path"]).resolve()) == s["image_sha256"]
                for s in manifest["samples"]
            )
        )
        old = read(ROOT / "Saved/Augmentation/v1/preexisting_hashes.json")
        protected = {p: h for p, h in old.items() if p.startswith(("Data/", "Source/"))}
        integrity["preexisting_data_and_unreal_sources_unchanged"] = all(
            ((ROOT / p).exists() and sha(ROOT / p) == h for p, h in protected.items())
        )
        integrity["protected_files_checked"] = len(protected)
    integrity["baseline_opening_matches_unchanged"] = all(
        (
            all(
                (
                    records["baseline"][s["id"]]["metrics"]["openings"][k]
                    == read(BASE / "baseline" / s["id"] / "metrics.json")["metrics"]["openings"][k]
                    for k in [
                        "true_positive",
                        "predicted",
                        "reference",
                        "unmatched_reference_ids",
                        "unmatched_prediction_ids",
                    ]
                )
            )
            for s in samples()
        )
    )
    checks = {}
    for arm in ARMS:
        checks[arm] = dict(
            evaluated=len(records[arm]),
            statuses=dict(Counter((r["status"] for r in records[arm].values()))),
        )
    model_path = Path((OUT / "model-path.txt").read_text().strip()) / "model.safetensors"
    with model_path.open("rb") as f:
        integrity["model_weights_sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
    integrity["human_correction_seconds"] = None
    integrity["browser_visual_qa"] = (
        "file:// navigation rejected by browser security policy; no workaround attempted. Static JS syntax check and generated overlay inspection performed."
    )
    write(
        OUT / "final_report.json",
        dict(
            results=report,
            confidence_intervals=intervals,
            initial_protocol=read(OUT / "protocol.json"),
            guided_protocol=read(OUT / "guided_protocol.json"),
            runtime=read(OUT / "vlm_runtime.json"),
            completeness=checks,
            verification=integrity,
            postprocessing_fix=(
                read(OUT / "postprocessing-fix.json")
                if (OUT / "postprocessing-fix.json").exists()
                else None
            ),
            policy="All 19 images per arm included, failed cases contribute empty geometry and all reference misses. Numeric OCR fixed across arms. Human correction time pending.",
        ),
    )

    def pct(x):
        return "undefined" if x is None else f"{100 * x:.1f}%"

    lines = [
        "# Geometry separation and local VLM pilot — 2026-10-19",
        "",
        "**Decision:** use conservative grid suppression as the leading opt-in candidate. Keep the baseline available. The simple annotation filter and this small local VLM need further validation before default deployment.",
        "",
        "## Scope and method",
        "",
        "19 frozen validation originals: five human drawings and 14 synthetic renders, representing 11 parent-plan groups. This is an adaptive, retrospective development study. Images from the same synthetic plan are not independent observations; no new writers or test-set generalization are claimed.",
        "",
        "Every arm shares the saved RapidOCR hypotheses and working-image frame. Ground truth enters only after prediction is persisted. Existing opening endpoint tolerances and region IoU ≥ 0.50 are unchanged. Exact topology requires both all matched regions with no extras and the correct multiset of opening-linked region pairs. One human sample has no region reference, leaving 18 scorable images.",
        "",
        "Arms: baseline replay; conservative periodic grid suppression; grid plus a deterministic contrast/width annotation rule; local VLM-only geometry; bounded hybrid using structural candidates and VLM keep/reject decisions. The annotation rule is not a trained semantic segmentation model.",
        "",
        "The local model is quantized Qwen2.5-VL-3B-Instruct, pinned at `46d4cf06a06ffc1a766c214174f9cbed2f45bcab`, using MLX-VLM. No fine-tuning or external image submission took place.",
        "",
        "An initial strict-format preflight and an array-constrained preflight failed through schema confusion, repetition, or truncation. Their responses are preserved separately. The final run constrains JSON syntax and uses boolean decisions for supplied candidate IDs, normalized deterministically to selected-ID lists. Native rectangle suggestions are disabled; every reported exact-topology score uses the same graph decoder. This format iteration used validation data and is explicitly not a fresh holdout.",
        "",
        "The bounded hybrid can add up to four opening intervals but cannot add new walls; its wall recall is limited by the structural candidate set. This experiment does not rule out stronger VLMs, local crop classifiers, different fusion rules, or trained geometry models.",
        "",
        "## Measured results",
        "",
    ]
    for cohort in ["all", "human", "synthetic"]:
        lines += [
            f"### {cohort}",
            "",
            "| Arm | Opening P | Opening R | Opening F1 | Exact topology | Geometry/VLM p50 / p95 seconds | Failed |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for arm in ARMS:
            r = report[arm][cohort]
            op = r["openings"]
            top = r["exact_topology"]
            tm = r["inference_seconds"]
            lines.append(
                f"| {arm} | {pct(op['precision'])} | {pct(op['recall'])} | {pct(op['f1'])} | {top['correct']}/{top['scorable']} | {tm['p50']:.2f} / {tm['p95']:.2f} | {r['failed']} |"
            )
        lines.append("")
    lines += [
        "Timings exclude shared cached OCR, source-image preparation and initial model loading, and include the common topology stage. Hybrid timing adds the measured structural-stage cost. These are observed local wall-clock timings, not a controlled hardware performance benchmark. Model initialization and peak generation memory are separately recorded.",
        "",
        "## Interpretation",
        "",
        "- Grid suppression removes only faint pixels supported by repeated axis-aligned line families. High-contrast crossings and original RGB are retained. Rotated/perspective grids can cause abstention; faint wall pixels remain a known risk requiring broader capture tests.",
        "- The major human precision improvement comes from Data_18: baseline 2 matched openings out of 54 predictions becomes 2 out of 2 after grid suppression. Other human validation cases retain their opening counts. Five human plans are too few to establish broad generalization.",
        "- The annotation rule removes many nonstructural rail candidates but also loses genuine openings, especially in synthetic cases. A higher F1 alone does not justify accepting its recall loss.",
        "- VLM quality must be judged by these localization and topology results, not by valid JSON. The guided grammar has no ground-truth coordinates. Unsupported new walls are rejected using pixel evidence; unresolved opening attachments remain visible to the common graph decoder.",
        "- In all 19 hybrid responses the model retained every supplied candidate and added no geometry. A no-op guard preserves the complete structural recovery evidence. The final hybrid predictions are therefore equivalent to the structural arm; the VLM provided no semantic improvement. Original recorded model times were retained when replaying this postprocessing fix.",
        "- Region and wall coverage metrics, endpoint errors on matched openings, unmatched-opening correction proxies and parent-plan bootstrap intervals are in `final_report.json`. Bootstrap intervals remain conditional on this small validation set.",
        "",
        "## Actual correction time",
        "",
        "Human correction time has not been measured and remains null. No duration was inferred from false-positive counts. `review_benchmark.html` records actual wall/opening additions, deletions, endpoint movement, wall-clock duration and visible-tab duration. It exports local JSON; the result is not accepted metric geometry or automatically trusted training GT.",
        "",
        "For a useful timing study, allocate blinded variants to reviewers, counterbalance order and use separate practice examples. Seeing the same plan repeatedly introduces learning effects. Independently verify corrected geometry before comparing speed. The comparison gallery reveals arm identities and should be viewed after assigned blinded reviews.",
        "",
        "Browser file navigation was blocked by the computer-use security policy. Static JavaScript syntax was checked; browser interaction was not verified. No alternate route was used to bypass that restriction.",
        "",
        "## Integration and next decision",
        "",
        "The production UI still defaults to the existing baseline. The Python API/CLI now accepts an explicit `geometry_profile` / `--geometry-profile` of `baseline`, `grid`, or `structural`; the new settings affect geometry only and receive distinct revision hashes. OCR uses untouched source RGB. VLM runs remain offline experiments.",
        "",
        "Example opt-in run from the repository root:",
        "",
        "```sh",
        "Saved/Step07/python/bin/python -m SketchPipeline.perception.run --image Data/Data_18.png --geometry-profile grid --output Saved/GeometryStudy/v1/integrated-grid",
        "```",
        "",
        "Before a dedicated segmentation/keypoint training run, export versioned dimension-rail/grid supervision and review real same-ink annotation confusions. Existing synthetic masks omit separate rail/grid masks, while human traces are approximate rather than dense pixel GT. This pilot does not justify training against unverified background labels. No geometry training was started.",
        "",
        "Reproduce classical arms with `python -m SketchPipeline.experiments.geometry_study` in the Step07 runtime; final VLM arms with `python -m SketchPipeline.experiments.geometry_vlm_guided` in the isolated geometry-study runtime; publish with `python -m SketchPipeline.experiments.geometry_report`. All existing source images, GT and Unreal code remain unchanged.",
        "",
        "Artifacts: `Saved/GeometryStudy/v1/final_report.json`, `index.html`, `review_benchmark.html`, per-arm predictions/metrics, raw model prompts/responses, protocols, dependency freeze and verification.",
        "",
        "The 720-image and 973-protected-file integrity checks passed before the final postprocessing replay. Subsequent raw-image reads returned an OS permission error; the final replay reused stored predictions and that explicitly dated integrity check. No source data was rewritten. Full fresh-source reproduction requires file access to be available.",
        "",
        "Model sources: [original Qwen card](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct), [quantized snapshot](https://huggingface.co/mlx-community/Qwen2.5-VL-3B-Instruct-4bit/tree/46d4cf06a06ffc1a766c214174f9cbed2f45bcab), [MLX-VLM](https://github.com/Blaizzy/mlx-vlm).",
    ]
    (ROOT / "Docs/geometry_multimodal_pilot_results_2026_10_19.md").write_text(
        "\n".join(lines) + "\n"
    )
    build()
    print(json.dumps(dict(results=report, verification=integrity), indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reuse-integrity", action="store_true")
    a = p.parse_args()
    run(a.reuse_integrity)
