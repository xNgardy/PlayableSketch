from collections import Counter
from copy import deepcopy
import math
import re
import numpy as np


def ratio(a, b):
    return a / b if b else None


def counts(tp, predicted, reference):
    return dict(
        true_positive=tp,
        predicted=predicted,
        reference=reference,
        precision=ratio(tp, predicted),
        recall=ratio(tp, reference),
        f1=ratio(2 * tp, predicted + reference),
    )


def pairs(predicted, reference, cost, threshold):
    options = [sorted(((cost(p, r), j) for j, r in enumerate(reference))) for p in predicted]
    assigned = {}

    def augment(i, visited):
        for value, j in options[i]:
            if not math.isfinite(value) or value > threshold or j in visited:
                continue
            visited.add(j)
            if j not in assigned or augment(assigned[j], visited):
                assigned[j] = i
                return True
        return False

    for i in range(len(predicted)):
        augment(i, set())
    return sorted(((i, j, cost(predicted[i], reference[j])) for j, i in assigned.items()))


def endpoint_error(a, b):
    a, b = (np.asarray(a, float), np.asarray(b, float))
    return float(
        min(np.linalg.norm(a - b, axis=1).max(), np.linalg.norm(a - b[::-1], axis=1).max())
    )


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = row
    return previous[-1]


def digit_error(text_metric):
    digits = lambda value: "".join(re.findall("\\d", value or ""))
    rows = text_metric["matched_pairs"]
    edits = sum(
        (edit_distance(digits(x["predicted_raw"]), digits(x["expected_raw"])) for x in rows)
    )
    denominator = sum((len(digits(x["expected_raw"])) for x in rows))
    return (edits, denominator)


def numeric_metrics(metric, predicted_texts, reference_texts):
    digits = lambda text: "".join(re.findall("\\d", text or ""))
    edits, den = digit_error(metric)
    pred = {t["id"]: t for t in predicted_texts}
    ref = {t["id"]: t for t in reference_texts}
    for id in metric["unmatched_reference_ids"]:
        n = len(digits(ref[id]["raw_text"]))
        edits += n
        den += n
    for id in metric["unmatched_prediction_ids"]:
        edits += len(digits(pred[id]["raw_text"]))
    return dict(
        exact_correct=metric["numeric_exact_correct"],
        reference=metric["reference"],
        exact_recall=ratio(metric["numeric_exact_correct"], metric["reference"]),
        digit_edits=edits,
        reference_digits=den,
        digit_error_rate=ratio(edits, den),
    )


def distribution(values):
    finite = [float(x) for x in values if x is not None and math.isfinite(x)]
    return dict(
        count=len(finite),
        p50=float(np.percentile(finite, 50)) if finite else None,
        p95=float(np.percentile(finite, 95)) if finite else None,
        maximum=max(finite) if finite else None,
    )


def align_layout(predicted, reference, quarter_turns=0):
    out = deepcopy(predicted)

    def points(doc):
        return np.asarray([v["position_cm"] for v in doc["layout"]["vertices"]], float)

    p, r = (points(out), points(reference))
    if not len(p) or not len(r) or (not np.isfinite(p).all()) or (not np.isfinite(r).all()):
        raise ValueError("Complete finite cm coordinates required")
    angle = quarter_turns * math.pi / 2
    rotation = np.asarray([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    transformed = p @ rotation.T
    shift = r.min(axis=0) - transformed.min(axis=0)
    for v, xy in zip(out["layout"]["vertices"], transformed + shift):
        v["position_cm"] = xy.tolist()
    return out


def compare_layout(predicted, reference, tolerance_cm=0.1):
    if predicted is None:
        return dict(status="not_computed", exact=None, reason="metric stage unavailable")
    try:
        aligned = align_layout(predicted, reference)
    except (ValueError, TypeError):
        return dict(status="not_computed", exact=None, reason="unresolved metric coordinates")
    p, r = (aligned["layout"], reference["layout"])
    if any(
        (
            o.get(k) is None
            for o in p["openings"]
            for k in ("clear_width_cm", "center_offset_cm", "clear_height_cm")
        )
    ):
        return dict(status="not_computed", exact=None, reason="Unresolved opening dimensions")

    def entities(layout):
        vertices = {v["id"]: v["position_cm"] for v in layout["vertices"]}
        walls = {w["id"]: w for w in layout["walls"]}
        regions = layout["rooms"] + layout["corridors"]
        bounds = []
        for x in regions:
            points = np.asarray([vertices[id] for id in x["boundary_vertex_ids"]])
            bounds.append([points.min(axis=0), points.max(axis=0)])
        return (vertices, walls, regions, bounds)

    pv, pw, pr, pb = entities(p)
    rv, rw, rr, rb = entities(r)

    def iou(a, b):
        a, b = (np.asarray(a), np.asarray(b))
        inter = np.maximum(0, np.minimum(a[1], b[1]) - np.maximum(a[0], b[0])).prod()
        union = (a[1] - a[0]).prod() + (b[1] - b[0]).prod() - inter
        return float(inter / union) if union else 0

    region_pairs = pairs(
        list(enumerate(pb)),
        list(enumerate(rb)),
        lambda a, b: (
            1 - iou(a[1], b[1])
            if (a[0] < len(p["rooms"])) == (b[0] < len(r["rooms"]))
            else math.inf
        ),
        0.5,
    )
    mapping = {pr[i]["id"]: rr[j]["id"] for i, j, _ in region_pairs}
    error = [float(np.max(np.abs(np.asarray(pb[i]) - rb[j]))) for i, j, _ in region_pairs]
    wall_pairs = pairs(
        list(pw.values()),
        list(rw.values()),
        lambda a, b: endpoint_error(
            [pv[a["start_vertex_id"]], pv[a["end_vertex_id"]]],
            [rv[b["start_vertex_id"]], rv[b["end_vertex_id"]]],
        ),
        tolerance_cm,
    )
    wall_map = {list(pw)[i]: list(rw)[j] for i, j, _ in wall_pairs}
    p_open, r_open = (p["openings"], r["openings"])

    def connected(o, mapped=False):
        return tuple(
            sorted(
                (
                    mapping.get(e["id"], "unmapped:" + e["id"]) if mapped else e["id"]
                    for e in o["connected_entities"]
                )
            )
        )

    def opening_cost(a, b):
        if a["type"] != b["type"] or connected(a, True) != connected(b):
            return math.inf
        wa, wb = (pw[a["wall_id"]], rw[b["wall_id"]])
        if wall_map.get(a["wall_id"]) != b["wall_id"]:
            return math.inf

        def center(o, w, vertices):
            start, end = (
                np.asarray(vertices[w["start_vertex_id"]]),
                np.asarray(vertices[w["end_vertex_id"]]),
            )
            return start + (end - start) / np.linalg.norm(end - start) * o["center_offset_cm"]

        return float(np.linalg.norm(center(a, wa, pv) - center(b, wb, rv)))

    opening_pairs = pairs(p_open, r_open, opening_cost, max(10, tolerance_cm))
    widths = [
        abs(p_open[i]["clear_width_cm"] - r_open[j]["clear_width_cm"]) for i, j, _ in opening_pairs
    ]
    offsets = [e for _, _, e in opening_pairs]
    heights = [
        abs(p_open[i]["clear_height_cm"] - r_open[j]["clear_height_cm"])
        for i, j, _ in opening_pairs
    ]

    def relations(layout, mapped=False):
        return Counter(
            (
                tuple(
                    sorted(
                        (
                            mapping.get(id, "unmapped:" + id) if mapped else id
                            for id in w["region_ids"]
                        )
                    )
                )
                for w in layout["walls"]
                if len(w["region_ids"]) == 2
            )
        )

    physical_p = Counter(((o["type"], connected(o, True)) for o in p_open))
    physical_r = Counter(((o["type"], connected(o)) for o in r_open))
    exact_regions = len(region_pairs) == len(pr) == len(rr) and all(
        (e <= tolerance_cm for e in error)
    )
    exact_walls = len(wall_pairs) == len(pw) == len(rw)
    exact_openings = len(opening_pairs) == len(p_open) == len(r_open) and all(
        (e <= tolerance_cm for e in widths + offsets + heights)
    )
    settings_equal = all(
        (
            abs(aligned["settings"][k] - reference["settings"][k]) <= tolerance_cm
            for k in ("wall_thickness_cm", "wall_height_cm", "door_height_cm", "floor_thickness_cm")
        )
    )

    def roles(doc, mapped=False):
        return tuple(
            (
                mapping.get(doc.get(k), "unmapped") if mapped and doc.get(k) else doc.get(k)
                for k in ("start_room_id", "goal_room_id")
            )
        )

    exact_roles = (
        roles(aligned, True) == roles(reference)
        and aligned["validation_mode"] == reference["validation_mode"]
    )
    return dict(
        status="computed",
        alignment="translation only; fixed canonical yaw; no scaling/reflection",
        exact=exact_regions
        and exact_walls
        and exact_openings
        and settings_equal
        and exact_roles
        and (relations(p, True) == relations(r))
        and (physical_p == physical_r),
        regions=counts(len(region_pairs), len(pr), len(rr)),
        walls=counts(len(wall_pairs), len(pw), len(rw)),
        openings=counts(len(opening_pairs), len(p_open), len(r_open)),
        region_max_error_cm=max(error, default=None),
        wall_endpoint_error_cm=distribution([e for _, _, e in wall_pairs]),
        opening_width_error_cm=distribution(widths),
        opening_center_displacement_cm=distribution(offsets),
        opening_height_error_cm=distribution(heights),
        shared_wall_relations_exact=relations(p, True) == relations(r),
        opening_relations_exact=physical_p == physical_r,
        settings_exact=settings_equal,
        roles_exact=exact_roles,
    )


def association_metrics(
    proposals, annotations, text_mapping, transform=lambda x: x, tolerance_px=20
):
    if proposals is None:
        return dict(status="not_computed", top1=None, top3=None, reference=len(annotations))
    by_text = {
        text_mapping.get(p["evidence_id"]): p for p in proposals if p["evidence_id"] in text_mapping
    }
    hits = [0, 0]
    visible = 0
    for a in annotations:
        prediction = by_text.get(a["text_id"])
        if prediction:
            visible += 1
        for i, k in enumerate((1, 3)):
            if prediction and any(
                (
                    endpoint_error(
                        transform([c["start_px_y_up"], c["end_px_y_up"]]),
                        [a["span_start_px"], a["span_end_px"]],
                    )
                    <= tolerance_px
                    for c in prediction["candidates"][:k]
                )
            ):
                hits[i] += 1
    return dict(
        status="computed",
        reference=len(annotations),
        detected_texts=visible,
        top1_correct=hits[0],
        top3_correct=hits[1],
        top1=ratio(hits[0], len(annotations)),
        top3=ratio(hits[1], len(annotations)),
    )


def end_to_end(records):
    before = Counter((r.get("automatic_state", "not_computed") for r in records))
    reviewed = [r for r in records if r.get("reviewed")]
    wrong = [
        r["id"]
        for r in records
        if r.get("automatic_state") == "auto_accepted" and r.get("correct") is not True
    ]
    return dict(
        total=len(records),
        before=dict(before),
        reviewed=len(reviewed),
        reviewed_correct=sum((r.get("review_correct") is True for r in reviewed)),
        reviewed_unscored=sum((r.get("review_correct") is None for r in reviewed)),
        false_auto_accepts=wrong,
        false_auto_accept_rate=ratio(
            len(wrong), sum((r.get("automatic_state") == "auto_accepted" for r in records))
        ),
        automatic_metric_accuracy=(
            None
            if not any((r.get("correct") is not None for r in records))
            else ratio(sum((r.get("correct") is True for r in records)), len(records))
        ),
    )


def release_gate(
    *,
    false_auto_accepts,
    invalid_exports,
    regressions_passed,
    human_review_cases,
    unseen_writer_cases,
    p95_seconds=None,
    latency_budget_seconds=30,
    correction_seconds=None,
):
    reasons = []
    if false_auto_accepts:
        reasons.append("critical_false_auto_accept")
    if invalid_exports:
        reasons.append("known_invalid_exported")
    if not regressions_passed:
        reasons.append("regression_failure")
    if p95_seconds is None or p95_seconds > latency_budget_seconds:
        reasons.append("latency_budget_missing_or_exceeded")
    if not human_review_cases or correction_seconds is None:
        reasons.append("human_correction_cost_unmeasured")
    if not unseen_writer_cases:
        reasons.append("no_independent_unseen_writer_evaluation")
    return dict(
        local_review_required_workflow=(
            "passed"
            if not false_auto_accepts and (not invalid_exports) and regressions_passed
            else "failed"
        ),
        autonomous_or_general_release="blocked" if reasons else "passed",
        blockers=reasons,
        model_action="retain baseline; no new training without same-protocol measurable benefit",
    )


def compare_reports(baseline, candidate):
    if not baseline.get("comparability_key") or baseline["comparability_key"] != candidate.get(
        "comparability_key"
    ):
        raise ValueError(
            "Different data/reference hashes, split or tolerance policy; comparison refused"
        )
    a = {r["id"]: r for r in baseline["samples"]}
    b = {r["id"]: r for r in candidate["samples"]}
    if a.keys() != b.keys():
        raise ValueError("Missing candidate samples; retain failed/unsupported cases")
    changes = {}
    for cohort in baseline["cohorts"].keys() & candidate["cohorts"].keys():
        x, y = (baseline["cohorts"][cohort], candidate["cohorts"][cohort])

        def delta(a, b):
            return b - a if a is not None and b is not None else None

        changes[cohort] = dict(
            numeric_exact_recall_delta=delta(
                x["numeric"]["exact_recall"], y["numeric"]["exact_recall"]
            ),
            opening_f1_delta=delta(x["openings"]["f1"], y["openings"]["f1"]),
            note="Paired cohort deltas on identical frozen inputs; no unseen-writer claim. Null means an unavailable metric.",
        )
    return dict(comparable=True, samples=len(a), cohort_deltas=changes)
