import math
from .contract import near_edge_to_center
from SketchPipeline.validation.validate import validate_document


def canonical_preview(document, source_points, indices, solution, centers, settings):
    top = document["topology"]
    design = document["physical_design"]
    rotation = design["orientation_degrees"]
    translation = design["anchor"]["position_cm"]

    def point(identifier):
        x = float(solution[indices[0][identifier]])
        y = -float(solution[indices[1][identifier]])
        x, y = {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[rotation]
        return [round(x + translation[0], 6), round(y + translation[1], 6)]

    positions = {identifier: point(identifier) for identifier in source_points}
    if any(len(r["geometry"]["points_px"]) != 4 for r in top["regions"]):
        from .room_tiling import tiled_preview

        return tiled_preview(document, positions, settings)
    note = "Joint design suggestion; not measured from the source image."
    provenance = lambda text: {"method": "derived", "evidence_ids": [], "note": text}
    layout = {
        k: []
        for k in ["vertices", "walls", "rooms", "corridors", "openings", "passages", "dimensions"]
    }
    for identifier, p in positions.items():
        layout["vertices"].append(
            {"id": identifier, "position_cm": p, "state": "derived", "provenance": provenance(note)}
        )
    wall_index = {}
    for w in top["walls"]:
        a, b = (w["start_junction_id"], w["end_junction_id"])
        pa, pb = (positions[a], positions[b])
        axis = 0 if pa[1] == pb[1] else 1
        if pa[1 - axis] != pb[1 - axis] or pa == pb:
            raise ValueError("Non-orthogonal or zero wall: " + w["id"])
        if pa[axis] > pb[axis]:
            a, b = (b, a)
        wall = {
            "id": w["id"],
            "start_vertex_id": a,
            "end_vertex_id": b,
            "axis": "xy"[axis],
            "thickness_cm": settings["wall_thickness_cm"],
            "height_cm": settings["wall_height_cm"],
            "region_ids": w["entity_ids"],
            "provenance": provenance(note),
        }
        layout["walls"].append(wall)
        wall_index[w["id"]] = wall
    for region in top["regions"]:
        edges = [wall_index[w] for w in region["wall_ids"]]
        vertices = set((v for e in edges for v in [e["start_vertex_id"], e["end_vertex_id"]]))
        center = [sum((positions[v][a] for v in vertices)) / len(vertices) for a in (0, 1)]
        ordered = sorted(
            vertices,
            key=lambda v: math.atan2(positions[v][1] - center[1], positions[v][0] - center[0]),
        )
        pair_to_wall = {
            frozenset([e["start_vertex_id"], e["end_vertex_id"]]): e["id"] for e in edges
        }
        try:
            boundary = [
                pair_to_wall[frozenset([a, b])] for a, b in zip(ordered, ordered[1:] + ordered[:1])
            ]
        except KeyError:
            raise ValueError("Region boundary is incomplete or not noded: " + region["id"])
        layout["rooms" if region["type"] == "room" else "corridors"].append(
            {
                "id": region["id"],
                "name": region["name"],
                "boundary_vertex_ids": ordered,
                "boundary_wall_ids": boundary,
                "role": "none",
                "provenance": provenance(note),
            }
        )
    kinds = {r["id"]: "room" if r["type"] == "room" else "corridor" for r in top["regions"]}
    values = {(v["entity_id"], v["parameter"]): v["value"] for v in design["values"]}
    for o in top["openings"]:
        wid = o["support_wall_id"]
        wall = wall_index[wid]
        axis = "xy".index(wall["axis"])
        a, b = (positions[wall["start_vertex_id"]], positions[wall["end_vertex_id"]])
        length = b[axis] - a[axis]
        reference = o["placement"]["reference_junction_id"]
        ref_position = positions[reference][axis] - a[axis]
        direction = 1 if reference == wall["start_vertex_id"] else -1
        width = values[o["id"], "clear_width_cm"]
        near = values[o["id"], "near_edge_offset_cm"]
        center = near_edge_to_center(
            length, ref_position, direction, near, width, tolerance_cm=1e-05
        )
        entities = [{"id": r, "type": kinds[r]} for r in o["entity_ids"]]
        layout["openings"].append(
            {
                "id": o["id"],
                "wall_id": wid,
                "type": o["type"],
                "center_offset_cm": round(center, 6),
                "clear_width_cm": width,
                "clear_height_cm": values[o["id"], "height_cm"],
                "connected_entities": entities,
                "state": "derived",
                "provenance": provenance(note),
            }
        )
        layout["passages"].append(
            {
                "id": "passage_" + o["id"],
                "opening_id": o["id"],
                "connected_entities": entities,
                "type": o["type"],
                "provenance": provenance(note),
            }
        )
    result = {
        "schema_version": "playablesketch-layout/1.0",
        "kind": "draft_layout",
        "document_id": document["document_id"],
        "revision_id": document["revision_id"],
        "parent_revision_id": document["parent_revision_id"],
        "algorithm_version": "shape-sizing/2.0",
        "observation_document_id": document["document_id"],
        "source": {
            k: document["image_evidence"]["source"][k] for k in ["image_path", "image_sha256"]
        }
        | {"legacy_draft_path": None},
        "units": "cm",
        "coordinate_system": "local_x_right_y_up_z_up",
        "dimension_basis": "wall_centerline",
        "validation_mode": "geometry_only",
        "start_room_id": None,
        "goal_room_id": None,
        "settings": dict(settings, source="configured"),
        "review": {"status": "pending", "reviewer": None},
        "layout": layout,
        "status": "needs_review",
        "issues": [],
        "validation": {
            "metric": "not_run",
            "validator_version": None,
            "tolerance_cm": 0.001,
            "engine_geometry": "not_run",
            "navigation": "not_run",
        },
        "notes": [
            "Shape-authoring linkage: observation_document_id identifies the real authoring document, not an OCR observations document.",
            "Provenance, sizing origins, locks and source geometry remain in the authoring sidecar.",
            note,
            "This is a preview draft. Exact-snapshot confirmation and validated export belong to the delivery boundary.",
        ],
    }
    report = validate_document(result)
    if not report["schema_valid"] or not report["metric_valid"]:
        raise ValueError(str(report["issues"]))
    return {
        "canonical": result,
        "validation": report,
        "authoring_revision_id": document["revision_id"],
    }
