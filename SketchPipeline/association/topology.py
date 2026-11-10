from copy import deepcopy
from pathlib import Path
import numpy as np
from SketchPipeline.review.server import analyze_state, digest, file_hash
from SketchPipeline.validation.validate import load_json, validate_document


def provenance(note, method="derived"):
    return {"method": method, "evidence_ids": [], "note": note}


def load_review(path, observations_path, expected_revision_id):
    path, observations_path = (Path(path).resolve(), Path(observations_path).resolve())
    revision, observations = (load_json(path), load_json(observations_path))
    if revision.get("schema_version") != "playablesketch-topology-review/1.0":
        raise ValueError("Unsupported topology review version")
    if (
        revision.get("revision_id") != expected_revision_id
        or path.name != expected_revision_id + ".json"
    ):
        raise ValueError("Metric input must bind to this exact topology revision")
    if (
        path.parent.name != "revisions"
        or load_json(path.parent.parent / "latest.json")["revision_id"] != expected_revision_id
    ):
        raise ValueError("Stale topology revision; rebind dimensions to latest review")
    if (
        revision.get("status") != "reviewed"
        or revision.get("review_action") != "accept"
        or revision.get("units") != "px"
        or (revision.get("metric_layout_created") is not False)
    ):
        raise ValueError("An accepted pixel topology review is required")
    if revision.get("revision_sha256") != digest(
        {k: v for k, v in revision.items() if k != "revision_sha256"}
    ):
        raise ValueError("Topology revision digest mismatch")
    if revision.get("state_sha256") != digest(revision["state"]):
        raise ValueError("State digest mismatch")
    sources = revision["source_fingerprints"]
    if str(observations_path) not in sources:
        raise ValueError("Observations are not linked to this review")
    if not sources:
        raise ValueError("Missing source fingerprints")
    for filename, checksum in sources.items():
        if file_hash(Path(filename)) != checksum:
            raise ValueError(f"Source changed since review: {filename}")
    check = validate_document(observations)
    if not check["schema_valid"] or check["issues"]:
        raise ValueError(f"Invalid observations: {check['issues']}")
    if observations["source"]["image_sha256"] != revision["source_image_sha256"]:
        raise ValueError("Review/observation image identity mismatch")
    image = (observations_path.parent / observations["source"]["image_path"]).resolve()
    if str(image) not in sources or file_hash(image) != revision["source_image_sha256"]:
        raise ValueError("Original image is not linked/unchanged")
    frame = revision["frame"]
    forward, backward = (
        np.array(frame[k], dtype=float) for k in ("original_to_review", "review_to_original")
    )
    observation_frame = np.array(observations["frame"]["original_to_frame"], dtype=float)
    for matrix in (forward, backward, observation_frame):
        if (
            matrix.shape != (3, 3)
            or not np.isfinite(matrix).all()
            or (not np.allclose(matrix[2], [0, 0, 1]))
            or (abs(np.linalg.det(matrix)) < 1e-12)
        ):
            raise ValueError("Expected finite invertible affine frame")
    if not np.allclose(forward @ backward, np.eye(3), atol=1e-07):
        raise ValueError("Review transforms are not inverses")
    analysis = analyze_state(revision["state"], frame["width_px"], frame["height_px"])
    if (
        not analysis["validation"]["ready_to_review"]
        or analysis["state"] != revision["state"]
        or analysis["topology"] != revision["topology"]
    ):
        raise ValueError("Saved topology fails exact re-analysis")
    return (revision, observations, forward @ np.linalg.inv(observation_frame))


def skeleton(revision, observations, region_kinds, settings):
    regions = revision["topology"]["regions"]
    if set(region_kinds) != {r["id"] for r in regions} or any(
        (v not in ("room", "corridor") for v in region_kinds.values())
    ):
        raise ValueError("Explicit room/corridor kind required for every reviewed region")
    if not any((v == "room" for v in region_kinds.values())):
        raise ValueError("At least one room required")
    config = {
        "wall_thickness_cm": 20,
        "wall_height_cm": 300,
        "door_height_cm": 220,
        "floor_thickness_cm": 20,
        "source": "configured",
    }
    if set(settings) - (set(config) - {"source"}):
        raise ValueError("Unknown metric setting")
    config.update(settings)
    if any(
        (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or (not np.isfinite(v))
            or (v <= 0)
            for k, v in config.items()
            if k != "source"
        )
    ):
        raise ValueError("Settings must be finite and positive")
    if config["door_height_cm"] > config["wall_height_cm"]:
        raise ValueError("Door height exceeds wall height")
    rects = {}
    for r in regions:
        if not r["rectangle_candidate"] or r.get("hole_count", 0):
            raise ValueError("Only rectangular reviewed regions supported")
        xmin, ymin, xmax, ymax = r["bounds_px_rotated"]
        rects[r["id"]] = [(xmin, -ymax), (xmax, -ymax), (xmax, -ymin), (xmin, -ymin)]
    all_corners = sorted({p for corners in rects.values() for p in corners})
    layout = {
        k: []
        for k in ("vertices", "walls", "rooms", "corridors", "openings", "passages", "dimensions")
    }
    pixels, vertices, walls = ({}, {}, {})
    used_ids = set(rects) | {o["id"] for o in revision["state"]["openings"]}

    def uid(prefix):
        i = 1
        while f"{prefix}{i:04d}" in used_ids:
            i += 1
        identifier = f"{prefix}{i:04d}"
        used_ids.add(identifier)
        return identifier

    def vertex(point):
        if point not in vertices:
            identifier = uid("mv")
            vertices[point] = identifier
            pixels[identifier] = point
            layout["vertices"].append(
                {
                    "id": identifier,
                    "position_cm": [None, None],
                    "state": "missing",
                    "provenance": provenance("Reviewed topology vertex; centimetres unresolved."),
                }
            )
        return vertices[point]

    for rid, corners in rects.items():
        boundary_v, boundary_w = ([], [])
        for a, b in zip(corners, corners[1:] + corners[:1]):
            axis = 0 if a[1] == b[1] else 1
            points = [
                p
                for p in all_corners
                if abs(p[1 - axis] - a[1 - axis]) < 1e-07
                and min(a[axis], b[axis]) <= p[axis] <= max(a[axis], b[axis])
            ]
            points.sort(key=lambda p: p[axis], reverse=a[axis] > b[axis])
            for p, q in zip(points, points[1:]):
                boundary_v.append(vertex(p))
                start, end = sorted((p, q), key=lambda pt: pt[axis])
                key = (start, end)
                if key not in walls:
                    wid = uid("mw")
                    walls[key] = wid
                    layout["walls"].append(
                        {
                            "id": wid,
                            "start_vertex_id": vertex(start),
                            "end_vertex_id": vertex(end),
                            "axis": "xy"[axis],
                            "thickness_cm": config["wall_thickness_cm"],
                            "height_cm": config["wall_height_cm"],
                            "region_ids": [],
                            "provenance": provenance(
                                "Unique noded reviewed boundary; logical opening interface retained."
                            ),
                        }
                    )
                wid = walls[key]
                boundary_w.append(wid)
                next((w for w in layout["walls"] if w["id"] == wid))["region_ids"].append(rid)
        layout["rooms" if region_kinds[rid] == "room" else "corridors"].append(
            {
                "id": rid,
                "name": rid,
                "boundary_vertex_ids": boundary_v,
                "boundary_wall_ids": boundary_w,
                "role": "none",
                "provenance": provenance(
                    "Explicit semantic kind bound to this review revision.", "user_correction"
                ),
            }
        )
    opening_pixels = {}
    edges = {e["opening_id"]: e for e in revision["topology"]["region_connectivity_graph"]["edges"]}
    for o in revision["state"]["openings"]:
        if o["decision"] == "rejected":
            continue
        if o["decision"] != "approved" or o["kind"] not in ("door", "open_passage"):
            raise ValueError("Unreviewed opening")
        edge = edges[o["id"]]
        owners = edge["adjacent_region_ids"]
        p, q = [(pt[0], -pt[1]) for pt in (o["start"], o["end"])]
        axis = 0 if o["axis"] == "horizontal" else 1
        candidates = []
        for w in layout["walls"]:
            a, b = (pixels[w[k]] for k in ("start_vertex_id", "end_vertex_id"))
            if (
                set(w["region_ids"]) == set(owners)
                and w["axis"] == "xy"[axis]
                and all(
                    (
                        abs(pt[1 - axis] - a[1 - axis]) < 1e-06
                        and a[axis] - 1e-06 <= pt[axis] <= b[axis] + 1e-06
                        for pt in (p, q)
                    )
                )
            ):
                candidates.append(w)
        if len(candidates) != 1:
            raise ValueError(f"{o['id']}: opening crosses/ambiguously matches noded interface")
        entities = [{"type": region_kinds[r], "id": r} for r in owners]
        layout["openings"].append(
            {
                "id": o["id"],
                "wall_id": candidates[0]["id"],
                "type": o["kind"],
                "center_offset_cm": None,
                "clear_width_cm": None,
                "clear_height_cm": config[
                    "door_height_cm" if o["kind"] == "door" else "wall_height_cm"
                ],
                "connected_entities": entities,
                "state": "missing",
                "provenance": provenance("Approved pixel opening; no implicit cm size/alignment."),
            }
        )
        opening_pixels[o["id"]] = sorted((p, q), key=lambda pt: pt[axis])
        layout["passages"].append(
            {
                "id": uid("mp"),
                "opening_id": o["id"],
                "connected_entities": deepcopy(entities),
                "type": o["kind"],
                "provenance": provenance("Passage through reviewed opening."),
            }
        )
    doc = {
        "schema_version": "playablesketch-layout/1.0",
        "kind": "draft_layout",
        "document_id": "metric-" + revision["case_id"],
        "revision_id": "metric-" + revision["revision_id"],
        "parent_revision_id": None,
        "algorithm_version": "metric-solver/1.0",
        "observation_document_id": observations["document_id"],
        "source": deepcopy(observations["source"]),
        "units": "cm",
        "coordinate_system": "local_x_right_y_up_z_up",
        "dimension_basis": "wall_centerline",
        "validation_mode": "geometry_only",
        "start_room_id": None,
        "goal_room_id": None,
        "settings": config,
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
            "Topology approved independently of metric review. Explicit dimensions/relations required."
        ],
    }
    return (doc, {"vertices": pixels, "openings": opening_pixels, "regions": rects})
