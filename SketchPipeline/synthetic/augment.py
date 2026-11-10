import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw
from jsonschema import Draft202012Validator
from SketchPipeline.validation.validate import SCHEMAS, validate_document

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "Data/augmented/v1"
SOURCE_MANIFESTS = [
    ROOT / "Data/annotations/v1/manifest_all_50.json",
    ROOT / "Data/synthetic/v1/handdrawn_pilot/manifest.json",
    ROOT / "Data/synthetic/v1/extra_plans/manifest.json",
]
PROFILES = ("rotate", "perspective", "lighting", "capture", "combined")
POINT_FIELDS = {"point_px", "start_px", "end_px", "span_start_px", "span_end_px"}
POLYGON_FIELDS = {"polygon_px"}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path, base):
    return Path(os.path.relpath(path, base)).as_posix()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def project(points, matrix):
    homogeneous = np.c_[np.asarray(points, dtype=float), np.ones(len(points))]
    mapped = homogeneous @ np.asarray(matrix).T
    require(np.all(mapped[:, 2] > 0), "Invalid projective denominator")
    return (mapped[:, :2] / mapped[:, 2:]).round(7).tolist()


def transfer(document, matrix):
    if isinstance(document, list):
        return [transfer(item, matrix) for item in document]
    if not isinstance(document, dict):
        return document
    result = {}
    for key, value in document.items():
        if key in POINT_FIELDS and value is not None:
            result[key] = project([value], matrix)[0]
        elif key in POLYGON_FIELDS and value is not None:
            result[key] = project(value, matrix)
        else:
            require(
                not key.endswith("_px") or key in {"width_px", "height_px"},
                f"Unrecognized pixel field: {key}",
            )
            result[key] = transfer(value, matrix)
    return result


def pixel_points(document):
    if isinstance(document, dict):
        for key, value in document.items():
            if key in POINT_FIELDS and value is not None:
                yield value
            elif key in POLYGON_FIELDS and value is not None:
                yield from value
            else:
                yield from pixel_points(value)
    elif isinstance(document, list):
        for value in document:
            yield from pixel_points(value)


def metric_signature(report):
    return dict(
        metric_valid=report["metric_valid"],
        issues=sorted(((i["code"], i.get("entity_id"), i.get("path")) for i in report["issues"])),
    )


def sources():
    bundles = []
    for path in SOURCE_MANIFESTS:
        for sample in read(path)["samples"]:
            obs_path = (path.parent / sample["observations_path"]).resolve()
            side_path = (path.parent / sample["annotations_path"]).resolve()
            obs, side = (read(obs_path), read(side_path))
            metric_path = (side_path.parent / side["reference_draft_path"]).resolve()
            image_path = (path.parent / sample["image_path"]).resolve()
            draft = read(metric_path)
            require(
                sha(image_path) == sample["image_sha256"] == obs["source"]["image_sha256"],
                f"Source hash mismatch: {sample['id']}",
            )
            require(
                not validate_document(obs)["issues"], f"Invalid source observations: {sample['id']}"
            )
            require(
                obs["frame"]["id"] == "original"
                and np.array_equal(obs["frame"]["original_to_frame"], np.eye(3)),
                "Sources must use encoded original image coordinates",
            )
            Draft202012Validator(SCHEMAS["urn:playablesketch:pixel-annotations:1"]).validate(side)
            metric_report = validate_document(draft, obs)
            require(metric_report["schema_valid"], f"Invalid source metric schema: {sample['id']}")
            bundles.append(
                dict(
                    sample=sample,
                    manifest_path=path,
                    image_path=image_path,
                    obs_path=obs_path,
                    side_path=side_path,
                    metric_path=metric_path,
                    obs=obs,
                    side=side,
                    draft=draft,
                    metric_report=metric_report,
                    origin="synthetic" if sample.get("origin") == "synthetic" else "human",
                )
            )
    require(len({b["sample"]["id"] for b in bundles}) == len(bundles), "Duplicate source IDs")
    return bundles


def parameters(source_id, profile, width, height):
    seed = int.from_bytes(
        hashlib.sha256(f"augmentation-v1:{source_id}:{profile}".encode()).digest()[:8], "big"
    )
    rng = np.random.default_rng(seed)
    matrix = np.eye(3)
    settings = dict(
        seed=seed,
        profile=profile,
        angle_degrees=0.0,
        gamma=1.0,
        gain=1.0,
        shadow_strength=0.0,
        noise_sigma=0.0,
        blur_sigma=0.0,
        jpeg_quality=None,
        tint_rgb=[1.0, 1.0, 1.0],
        perspective_fraction=0.0,
    )
    corners = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=float
    )
    if profile in {"rotate", "combined"}:
        angle = float(rng.choice([-1, 1]) * rng.uniform(1.5, 4.0))
        matrix[:2] = cv2.getRotationMatrix2D(((width - 1) / 2, (height - 1) / 2), angle, 1.0)
        settings["angle_degrees"] = angle
    if profile in {"perspective", "combined"}:
        amount = 0.035 if profile == "perspective" else 0.025
        destination = corners + rng.uniform(-amount, amount, (4, 2)) * [width, height]
        matrix = (
            cv2.getPerspectiveTransform(corners.astype("float32"), destination.astype("float32"))
            @ matrix
        )
        settings["perspective_fraction"] = amount
    if profile in {"rotate", "perspective", "combined"}:
        warped = np.asarray(project(corners, matrix))
        low, high = (warped.min(axis=0), warped.max(axis=0))
        margin = 24
        scale = float(
            min(
                (width - 1 - 2 * margin) / (high[0] - low[0]),
                (height - 1 - 2 * margin) / (high[1] - low[1]),
            )
        )
        center = (low + high) / 2
        fit = np.array(
            [
                [scale, 0, (width - 1) / 2 - scale * center[0]],
                [0, scale, (height - 1) / 2 - scale * center[1]],
                [0, 0, 1.0],
            ]
        )
        matrix = fit @ matrix
    if profile in {"lighting", "combined"}:
        settings.update(
            gamma=float(rng.uniform(0.92, 1.12)),
            gain=float(rng.uniform(0.97, 1.02)),
            shadow_strength=float(rng.uniform(0.08, 0.18)),
            noise_sigma=float(rng.uniform(0.5, 1.2)),
            tint_rgb=[1.0, float(rng.uniform(0.98, 1.0)), float(rng.uniform(0.95, 0.99))],
        )
    if profile in {"capture", "combined"}:
        settings.update(
            blur_sigma=float(rng.uniform(0.32, 0.55)),
            jpeg_quality=int(rng.integers(84, 94)),
            noise_sigma=float(rng.uniform(0.6, 1.4)),
        )
    return (matrix, settings)


def augment_pixels(image, matrix, settings):
    height, width = image.shape[:2]
    out = cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    if settings["profile"] in {"lighting", "combined", "capture"}:
        values = out.astype(np.float32) / 255
        values = np.power(values, settings["gamma"]) * settings["gain"]
        if settings["shadow_strength"]:
            xx = np.linspace(0, 1, width, dtype=np.float32)[None, :]
            yy = np.linspace(0, 1, height, dtype=np.float32)[:, None]
            gradient = 0.65 * xx + 0.35 * yy
            values *= (1 - settings["shadow_strength"] * gradient)[..., None]
        values *= np.array(settings["tint_rgb"], dtype=np.float32)
        rng = np.random.default_rng(settings["seed"] ^ 11258247)
        values += rng.normal(0, settings["noise_sigma"] / 255, (height, width, 1)).astype("float32")
        out = (np.clip(values, 0, 1) * 255).round().astype("uint8")
    if settings["blur_sigma"]:
        out = cv2.GaussianBlur(out, (3, 3), settings["blur_sigma"])
    if settings["jpeg_quality"] is not None:
        ok, encoded = cv2.imencode(
            ".jpg",
            cv2.cvtColor(out, cv2.COLOR_RGB2BGR),
            [cv2.IMWRITE_JPEG_QUALITY, settings["jpeg_quality"]],
        )
        require(ok, "JPEG encoding failed")
        out = cv2.cvtColor(cv2.imdecode(encoded, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    return out


def render(bundle, profile, out):
    source = bundle["sample"]
    sid = f"AUG_{source['id']}_{profile}"
    with Image.open(bundle["image_path"]) as im:
        require(
            im.getexif().get(274, 1) == 1, "Unexpected EXIF orientation; explicit handling required"
        )
        pixels = np.asarray(im.convert("RGB"))
    height, width = pixels.shape[:2]
    matrix, settings = parameters(source["id"], profile, width, height)
    transformed_corners = project(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], matrix
    )
    require(
        all((0 <= x <= width - 1 and 0 <= y <= height - 1 for x, y in transformed_corners)),
        "Source clipping",
    )
    image_path = out / "images" / f"{sid}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(augment_pixels(pixels, matrix, settings)).save(image_path, compress_level=3)
    image_sha = sha(image_path)
    obs = transfer(bundle["obs"], matrix)
    side = transfer(bundle["side"], matrix)
    draft = deepcopy(bundle["draft"])
    for document in (obs, draft):
        document["document_id"] = f"{sid}_{('observations' if document is obs else 'layout')}"
        document["revision_id"] = "augmentation-1"
        document["source"] = dict(
            image_path="../images/" + image_path.name,
            image_sha256=image_sha,
            legacy_draft_path=None,
        )
        document["notes"].append(
            "Automatically transferred from "
            + source["id"]
            + "; cm values and unresolved/conflicting evidence preserved. Not new manual review."
        )
    obs["frame"] = dict(
        id="original", width_px=width, height_px=height, original_to_frame=np.eye(3).tolist()
    )
    for text in obs["texts"]:
        text["method"] = "augmentation_transfer"
    side.update(
        method="augmentation_transfer",
        observations_path=f"{sid}.observations.json",
        reference_draft_path=f"../metric/{sid}.draft.json",
        precision="Projective transfer of source annotations; source trace precision is inherited. "
        + bundle["side"]["precision"],
    )
    for association in side["associations"]:
        association["endpoint_basis"] = "augmentation_transferred_endpoints"
        association["provenance"] = "augmentation_transferred_association"
    for region in side.get("regions", []):
        region["status"] = "augmentation_transferred_boundary"
    for gap in side["gaps"]:
        gap["semantic_provenance"] = (
            "Transferred source interpretation: " + gap["semantic_provenance"]
        )
    side["issues"].append("AUTOMATIC_AUGMENTATION_TRANSFER_NOT_NEW_MANUAL_REVIEW")
    draft.update(
        observation_document_id=obs["document_id"],
        parent_revision_id=bundle["draft"]["revision_id"],
        algorithm_version="annotation-transfer-augmentation/1.0",
        review=dict(status="pending", reviewer=None),
    )
    write(out / "annotations" / f"{sid}.observations.json", obs)
    write(out / "annotations" / f"{sid}.annotations.json", side)
    write(out / "metric" / f"{sid}.draft.json", draft)
    masks = {}
    rendering = None
    if source.get("rendering_path"):
        rendering = read(bundle["manifest_path"].parent / source["rendering_path"])
        for name, mask_path in rendering["masks"].items():
            path = out / "masks" / f"{sid}_{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(bundle["manifest_path"].parent / mask_path) as im:
                mask = np.asarray(im.convert("L"))
            warped = cv2.warpPerspective(
                mask,
                matrix,
                (width, height),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            Image.fromarray(warped).save(path)
            masks[name] = relative(path, out)
    metric_report = validate_document(draft, obs)
    require(
        metric_signature(metric_report) == metric_signature(bundle["metric_report"]),
        "Changed metric semantics",
    )
    status = (
        "valid"
        if metric_report["metric_valid"]
        else (
            "conflicting"
            if any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in metric_report["issues"]))
            else "incomplete"
        )
    )
    metadata = dict(
        schema_version="playablesketch-augmentation/1.0",
        sample_id=sid,
        source_id=source["id"],
        source_origin=bundle["origin"],
        source_files={
            key: dict(path=relative(bundle[key], out), sha256=sha(bundle[key]))
            for key in ["image_path", "obs_path", "side_path", "metric_path"]
        },
        source_manifest=relative(bundle["manifest_path"], out),
        source_to_augmented=matrix.tolist(),
        augmented_to_source=np.linalg.inv(matrix).tolist(),
        source_corners_in_augmented=transformed_corners,
        output_size_px=[width, height],
        parameters=settings,
        validation=metric_report,
        masks=masks,
        mask_semantics="Transferred synthetic renderer coverage, without photometric effects; no pixel masks fabricated for human traces.",
        source_annotation_precision=bundle["side"]["precision"],
        source_text_methods={t["id"]: t["method"] for t in bundle["obs"]["texts"]},
    )
    if rendering:
        metadata["renderer_canvas_to_augmented"] = (
            matrix @ np.asarray(rendering["canvas_to_image"])
        ).tolist()
    write(out / "transforms" / f"{sid}.json", metadata)
    return dict(
        id=sid,
        origin="augmented",
        source_origin=bundle["origin"],
        source_id=source["id"],
        base_plan_id=source["base_plan_id"],
        writer_id=source.get("writer_id"),
        synthetic_style_id=source.get("synthetic_style_id"),
        split="development",
        profile=profile,
        image_path=relative(image_path, out),
        image_sha256=image_sha,
        encoded_size_px=[width, height],
        exif_orientation=1,
        annotation_status=obs["region_annotation_status"],
        observations_path=f"annotations/{sid}.observations.json",
        annotations_path=f"annotations/{sid}.annotations.json",
        metric_path=f"metric/{sid}.draft.json",
        transform_path=f"transforms/{sid}.json",
        metric_status=status,
        source_metric_status=source["metric_status"],
        review_status="pending",
        counts={k: len(obs[k]) for k in ["texts", "lines", "opening_candidates"]},
    )


def original_entry(bundle, out):
    sample = deepcopy(bundle["sample"])
    for key, pathkey in [
        ("image_path", "image_path"),
        ("observations_path", "obs_path"),
        ("annotations_path", "side_path"),
        ("metric_path", "metric_path"),
    ]:
        sample[key] = relative(bundle[pathkey], out)
    if sample.get("rendering_path"):
        sample["rendering_path"] = relative(
            bundle["manifest_path"].parent / sample["rendering_path"], out
        )
    sample.update(origin=bundle["origin"], augmented=False)
    return sample


def audit(out, bundles=None):
    out = Path(out)
    bundles = sources() if bundles is None else bundles
    source_map = {b["sample"]["id"]: b for b in bundles}
    manifest = read(out / "manifest.json")
    sample_ids, hashes, grouped, statuses = (set(), set(), Counter(), Counter())
    profile_pairs = set()
    text_count = 0
    for sample in manifest["samples"]:
        sid = sample["id"]
        require(sid not in sample_ids, "Duplicate augmentation ID")
        sample_ids.add(sid)
        bundle = source_map[sample["source_id"]]
        profile_pair = (sample["source_id"], sample["profile"])
        require(
            profile_pair not in profile_pairs and sample["profile"] in PROFILES,
            "Duplicate/unknown augmentation profile",
        )
        profile_pairs.add(profile_pair)
        obs = read(out / sample["observations_path"])
        side = read(out / sample["annotations_path"])
        draft = read(out / sample["metric_path"])
        meta = read(out / sample["transform_path"])
        width, height = sample["encoded_size_px"]
        require(
            sha(out / sample["image_path"])
            == sample["image_sha256"]
            == obs["source"]["image_sha256"],
            f"{sid}: image hash mismatch",
        )
        require(
            sample["image_sha256"] not in hashes
            and sample["image_sha256"] != bundle["sample"]["image_sha256"],
            "Duplicate image bytes",
        )
        hashes.add(sample["image_sha256"])
        for file in meta["source_files"].values():
            require(sha(out / file["path"]) == file["sha256"], "Modified source file")
        require(not validate_document(obs)["issues"], f"{sid}: observations schema/semantic error")
        Draft202012Validator(SCHEMAS["urn:playablesketch:pixel-annotations:1"]).validate(side)
        require(
            (out / sample["observations_path"]).parent.joinpath(side["observations_path"]).resolve()
            == (out / sample["observations_path"]).resolve(),
            "Sidecar link mismatch",
        )
        require(
            (out / sample["annotations_path"])
            .parent.joinpath(side["reference_draft_path"])
            .resolve()
            == (out / sample["metric_path"]).resolve(),
            "Metric link mismatch",
        )
        require(
            (out / sample["observations_path"])
            .parent.joinpath(obs["source"]["image_path"])
            .resolve()
            == (out / sample["image_path"]).resolve(),
            "Observation image mismatch",
        )
        require(
            draft["source"] == obs["source"]
            and draft["observation_document_id"] == obs["document_id"],
            "Metric source mismatch",
        )
        report = validate_document(draft, obs)
        require(
            metric_signature(report) == metric_signature(bundle["metric_report"]),
            "Metric validation changed",
        )
        actual_status = (
            "valid"
            if report["metric_valid"]
            else (
                "conflicting"
                if any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in report["issues"]))
                else "incomplete"
            )
        )
        require(sample["metric_status"] == actual_status, "Misclassified metric status")
        require(
            sample["counts"] == {k: len(obs[k]) for k in ["texts", "lines", "opening_candidates"]},
            "Annotation counts mismatch",
        )
        require(
            obs["frame"]["id"] == "original"
            and [obs["frame"]["width_px"], obs["frame"]["height_px"]] == [width, height]
            and np.array_equal(obs["frame"]["original_to_frame"], np.eye(3)),
            "Incorrect target coordinate frame",
        )
        require(
            draft["layout"] == bundle["draft"]["layout"]
            and draft["settings"] == bundle["draft"]["settings"],
            "Metric values/unknowns changed",
        )
        require(
            draft["review"]["status"] == "pending" and (not report["exportable"]),
            "Augmentation cannot confer acceptance",
        )
        matrix, inverse = (
            np.array(meta["source_to_augmented"]),
            np.array(meta["augmented_to_source"]),
        )
        require(np.allclose(matrix @ inverse, np.eye(3), atol=1e-08), "Noninvertible transfer")
        for source_doc, target_doc in [(bundle["obs"], obs), (bundle["side"], side)]:
            source_points = list(pixel_points(source_doc))
            target_points = list(pixel_points(target_doc))
            require(len(source_points) == len(target_points), "Annotation primitive omitted")
            if source_points:
                expected = project(source_points, matrix)
                require(
                    np.allclose(expected, target_points, atol=1e-06),
                    "Pixel transformation mismatch",
                )
                require(
                    np.allclose(project(target_points, inverse), source_points, atol=0.0001),
                    "Round-trip mismatch",
                )
            require(
                all((0 <= x <= width - 1 and 0 <= y <= height - 1 for x, y in target_points)),
                "Annotation outside image",
            )
        require(
            [(t["raw_text"], t["parsed_value_cm"]) for t in obs["texts"]]
            == [(t["raw_text"], t["parsed_value_cm"]) for t in bundle["obs"]["texts"]],
            "Transcription changed",
        )
        require(
            all((t["method"] == "augmentation_transfer" for t in obs["texts"])),
            "Misleading annotation provenance",
        )
        require(
            sample["base_plan_id"] == bundle["sample"]["base_plan_id"]
            and sample["writer_id"] == bundle["sample"]["writer_id"]
            and (sample["split"] == "development"),
            "Lineage/split mismatch",
        )
        with Image.open(out / sample["image_path"]) as im:
            require(list(im.size) == [width, height], "Image size mismatch")
        for path in meta["masks"].values():
            with Image.open(out / path) as im:
                require(list(im.size) == [width, height], "Mask size mismatch")
        grouped[sample["source_id"]] += 1
        statuses[sample["metric_status"]] += 1
        text_count += len(obs["texts"])
    require(
        set(grouped) == set(source_map) and set(grouped.values()) == {len(PROFILES)},
        "Incomplete source coverage",
    )
    combined = read(out / "manifest_with_originals.json")["samples"]
    require(
        len(combined) == len(bundles) + len(sample_ids)
        and len({s["id"] for s in combined}) == len(combined),
        "Combined manifest mismatch",
    )
    require(
        combined[: len(bundles)] == [original_entry(b, out) for b in bundles]
        and combined[len(bundles) :] == manifest["samples"],
        "Combined entries differ",
    )
    require(not list((out / "metric").glob("*.validated.json")), "Unexpected accepted exports")
    return dict(
        source_images=len(bundles),
        source_human=50,
        source_synthetic=70,
        new_images=len(sample_ids),
        profiles_per_source=len(PROFILES),
        combined_images=len(combined),
        base_plan_groups=len({s["base_plan_id"] for s in combined}),
        augmented_text_regions=text_count,
        metric_status_counts=dict(statuses),
        annotations_in_bounds=True,
        coordinate_round_trips_passed=True,
        metric_semantics_preserved=True,
        all_sources_covered=True,
        training_performed=False,
    )


def gallery(out, bundles, samples):
    sample_map = {(s["source_id"], s["profile"]): s for s in samples}
    rows, tiles = ([], [])
    for bundle in bundles:
        source = bundle["sample"]
        entries = [("original", relative(bundle["image_path"], out))] + [
            (p, sample_map[source["id"], p]["image_path"]) for p in PROFILES
        ]
        cells = []
        for label, path in entries:
            cells.append(
                f"""<figure><a href="{html.escape(path)}"><img loading="lazy" src="{html.escape(path)}" alt="{html.escape(source['id'])} {label}"></a><figcaption>{label}</figcaption></figure>"""
            )
        rows.append(
            f"<section><h2>{html.escape(source['id'])} · {bundle['origin']}</h2><div>"
            + "".join(cells)
            + "</div></section>"
        )
        if source["id"] in ["Data_7", "Data_41", "SP002_ink", "SX003_ink"]:
            for label, path in entries:
                with Image.open(out / path) as im:
                    thumb = im.convert("RGB")
                    thumb.thumbnail((340, 300))
                tile = Image.new("RGB", (360, 340), "white")
                tile.paste(thumb, ((360 - thumb.width) // 2, 32 + (300 - thumb.height) // 2))
                ImageDraw.Draw(tile).text((8, 8), source["id"] + " / " + label, fill="black")
                tiles.append(tile)
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Augmentation v1</title><style>body{font:16px system-ui;background:#eee;margin:20px}section{margin-bottom:36px}section>div{display:grid;grid-template-columns:repeat(6,minmax(170px,1fr));gap:8px;overflow:auto}figure{margin:0}img{width:100%;background:white}figcaption{padding:5px}h2{font-size:18px}</style><h1>Augmentation v1 — 120 sources + 600 new images</h1><p>Original, rotation, perspective, lighting, capture and combined. Click for full resolution. All annotations are transferred with the same homography; cm semantics are unchanged. Development groups are inherited. No training.</p>'
        + "".join(rows)
        + "</html>"
    )
    (out / "index.html").write_text(page)
    sheet = Image.new("RGB", (6 * 360, 4 * 340), "#dddddd")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (i % 6 * 360, i // 6 * 340))
    sheet.save(out / "comparison.jpg", quality=92)


def run(output):
    require(not output.exists(), "Output already exists; use --check or choose a fresh --output")
    bundles = sources()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".augmentation-", dir=output.parent))
    samples = []
    for index, bundle in enumerate(bundles, 1):
        for profile in PROFILES:
            samples.append(render(bundle, profile, staging))
        if index % 5 == 0:
            print(
                f"{index}/{len(bundles)} sources; {len(samples)} augmentations generated",
                flush=True,
            )
    manifest = dict(
        schema_version="playablesketch-augmentation-dataset/1.0",
        split_policy="development_only; inherit parent base_plan_id and writer; no independent holdout",
        generator_version="annotation-transfer-augmentation/1.0",
        profiles=list(PROFILES),
        samples=samples,
    )
    write(staging / "manifest.json", manifest)
    write(
        staging / "manifest_with_originals.json",
        dict(
            schema_version=manifest["schema_version"],
            split_policy=manifest["split_policy"],
            samples=[original_entry(b, staging) for b in bundles] + samples,
        ),
    )
    gallery(staging, bundles, samples)
    report = audit(staging, bundles)
    write(staging / "verification.json", report)
    staging.rename(output)
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Label-preserving augmentation of every curated human and synthetic image."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(audit(args.output), indent=2))
    else:
        run(args.output)


if __name__ == "__main__":
    main()
