import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from jsonschema import Draft202012Validator
from SketchPipeline.validation.validate import SCHEMAS, validate_document
from SketchPipeline.synthetic.augment import parameters, augment_pixels, transfer, pixel_points
from SketchPipeline.shape_authoring.synthetic import render, CHANNELS
from SketchPipeline.shape_authoring.decoder import boundary_graph
from .manual_traces import SAMPLES

ROOT = Path(__file__).resolve().parents[3]
ANN = ROOT / "Data/annotations/v1"
OUT = ROOT / "Data/synthetic/corridor_addon_v1"
REVIEW = ROOT / "Saved/DataPreparation/new20_v1"
TRUTH = ROOT / "Data/ground_truth/structural_v1"
SEED = 5112026


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def relative(path, base):
    return os.path.relpath(path, base)


def lineparts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [list(geometry.coords)]
    return [p for child in getattr(geometry, "geoms", []) for p in lineparts(child)]


def labels_from_geometry(
    identifier, image, regions, links, ticks, method, notes, annotation_folder, reference_path
):
    width, height = Image.open(image).size
    polys = [Polygon(p) for _, p in regions]
    assert all((p.is_valid and p.area > 0 for p in polys)), identifier
    assert all(
        (p.intersection(q).area < 0.001 for i, p in enumerate(polys) for q in polys[:i])
    ), identifier
    lines = []
    strokes = []
    gaps = []
    owners = []

    def stroke(kind, points):
        ids = []
        for a, b in zip(points, points[1:]):
            if np.linalg.norm(np.asarray(a) - b) < 0.5:
                continue
            lid = f"l{len(lines) + 1:04}"
            ids.append(lid)
            lines.append(
                {
                    "id": lid,
                    "start_px": list(map(float, a)),
                    "end_px": list(map(float, b)),
                    "score": None,
                }
            )
        if ids:
            strokes.append({"id": f"s{len(strokes) + 1:04}", "kind": kind, "line_ids": ids})

    for a, b, span, gap, kind in links:
        rail = LineString(span)
        assert all((rail.difference(polys[i].boundary.buffer(1.6)).length < 3 for i in (a, b))), (
            identifier,
            "interface",
            a,
            b,
        )
        interval = [list(rail.interpolate(rail.project(Point(p))).coords[0]) for p in gap]
        gid = f"g{len(gaps) + 1:03}"
        gaps.append(
            {
                "id": gid,
                "kind": kind,
                "start_px": interval[0],
                "end_px": interval[1],
                "opening_candidate_id": None,
                "semantic_provenance": (
                    "Visual interpretation of photographed ink; approximate pixel endpoints."
                    if method == "manual_visual_trace"
                    else "Explicit procedural geometry; same source used for pixels and labels."
                ),
            }
        )
        owners.append(
            {
                "id": gid,
                "entity_ids": [f"r{a + 1:02}", f"r{b + 1:02}"],
                "kind": kind,
                "start_px": interval[0],
                "end_px": interval[1],
            }
        )
    linework = unary_union([p.boundary for p in polys])
    if gaps:
        cuts = unary_union([LineString([g["start_px"], g["end_px"]]) for g in gaps]).buffer(0.8)
        linework = linework.difference(cuts)
    for points in lineparts(linework):
        stroke("wall", points)
    for points in ticks:
        stroke("tick", points)
    corners = {}
    neighbors = defaultdict(set)
    for _, polygon in regions:
        for j, p in enumerate(polygon):
            key = tuple(p)
            prev = np.array(polygon[j - 1])
            nxt = np.array(polygon[(j + 1) % len(polygon)])
            u = prev - p
            v = nxt - p
            cos = np.dot(u, v) / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-09)
            if cos > -0.9:
                corners[key] = "corner"
            neighbors[key].update([tuple(prev), tuple(nxt)])
    for a, b, span, gap, kind in links:
        for p in span:
            corners[tuple(p)] = "tee"
    junctions = [
        {
            "id": f"j{i + 1:03}",
            "point_px": list(p),
            "kind": kind,
            "status": "approximate_intended_junction",
        }
        for i, (p, kind) in enumerate(sorted(corners.items()))
    ]
    obs = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": identifier + "_observations",
        "revision_id": "structural-labels-1",
        "source": {
            "image_path": relative(image, annotation_folder),
            "image_sha256": sha(image),
            "legacy_draft_path": None,
        },
        "units": "px",
        "coordinate_system": "u_right_v_down",
        "frame": {
            "id": "original",
            "width_px": width,
            "height_px": height,
            "original_to_frame": np.eye(3).tolist(),
        },
        "region_annotation_status": "complete",
        "texts": [],
        "lines": lines,
        "opening_candidates": [],
        "issues": [],
        "notes": [
            "Structural geometry only; physical dimensions absent, no metric/playability approval."
        ]
        + list(notes),
    }
    annotation = {
        "schema_version": "playablesketch-pixel-annotations/1.0",
        "observations_path": identifier + ".observations.json",
        "reference_draft_path": relative(reference_path, annotation_folder),
        "coordinate_frame": "original",
        "method": method,
        "precision": (
            "Approximate actual-image visual traces; uncertain boundary pixels remain unlabelled in weak supervision. Not dense human ground truth."
            if method == "manual_visual_trace"
            else "Procedural intended geometry; original renderer masks provide dense structural supervision."
        ),
        "strokes": strokes,
        "junctions": junctions,
        "gaps": gaps,
        "associations": [],
        "issues": (
            ["NO_PHYSICAL_DIMENSIONS", "APPROXIMATE_VISUAL_GEOMETRY"]
            if method == "manual_visual_trace"
            else ["NO_PHYSICAL_DIMENSIONS", "SYNTHETIC_GENERATED"]
        ),
        "regions": [
            {
                "region_id": f"r{i + 1:02}",
                "kind": kind,
                "polygon_px": p,
                "status": (
                    "manual_intended_boundary"
                    if method == "manual_visual_trace"
                    else "generated_intended_boundary"
                ),
            }
            for i, (kind, p) in enumerate(regions)
        ],
    }
    reference = {
        "schema_version": "playablesketch-structural-reference/1.0",
        "kind": "structural_reference",
        "image_sha256": sha(image),
        "coordinate_frame": "original",
        "regions": annotation["regions"],
        "openings": owners,
        "physical_dimensions_known": False,
        "metric_validated": False,
        "approximate": method == "manual_visual_trace",
        "notes": list(notes),
    }
    return (obs, annotation, reference)


def validate_pair(obs, annotation):
    assert not validate_document(obs)["issues"]
    Draft202012Validator(SCHEMAS["urn:playablesketch:pixel-annotations:1"]).validate(annotation)
    width, height = (obs["frame"]["width_px"], obs["frame"]["height_px"])
    for document in (obs, annotation):
        assert all((0 <= x < width and 0 <= y < height for x, y in pixel_points(document)))
    line_ids = {l["id"] for l in obs["lines"]}
    assert all((set(s["line_ids"]) <= line_ids for s in annotation["strokes"]))


def original_labels():
    plans = json.loads((ROOT / "Docs/drawing_pack_20/plan_manifest.json").read_text())["plans"]
    entries = []
    for n, s in SAMPLES.items():
        image = ROOT / f"Data/Data_{n}.png"
        original = ImageOps.exif_transpose(Image.open(image))
        thumb = original.copy()
        thumb.thumbnail((675, 740))
        index = (n - 51) % 4
        ox = 12 + index % 2 * 700
        oy = 40 + index // 2 * 800
        sx, sy = (original.width / thumb.width, original.height / thumb.height)

        def native(p):
            return [round((p[0] - ox) * sx, 5), round((p[1] - oy) * sy, 5)]

        regions = [(kind, [native(p) for p in polygon]) for kind, polygon in s["regions"]]
        links = [
            (a, b, [native(p) for p in span], [native(p) for p in gap], kind)
            for a, b, span, gap, kind in s["links"]
        ]
        ticks = [[native(p) for p in points] for points in s["ticks"]]
        identifier = f"Data_{n}"
        refpath = TRUTH / (identifier + ".structural.json")
        obs, ann, reference = labels_from_geometry(
            identifier,
            image,
            regions,
            links,
            ticks,
            "manual_visual_trace",
            s["notes"],
            ANN,
            refpath,
        )
        validate_pair(obs, ann)
        for suffix, doc in [("observations", obs), ("annotations", ann)]:
            write(ANN / (identifier + "." + suffix + ".json"), doc)
        write(refpath, reference)
        entry = {
            "id": identifier,
            "origin": "human",
            "image_path": relative(image, OUT),
            "image_sha256": sha(image),
            "base_plan_id": f"new20_P{n - 50:02}",
            "writer_id": "new20_same_user",
            "split": plans[n - 51]["split"],
            "annotations_path": relative(ANN / (identifier + ".annotations.json"), OUT),
            "observations_path": relative(ANN / (identifier + ".observations.json"), OUT),
            "structural_reference_path": relative(refpath, OUT),
            "label_quality": "approximate_manual_visual_trace",
            "training_eligible": plans[n - 51]["split"] == "train",
            "counts": {
                "rooms": sum((k == "room" for k, _ in regions)),
                "corridor_segments": sum((k == "corridor" for k, _ in regions)),
                "doors": sum((g["kind"] == "door" for g in ann["gaps"])),
                "open_passages": sum((g["kind"] == "open_passage" for g in ann["gaps"])),
            },
        }
        entries.append(entry)
        preview(image, ann, REVIEW / "review" / (identifier + ".png"))
    write(
        ANN / "manifest_structural_51_70.json",
        {
            "schema_version": "playablesketch-dataset/1.0",
            "base_path": str(OUT.relative_to(ROOT)),
            "split_policy": "Preassigned drawing-pack groups; retrospective same-writer development holdout, not blind or unseen-writer.",
            "samples": entries,
        },
    )
    return entries


def preview(image, annotation, path):
    im = Image.open(image).convert("RGB")
    draw = ImageDraw.Draw(im, "RGBA")
    for r in annotation["regions"]:
        color = (0, 145, 215, 35) if r["kind"] == "room" else (235, 136, 0, 55)
        p = [tuple(v) for v in r["polygon_px"]]
        draw.polygon(p, fill=color)
        draw.line(p + [p[0]], fill=color[:3] + (200,), width=max(2, im.width // 400))
        draw.text(p[0], r["region_id"], fill=(0, 60, 130, 255))
    for g in annotation["gaps"]:
        p = [tuple(g["start_px"]), tuple(g["end_px"])]
        draw.line(
            p,
            fill=(220, 0, 120, 255) if g["kind"] == "door" else (0, 170, 70, 255),
            width=max(4, im.width // 250),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    im.thumbnail((900, 900))
    im.save(path)


def human_derivatives(originals):
    entries = []
    for parent in originals:
        if parent["split"] != "train":
            continue
        image = OUT / parent["image_path"]
        pixels = np.array(Image.open(image).convert("RGB"))
        h, w = pixels.shape[:2]
        obs = json.loads((OUT / parent["observations_path"]).read_text())
        ann = json.loads((OUT / parent["annotations_path"]).read_text())
        reference = json.loads((OUT / parent["structural_reference_path"]).read_text())
        for profile in ["rotate", "perspective", "lighting", "capture", "combined"]:
            matrix, settings = parameters(parent["id"] + "-corridor-addon-v1", profile, w, h)
            identifier = parent["id"] + "_" + profile
            dest = OUT / "images" / (identifier + ".png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(augment_pixels(pixels, matrix, settings)).save(dest)
            moved_obs, moved_ann, moved_ref = [transfer(d, matrix) for d in (obs, ann, reference)]
            folder = OUT / "annotations"
            refpath = OUT / "references" / (identifier + ".structural.json")
            moved_obs.update(document_id=identifier + "_observations", revision_id="augmentation-1")
            moved_obs["source"].update(image_path=relative(dest, folder), image_sha256=sha(dest))
            moved_obs["frame"]["original_to_frame"] = np.eye(3).tolist()
            moved_ann.update(
                method="augmentation_transfer",
                observations_path=identifier + ".observations.json",
                reference_draft_path=relative(refpath, folder),
            )
            for r in moved_ann["regions"]:
                r["status"] = "augmentation_transferred_boundary"
            moved_ref["image_sha256"] = sha(dest)
            moved_ref["approximate"] = True
            validate_pair(moved_obs, moved_ann)
            for old, new in zip(
                pixel_points(ann), pixel_points(transfer(moved_ann, np.linalg.inv(matrix)))
            ):
                assert np.allclose(old, new, atol=0.0002)
            for suffix, doc in [("observations", moved_obs), ("annotations", moved_ann)]:
                write(folder / (identifier + "." + suffix + ".json"), doc)
            write(refpath, moved_ref)
            write(
                OUT / "transforms" / (identifier + ".json"),
                {
                    "parent": parent["id"],
                    "matrix": matrix.tolist(),
                    "inverse": np.linalg.inv(matrix).tolist(),
                    "settings": settings,
                    "labels_transformed_with_image": True,
                },
            )
            entries.append(
                {
                    "id": identifier,
                    "origin": "human_derivative",
                    "base_plan_id": parent["base_plan_id"],
                    "parent_id": parent["id"],
                    "writer_id": parent["writer_id"],
                    "split": "train",
                    "training_eligible": True,
                    "image_path": relative(dest, OUT),
                    "image_sha256": sha(dest),
                    "annotations_path": relative(folder / (identifier + ".annotations.json"), OUT),
                    "observations_path": relative(
                        folder / (identifier + ".observations.json"), OUT
                    ),
                    "structural_reference_path": relative(refpath, OUT),
                    "label_quality": "transferred_approximate_manual_trace",
                }
            )
    return entries


def spec_from_rectangles(identifier, rooms, corridors, seed, closed=()):
    boxes = [
        {"type": "room" if i < len(rooms) else "corridor_segment", "bounds_px": list(b)}
        for i, b in enumerate(rooms + corridors)
    ]
    for i, a in enumerate(boxes):
        for b in boxes[:i]:
            assert (
                Polygon(rect(a["bounds_px"])).intersection(Polygon(rect(b["bounds_px"]))).area
                < 1e-06
            )
    rng = np.random.default_rng(seed)
    openings = []
    closed = {tuple(sorted(p)) for p in closed}
    for segment, owners in boundary_graph(boxes)[0].items():
        if len(owners) != 2 or tuple(sorted(owners)) in closed:
            continue
        axis = 0 if segment[0][1] == segment[1][1] else 1
        normal = 1 - axis
        lo, hi = sorted([p[axis] for p in segment])
        fixed = segment[0][normal]
        if hi - lo < 4:
            continue
        has_room = any((boxes[i]["type"] == "room" for i in owners))
        kind = "door" if has_room and rng.random() < 0.72 else "open_passage"
        gap = [lo + (hi - lo) * 0.26, hi - (hi - lo) * 0.26] if kind == "door" else [lo, hi]
        openings.append(
            {
                "id": f"o{len(openings) + 1:03}",
                "entity_ids": [f"r{i + 1:02}" for i in owners],
                "axis": axis,
                "fixed": fixed,
                "interval": gap,
                "type": kind,
            }
        )
    return {
        "id": identifier,
        "seed": seed,
        "regions": [
            {"id": f"r{i + 1:02}", "type": b["type"], "bounds_px": b["bounds_px"]}
            for i, b in enumerate(boxes)
        ],
        "openings": openings,
    }


def rect(b):
    x, y, X, Y = b
    return [[x, y], [X, y], [X, Y], [x, Y]]


def fit_rectangles(rooms, corridors, seed):
    rng = np.random.default_rng(seed)
    stretch = rng.uniform(0.87, 1.13, 2)
    all_boxes = np.asarray(rooms + corridors, float).reshape(-1, 2, 2) * stretch
    if seed % 2:
        all_boxes[:, :, 0] = -all_boxes[:, :, 0]
    if seed % 3 == 0:
        all_boxes = all_boxes[:, :, ::-1]
    lo = all_boxes.min((0, 1))
    hi = all_boxes.max((0, 1))
    scale = 216 / max(hi - lo)
    all_boxes = (all_boxes - lo) * scale + 20
    fitted = [np.r_[b.min(0), b.max(0)].round(6).tolist() for b in all_boxes]
    return (fitted[: len(rooms)], fitted[len(rooms) :])


def complex_specs():
    families = [
        (
            [(20, 20, 140, 120), (330, 300, 450, 420), (330, 20, 450, 120)],
            [(60, 120, 90, 260), (90, 230, 330, 260), (330, 120, 360, 230), (330, 230, 360, 300)],
        ),
        (
            [(20, 20, 120, 120), (300, 20, 420, 120), (200, 350, 300, 450), (10, 170, 60, 230)],
            [(60, 120, 90, 280), (90, 250, 330, 280), (330, 120, 360, 280), (220, 280, 245, 350)],
        ),
        (
            [(20, 20, 120, 120), (200, 20, 300, 120), (200, 250, 300, 350), (360, 250, 460, 350)],
            [
                (120, 60, 200, 90),
                (230, 120, 260, 250),
                (300, 290, 360, 320),
                (60, 120, 90, 200),
                (90, 170, 160, 200),
            ],
        ),
        (
            [(180, 20, 280, 100), (180, 300, 280, 400), (20, 170, 90, 260), (350, 180, 460, 260)],
            [(90, 100, 120, 300), (120, 100, 320, 130), (120, 270, 320, 300), (320, 100, 350, 300)],
        ),
    ]
    for i in range(20):
        seed = SEED + 100 + i
        rooms, corridors = families[i % 4]
        rooms, corridors = fit_rectangles(rooms, corridors, seed)
        closed = [(0, len(rooms))] if i in (0, 8, 16) else []
        yield (
            spec_from_rectangles(f"CX{i + 1:03}", rooms, corridors, seed, closed),
            f"complex_family_{i % 4}",
        )


def procedural_entry(spec, parent, family):
    identifier = spec["id"]
    image = OUT / "images" / (identifier + ".png")
    image.parent.mkdir(parents=True, exist_ok=True)
    gray, masks, rendered = render(spec["seed"], "wavy", 512, specification=spec)
    Image.fromarray(gray).save(image)
    regions = [
        (
            "room" if r["type"] == "room" else "corridor",
            [[v * 2 for v in p] for p in rect(r["bounds_px"])],
        )
        for r in spec["regions"]
    ]
    indices = {r["id"]: i for i, r in enumerate(spec["regions"])}
    links = []
    ticks = []
    segments = boundary_graph(
        [{"type": r["type"], "bounds_px": r["bounds_px"]} for r in spec["regions"]]
    )[0]
    for o in spec["openings"]:
        a, b = [indices[v] for v in o["entity_ids"]]
        axis = o["axis"]
        normal = 1 - axis
        full = next(
            (
                segment
                for segment, owners in segments.items()
                if set(owners) == {a, b}
                and segment[0][normal] == o["fixed"]
                and (min((p[axis] for p in segment)) <= o["interval"][0])
                and (max((p[axis] for p in segment)) >= o["interval"][1])
            )
        )
        gap = [[t, o["fixed"]] if axis == 0 else [o["fixed"], t] for t in o["interval"]]
        links.append(
            (a, b, [[v * 2 for v in p] for p in full], [[v * 2 for v in p] for p in gap], o["type"])
        )
        if o["type"] == "door":
            for p in gap:
                start = np.array(p) * 2
                end = start.copy()
                start[normal] -= 12
                end[normal] += 12
                ticks.append([start.tolist(), end.tolist()])
    folder = OUT / "annotations"
    refpath = OUT / "references" / (identifier + ".structural.json")
    obs, ann, reference = labels_from_geometry(
        identifier,
        image,
        regions,
        links,
        ticks,
        "synthetic_render",
        [
            "Procedural structural render, not a real human writer. Dense masks follow rendered wall/tick strokes."
        ],
        folder,
        refpath,
    )
    validate_pair(obs, ann)
    for suffix, doc in [("observations", obs), ("annotations", ann)]:
        write(folder / (identifier + "." + suffix + ".json"), doc)
    write(refpath, reference)
    write(OUT / "specifications" / (identifier + ".json"), spec)
    targets = np.zeros((8, 512, 512), np.uint8)
    targets[:6] = (masks > 0).astype(np.uint8)
    for r in spec["regions"]:
        polygon = np.rint(np.asarray(rect(r["bounds_px"])) * 2).astype(np.int32)
        cv2.polylines(targets[7], [polygon], True, 1, 6)
    for o in spec["openings"]:
        if o["type"] != "door":
            continue
        for t in o["interval"]:
            p = [t, o["fixed"]] if o["axis"] == 0 else [o["fixed"], t]
            cv2.circle(targets[6], tuple(np.rint(np.array(p) * 2).astype(int)), 6, 1, -1)
    maskpath = OUT / "targets" / (identifier + ".npz")
    maskpath.parent.mkdir(exist_ok=True)
    np.savez_compressed(maskpath, target=targets, known=np.ones_like(targets, np.uint8))
    preview(image, ann, REVIEW / "synthetic_review" / (identifier + ".png"))
    return {
        "id": identifier,
        "origin": "guide_render" if identifier.startswith("GP") else "procedural_complex",
        "base_plan_id": parent,
        "geometry_family": family,
        "writer_id": None,
        "split": "train",
        "training_eligible": True,
        "image_path": relative(image, OUT),
        "image_sha256": sha(image),
        "annotations_path": relative(folder / (identifier + ".annotations.json"), OUT),
        "observations_path": relative(folder / (identifier + ".observations.json"), OUT),
        "structural_reference_path": relative(refpath, OUT),
        "targets_path": relative(maskpath, OUT),
        "label_quality": "renderer_dense_structural_targets",
    }


def guide_interfaces(p):
    contacts = []
    for i, a in enumerate(p["rooms"]):
        for j, b in enumerate(p["corridors"]):
            for normal in (0, 1):
                along = 1 - normal
                for first, second in ((a[normal + 2], b[normal]), (a[normal], b[normal + 2])):
                    lo = max(a[along], b[along])
                    hi = min(a[along + 2], b[along + 2])
                    if first == second and hi > lo:
                        contacts.append((i, len(p["rooms"]) + j))
    return contacts


def procedures():
    entries = []
    plans = json.loads((ROOT / "Docs/drawing_pack_20/plan_manifest.json").read_text())["plans"]
    for i, p in enumerate(plans):
        if p["split"] != "train":
            continue
        rooms, corridors = fit_rectangles(p["rooms"], p["corridors"], SEED + i)
        closed = [(1, 2)] if p["id"] == "P17" else []
        spec = spec_from_rectangles("GP" + p["id"][1:], rooms, corridors, SEED + i, closed)
        contacts = guide_interfaces(p)
        door_pairs = {frozenset(contacts[k]) for k in p["doors"]}
        boxes = [{"type": r["type"], "bounds_px": r["bounds_px"]} for r in spec["regions"]]
        segments = boundary_graph(boxes)[0]
        for o in spec["openings"]:
            owner_ids = {int(v[1:]) - 1 for v in o["entity_ids"]}
            kind = "door" if frozenset(owner_ids) in door_pairs else "open_passage"
            full = next(
                (
                    seg
                    for seg, owners in segments.items()
                    if set(owners) == owner_ids and seg[0][1 - o["axis"]] == o["fixed"]
                )
            )
            lo, hi = sorted((p[o["axis"]] for p in full))
            o.update(
                type=kind,
                interval=(
                    [lo + (hi - lo) * 0.25, hi - (hi - lo) * 0.25] if kind == "door" else [lo, hi]
                ),
            )
        entries.append(procedural_entry(spec, "new20_" + p["id"], "drawing_guide_" + p["id"]))
    for spec, family in complex_specs():
        entries.append(procedural_entry(spec, "procedural_" + spec["id"], family))
    return entries


def prepare_weak_targets(entries):
    from SketchPipeline.shape_authoring.human_supervision import weak_targets
    from SketchPipeline.shape_authoring.dino_experiment import auxiliary_targets

    statistics = []
    for entry in entries:
        if entry["origin"] not in ("human", "human_derivative"):
            continue
        image = Image.open(OUT / entry["image_path"]).convert("L")
        gray = np.asarray(image)
        h, w = gray.shape
        scale = 480 / max(w, h)
        matrix = np.array(
            [[scale, 0, (512 - w * scale) / 2], [0, scale, (512 - h * scale) / 2], [0, 0, 1.0]]
        )
        native = cv2.warpPerspective(gray, matrix, (512, 512), borderValue=255)
        obs = json.loads((OUT / entry["observations_path"]).read_text())
        ann = json.loads((OUT / entry["annotations_path"]).read_text())
        labels = {
            "regions": ann["regions"],
            "strokes": ann["strokes"],
            "lines": {l["id"]: l for l in obs["lines"]},
            "junctions": ann["junctions"],
            "gaps": ann["gaps"],
            "distractor_polygons": [],
        }
        metadata = {
            "original_to_working": matrix.tolist(),
            "working_to_original": np.linalg.inv(matrix).tolist(),
            "working_size_px": [512, 512],
        }
        target, known, stats = weak_targets(native, metadata, labels)
        target, known = auxiliary_targets(native, metadata, labels, target, known)
        assert target.shape == known.shape == (8, 512, 512)
        for channel, kind in [(1, "room"), (2, "corridor")]:
            if any((r["kind"] == kind for r in ann["regions"])):
                assert ((target[channel] > 0) & (known[channel] > 0)).any(), entry["id"]
        entry["targets_path"] = "targets/" + entry["id"] + ".npz"
        dest = OUT / entry["targets_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dest, target=target.astype(np.uint8), known=known.astype(np.float16))
        entry["input_512_path"] = "inputs/" + entry["id"] + ".png"
        p = OUT / entry["input_512_path"]
        p.parent.mkdir(exist_ok=True)
        Image.fromarray(native).save(p)
        entry["target_preprocessing_path"] = "transforms/" + entry["id"] + "-target-frame.json"
        write(OUT / entry["target_preprocessing_path"], metadata)
        statistics.append(
            {
                "id": entry["id"],
                "split": entry["split"],
                **stats,
                "door_endpoint_positive_pixels": int(target[6].sum()),
                "known_fraction_8_channels": float((known > 0).mean()),
            }
        )
    write(
        OUT / "weak_supervision_audit.json",
        {"samples": statistics, "human_dense_ground_truth": False, "model_inference_run": False},
    )


def audit(entries, protected):
    parent_roles = defaultdict(set)
    hash_roles = defaultdict(set)
    for entry in entries:
        parent_roles[entry["base_plan_id"]].add(entry["split"])
        hash_roles[entry["image_sha256"]].add(entry["split"])
        assert sha(OUT / entry["image_path"]) == entry["image_sha256"]
        obs = json.loads((OUT / entry["observations_path"]).read_text())
        ann = json.loads((OUT / entry["annotations_path"]).read_text())
        validate_pair(obs, ann)
        assert (OUT / entry["observations_path"]).parent.joinpath(
            obs["source"]["image_path"]
        ).resolve() == (OUT / entry["image_path"]).resolve()
        assert (
            (OUT / entry["annotations_path"]).parent.joinpath(ann["reference_draft_path"]).exists()
        )
        assert entry["training_eligible"] == (entry["split"] == "train")
        if entry["origin"] in ("human_derivative", "guide_render"):
            assert entry["split"] == "train"
        with np.load(OUT / entry["targets_path"]) as z:
            assert z["target"].shape == z["known"].shape == (8, 512, 512)
            assert np.isfinite(z["known"]).all() and np.isfinite(z["target"]).all()
            assert np.all((z["target"] == 0) | (z["target"] == 1))
    assert all((len(v) == 1 for v in list(parent_roles.values()) + list(hash_roles.values())))
    assert all((sha(ROOT / p) == digest for p, digest in protected.items()))
    return {
        "schema_valid_samples": len(entries),
        "sample_counts_by_origin": dict(Counter((e["origin"] for e in entries))),
        "sample_counts_by_split": dict(Counter((e["split"] for e in entries))),
        "parent_groups": len(parent_roles),
        "cross_split_parent_or_hash_leakage": False,
        "all_original_images_and_old_annotations_unchanged": True,
        "checkpoint_unchanged": True,
        "training_run": False,
        "model_inference_run": False,
        "scope": "Visually curated same-writer development holdout. Augmentations do not create independent writers or new blind test data.",
    }


def gallery(entries):
    parts = []
    for entry in entries:
        preview_path = (
            REVIEW
            / ("review" if entry["origin"] == "human" else "synthetic_review")
            / (entry["id"] + ".png")
        )
        if not preview_path.exists():
            continue
        parts.append(
            f"""<figure><figcaption>{entry['id']} / {entry['origin']} / {entry['split']}</figcaption><img src="{relative(preview_path, REVIEW)}"></figure>"""
        )
    (REVIEW / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>New20 annotation review</title><style>body{font:14px system-ui;margin:24px}figure{display:inline-block;width:30%;vertical-align:top;border:1px solid #ddd;padding:8px}img{width:100%}</style><h1>Actual-image structural labels and new procedural samples</h1><p>Blue: rooms; orange: corridor segments; pink: doors; green: open passages. Approximate human boundaries, not dense ground truth. Physical scale unknown.</p>'
        + "".join(parts)
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only audit of prepared images, labels, splits and targets",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Explicitly regenerate this add-on from reviewed source traces",
    )
    args = parser.parse_args()
    if args.check:
        entries = json.loads((OUT / "manifest.json").read_text())["samples"]
        protected = json.loads((REVIEW / "source_freeze.json").read_text())["protected_files"]
        print(json.dumps(audit(entries, protected)))
        return
    if (OUT / "manifest.json").exists() and (not args.rebuild):
        raise FileExistsError(
            "Add-on already prepared. Use --check, or --rebuild to regenerate derived artifacts."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    freeze_path = REVIEW / "source_freeze.json"
    if freeze_path.exists():
        protected = json.loads(freeze_path.read_text())["protected_files"]
    else:
        paths = (
            list((ROOT / "Data/annotations/v1").glob("*"))
            + list((ROOT / "Data").glob("Data_*.*"))
            + [
                ROOT / "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt",
                ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json",
            ]
        )
        protected = {str(p.relative_to(ROOT)): sha(p) for p in paths if p.is_file()}
        write(
            freeze_path,
            {
                "protected_files": protected,
                "training_run": False,
                "seed": SEED,
                "notes": "Frozen before writing new labels; historical datasets and live checkpoint remain unchanged.",
            },
        )
    originals = original_labels()
    print("original labels", len(originals), flush=True)
    derivatives = human_derivatives(originals)
    print("human derivatives", len(derivatives), flush=True)
    generated = procedures()
    print("procedural samples", len(generated), flush=True)
    entries = originals + derivatives + generated
    prepare_weak_targets(entries)
    report = audit(entries, protected)
    write(OUT / "audit.json", report)
    protocol = {
        "version": "corridor-data-addon/1.0",
        "seed": SEED,
        "training_run": False,
        "model_selection_run": False,
        "channels": CHANNELS + ["door_endpoint", "logical_boundary"],
        "counts": report["sample_counts_by_origin"],
        "split_counts": report["sample_counts_by_split"],
        "mixing_plan": {
            "historical_parent_probability": 0.75,
            "new_human_parent_probability": 0.2,
            "new_procedural_family_probability": 0.05,
            "sampling_unit": "Uniform parent first, then one original/derivative view; views never increase parent weight.",
            "new_human_parent_pool_origins": ["human", "human_derivative", "guide_render"],
            "new_procedural_family_pool_origins": ["procedural_complex"],
            "apply_to": "Future training only; no existing training protocol or active model modified.",
        },
        "holdout_policy": "Guide renders and all augmented photos inherit original split. No validation/test derivatives generated. Same-user development comparison, not writer holdout.",
        "annotation_precision": "Human and photo derivatives use masked weak supervision with uncertainty. Procedural samples use dense renderer targets. No physical dimensions invented.",
        "samples": entries,
    }
    write(OUT / "manifest.json", protocol)
    gallery(entries)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
