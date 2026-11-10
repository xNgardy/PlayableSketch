import numpy as np
from .decoder import authoring_document, boundary_graph
from .room_geometry import rectangular_parts


def tiled_preview(document, positions, settings):
    from .sizing_adapter import canonical_preview

    top = document["topology"]
    source_points = {tuple(j["geometry"]["points_px"][0]): j["id"] for j in top["junctions"]}
    boxes, sources, names, ids, display = [], {}, {}, [], []
    for region in top["regions"]:
        polygon = [
            [positions[source_points[tuple(p)]][0], -positions[source_points[tuple(p)]][1]]
            for p in region["geometry"]["points_px"]
        ]
        display.append(
            {"id": region["id"], "name": region["name"], "points_cm": [[x, -y] for x, y in polygon]}
        )
        parts = rectangular_parts(polygon)
        for i, bounds in enumerate(parts):
            identifier = region["id"] if i == 0 else region["id"] + f"_part_{i + 1}"
            boxes.append({"type": "room", "bounds_px": bounds})
            ids.append(identifier)
            sources[identifier] = region["id"]
            names[identifier] = region["name"]
    segments, _ = boundary_graph(boxes)
    openings = []
    values = {
        (v["entity_id"], v["parameter"]): v["value"] for v in document["physical_design"]["values"]
    }
    walls = {w["id"]: w for w in top["walls"]}
    original_openings = {}
    for opening in top["openings"]:
        wall = walls[opening["support_wall_id"]]
        ref = opening["placement"]["reference_junction_id"]
        other = (
            wall["end_junction_id"]
            if ref == wall["start_junction_id"]
            else wall["start_junction_id"]
        )
        a, b = np.asarray(positions[ref], float), np.asarray(positions[other], float)
        direction = (b - a) / np.linalg.norm(b - a)
        near = values[opening["id"], "near_edge_offset_cm"]
        width = values[opening["id"], "clear_width_cm"]
        p, q = a + direction * near, a + direction * (near + width)
        p[1], q[1] = -p[1], -q[1]
        axis = int(abs(q[1] - p[1]) > abs(q[0] - p[0]))
        p, q = sorted([p, q], key=lambda v: v[axis])
        match = None
        for segment, owners in segments.items():
            if len(owners) != 2 or {sources[ids[i]] for i in owners} != set(opening["entity_ids"]):
                continue
            if all(
                abs(v[1 - axis] - segment[0][1 - axis]) < 1e-5
                and segment[0][axis] - 1e-5 <= v[axis] <= segment[1][axis] + 1e-5
                for v in (p, q)
            ):
                match = segment, owners
                break
        if match is None:
            raise ValueError(
                "A door crosses a floor partition. Move it onto one continuous boundary: "
                + opening["id"]
            )
        segment, owners = match
        index = len(openings)
        openings.append(
            {
                "segment": segment,
                "entity_indices": owners,
                "start": p.tolist(),
                "end": q.tolist(),
                "type": opening["type"],
            }
        )
        original_openings[index] = opening["id"]
    for segment, owners in segments.items():
        if len(owners) != 2 or sources[ids[owners[0]]] != sources[ids[owners[1]]]:
            continue
        a, b = np.asarray(segment[0], float), np.asarray(segment[1], float)
        length = np.linalg.norm(b - a)
        half = settings["wall_thickness_cm"] / 2
        if length <= 2 * half:
            raise ValueError("A room bend is too narrow for the configured wall thickness.")
        direction = (b - a) / length
        openings.append(
            {
                "segment": segment,
                "entity_indices": owners,
                "start": (a + direction * half).tolist(),
                "end": (b - direction * half).tolist(),
                "type": "open_passage",
            }
        )
    fake = authoring_document(
        document["image_evidence"]["source"], document["image_evidence"], boxes, openings
    )
    remap = {r["id"]: identifier for r, identifier in zip(fake["topology"]["regions"], ids)}
    for region in fake["topology"]["regions"]:
        region["id"] = remap[region["id"]]
        region["name"] = names[region["id"]]
    for collection in ("walls", "openings", "connections"):
        for entity in fake["topology"][collection]:
            entity["entity_ids"] = [remap[r] for r in entity["entity_ids"]]
    fake["physical_design"]["values"] = []
    display_openings = []
    for i, (opening, proposal) in enumerate(zip(fake["topology"]["openings"], openings)):
        old_id = opening["id"]
        identifier = original_openings.get(i, "floor_join_" + str(i + 1))
        opening["id"] = identifier
        for connection in fake["topology"]["connections"]:
            connection["opening_ids"] = [
                identifier if oid == old_id else oid for oid in connection["opening_ids"]
            ]
        axis = 0 if proposal["segment"][0][1] == proposal["segment"][1][1] else 1
        near = proposal["start"][axis] - proposal["segment"][0][axis]
        width = proposal["end"][axis] - proposal["start"][axis]
        if abs(near) < 1e-5:
            near = 0.0
        for parameter, value in {
            "near_edge_offset_cm": near,
            "clear_width_cm": width,
            "height_cm": (
                settings["door_height_cm"]
                if opening["type"] == "door"
                else settings["wall_height_cm"]
            ),
        }.items():
            fake["physical_design"]["values"].append(
                {"entity_id": identifier, "parameter": parameter, "value": value}
            )
        if i in original_openings:
            display_openings.append(
                {
                    "id": identifier,
                    "type": opening["type"],
                    "points_cm": [[p[0], -p[1]] for p in [proposal["start"], proposal["end"]]],
                }
            )
    fake["document_id"] = document["document_id"]
    fake["revision_id"] = document["revision_id"]
    fake["parent_revision_id"] = document["parent_revision_id"]
    coords = {j["id"]: j["geometry"]["points_px"][0] for j in fake["topology"]["junctions"]}
    indices = [{identifier: i * 2 + axis for i, identifier in enumerate(coords)} for axis in (0, 1)]
    solution = np.asarray([v for p in coords.values() for v in p])
    preview = canonical_preview(fake, coords, indices, solution, {}, settings)
    preview.update(
        display_regions=display, display_openings=display_openings, region_sources=sources
    )
    preview["canonical"]["notes"].append(
        "Nonrectangular rooms are exported as adjoining rectangular floor parts with full-width internal passages. Authoring retains each original room polygon."
    )
    return preview
