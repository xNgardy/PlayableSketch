from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import html
import hashlib
import json
from pathlib import Path
import platform
import time
import numpy as np
from .protocol import ROOT, POLICY, freeze, read, sha, verify, write
from .metrics import (
    association_metrics,
    compare_layout,
    counts,
    distribution,
    end_to_end,
    endpoint_error,
    numeric_metrics,
    pairs,
    ratio,
    release_gate,
)
from .review import correction_metrics


def original_points(points, working):
    topo = working["topology"]
    center = np.asarray(working["preprocessing"]["working_size_px"]) / 2
    angle = np.radians(topo["rotation_degrees_removed"])
    c, s = (np.cos(angle), np.sin(angle))
    p = (np.asarray(points) - center) @ np.asarray([[c, -s], [s, c]]).T + center
    q = np.c_[p, np.ones(len(p))] @ np.asarray(working["preprocessing"]["working_to_original"]).T
    return (q[:, :2] / q[:, 2:]).tolist()


def graph_metrics(working, reference, side):
    topo = working.get("topology")
    if not topo:
        return dict(status="not_computed", walls=None, junctions=None)
    walls = [
        original_points([e["a"], e["b"]], working)
        for e in topo["wall_graph"]["edges"]
        if e["kind"] == "physical_wall"
    ]
    lines = {l["id"]: l for l in reference["lines"]}
    truth = []
    for stroke in side["strokes"]:
        if stroke["kind"] != "wall":
            continue
        ids = stroke["line_ids"]
        truth.append([lines[ids[0]]["start_px"], lines[ids[-1]]["end_px"]])
    tolerance = max(
        8,
        POLICY["wall_endpoint_fraction"]
        * max(reference["frame"]["width_px"], reference["frame"]["height_px"]),
    )
    matched = pairs(walls, truth, endpoint_error, tolerance)
    nodes = topo["wall_graph"]["nodes"]
    points = original_points([n["point_px_rotated"] for n in nodes], working) if nodes else []
    expected = [j["point_px"] for j in side["junctions"]]
    jp = pairs(points, expected, lambda a, b: float(np.linalg.norm(np.asarray(a) - b)), tolerance)
    return dict(
        status="computed",
        walls={
            **counts(len(matched), len(walls), len(truth)),
            "endpoint_error_px": distribution([e for _, _, e in matched]),
            "tolerance_px": tolerance,
        },
        junctions={
            **counts(len(jp), len(points), len(expected)),
            "distance_px": distribution([e for _, _, e in jp]),
            "tolerance_px": tolerance,
        },
        note="One-to-one whole graph edges vs manual strokes; graph nodes include opening endpoints, so extra nodes count as false positives. No junction type accuracy claim.",
    )


def summarize(records):
    result = dict(samples=len(records), status_counts=dict(Counter((r["status"] for r in records))))
    computed = [r for r in records if r.get("metrics")]
    for key in ("text", "openings"):
        result[key] = counts(
            *(
                sum((r["metrics"][key][k] for r in computed))
                for k in ("true_positive", "predicted", "reference")
            )
        )
        result[key]["computed_samples"] = len(computed)
        result[key]["all_reference_objects"] = sum(
            (r.get("reference_counts", {}).get(key, 0) for r in records)
        )
        result[key]["recall_over_all_reference"] = ratio(
            result[key]["true_positive"], result[key]["all_reference_objects"]
        )
    nums = [r["numeric"] for r in computed]
    correct = sum((x["exact_correct"] for x in nums))
    ref = sum((x["reference"] for x in nums))
    edits = sum((x["digit_edits"] for x in nums))
    digits = sum((x["reference_digits"] for x in nums))
    result["numeric"] = dict(
        exact_correct=correct,
        reference=ref,
        exact_recall=ratio(correct, ref),
        digit_edits=edits,
        reference_digits=digits,
        digit_error_rate=ratio(edits, digits),
    )
    result["walls_length_coverage"] = {}
    for method in ("lsd", "hough"):
        result["walls_length_coverage"][method] = {}
        for mode in ("precision", "recall"):
            total = sum((r["metrics"]["walls"][method][mode]["total_length_px"] for r in computed))
            covered = sum(
                (r["metrics"]["walls"][method][mode]["covered_length_px"] for r in computed)
            )
            result["walls_length_coverage"][method][mode] = dict(
                covered_px=covered, total_px=total, coverage=ratio(covered, total)
            )
    for key in ("walls", "junctions"):
        g = [r["graph"][key] for r in records if r.get("graph", {}).get(key) is not None]
        result["graph_" + key] = dict(
            computed_samples=len(g),
            **counts(
                *(sum((x[k] for x in g)) for k in ("true_positive", "predicted", "reference"))
            ),
        )
    top = [
        r["topology"]["connectivity"]
        for r in records
        if r.get("topology", {}).get("connectivity") is not None
    ]
    result["exact_topology"] = dict(
        correct=sum((x["full_plan_exact"] for x in top)),
        scorable=len(top),
        not_computed=len(records) - len(top),
        accuracy=ratio(sum((x["full_plan_exact"] for x in top)), len(top)),
        full_denominator_success_fraction=ratio(
            sum((x["full_plan_exact"] for x in top)), len(records)
        ),
    )
    result["latency_seconds"] = distribution([r.get("duration_seconds") for r in records])
    result["metric_geometry"] = dict(
        status="not_computed",
        cm_error=None,
        reason="No automatic accepted metric layouts in baseline perception replay",
    )
    result["association"] = dict(
        status="not_computed",
        accuracy=None,
        reason="No frozen automatic text-to-metric-span output in the historical run",
    )
    return result


def solver_regression(output, root=ROOT):
    from SketchPipeline.solver.linear import solve
    from SketchPipeline.validation.validate import validate_document, as_validated

    cases = []
    invalid_exports = []
    for n in range(1, 51):
        source = root / f"Data/ground_truth/v1/Data_{n}.draft.json"
        doc = read(source)
        expected = validate_document(
            doc, read(root / f"Data/annotations/v1/Data_{n}.observations.json")
        )
        if n in (9, 10, 19, 20):
            for region in doc["layout"]["rooms"] + doc["layout"]["corridors"]:
                vs = region["boundary_vertex_ids"]
                for i, wid in enumerate(region["boundary_wall_ids"]):
                    wall = next((w for w in doc["layout"]["walls"] if w["id"] == wid))
                    a, b = (vs[i], vs[(i + 1) % 4])
                    if i >= 2:
                        a, b = (b, a)
                    wall.update(start_vertex_id=a, end_vertex_id=b)
        for v in doc["layout"]["vertices"]:
            v["position_cm"] = [12345, -98765]
        for o in doc["layout"]["openings"]:
            o.update(center_offset_cm=777, clear_width_cm=333)
        relations = []
        if n == 8:
            relations = [
                dict(
                    id="alignment",
                    type="centered_opening",
                    opening_id="d0",
                    state="confirmed",
                    note="Explicit reference premise, not inferred",
                ),
                dict(
                    id="entrance",
                    type="full_span_opening",
                    opening_id="o-c0-rB",
                    state="confirmed",
                    note="Explicit reference premise, not inferred",
                ),
            ]
        start = time.perf_counter()
        try:
            draft, report = solve(doc, relations=relations)
            elapsed = time.perf_counter() - start
            try:
                as_validated(
                    draft,
                    "controlled-evaluation-fixture",
                    read(root / f"Data/annotations/v1/Data_{n}.observations.json"),
                )
                could_accept = True
            except ValueError:
                could_accept = False
            if not expected["metric_valid"] and could_accept:
                invalid_exports.append(f"Data_{n}")
            reference = root / f"Data/ground_truth/v1/Data_{n}.validated.json"
            comparison = (
                compare_layout(draft, read(reference))
                if reference.exists() and report["status"] == "determined"
                else dict(status="not_computed", exact=None)
            )
            result = dict(
                id=f"Data_{n}",
                expected_reference_metric_valid=expected["metric_valid"],
                linear_status=report["status"],
                metric_valid=report["validation"]["metric_valid"],
                could_accept_controlled_fixture=could_accept,
                actual_export_written=False,
                rank=report["rank"],
                variables=report["variable_count"],
                nullity=report["nullity"],
                max_residual_cm=report["max_residual_cm"],
                confirmed_dimension_error_cm=(
                    distribution(
                        [
                            abs(e["diagnostic_residual_cm"])
                            for e in report["equations"]
                            if e["kind"] == "dimension"
                            and e.get("diagnostic_residual_cm") is not None
                        ]
                    )
                    if report["status"] == "determined"
                    else None
                ),
                metric_comparison=comparison,
                duration_seconds=elapsed,
                legacy_direction_normalized=n in (9, 10, 19, 20),
                issues=[i["code"] for i in report["validation"]["issues"]],
            )
            write(output / f"Data_{n}" / "draft.json", draft)
            write(output / f"Data_{n}" / "solver-report.json", report)
        except (ValueError, TypeError, KeyError) as error:
            result = dict(
                id=f"Data_{n}",
                linear_status="failed",
                error=str(error),
                expected_reference_metric_valid=expected["metric_valid"],
                metric_comparison=dict(status="not_computed", exact=None),
                duration_seconds=time.perf_counter() - start,
            )
        cases.append(result)
    return dict(
        scope="Manual topology + confirmed associations; numeric coordinates deliberately scrambled; NOT automatic perception or user review accuracy.",
        cases=cases,
        statuses=dict(Counter((c["linear_status"] for c in cases))),
        invalid_exports=invalid_exports,
        known_invalids=sum((not c["expected_reference_metric_valid"] for c in cases)),
        latency_seconds=distribution([c["duration_seconds"] for c in cases]),
    )


def review_history(root=ROOT):
    results = []
    for folder, cohort in [
        (root / "Saved/Step08/topology-review/metric", "user_sessions"),
        (
            root / "Saved/Step10/v1/controlled_fixture/reviews/metric",
            "controlled_automation_fixture",
        ),
    ]:
        for pointer in sorted(folder.glob("*/latest.json")):
            rid = read(pointer)["revision_id"]
            records = []
            seen = set()
            while rid:
                if rid in seen:
                    raise ValueError("Review history cycle")
                seen.add(rid)
                record = read(pointer.parent / "revisions" / f"{rid}.json")
                from SketchPipeline.review.server import digest

                if record.get("sha256") != digest(
                    {k: v for k, v in record.items() if k != "sha256"}
                ):
                    raise ValueError("Review ledger tampered")
                records.append(record)
                rid = record.get("parent_revision_id")
            records.reverse()
            results.append(
                dict(
                    case_id=pointer.parent.name,
                    cohort=cohort,
                    latest_status=records[-1]["status"],
                    measured=correction_metrics(records),
                    final_metric_valid=records[-1]["report"]["validation"]["metric_valid"],
                    final_reference_correctness=None,
                    note="Internal validator pass is not reference correctness. Controlled automation is not a human review-time benchmark.",
                )
            )
    return results


def run(output, root=ROOT):
    output = Path(output).resolve()
    root = Path(root).resolve()
    protocol = freeze(output, root)
    verify(protocol, root)
    records = []
    manifest = root / protocol["dataset_manifest"]
    failures = []
    for s in protocol["samples"]:
        base = root / "Saved/Evaluation/v1/baseline" / s["id"]
        rec = dict(
            id=s["id"],
            origin=s["origin"],
            base_plan_id=s["base_plan_id"],
            profile=s.get("profile", "original"),
            split=protocol["split"]["group_split"][s["base_plan_id"]],
            automatic_state="needs_review",
            reviewed=False,
            correct=None,
            review_correct=None,
            graph={},
            topology={},
        )
        ref = read(manifest.parent / s["observations_path"])
        side = read(manifest.parent / s["annotations_path"])
        rec["reference_counts"] = dict(
            text=len(ref["texts"]), openings=sum((g["kind"] != "incidental" for g in side["gaps"]))
        )
        try:
            cached = read(base / "metrics.json")
            working = read(base / "working.json")
            obs = read(base / "observations.json")
            if (
                cached["image_sha256"] != s["image_sha256"]
                or obs["source"]["image_sha256"] != s["image_sha256"]
            ):
                raise ValueError("Prediction source mismatch")
            ref = read(manifest.parent / s["observations_path"])
            side = read(manifest.parent / s["annotations_path"])
            if ref["source"]["image_sha256"] != s["image_sha256"]:
                raise ValueError("Reference source mismatch")
            rec.update(
                status="cached_inference_replay",
                metrics=cached["metrics"],
                duration_seconds=cached["duration_seconds"],
                numeric=numeric_metrics(cached["metrics"]["text"], obs["texts"], ref["texts"]),
            )
            if s["origin"] != "augmented":
                rec["graph"] = graph_metrics(working, ref, side)
                path = root / "Saved/Evaluation/v1/topology" / f"{s['id']}.json"
                rec["topology"] = read(path) if path.exists() else dict(status="not_computed")
            rec["failure_categories"] = []
            if rec["numeric"]["exact_correct"] < rec["numeric"]["reference"]:
                rec["failure_categories"].append("numeric_recognition_or_detection")
            if (
                cached["metrics"]["openings"]["true_positive"]
                < cached["metrics"]["openings"]["predicted"]
            ):
                rec["failure_categories"].append("false_opening")
            if (
                cached["metrics"]["openings"]["true_positive"]
                < cached["metrics"]["openings"]["reference"]
            ):
                rec["failure_categories"].append("missed_opening")
            if (rec["topology"].get("connectivity") or {}).get("full_plan_exact") is False:
                rec["failure_categories"].append("topology")
        except (OSError, ValueError, KeyError, TypeError) as error:
            rec.update(
                status="failed",
                automatic_state="failed",
                metrics=None,
                error=str(error),
                failure_categories=["missing_or_invalid_stage_artifact"],
            )
        records.append(rec)
        if rec["failure_categories"]:
            failures.append(rec["id"])
    cohorts = {"all": records}
    for key in ("origin", "profile", "split"):
        for value in sorted({r[key] for r in records}):
            cohorts[f"{key}/{value}"] = [r for r in records if r[key] == value]
    for origin in ("human", "synthetic"):
        for profile in sorted({r["profile"] for r in records}):
            cohorts[f"{origin}/{profile}"] = [
                r
                for r in records
                if r["profile"] == profile
                and (
                    r["origin"] == origin
                    or next((s for s in protocol["samples"] if s["id"] == r["id"])).get(
                        "source_origin"
                    )
                    == origin
                )
            ]
    summaries = {k: summarize(v) for k, v in cohorts.items() if v}
    solver = solver_regression(output / "solver", root)
    reviews = review_history(root)
    expected_solver = read(root / "Saved/Step09/v1/final_regression/summary.json")
    expected_states = {c["case_id"]: c["linear_status"] for c in expected_solver["cases"]}
    solver["prior_regressions_passed"] = all(
        (
            c["linear_status"] == expected_states[c["id"]]
            for c in solver["cases"]
            if c["id"] in expected_states
        )
    )
    physical = read(root / "Saved/Step12/physical-fixtures.json")
    verification = read(root / "Saved/Step12/verification.json")
    negative = {
        "closed_wall",
        "narrow_door",
        "low_lintel",
        "prop_blockage",
        "larger_agent",
        "corridor_agent_too_wide",
        "disconnected_floor",
    }
    physical_correct = all(
        (
            f["pawn"]
            == (
                "failed"
                if f["fixture"] in negative
                else "not_applicable" if f["fixture"] == "geometry_only_floor_sanity" else "passed"
            )
            for f in physical["fixtures"]
        )
    )
    end = end_to_end(records)
    end["measurement_scope"] = (
        "Product mandatory-review contract applied to frozen perception artifacts; not 720 live image-to-Pawn jobs. Automatic metric output is absent."
    )
    release = release_gate(
        false_auto_accepts=end["false_auto_accepts"],
        invalid_exports=solver["invalid_exports"],
        regressions_passed=physical_correct
        and verification["all_expected_outcomes"]
        and solver["prior_regressions_passed"]
        and (not solver["invalid_exports"]),
        human_review_cases=sum((r["cohort"] == "user_sessions" for r in reviews)),
        unseen_writer_cases=0,
        p95_seconds=summaries["all"]["latency_seconds"]["p95"],
        correction_seconds=None,
    )
    comparable = dict(
        policy=protocol["policy"],
        split=protocol["split"]["group_split"],
        data={k: v for k, v in protocol["input_sha256"].items() if k.startswith("Data/")},
    )
    comparison_key = hashlib.sha256(
        json.dumps(comparable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = dict(
        schema_version="step13-evaluation-report/1.0",
        protocol_sha256=sha(output / "protocol.json"),
        comparability_key=comparison_key,
        scope=protocol["policy"]["scope"],
        generated_utc=datetime.now(timezone.utc).isoformat(),
        input_integrity=dict(
            verified=True,
            pinned_files=len(protocol["input_sha256"]),
            missing_inputs=protocol["missing_inputs"],
        ),
        leakage=protocol["leakage_audit"],
        cohorts=summaries,
        samples=records,
        end_to_end=end,
        solver=solver,
        reviews=reviews,
        physical=dict(
            expected_outcomes_passed=physical_correct,
            fixtures=physical["fixtures"],
            source_verification=verification,
        ),
        release=release,
        failure_counts=dict(Counter((k for r in records for k in r["failure_categories"]))),
        latency_policy="Historical full perception wall clock (hardware/config pinned in protocol). New solver timings separate. Replay wall clock is not inference time.",
        runtime=read(root / "Saved/Evaluation/v1/runtime.json"),
        evaluator_runtime=dict(python=platform.python_version(), platform=platform.platform()),
        limitations=[
            "All splits are previously used development data; no unseen-writer claim.",
            "Automatic metric geometry/association outputs absent: null, not zero error.",
            "Review time is not retrospectively known; controlled fixture correctness is not human productivity.",
            "New handwriting writers and true phone captures remain uncollected.",
            "Physical fixtures are controlled, not image-to-Pawn success on every image.",
        ],
    )
    verify(protocol, root)
    write(output / "report.json", report)
    write(output / "release.json", release)
    write(
        output / "failures.json",
        [
            dict(id=r["id"], categories=r["failure_categories"])
            for r in records
            if r["failure_categories"]
        ],
    )
    gallery(output, report, manifest)
    return report


def gallery(output, report, manifest):
    from PIL import Image, ImageDraw
    import os

    cards = []
    selected = sorted(
        (r for r in report["samples"] if r["origin"] == "human"),
        key=lambda r: (-len(r["failure_categories"]), int(r["id"].split("_")[-1])),
    )[:12]
    samples = {s["id"]: s for s in read(manifest)["samples"]}
    for r in selected:
        s = samples[r["id"]]
        image_path = (manifest.parent / s["image_path"]).resolve()
        with Image.open(image_path) as image:
            original = image.convert("RGB")
            draw = ImageDraw.Draw(original)
            obs = read(ROOT / "Saved/Evaluation/v1/baseline" / r["id"] / "observations.json")
            for t in obs["texts"]:
                if t["polygon_px"]:
                    draw.line(
                        [tuple(p) for p in t["polygon_px"]] + [tuple(t["polygon_px"][0])],
                        fill="#cb442a",
                        width=3,
                    )
            working = read(ROOT / "Saved/Evaluation/v1/baseline" / r["id"] / "working.json")
            false_ids = (
                set(r["metrics"]["openings"]["unmatched_prediction_ids"])
                if r.get("metrics")
                else set()
            )
            for gap in working.get("gaps", []):
                if gap["id"] in false_ids:
                    draw.line(
                        [tuple(gap["start_original"]), tuple(gap["end_original"])],
                        fill="#e87a0a",
                        width=8,
                    )
            original.thumbnail((750, 600))
            thumb = output / "gallery" / f"{r['id']}.jpg"
            thumb.parent.mkdir(exist_ok=True)
            original.save(thumb)
        cards.append(
            f"<article><h2>{html.escape(r['id'])}</h2><img src='gallery/{r['id']}.jpg'><p>{html.escape(', '.join(r['failure_categories']))}</p><p>Exact numeric {r.get('numeric', {}).get('exact_correct')}/{r.get('numeric', {}).get('reference')}; red boxes = OCR predictions; orange spans = unmatched opening predictions. Both are hypotheses, not ground truth.</p><a href='{html.escape(os.path.relpath(image_path, output), quote=True)}'>Original evidence</a></article>"
        )
    summary = html.escape(
        json.dumps(
            {k: report[k] for k in ("scope", "end_to_end", "failure_counts", "release")}, indent=2
        )
    )
    (output / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Step 13 evaluation</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;background:#f3f4f5;color:#172126}article,pre{background:white;padding:20px;margin:18px 0;overflow:auto}img{max-width:100%}</style><h1>Step 13 — development evaluation</h1><p>Historical inference replay; current solver regression; separate physical evidence. No independent unseen-writer accuracy claim.</p><p><a href='report.json'>Full report</a> · <a href='protocol.json'>Frozen protocol</a> · <a href='challenges/index.html'>Fresh capture/convention challenges</a></p><pre>"
        + summary
        + "</pre>"
        + "".join(cards)
    )
