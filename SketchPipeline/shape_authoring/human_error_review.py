import argparse
from collections import Counter
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, Point
from SketchPipeline.evaluation.metrics import pairs, endpoint_error
from SketchPipeline.preprocessing.prepare import project
from .decoder import iou
from .human_supervision import ROOT, structural_labels
from .synthetic import write_json


def reference(n, metadata):
    labels = structural_labels(n)
    matrix = metadata["original_to_working"]
    regions = []
    for r in labels["regions"]:
        points = project(r["polygon_px"], matrix)
        regions.append(
            {
                "id": r["region_id"],
                "type": "corridor_segment" if r["kind"] == "corridor" else "room",
                "bounds_px": np.r_[points.min(axis=0), points.max(axis=0)].tolist(),
                "polygon": points.tolist(),
            }
        )
    openings = []
    for g in labels["gaps"]:
        if g["kind"] not in ("door", "open_passage"):
            continue
        points = project([g["start_px"], g["end_px"]], matrix)
        mid = Point(points.mean(axis=0))
        distances = sorted(
            ((Polygon(r["polygon"]).boundary.distance(mid), r["id"]) for r in regions)
        )
        attached = (
            [r[1] for r in distances[:2]]
            if len(distances) >= 2 and distances[1][0] < max(metadata["working_size_px"]) * 0.04
            else []
        )
        openings.append(
            {"id": g["id"], "type": g["kind"], "points_px": points.tolist(), "entity_ids": attached}
        )
    return {
        "id": f"Data_{n}",
        "regions": regions,
        "openings": openings,
        "approximate_human_labels": True,
        "reference_policy_version": "structural-openings/2.0",
        "excluded_non_opening_gaps": sum(
            (g["kind"] not in ("door", "open_passage") for g in labels["gaps"])
        ),
    }


def review(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    figures = []
    for n in [3, 8, 18, 31, 41, 45]:
        folder = (
            ROOT
            / "Saved/ShapeFirst/decoder_refinement/v5/human"
            / f"Data_{n}"
            / "square_512/refined_paired_raw"
        )
        prediction = json.loads((folder / "prediction.json").read_text())
        document = prediction["authoring"]
        cached = json.loads(
            (
                ROOT / f"Saved/ShapeFirst/diagnostics/v2/Data_{n}/square_512/prediction.json"
            ).read_text()
        )
        metadata = cached["canonical_preprocessing"]
        ref = reference(n, metadata)
        actual = document["topology"]
        bounds = lambda r: np.r_[
            np.min(r["geometry"]["points_px"], axis=0), np.max(r["geometry"]["points_px"], axis=0)
        ]
        matched_regions = pairs(
            actual["regions"], ref["regions"], lambda a, b: 1 - iou(bounds(a), b["bounds_px"]), 0.5
        )
        found = {ref["regions"][j]["id"] for i, j, c in matched_regions}
        predicted = actual["openings"]
        gaps = ref["openings"]
        matched = pairs(
            predicted,
            gaps,
            lambda a, b: (
                endpoint_error(a["geometry"]["points_px"], b["points_px"])
                if a["type"] == b["type"]
                else float("inf")
            ),
            max(metadata["working_size_px"]) * 0.04,
        )
        found_gaps = {j for i, j, c in matched}
        source = cv2.imread(
            str(ROOT / f"Saved/ShapeFirst/diagnostics/v2/Data_{n}/baseline_256/input.png"), 0
        )
        image = (
            Image.fromarray(source)
            .convert("RGB")
            .resize((source.shape[1] * 3, source.shape[0] * 3))
        )
        draw = ImageDraw.Draw(image)
        for r in ref["regions"]:
            draw.rectangle([v * 3 for v in r["bounds_px"]], outline="#16a34a", width=2)
        for r in actual["regions"]:
            draw.rectangle((bounds(r) * 3).tolist(), outline="#f97316", width=2)
        transform = np.asarray(cached["preprocessing"]["original_to_working"]) @ np.asarray(
            metadata["working_to_original"]
        )
        for index, gap in enumerate(gaps):
            missing = sorted(set(gap["entity_ids"]) - found)
            candidates = []
            for c in prediction["decoder"]["opening_evidence"]["candidates"]:
                segment = c["segment"]
                axis = 0 if segment[0][1] == segment[1][1] else 1
                positions = [
                    (t - transform[axis, 2]) / transform[axis, axis] for t in c["native_gap_px"]
                ]
                p, q = (list(segment[0]), list(segment[1]))
                p[axis], q[axis] = positions
                cost = endpoint_error([p, q], gap["points_px"])
                candidates.append((cost, c))
            closest = min(candidates, key=lambda v: v[0]) if candidates else None
            if index in found_gaps:
                reason = "detected"
            elif not gap["entity_ids"]:
                reason = "reference_attachment_uncertain"
            elif missing:
                reason = "missing_connected_region"
            elif closest is None or closest[0] > max(metadata["working_size_px"]) * 0.08:
                reason = "gap_or_support_search_missed"
            else:
                c = closest[1]
                reason = (
                    "wall_support_rejected"
                    if min(c["wall_support"]) < 0.6
                    else (
                        "paired_tick_ink_rejected"
                        if c["raw_tick_support"] < 0.6
                        else "marker_or_span_policy_rejected"
                    )
                )
            row = {
                "image_id": f"Data_{n}",
                "opening_id": gap["id"],
                "type": gap["type"],
                "detected": index in found_gaps,
                "reason": reason,
                "reference_entities": gap["entity_ids"],
                "missing_entities": missing,
                "reference_points_px": gap["points_px"],
                "nearest_candidate_distance_px": closest[0] if closest else None,
                "nearest_candidate": closest[1] if closest else None,
                "reference_attachment_is_approximate": True,
                "diagnostic_only": True,
            }
            rows.append(row)
            color = "#16a34a" if row["detected"] else "#dc2626"
            draw.line([tuple(np.asarray(p) * 3) for p in gap["points_px"]], fill=color, width=5)
            mid = np.mean(gap["points_px"], axis=0) * 3
            draw.text(tuple(mid + [6, 0]), gap["id"], fill=color)
        image.save(output / f"Data_{n}.png")
        records = [r for r in rows if r["image_id"] == f"Data_{n}"]
        text = "<br>".join(
            (
                f"{r['opening_id']}: {r['reason']}"
                + (f" — missing {r['missing_entities']}" if r["missing_entities"] else "")
                for r in records
            )
        )
        figures.append(f'<section><h2>Data {n}</h2><img src="Data_{n}.png"><p>{text}</p></section>')
    missed = [r for r in rows if not r["detected"]]
    result = {
        "version": "shape-opening-failure-review/1.0",
        "total_reference_openings": len(rows),
        "detected": len(rows) - len(missed),
        "missed": len(missed),
        "missed_reason_counts": dict(Counter((r["reason"] for r in missed))),
        "new_region_sidecar_used_for_diagnostics_only": True,
        "rows": rows,
        "human_correction_time_seconds": None,
    }
    write_json(output / "review.json", result)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Missing opening audit</title><style>body{font:15px system-ui;background:#f8f8f8;margin:24px}section{padding:16px;background:white;border:1px solid #ddd;margin:16px 0}img{max-width:100%}</style><h1>Missing opening audit</h1><p>Existing development predictions. Green: reference regions and detected openings; orange: predicted regions; red: missed openings. Labels are approximate. Ground truth is diagnostic only.</p>'
        + "".join(figures)
    )
    print(json.dumps({k: result[k] for k in ["detected", "missed", "missed_reason_counts"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/human_adaptation/v1/error_review"
    )
    args = parser.parse_args()
    review(args.output)
