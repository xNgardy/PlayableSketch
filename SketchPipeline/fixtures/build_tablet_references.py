import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from PIL import Image
from SketchPipeline.validation.validate import as_validated, validate_document

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Data/annotations/v1/tablet_11_20.source.json"
ANNOTATIONS = SOURCE.parent
METRIC = ROOT / "Data/ground_truth/v1"


def provenance(method="derived", evidence=(), note=""):
    return {"method": method, "evidence_ids": list(evidence), "note": note}


def polygon(box):
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def build_case(spec):
    identifier = spec["id"]
    image = (ANNOTATIONS / spec["image_path"]).resolve()
    if hashlib.sha256(image.read_bytes()).hexdigest() != spec["image_sha256"]:
        raise ValueError(identifier + ": source image changed")
    with Image.open(image) as im:
        if list(im.size) != spec["size_px"]:
            raise ValueError(identifier + ": image dimensions changed")
    source = {
        "image_path": spec["image_path"],
        "image_sha256": spec["image_sha256"],
        "legacy_draft_path": None,
    }
    obs = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": identifier.lower() + "_observations",
        "revision_id": "tablet-manual-1",
        "source": source,
        "units": "px",
        "coordinate_system": "u_right_v_down",
        "frame": {
            "id": "original",
            "width_px": spec["size_px"][0],
            "height_px": spec["size_px"][1],
            "original_to_frame": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },
        "region_annotation_status": "complete",
        "texts": [],
        "lines": [],
        "opening_candidates": [],
        "issues": [],
        "notes": spec["notes"],
    }
    side = {
        "schema_version": "playablesketch-pixel-annotations/1.0",
        "observations_path": identifier + ".observations.json",
        "reference_draft_path": "../../ground_truth/v1/" + identifier + ".draft.json",
        "coordinate_frame": "original",
        "method": "manual_visual_trace",
        "precision": "Approximate manual user-ink traces, enclosing dimension-label polygons and intended region boundaries; not pixel-perfect masks.",
        "strokes": [],
        "junctions": [],
        "gaps": [],
        "associations": [],
        "regions": [
            {
                "region_id": r["id"],
                "kind": r["kind"],
                "polygon_px": r["polygon_px"],
                "status": "manual_intended_boundary",
            }
            for r in spec["regions"]
        ],
        "issues": spec.get(
            "pixel_issues",
            [
                "TABLET_DIGITAL_EXPORT",
                "GRID_BACKGROUND_IS_NOT_WALL",
                "HAND_DRAWN_STROKES_APPROXIMATE",
                "SOME_LABELS_NOT_PARALLEL_OR_MULTILINE",
            ],
        ),
    }
    for i, stroke in enumerate(spec["strokes"], 1):
        ids = []
        for a, b in zip(stroke["points_px"], stroke["points_px"][1:]):
            line_id = f"l{len(obs['lines']) + 1:03d}"
            obs["lines"].append({"id": line_id, "start_px": a, "end_px": b, "score": None})
            ids.append(line_id)
        side["strokes"].append({"id": f"s{i:03d}", "kind": stroke["kind"], "line_ids": ids})
    for i, (point, kind) in enumerate(spec["junctions"], 1):
        side["junctions"].append(
            {
                "id": f"j{i:03d}",
                "point_px": point,
                "kind": kind,
                "status": "approximate_intended_junction",
            }
        )
    for i, opening in enumerate(spec["openings"], 1):
        a, b = opening["gap_px"]
        x0, y0 = [min(a[j], b[j]) for j in (0, 1)]
        x1, y1 = [max(a[j], b[j]) for j in (0, 1)]
        candidate = f"o{i:03d}"
        obs["opening_candidates"].append(
            {
                "id": candidate,
                "polygon_px": polygon([x0 - 5, y0 - 5, x1 + 5, y1 + 5]),
                "score": None,
            }
        )
        side["gaps"].append(
            {
                "id": f"g{i:03d}",
                "kind": opening["kind"],
                "start_px": a,
                "end_px": b,
                "opening_candidate_id": candidate,
                "semantic_provenance": "manual image inspection and author drawing convention; center/edge semantics are explicit in dimensions",
            }
        )
    for a, b in spec.get("incidental_gaps", []):
        side["gaps"].append(
            {
                "id": f"g{len(side['gaps']) + 1:03d}",
                "kind": "incidental",
                "start_px": a,
                "end_px": b,
                "opening_candidate_id": None,
                "semantic_provenance": "Small unmarked corner break; not a door",
            }
        )
    layout = {
        key: []
        for key in ("vertices", "walls", "rooms", "corridors", "openings", "passages", "dimensions")
    }
    settings = {
        "source": "configured",
        "wall_thickness_cm": 20,
        "wall_height_cm": 300,
        "door_height_cm": 220,
        "floor_thickness_cm": 20,
    }
    kinds = {r["id"]: r["kind"] for r in spec["regions"]}
    corners = {}
    for r in spec["regions"]:
        x0, y0, x1, y1 = r["bounds_cm"]
        corners[r["id"]] = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    known = {p for values in corners.values() for p in values if None not in p}
    vertices, walls = ({}, {})

    def vertex(point, identity):
        key = point if None not in point else identity
        if key not in vertices:
            vid = f"v{len(vertices) + 1:03d}"
            vertices[key] = vid
            layout["vertices"].append(
                {
                    "id": vid,
                    "position_cm": list(point),
                    "state": "derived" if None not in point else "missing",
                    "provenance": provenance(
                        note="Manual metric reference from observed dimensions; null stays unresolved."
                    ),
                }
            )
        return vertices[key]

    for region_id, points in corners.items():
        boundary, axes = ([], [])
        for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
            axis = index % 2
            candidates = [a]
            if None not in a + b:
                candidates = [
                    p
                    for p in known
                    if p[1 - axis] == a[1 - axis]
                    and min(a[axis], b[axis]) <= p[axis] <= max(a[axis], b[axis])
                ]
                candidates.sort(key=lambda p: p[axis], reverse=b[axis] < a[axis])
                candidates = candidates[:-1]
            for point in candidates:
                boundary.append(vertex(point, (region_id, index)))
                axes.append(axis)
        wall_ids = []
        by_id = {v["id"]: v["position_cm"] for v in layout["vertices"]}
        for a, b, axis in zip(boundary, boundary[1:] + boundary[:1], axes):
            key = tuple(sorted((a, b)))
            if key not in walls:
                start, end = (a, b)
                if None not in by_id[a] + by_id[b] and by_id[a][axis] > by_id[b][axis]:
                    start, end = (b, a)
                record = {
                    "id": f"w{len(walls) + 1:03d}",
                    "start_vertex_id": start,
                    "end_vertex_id": end,
                    "axis": "xy"[axis],
                    "thickness_cm": 20,
                    "height_cm": 300,
                    "region_ids": [],
                    "provenance": provenance(
                        note="Unique noded centerline boundary from the manual rectangular topology."
                    ),
                }
                walls[key] = record
                layout["walls"].append(record)
            walls[key]["region_ids"].append(region_id)
            wall_ids.append(walls[key]["id"])
        layout["corridors" if kinds[region_id] == "corridor" else "rooms"].append(
            {
                "id": region_id,
                "name": region_id,
                "boundary_vertex_ids": boundary,
                "boundary_wall_ids": wall_ids,
                "role": "none",
                "provenance": provenance(
                    "manual_annotation",
                    note="Manually interpreted intended region in the uploaded drawing.",
                ),
            }
        )
    positions = {v["id"]: v["position_cm"] for v in layout["vertices"]}
    for i, opening in enumerate(spec["openings"], 1):
        center = opening["center_cm"]
        matches = []
        for wall in layout["walls"]:
            a, b = (positions[wall["start_vertex_id"]], positions[wall["end_vertex_id"]])
            axis = "xy".index(wall["axis"])
            if (
                set(wall["region_ids"]) == set(opening["region_ids"])
                and None not in a + b
                and (center[1 - axis] == a[1 - axis])
            ):
                if center[axis] is None:
                    matches.append((wall, None))
                elif a[axis] <= center[axis] <= b[axis]:
                    matches.append((wall, center[axis] - a[axis]))
        if len(matches) != 1:
            raise ValueError(f"{identifier}: ambiguous supporting wall for {opening['id']}")
        wall, local_center = matches[0]
        entities = [{"type": kinds[r], "id": r} for r in opening["region_ids"]]
        layout["openings"].append(
            {
                "id": opening["id"],
                "wall_id": wall["id"],
                "type": opening["kind"],
                "center_offset_cm": local_center,
                "clear_width_cm": opening["clear_width_cm"],
                "clear_height_cm": 220 if opening["kind"] == "door" else 300,
                "connected_entities": entities,
                "state": (
                    "missing"
                    if local_center is None
                    else "confirmed" if opening["kind"] == "door" else "derived"
                ),
                "provenance": provenance(
                    "manual_annotation" if opening["kind"] == "door" else "derived",
                    [f"o{i:03d}"],
                    (
                        "Opening location has no metric dimension; supporting wall and observed width are known, center remains null."
                        if local_center is None
                        else "Door center derived from edge/chain dimensions; open-passage clear width derived from centerline corridor width minus wall thickness."
                    ),
                ),
            }
        )
        layout["passages"].append(
            {
                "id": "p-" + opening["id"],
                "opening_id": opening["id"],
                "type": opening["kind"],
                "connected_entities": entities,
                "provenance": provenance(note="Manual connection through this opening."),
            }
        )

    def target_and_basis(raw):
        target = deepcopy(raw)
        if target["type"] == "manual_wall_span":
            start, end = (target["start_cm"], target["end_cm"])
            axis = 0 if start[1] == end[1] else 1
            matches = []
            for wall in layout["walls"]:
                a, b = (positions[wall["start_vertex_id"]], positions[wall["end_vertex_id"]])
                if (
                    None not in a + b
                    and wall["axis"] == "xy"[axis]
                    and (a[1 - axis] == start[1 - axis])
                    and (start[axis] <= a[axis])
                    and (b[axis] <= end[axis])
                ):
                    matches.append((a[axis], wall["id"]))
            if not matches:
                raise ValueError(identifier + ": measured wall span has no canonical wall")
            return (
                {"type": "wall_chain", "wall_ids": [wid for _, wid in sorted(matches)]},
                "wall_centerline",
            )
        basis = (
            "clear_opening"
            if target["type"] == "opening_width"
            else (
                "edge_offset"
                if target["type"] in ("opening_offset", "opening_separation")
                else "wall_centerline"
            )
        )
        return (target, basis)

    for i, label in enumerate(spec["texts"], 1):
        tid, did = (f"t{i:03d}", f"m{i:03d}")
        obs["texts"].append(
            {
                "id": tid,
                "raw_text": label["raw_text"],
                "polygon_px": label.get("polygon_px", polygon(label["box_px"])),
                "parsed_value_cm": label["value_cm"],
                "score": None,
                "method": "manual_transcription",
            }
        )
        target, basis = target_and_basis(label["target"])
        layout["dimensions"].append(
            {
                "id": did,
                "value_cm": label["value_cm"],
                "basis": basis,
                "target": target,
                "state": "confirmed",
                "span_label": f"{identifier}.{tid}",
                "provenance": provenance(
                    "manual_annotation",
                    [tid],
                    "Observed label and explicitly interpreted measured endpoints; not an OCR prediction.",
                ),
            }
        )
        side["associations"].append(
            {
                "text_id": tid,
                "dimension_id": did,
                "span_start_px": label["span_px"][0],
                "span_end_px": label["span_px"][1],
                "endpoint_basis": "manual_interpretation_of_measured_span",
                "provenance": (
                    "author_confirmed_corner_to_opening_edge"
                    if target["type"] == "opening_offset"
                    else "manual_image_and_reference_review"
                ),
            }
        )
    for missing in spec.get("missing_dimensions", []):
        target, basis = target_and_basis(missing["target"])
        layout["dimensions"].append(
            {
                "id": f"m{len(layout['dimensions']) + 1:03d}",
                "value_cm": None,
                "basis": basis,
                "target": target,
                "state": "missing",
                "span_label": missing["label"],
                "provenance": provenance(
                    note="Not present in the image; do not use pixel proportions."
                ),
            }
        )
    draft = {
        "schema_version": "playablesketch-layout/1.0",
        "kind": "draft_layout",
        "document_id": identifier.lower() + "_layout",
        "revision_id": "tablet-manual-1",
        "parent_revision_id": None,
        "algorithm_version": "manual-tablet-reference/1.0",
        "observation_document_id": obs["document_id"],
        "source": source,
        "units": "cm",
        "coordinate_system": "local_x_right_y_up_z_up",
        "dimension_basis": "wall_centerline",
        "validation_mode": "geometry_only",
        "start_room_id": None,
        "goal_room_id": None,
        "settings": settings,
        "review": {"status": "pending", "reviewer": None},
        "layout": layout,
        "status": (
            "conflicting"
            if spec["expected_status"] == "conflicting"
            else "needs_review" if spec["expected_status"] == "incomplete" else "draft"
        ),
        "issues": [],
        "validation": {
            "metric": "not_run",
            "validator_version": None,
            "tolerance_cm": 0.001,
            "engine_geometry": "not_run",
            "navigation": "not_run",
        },
        "notes": spec["notes"]
        + [
            "Manual reference annotation only; not automated model output or a claim of successful gameplay."
        ],
    }
    checked_obs = validate_document(obs)
    checked = validate_document(draft, obs)
    if not checked_obs["schema_valid"] or checked_obs["issues"] or (not checked["schema_valid"]):
        raise ValueError(f"{identifier}: schema/evidence failure: {checked_obs} {checked}")
    if spec["expected_status"] == "reference_validated" and (not checked["metric_valid"]):
        raise ValueError(f"{identifier}: unexpected metric failure: {checked}")
    if spec["expected_status"] == "conflicting" and (
        not any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in checked["issues"]))
    ):
        raise ValueError(identifier + ": expected dimension conflict is missing")
    if spec["expected_status"] == "incomplete" and (
        not any((i["code"] == "SKETCH_DIMENSION_MISSING" for i in checked["issues"]))
    ):
        raise ValueError(identifier + ": expected missing dimension is missing")
    if not checked["metric_valid"]:
        draft["issues"] = checked["issues"]
    return (obs, side, draft)


def artifacts(
    source_path=SOURCE,
    batch_manifest="manifest_tablet_11_20.json",
    previous_manifest="manifest.json",
    combined_manifest="manifest_all_20.json",
):
    source_path = Path(source_path)
    if source_path.parent.resolve() != ANNOTATIONS.resolve():
        raise ValueError("Manual sources must share the annotation directory and image-path base.")
    source = json.loads(source_path.read_text())
    output, samples = ({}, [])
    for spec in source["samples"]:
        identifier = spec["id"]
        obs, side, draft = build_case(spec)
        output[ANNOTATIONS / (identifier + ".observations.json")] = obs
        output[ANNOTATIONS / (identifier + ".annotations.json")] = side
        output[METRIC / (identifier + ".observations.json")] = obs
        output[METRIC / (identifier + ".draft.json")] = draft
        if spec["expected_status"] == "reference_validated":
            output[METRIC / (identifier + ".validated.json")] = as_validated(
                draft, "manual-tablet-reference-annotation", obs
            )
        samples.append(
            {
                "id": identifier,
                "image_path": spec["image_path"],
                "image_sha256": spec["image_sha256"],
                "encoded_size_px": spec["size_px"],
                "exif_orientation": 1,
                "base_plan_id": spec["base_plan_id"],
                "writer_id": spec["writer_id"],
                "split": "development",
                "observations_path": identifier + ".observations.json",
                "annotations_path": identifier + ".annotations.json",
                "annotation_status": "complete",
                "counts": {k: len(obs[k]) for k in ("texts", "lines", "opening_candidates")},
                "metric_status": spec["expected_status"],
                "page_corners": None,
                "page_aspect_ratio": None,
            }
        )
    policy = "development_only; group variants/crops by base_plan_id and writer; no held-out accuracy claim"
    output[ANNOTATIONS / batch_manifest] = {
        "schema_version": "playablesketch-dataset/1.0",
        "split_policy": policy,
        "samples": samples,
    }
    old = json.loads((ANNOTATIONS / previous_manifest).read_text())
    if {s["id"] for s in old["samples"]} & {s["id"] for s in samples}:
        raise ValueError("Combined manifest would contain duplicate sample IDs.")
    output[ANNOTATIONS / combined_manifest] = {
        "schema_version": "playablesketch-dataset/1.0",
        "split_policy": policy,
        "samples": old["samples"] + samples,
    }
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce manual Data_11–20 labels; never run inference or train a model."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only generated Data_11–20 artifacts and their separate manifests",
    )
    args = parser.parse_args()
    output = artifacts()
    if args.check:
        missing = [
            str(p.relative_to(ROOT))
            for p, d in output.items()
            if not p.exists() or json.loads(p.read_text()) != d
        ]
        if missing:
            raise SystemExit("Reference differences: " + ", ".join(missing))
        print(f"All {len(output)} tablet reference artifacts match their manual source.")
        return
    if not args.overwrite and any((p.exists() for p in output)):
        raise SystemExit(
            "Existing generated labels are preserved. Use --check or explicitly --overwrite."
        )
    for path, document in output.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n")
    print(
        f"Wrote {len(output)} artifacts: 10 observation pairs, 10 pixel sidecars, 10 metric drafts, 8 metric references and 2 manifests."
    )


if __name__ == "__main__":
    main()
