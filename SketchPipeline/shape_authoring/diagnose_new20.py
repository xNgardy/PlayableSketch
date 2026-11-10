import argparse
import copy
import csv
import html
import json
import types
from collections import Counter
from itertools import combinations
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, LineString
from shapely.ops import snap
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.evaluation.metrics import pairs, endpoint_error, counts
from . import door_geometry as door
from .decoder import boundary_graph, iou
from .decoder_refined import decode
from .passage_refinement import opening_candidates as passages
from .corridor_junctions import add_observed_passages
from .corridor_candidates import wall_ink
from .evaluate_unified_areas import cases
from .human_error_review import reference as legacy_reference
from .pilot import score as legacy_score
from .dino_model import ROOT, sha
from .synthetic import write_json

ARMS = ["baseline", "reference_regions", "reference_endpoints", "reference_both"]
SENSITIVITY = ["reference_regions_recovery_fallback", "reference_both_recovery_fallback"]
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def reference(n, metadata, overrides=None):
    raw = json.loads(
        (ROOT / f"Data/ground_truth/structural_v1/Data_{n}.structural.json").read_text()
    )
    for change in (overrides or {}).get("changes", []):
        if change["sample_id"] != f"Data_{n}":
            continue
        assert sha(ROOT / f"Data/Data_{n}.png") == change["source_sha256"]
        opening = next((g for g in raw["openings"] if g["id"] == change["opening_id"]))
        for key, value in change["old"].items():
            assert opening[key] == value
        opening.update(change["new"])
    matrix = metadata["original_to_working"]
    regions = []
    for r in raw["regions"]:
        p = project(r["polygon_px"], matrix)
        regions.append(
            {
                "id": r["region_id"],
                "type": "room" if r["kind"] == "room" else "corridor_segment",
                "polygon": p.tolist(),
                "bounds_px": np.r_[p.min(0), p.max(0)].tolist(),
            }
        )
    openings = [
        {
            **g,
            "type": g["kind"],
            "points_px": project([g["start_px"], g["end_px"]], matrix).tolist(),
        }
        for g in raw["openings"]
    ]
    return ({"regions": regions, "openings": openings, "approximate_human_labels": True}, raw)


def reference_segments(regions):
    polygons = [Polygon(np.round(r["polygon"], 5)) for r in regions]
    segments, records = ({}, [])
    for i, j in combinations(range(len(polygons)), 2):
        common = snap(polygons[i].boundary, polygons[j].boundary, 0.001).intersection(
            polygons[j].boundary
        )
        lines = [common] if common.geom_type == "LineString" else list(getattr(common, "geoms", []))
        for line in lines:
            if line.geom_type != "LineString" or line.length < 0.1:
                continue
            p = np.asarray(line.coords)
            axis = int(np.ptp(p[:, 1]) > np.ptp(p[:, 0]))
            normal = 1 - axis
            fixed = float((p[:, normal].min() + p[:, normal].max()) / 2)
            a, b = (np.zeros(2), np.zeros(2))
            a[axis], b[axis] = (p[:, axis].min(), p[:, axis].max())
            a[normal] = b[normal] = fixed
            key = (tuple(a), tuple(b))
            segments[key] = [i, j]
            records.append(
                {
                    "owners": [regions[i]["id"], regions[j]["id"]],
                    "polygon_edge": p.tolist(),
                    "axis_support": key,
                    "maximum_normal_projection_px": float(np.abs(p[:, normal] - fixed).max()),
                }
            )
    return (segments, records)


def oracle_ticks(ink, axis, points):
    result = []
    side = max(ink.shape)
    for point in points:
        along, fixed = (point[axis], point[1 - axis])
        positions = np.arange(max(0, round(along) - 3), min(ink.shape[1 - axis], round(along) + 4))
        if not len(positions):
            continue
        patch = ink[:, positions] if axis == 0 else ink[positions, :].T
        occupied = patch.max(axis=1) > 0
        changes = np.diff(np.r_[False, occupied, False].astype(int))
        runs = list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))
        options = [(a, b) for a, b in runs if a - 2 <= fixed <= b + 1 and 5 <= b - a <= side * 0.8]
        if not options:
            continue
        lo, hi = min(options, key=lambda ab: abs((ab[0] + ab[1] - 1) / 2 - fixed))
        widths = []
        for normal in range(lo, hi):
            if abs(normal - fixed) < 3:
                continue
            values = patch[normal] > 0
            if values.any():
                widths.append(int(values.sum()))
        width = max(1, int(np.median(widths))) if widths else 1
        result.append({"at": float(along), "lo": float(lo), "hi": float(hi - 1), "width": width})
    return result


def oracle_door_stage(proposals, segments, gray, matrix, points):
    globals_detect = dict(door.detect_pairs.__globals__)
    globals_detect["ticks"] = lambda ink, axis: oracle_ticks(ink, axis, points)
    detector = types.FunctionType(door.detect_pairs.__code__, globals_detect)
    globals_open = dict(door.opening_candidates.__globals__)
    globals_open["detect_pairs"] = detector
    opener = types.FunctionType(door.opening_candidates.__code__, globals_open)
    result, detail = opener(proposals, segments, gray, matrix)
    detail["diagnostic_endpoint_adapter"] = (
        "unpaired locations + measured raw ink extents; original physical/ownership tests"
    )
    detail["oracle_points_native"] = np.asarray(points).tolist()
    return (result, detail)


def stage(segments, gray, probabilities, matrix, region_types, recovered, oracle=None):
    proposals, evidence = passages(segments, gray, probabilities, matrix, region_types=region_types)
    if recovered:
        proposals, detail = add_observed_passages(proposals, segments, gray, matrix, recovered)
        evidence["observed_interfaces"] = detail
    if oracle is None:
        proposals, detail = door.opening_candidates(proposals, segments, gray, matrix)
    else:
        proposals, detail = oracle_door_stage(proposals, segments, gray, matrix, oracle)
    evidence["observed_doors"] = detail
    evidence["diagnostic_working_to_native"] = np.asarray(matrix).tolist()
    return (proposals, evidence)


def document_for(template, regions, segments, proposals):
    doc = copy.deepcopy(template)
    top = doc["topology"]
    top.update(regions=[], openings=[], connections=[], walls=[], junctions=[])
    for r in regions:
        top["regions"].append(
            {
                "id": r["id"],
                "type": r["type"],
                "name": r["id"],
                "wall_ids": [],
                "geometry": {"points_px": r["polygon"], "state": "proposed"},
            }
        )
    for k, (segment, owners) in enumerate(segments.items()):
        top["walls"].append(
            {
                "id": f"support_{k}",
                "entity_ids": [regions[i]["id"] for i in owners],
                "geometry": {"points_px": segment, "state": "proposed"},
            }
        )
    relations = {}
    for p in proposals:
        owners = segments[p["segment"]]
        if len(owners) != 2:
            continue
        ids = [regions[i]["id"] for i in owners]
        oid = f"opening_{len(top['openings']) + 1:04d}"
        top["openings"].append(
            {
                "id": oid,
                "type": p["type"],
                "entity_ids": ids,
                "geometry": {"points_px": [p["start"], p["end"]], "state": "proposed"},
            }
        )
        relations.setdefault(tuple(sorted(ids)), []).append(oid)
    top["connections"] = [
        {"entity_ids": list(ids), "opening_ids": values} for ids, values in relations.items()
    ]
    doc["diagnostic_only"] = True
    doc["not_exportable_reason"] = (
        "Intervention evidence supports are axis projections; no accepted layout or complete wall graph."
    )
    return doc


def evaluate(doc, ref, size):
    pr, rr = (doc["topology"]["regions"], ref["regions"])
    bounds = lambda a: np.r_[
        np.min(a["geometry"]["points_px"], axis=0), np.max(a["geometry"]["points_px"], axis=0)
    ]
    region_pairs = pairs(pr, rr, lambda a, b: 1 - iou(bounds(a), b["bounds_px"]), 0.5)
    mapping = {pr[i]["id"]: rr[j]["id"] for i, j, _ in region_pairs}
    po, ro = (doc["topology"]["openings"], ref["openings"])
    tolerance = max(size) * 0.04
    cost = lambda a, b: (
        endpoint_error(a["geometry"]["points_px"], b["points_px"])
        if a["type"] == b["type"]
        else float("inf")
    )
    locations = pairs(po, ro, cost, tolerance)
    connected_cost = lambda a, b: (
        cost(a, b)
        if set((mapping.get(v, "unmatched:" + v) for v in a["entity_ids"])) == set(b["entity_ids"])
        else float("inf")
    )
    attached = pairs(po, ro, connected_cost, tolerance)
    pd, rd = ([o for o in po if o["type"] == "door"], [o for o in ro if o["type"] == "door"])
    doors = pairs(pd, rd, cost, tolerance)
    predicted_pairs = {
        tuple(sorted((mapping.get(v, "unmatched:" + v) for v in o["entity_ids"]))) for o in po
    }
    true_pairs = {tuple(sorted(o["entity_ids"])) for o in ro}
    correct_pairs = {tuple(sorted(ro[j]["entity_ids"])) for _, j, _ in attached}
    return {
        "regions": counts(len(region_pairs), len(pr), len(rr)),
        "doors": counts(len(doors), len(pd), len(rd)),
        "openings": counts(len(locations), len(po), len(ro)),
        "attached_openings": counts(len(attached), len(po), len(ro)),
        "connections": counts(len(correct_pairs), len(predicted_pairs), len(true_pairs)),
        "unmatched_produced_connections": len(predicted_pairs) - len(correct_pairs),
        "missed_connections": len(true_pairs) - len(correct_pairs),
        "false_connections_under_approximate_reference": len(po) - len(attached),
        "region_id_mapping": mapping,
        "location_matches": locations,
        "attachment_matches": attached,
        "region_type_matches": sum((pr[i]["type"] == rr[j]["type"] for i, j, _ in region_pairs)),
        "unmatched_is_not_proven_false": True,
    }


def candidate_lines(evidence):
    result = []
    for c in evidence.get("observed_doors", {}).get("pair_tests", []):
        axis = c["axis"]
        p = np.zeros((2, 2))
        p[:, axis] = c["native_interval"]
        p[:, 1 - axis] = c["observed_wall_axis"]
        result.append(
            {
                "points": p.tolist(),
                "status": c["status"],
                "reason": c.get(
                    "reason", "physical_thresholds" if c["status"] == "rejected" else c["status"]
                ),
                "record": c,
            }
        )
    tracked = evidence.get("tracked", {})
    matrix = np.asarray(evidence.get("diagnostic_working_to_native", np.eye(3)))
    for c in tracked.get("tracking_candidates", []):
        axis = c["axis"]
        p = np.zeros((2, 2))
        p[:, axis] = c["native_interval"]
        p[:, 1 - axis] = c["fixed"]
        start = int(np.ceil(project(c["segment"], matrix)[:, axis].min()))
        if c.get("path_px"):
            p[:, 1 - axis] = [
                c["path_px"][int(np.clip(round(t) - start, 0, len(c["path_px"]) - 1))]
                for t in p[:, axis]
            ]
        result.append(
            {
                "points": p.tolist(),
                "status": c.get("status", "unknown"),
                "reason": c.get("reason"),
                "record": c,
            }
        )
    for c in tracked.get("baseline", {}).get("candidates", []):
        segment = np.asarray(c["segment"])
        axis = 0 if segment[0, 1] == segment[1, 1] else 1
        p = np.zeros((2, 2))
        p[:, axis] = c["native_gap_px"]
        p[:, 1 - axis] = c["native_axis_px"]
        result.append(
            {
                "points": p.tolist(),
                "status": c.get("status", "unknown"),
                "reason": c.get("reason"),
                "record": c,
            }
        )
    for c in evidence.get("passage_candidates", []):
        p = project(c["segment"], matrix)
        axis = int(np.ptp(p[:, 1]) > np.ptp(p[:, 0]))
        p[:, 1 - axis] = c["native_axis"]
        result.append(
            {"points": p.tolist(), "status": c["status"], "reason": c.get("reason"), "record": c}
        )
    for c in evidence.get("observed_interfaces", {}).get("interfaces", []):
        result.append(
            {
                "points": project(c["segment"], matrix).tolist(),
                "status": c["status"],
                "reason": "physical_interface" if c["status"] == "rejected" else c["status"],
                "record": c,
            }
        )
    return result


def per_arm_gate_audit(gap, pred, native_points, working_to_native):
    m = pred["metrics"]
    mapping = m["region_id_mapping"]
    owner_ids = {
        r["id"]
        for r in pred["authoring"]["topology"]["regions"]
        if mapping.get(r["id"]) in gap["entity_ids"]
    }
    missing = sorted(set(gap["entity_ids"]) - set(mapping.values()))
    supports = (
        [
            w
            for w in pred["authoring"]["topology"]["walls"]
            if len(w["entity_ids"]) == 2 and set(w["entity_ids"]) == owner_ids
        ]
        if len(owner_ids) == 2
        else []
    )
    support_errors = [
        endpoint_error(project(w["geometry"]["points_px"], working_to_native), native_points)
        for w in supports
    ]
    candidates = sorted(
        [
            (endpoint_error(c["points"], native_points), c)
            for c in candidate_lines(pred["evidence"])
        ],
        key=lambda x: x[0],
    )
    local = [{"distance_native_px": cost, **c} for cost, c in candidates if cost <= 512 * 0.04]
    nearby_openings = [
        o
        for o in pred["authoring"]["topology"]["openings"]
        if endpoint_error(project(o["geometry"]["points_px"], working_to_native), native_points)
        <= 512 * 0.04
    ]
    if missing:
        blocker = "missing_region_or_corridor"
    elif not supports:
        blocker = "missing_or_wrong_shared_boundary"
    elif any((o["type"] != gap["type"] for o in nearby_openings)):
        blocker = "opening_type_mismatch_or_precedence"
    elif any((c["status"] == "unattached" for c in local)):
        blocker = "boundary_attachment_rejected"
    elif any((c["status"] in ("rejected", "needs_attention") for c in local)):
        blocker = "recorded_physical_or_semantic_rejection"
    elif any((c["status"] == "proposed" for c in local)):
        blocker = "type_location_ownership_or_matching"
    else:
        blocker = "candidate_search_or_early_filter_unresolved"
    return {
        "stage_evidence": blocker,
        "missing_regions": missing,
        "owner_shared_supports": supports,
        "support_endpoint_errors_native_px": support_errors,
        "nearby_candidate_records": local,
        "nearby_produced_openings": nearby_openings,
        "nearest_candidate": (
            {"distance_native_px": candidates[0][0], **candidates[0][1]} if candidates else None
        ),
    }


def failure_rows(sample, ref, predictions, gray, endpoint_map, working_to_native):
    base = predictions["baseline"]
    metrics = base["metrics"]
    mapping = metrics["region_id_mapping"]
    found = set(mapping.values())
    candidates = candidate_lines(base["evidence"])
    output = []
    for j, g in enumerate(ref["openings"]):
        p = project(g["points_px"], working_to_native)
        matched = {
            arm: any((k == j for _, k, _ in pred["metrics"]["attachment_matches"]))
            for arm, pred in predictions.items()
        }
        located = any((k == j for _, k, _ in metrics["location_matches"]))
        missing = [v for v in g["entity_ids"] if v not in found]
        owners = [
            v
            for v in base["authoring"]["topology"]["regions"]
            if mapping.get(v["id"]) in g["entity_ids"]
        ]
        owner_ids = {v["id"] for v in owners}
        shared = (
            [
                w
                for w in base["authoring"]["topology"]["walls"]
                if len(w["entity_ids"]) == 2 and set(w["entity_ids"]) == owner_ids
            ]
            if len(owner_ids) == 2
            else []
        )
        near = sorted([(endpoint_error(c["points"], p), c) for c in candidates], key=lambda t: t[0])
        close = near[0] if near else None
        responses = []
        for x, y in p:
            patch = endpoint_map[
                max(0, round(y) - 4) : round(y) + 5, max(0, round(x) - 4) : round(x) + 5
            ]
            responses.append(float(patch.max()) if patch.size else 0.0)
        reasons = []
        if not matched["baseline"]:
            if missing:
                reasons.append("missing_region_or_corridor")
            elif not shared:
                reasons.append("missing_or_wrong_shared_boundary")
            if (
                close
                and close[0] <= max(gray.shape) * 0.04
                and (close[1]["status"] in ("rejected", "unattached"))
            ):
                reasons.append(
                    "physical_check_rejected"
                    if close[1]["status"] == "rejected"
                    else "missing_or_wrong_shared_boundary"
                )
            if matched["reference_endpoints"] and (not missing):
                reasons.append("endpoint_localization_or_candidate_search")
            if not reasons:
                reasons.append("multiple_or_unresolved")
        gate_audits = {
            arm: per_arm_gate_audit(g, pred, p, working_to_native)
            for arm, pred in predictions.items()
        }
        for arm in gate_audits:
            if matched[arm]:
                gate_audits[arm]["stage_evidence"] = "matched"
        if not matched["baseline"] and located:
            reasons.append("location_detected_but_wrong_region_ownership")
        if not located and any(
            (
                o["type"] != g["type"]
                and endpoint_error(o["geometry"]["points_px"], g["points_px"]) <= 256 * 0.04
                for o in base["authoring"]["topology"]["openings"]
            )
        ):
            reasons.append("opening_type_mismatch")
        output.append(
            {
                "sample_id": sample,
                "opening_id": g["id"],
                "type": g["type"],
                "owners": g["entity_ids"],
                "reference_points_working": g["points_px"],
                "reference_points_native": p.tolist(),
                "localized_baseline": located,
                "attached_by_arm": matched,
                "missing_regions": missing,
                "compatible_owner_shared_wall_count": len(shared),
                "reasons": sorted(set(reasons)),
                "endpoint_head6_max_within_4_native_px": responses,
                "endpoint_head6_is_not_direct_production_input": True,
                "nearest_candidate_error_native_px": close[0] if close else None,
                "nearest_candidate": close[1] if close else None,
                "gate_audits": gate_audits,
                "causal_certainty": "Intervention-supported where recovered; otherwise stage evidence, not unique causal attribution.",
            }
        )
    return output


def render(
    sample, source, ref, predictions, endpoint_map, native_to_original, work_to_original, directory
):
    original = Image.open(source).convert("RGB")
    width, height = original.size
    scale = min(650 / width, 650 / height)
    size = (round(width * scale), round(height * scale))
    font = ImageFont.truetype(FONT, 16)
    small = ImageFont.truetype(FONT, 13)

    def panel(title):
        out = Image.new("RGB", (680, 710), "#f4f6f8")
        out.paste(original.resize(size), ((680 - size[0]) // 2, 45))
        ImageDraw.Draw(out).text((15, 12), title, fill="#111827", font=font)
        return out

    offset = np.array([(680 - size[0]) // 2, 45])

    def pts(p, matrix):
        return [tuple(x) for x in project(p, matrix) * scale + offset]

    def regions(out, records, matrix, predicted=False):
        draw = ImageDraw.Draw(out)
        for r in records:
            poly = r["geometry"]["points_px"] if predicted else r["polygon"]
            p = pts(poly, matrix)
            color = "#2563eb" if r["type"] == "room" else "#b45309"
            draw.line(p + [p[0]], fill=color, width=3)
            draw.text(p[0], r["id"], fill=color, font=small, stroke_width=1, stroke_fill="white")

    def openings(out, records, matrix, predicted=False):
        draw = ImageDraw.Draw(out)
        for r in records:
            p = pts(r["geometry"]["points_px"] if predicted else r["points_px"], matrix)
            color = "#15803d" if r["type"] == "door" else "#7c3aed"
            draw.line(p, fill=color, width=5)
            for x, y in p:
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
            draw.text(p[0], r["id"], font=small, fill=color, stroke_width=1, stroke_fill="white")

    panels = [
        panel("Özgün fotoğraf"),
        panel("Referans: mavi oda / kahve koridor"),
        panel("Mevcut bölge tahminleri"),
        panel("Model kapı uçları: head 6 olasılığı"),
        panel("Üretilen kapılar ve açık bağlantılar"),
        panel("Reddedilen / bağlanamayan adaylar"),
    ]
    regions(panels[1], ref["regions"], work_to_original)
    openings(panels[1], ref["openings"], work_to_original)
    base = predictions["baseline"]
    regions(panels[2], base["authoring"]["topology"]["regions"], work_to_original, True)
    field = cv2.warpPerspective(
        endpoint_map, np.asarray(native_to_original), (width, height), flags=cv2.INTER_LINEAR
    )
    heat = np.array(original).astype(float)
    alpha = np.clip(field, 0, 1) * 0.75
    heat = (heat * (1 - alpha[:, :, None]) + np.array([255, 0, 100]) * alpha[:, :, None]).astype(
        np.uint8
    )
    panels[3].paste(Image.fromarray(heat).resize(size), tuple(offset))
    ImageDraw.Draw(panels[3]).text(
        (15, 680),
        "Pembe yoğunluk 0–1; üretim bu kanalı doğrudan kullanmıyor.",
        font=small,
        fill="#111827",
    )
    openings(panels[4], base["authoring"]["topology"]["openings"], work_to_original, True)
    draw = ImageDraw.Draw(panels[4])
    centers = {
        r["id"]: np.mean(r["geometry"]["points_px"], axis=0)
        for r in base["authoring"]["topology"]["regions"]
    }
    for c in base["authoring"]["topology"]["connections"]:
        if all((v in centers for v in c["entity_ids"])):
            draw.line(
                pts([centers[v] for v in c["entity_ids"]], work_to_original),
                fill="#0891b2",
                width=2,
            )
    draw = ImageDraw.Draw(panels[5])
    candidates = candidate_lines(base["evidence"])
    rejected = [
        c for c in candidates if c["status"] in ("rejected", "unattached", "needs_attention")
    ]
    for k, c in enumerate(rejected):
        p = pts(c["points"], native_to_original)
        draw.line(p, fill="#dc2626", width=2)
        draw.text(p[0], str(k + 1), font=small, fill="#dc2626", stroke_width=1, stroke_fill="white")
    draw.text(
        (15, 680),
        f"{len(rejected)} aday; numaralı gerekçeler candidates.json dosyasında.",
        font=small,
        fill="#111827",
    )
    canvas = Image.new("RGB", (2040, 1420), "white")
    for i, p in enumerate(panels):
        canvas.paste(p, (i % 3 * 680, i // 3 * 710))
        p.save(directory / f"panel_{i + 1}.png")
    canvas.save(directory / "atlas.png")
    write_json(
        directory / "candidates.json",
        [{"atlas_number": i + 1, **c} for i, c in enumerate(rejected)],
    )
    comparison = Image.new("RGB", (2720, 710), "white")
    for i, arm in enumerate(ARMS):
        p = panel(arm)
        regions(p, predictions[arm]["authoring"]["topology"]["regions"], work_to_original, True)
        openings(p, predictions[arm]["authoring"]["topology"]["openings"], work_to_original, True)
        comparison.paste(p, (680 * i, 0))
    comparison.save(directory / "interventions.png")


def main(output, label_overrides=None):
    cv2.setNumThreads(1)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "protocol.json").exists():
        raise ValueError("Choose a new output; preserved runs cannot be overwritten")
    protected = [
        ROOT / f"SketchPipeline/shape_authoring/models/{n}"
        for n in ["shape-dinov2-decoder-v1.pt", "shape-unet-v1.pt"]
    ]
    protected += [ROOT / "Saved/ShapeFirst/dinov2/corridor_addon/v1/checkpoints/epoch_10.pt"]
    protected += sorted((ROOT / "SketchPipeline/shape_authoring").glob("*.py"))
    protected += sorted((ROOT / "SketchPipeline/shape_authoring").glob("*.json"))
    protected += [
        p
        for n in range(51, 71)
        for p in [
            ROOT / f"Data/Data_{n}.png",
            ROOT / f"Data/annotations/v1/Data_{n}.annotations.json",
            ROOT / f"Data/annotations/v1/Data_{n}.observations.json",
            ROOT / f"Data/ground_truth/structural_v1/Data_{n}.structural.json",
        ]
    ]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    overrides = json.loads(label_overrides.read_text()) if label_overrides else None
    protocol = {
        "version": "new20-component-diagnosis/1.1",
        "date": "2026-11-06",
        "arms": ARMS,
        "sensitivity_arms": SENSITIVITY,
        "physical_stage": "production passage-refinement + recovered-corridor fallback + observed-door-jambs/1.5; no ensemble",
        "reference_regions": "Exact annotated polygons; shared polygon boundaries projected to dominant image axis only for production physical evidence routines. Projection errors retained.",
        "reference_endpoints": "Unpaired unlabeled door-endpoint coordinates only; no owners/pairing/acceptance. Raw ink tick extents measured by diagnostic adapter; production physical tests unchanged.",
        "reference_open_passage_points_injected": False,
        "label_overrides": (
            {"path": str(label_overrides), "sha256": sha(label_overrides)}
            if label_overrides
            else None
        ),
        "reference_corridor_fallback": "Primary reference-region arms have no CV-recovered provenance, hence no recovered-only fallback. Two sensitivity arms mark every reference corridor as injected/recovered, rerunning the same physical fallback. Neither receives opening ownership/acceptance.",
        "evaluation": {
            "region_iou_min": 0.5,
            "region_matching": "axis-aligned bounding IoU, type agnostic; type counted separately",
            "endpoint_tolerance_working_side_fraction": 0.04,
            "assignment": "maximum-cardinality; type+position for doors, plus mapped owners for attachments",
            "owner_reference": "explicit structural reference IDs; legacy proximity scores also retained",
            "unmatched_predictions": "Reference-unmatched, NOT proof of physically false connection",
        },
        "cached_model_inference": True,
        "new_training": False,
        "production_modified": False,
        "human_approved": False,
        "hashes_before": hashes,
        "cache_hashes": {},
        "limitations": [
            "Previously seen same-writer development corpus.",
            "Approximate manual reference polygons/endpoints.",
            "Reference arms diagnostic only, not real-use results.",
            "Endpoint adapter changes proposal localization, not acceptance; not a trained endpoint detector upper bound.",
        ],
    }
    write_json(output / "protocol.json", protocol)
    all_rows, failures, gallery = ([], [], [])
    for origin, sample, split, folder in cases():
        if origin != "new_human":
            continue
        n = int(sample.split("_")[1])
        dest = output / sample
        dest.mkdir()
        old = json.loads((folder / "proposals.json").read_text())
        assert (
            old["model"]["checkpoint_sha256"]
            == hashes["SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt"]
        )
        for name in [
            "proposals.json",
            "evidence.png",
            "working.png",
            "model-masks.npz",
            "native-auxiliary-masks.npz",
        ]:
            p = folder / name
            protocol["cache_hashes"][str(p.relative_to(ROOT))] = sha(p)
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as z:
            prob = z["native_probabilities"]
        with np.load(folder / "native-auxiliary-masks.npz") as z:
            endpoints = z["probabilities"][6]
        wmeta, emeta = (old["preprocessing"], old["evidence_preprocessing"])
        to_work = np.asarray(wmeta["original_to_working"]) @ np.asarray(
            emeta["working_to_original"]
        )
        to_native = np.linalg.inv(to_work)
        ref, raw = reference(n, wmeta, overrides)
        assert raw["image_sha256"] == hashes[f"Data/Data_{n}.png"]
        original_points = [
            p for g in raw["openings"] if g["kind"] == "door" for p in [g["start_px"], g["end_px"]]
        ]
        oracle = (
            project(original_points, emeta["original_to_working"])
            if original_points
            else np.empty((0, 2))
        )
        doc, detail = decode(
            gray,
            prob,
            old["authoring"]["image_evidence"]["source"],
            emeta,
            working_gray=working,
            working_metadata=wmeta,
            evidence_to_working=to_work,
            region_policy="supported-corridors",
            opening_policy="corridor-passages",
            door_policy="observed-jambs",
        )
        historical = json.loads(
            (
                ROOT
                / f"Saved/ShapeFirst/task_ensemble/v2/new_human/{sample}/baseline/prediction.json"
            ).read_text()
        )["authoring"]
        assert doc["topology"] == historical["topology"], f"Baseline changed: {sample}"
        boxes = detail["region_boxes"]
        segments = boundary_graph(boxes)[0]
        recovered = [i for i, b in enumerate(boxes) if b.get("model_score") == 0.0]
        ordinary, replay = stage(
            segments, gray, prob, to_native, [b["type"] for b in boxes], recovered
        )
        predicted_regions = [
            {"id": r["id"], "type": r["type"], "polygon": r["geometry"]["points_px"]}
            for r in doc["topology"]["regions"]
        ]
        replay_doc = document_for(doc, predicted_regions, segments, ordinary)
        assert [
            (o["type"], o["entity_ids"], o["geometry"]["points_px"])
            for o in replay_doc["topology"]["openings"]
        ] == [
            (o["type"], o["entity_ids"], o["geometry"]["points_px"])
            for o in doc["topology"]["openings"]
        ], f"Production replay differs {sample}"
        refsegments, projection = reference_segments(ref["regions"])
        detail["opening_evidence"]["diagnostic_working_to_native"] = to_native.tolist()
        predictions = {"baseline": {"authoring": doc, "evidence": detail["opening_evidence"]}}
        for arm in ARMS[1:]:
            use_ref = arm in ("reference_regions", "reference_both")
            regions = ref["regions"] if use_ref else predicted_regions
            support = refsegments if use_ref else segments
            proposals, evidence = stage(
                support,
                gray,
                prob,
                to_native,
                [r["type"] for r in regions],
                [] if use_ref else recovered,
                oracle if arm in ("reference_endpoints", "reference_both") else None,
            )
            predictions[arm] = {
                "authoring": document_for(doc, regions, support, proposals),
                "evidence": evidence,
            }
        for arm in SENSITIVITY:
            regions = ref["regions"]
            recovered_ref = [i for i, r in enumerate(regions) if r["type"] == "corridor_segment"]
            proposals, evidence = stage(
                refsegments,
                gray,
                prob,
                to_native,
                [r["type"] for r in regions],
                recovered_ref,
                oracle if "both" in arm else None,
            )
            predictions[arm] = {
                "authoring": document_for(doc, regions, refsegments, proposals),
                "evidence": evidence,
            }
        max_roundtrip = 0.0
        for r in raw["regions"]:
            p = np.asarray(r["polygon_px"])
            max_roundtrip = max(
                max_roundtrip,
                float(
                    np.abs(
                        project(
                            project(p, emeta["original_to_working"]), emeta["working_to_original"]
                        )
                        - p
                    ).max()
                ),
            )
        metadata = {
            "source_folder": str(folder.relative_to(ROOT)),
            "working": wmeta,
            "evidence": emeta,
            "evidence_to_working": to_work.tolist(),
            "roundtrip_max_original_px": max_roundtrip,
            "reference_boundary_projections": projection,
            "baseline_matches_v2_topology": True,
            "production_stage_replay_equal": True,
        }
        write_json(dest / "coordinates.json", metadata)
        for arm, p in predictions.items():
            p["metrics"] = evaluate(p["authoring"], ref, wmeta["working_size_px"])
            write_json(dest / (arm + ".json"), p)
            all_rows.append(
                {"sample_id": sample, "split": split, "arm": arm, "metrics": p["metrics"]}
            )
        write_json(
            dest / "legacy_baseline_metrics.json",
            legacy_score(doc, legacy_reference(n, wmeta), wmeta["working_size_px"]),
        )
        rows = failure_rows(sample, ref, predictions, gray, endpoints, to_native)
        failures.extend(rows)
        write_json(dest / "failures.json", rows)
        write_json(dest / "reference.json", ref)
        render(
            sample,
            ROOT / f"Data/Data_{n}.png",
            ref,
            predictions,
            endpoints,
            emeta["working_to_original"],
            wmeta["working_to_original"],
            dest,
        )
        gallery.append(
            f'<section id="{sample}"><h2>{sample} · {split}</h2><a href="{sample}/atlas.png"><img loading="lazy" src="{sample}/atlas.png"></a><details><summary>Dört koşul karşılaştırması</summary><img loading="lazy" src="{sample}/interventions.png"></details><p><a href="{sample}/failures.json">Kapı / bağlantı nedenleri</a> · <a href="{sample}/candidates.json">Reddedilen adaylar</a> · <a href="{sample}/coordinates.json">Koordinat kayıtları</a></p><table><tr><th>Koşul</th><th>Doğru kapı</th><th>Doğru / üretilen / referans bağlantı</th></tr>'
            + "".join(
                (
                    f"<tr><td>{arm}</td><td>{p['metrics']['doors']['true_positive']}/{p['metrics']['doors']['reference']}</td><td>{p['metrics']['connections']['true_positive']}/{p['metrics']['connections']['predicted']}/{p['metrics']['connections']['reference']}</td></tr>"
                    for arm, p in predictions.items()
                )
            )
            + "</table></section>"
        )
        print(
            sample,
            split,
            {
                a: (
                    p["metrics"]["doors"]["true_positive"],
                    p["metrics"]["connections"]["true_positive"],
                )
                for a, p in predictions.items()
            },
            flush=True,
        )
    aggregate = {}
    for split in ["train", "validation", "test", "all"]:
        aggregate[split] = {}
        for arm in ARMS + SENSITIVITY:
            rows = [
                r["metrics"]
                for r in all_rows
                if r["arm"] == arm and (split == "all" or r["split"] == split)
            ]
            s = {"samples": len(rows)}
            for key in ["regions", "doors", "openings", "attached_openings", "connections"]:
                s[key] = counts(
                    sum((m[key]["true_positive"] for m in rows)),
                    sum((m[key]["predicted"] for m in rows)),
                    sum((m[key]["reference"] for m in rows)),
                )
            s["unmatched_produced_connections"] = sum(
                (m["unmatched_produced_connections"] for m in rows)
            )
            s["missed_connections"] = sum((m["missed_connections"] for m in rows))
            aggregate[split][arm] = s
    write_json(output / "protocol.json", protocol)
    write_json(
        output / "report.json",
        {
            "summary": aggregate,
            "rows": all_rows,
            "production_changed": False,
            "diagnostic_only": True,
        },
    )
    write_json(output / "failures.json", failures)
    with (output / "metrics.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "split",
                "arm",
                "metric",
                "correct",
                "predicted",
                "reference",
                "precision",
                "recall",
                "f1",
            ]
        )
        for split, arms in aggregate.items():
            for arm, metrics in arms.items():
                for key in ["doors", "attached_openings", "connections"]:
                    m = metrics[key]
                    writer.writerow(
                        [
                            split,
                            arm,
                            key,
                            m["true_positive"],
                            m["predicted"],
                            m["reference"],
                            m["precision"],
                            m["recall"],
                            m["f1"],
                        ]
                    )
    (output / "gallery.html").write_text(
        '<!doctype html><html lang="tr"><meta charset="utf-8"><title>20 çizim hata atlası</title><style>body{font:16px system-ui;background:#eef2f6;color:#172033;margin:24px}section{background:white;padding:18px;margin:24px 0}img{width:100%;height:auto}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ccc}summary{cursor:pointer}</style><h1>PlayableSketch · 20 çizim teşhis atlası</h1><p>6 Kasım 2026. Referanslı koşullar yalnız teşhis içindir. Mavi: oda; kahve: koridor; yeşil: kapı; mor: açık geçiş; turkuaz: üretilen bölge bağlantısı; kırmızı: reddedilen/bağlanamayan aday. Görseller özgün fotoğraf koordinatlarına geri yansıtılmıştır. Yaklaşık etiketler ve eksene izdüşürülen referans ortak sınırları için coordinates.json kayıtlarını inceleyin.</p>'
        + "".join(gallery)
        + "</html>"
    )
    changed = [p for p, h in hashes.items() if sha(ROOT / p) != h]
    assert not changed, changed
    write_json(
        output / "verification.json",
        {
            "protected_files_checked": len(hashes),
            "changed": changed,
            "baseline_v2_equal_samples": 20,
            "production_stage_replay_equal_samples": 20,
            "labels_modified": False,
            "training_started": False,
            "weights_promoted": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "Saved/ShapeFirst/new20_diagnosis/v1")
    parser.add_argument("--label-overrides", type=Path)
    args = parser.parse_args()
    main(args.output, args.label_overrides)
