import argparse
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import decode, prepare, InputError
from .contract import validate_authoring
from .decoder import (
    CONFIG,
    region_boxes,
    boundary_graph,
    opening_candidates,
    authoring_document,
    regularize_boxes,
)
from .synthetic import write_json

DEFAULT_LOCK = Path(__file__).with_name("models.lock.json")
PROFILE_NAMES = ("baseline", "refined", "refined-full", "hybrid")


def prepare_image(image):
    try:
        images, metadata = prepare(image, max_side=CONFIG["max_side"])
        from SketchPipeline.perception.geometry import detect_raw, dominant_rotation

        lines = detect_raw(images["gray"], "hough", max(images["gray"].shape))
        rotation = dominant_rotation(lines, max(images["gray"].shape))
        long = [
            line
            for line in lines
            if np.linalg.norm(np.array(line["end"]) - line["start"])
            > max(images["gray"].shape) * 0.2
        ]
        if len(long) >= 4 and 0.25 < abs(rotation) < 8:
            images, metadata = prepare(image, max_side=CONFIG["max_side"], deskew_degrees=rotation)
            metadata["automatic_deskew_degrees"] = rotation
        else:
            metadata["automatic_deskew_degrees"] = 0
        return (images["gray"], metadata)
    except InputError as error:
        original, upright, exif, _ = decode(image)
        h, w = upright.shape[:2]
        scale = min(1.0, CONFIG["max_side"] / max(w, h))
        W, H = (max(16, round(w * scale)), max(16, round(h * scale)))
        gray = cv2.cvtColor(cv2.resize(upright, (W, H)), cv2.COLOR_RGB2GRAY)
        forward = np.diag([W / w, H / h, 1.0]) @ exif
        return (
            gray,
            {
                "source_sha256": hashlib.sha256(Path(image).read_bytes()).hexdigest(),
                "original_size_px": [original.shape[1], original.shape[0]],
                "working_size_px": [W, H],
                "original_to_working": forward.tolist(),
                "working_to_original": np.linalg.inv(forward).tolist(),
                "automatic_deskew_degrees": 0,
                "manual_input_warning": str(error),
            },
        )


def classical(gray):
    from SketchPipeline.perception.structural import structural_evidence
    from SketchPipeline.perception.openings import gap_evidence
    from SketchPipeline.perception.topology import build_topology

    detectors, geometry, masks = structural_evidence(gray, [], "grid")
    primary = detectors["lsd"]
    recovery = geometry["recovery_lines"]["lsd"]
    gaps = gap_evidence(
        primary, [], gray.shape, recovery_lines=recovery, ink=masks["wall_ink"], diagnostics=False
    )
    topology = build_topology(
        primary + recovery, gaps, gray.shape, 0, ink=masks["unmasked_wall_ink"]
    )
    boxes = [
        {"type": "room", "bounds_px": r["bounds_px_rotated"], "model_score": 0.0}
        for r in topology["regions"]
        if r["rectangle_candidate"]
    ]
    boxes = regularize_boxes(boxes, gray.shape)
    openings, unresolved = opening_candidates(boundary_graph(boxes)[0], gray)
    return (boxes, openings, {"classic_topology": topology, "unresolved": unresolved})


def run(
    image,
    output,
    backend="learned",
    checkpoint=None,
    expected_sha256=None,
    reason=None,
    profile="baseline",
    normalize_ink=False,
):
    if profile not in PROFILE_NAMES:
        raise ValueError("Unknown shape proposal profile")
    if backend == "learned" and profile == "hybrid":
        from .hybrid_proposals import run as hybrid_run

        return hybrid_run(image, output, checkpoint, expected_sha256, normalize_ink)
    started = time.perf_counter()
    image = Path(image).resolve()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "proposals.json").exists():
        raise ValueError("Output already has proposals; use a new directory.")
    gray, preprocessing = prepare_image(image)
    source = {
        "image_path": str(image),
        "image_sha256": preprocessing["source_sha256"],
        "width_px": preprocessing["original_size_px"][0],
        "height_px": preprocessing["original_size_px"][1],
    }
    from SketchPipeline.perception.structural import suppress_grid

    cleaned, grid_mask, grid_info = suppress_grid(gray)
    cv2.imwrite(str(output / "working.png"), gray)
    cv2.imwrite(str(output / "cleaned.png"), cleaned)
    cv2.imwrite(str(output / "grid-mask.png"), grid_mask)
    alternatives = []
    diagnostics = []
    model_metadata = None
    raw = None
    status = "needs_attention"
    evidence_preprocessing = None
    profile_configuration = None
    normalization = None

    def model_inputs(raw_gray, clean_gray, content_bounds=None):
        nonlocal normalization
        if not normalize_ink:
            return (raw_gray, clean_gray)
        from .contrast import normalize_ink as normalize

        a, raw_info = normalize(raw_gray, content_bounds)
        b, clean_info = normalize(clean_gray, content_bounds)
        normalization = {"raw": raw_info, "cleaned": clean_info}
        cv2.imwrite(str(output / "model-input.png"), a)
        return (a, b)

    failure = reason
    inference_started = time.perf_counter()
    try:
        if backend == "learned":
            from .model import LocalSegmenter

            if checkpoint is None:
                lock = json.loads(DEFAULT_LOCK.read_text())
                if (
                    hashlib.sha256(
                        Path(__file__).with_name("proposals.config.json").read_bytes()
                    ).hexdigest()
                    != lock["config_sha256"]
                ):
                    raise ValueError("Shape proposal configuration checksum mismatch")
                checkpoint = Path(__file__).resolve().parents[2] / lock["checkpoint_path"]
                expected_sha256 = lock["checkpoint_sha256"]
            adapter = LocalSegmenter(checkpoint, expected_sha256)
            model_metadata = adapter.metadata
            if profile == "baseline":
                raw = adapter.predict(*model_inputs(gray, cleaned))
                np.savez_compressed(output / "model-masks.npz", probabilities=raw)
                for threshold in CONFIG["region_thresholds"]:
                    boxes, rejected = region_boxes(raw, gray, threshold)
                    openings, unresolved = opening_candidates(boundary_graph(boxes)[0], gray, raw)
                    alternatives.append(authoring_document(source, preprocessing, boxes, openings))
                    diagnostics.append(
                        {
                            "region_threshold": threshold,
                            "boxes": boxes,
                            "rejected": rejected,
                            "opening_evidence": [
                                {k: v for k, v in p.items() if k != "segment"} for p in openings
                            ],
                            "unresolved": unresolved,
                        }
                    )
            else:
                from .decoder_refined import decode as refined_decode, canonical_frame, POLICY
                from .diagnostic_preprocessing import suggest_crop, prepare_variant

                cropped = profile == "refined"
                crop, crop_report = (
                    suggest_crop(image) if cropped else (None, {"status": "not_requested"})
                )
                arm = {
                    "name": profile,
                    "max_side": POLICY["input_max_side"],
                    "square": True,
                    "crop": cropped,
                }
                native, evidence_preprocessing = prepare_variant(
                    image, arm, gray, preprocessing, crop
                )
                native_clean, _, _ = suppress_grid(native)
                native_raw = adapter.predict(
                    *model_inputs(
                        native,
                        native_clean,
                        evidence_preprocessing.get("diagnostic_content_bounds_px"),
                    )
                )
                matrix = np.asarray(preprocessing["original_to_working"]) @ np.asarray(
                    evidence_preprocessing["working_to_original"]
                )
                _, raw, _ = canonical_frame(
                    native,
                    native_raw,
                    gray,
                    matrix,
                    evidence_preprocessing.get("diagnostic_content_bounds_px"),
                )
                np.savez_compressed(
                    output / "model-masks.npz", probabilities=raw, native_probabilities=native_raw
                )
                cv2.imwrite(str(output / "evidence.png"), native)
                cv2.imwrite(str(output / "evidence-cleaned.png"), native_clean)
                profile_configuration = {
                    "decoder": POLICY,
                    "input": arm,
                    "crop": crop_report,
                    "mode": "paired_raw",
                    "experimental": True,
                    "human_automation_ready": False,
                }
                opening_policy = (
                    "corridor-passages"
                    if model_metadata.get("architecture") == "shape-dinov2/1.0"
                    else "legacy"
                )
                region_policy = (
                    "supported-corridors" if opening_policy == "corridor-passages" else "supported"
                )
                if opening_policy == "corridor-passages":
                    from .local_wall_tracking import POLICY as TRACKING_POLICY
                    from .corridor_refinement import POLICY as CORRIDOR_POLICY
                    from .passage_refinement import POLICY as PASSAGE_POLICY
                    from .door_geometry import POLICY as DOOR_POLICY
                    from .opening_alignment import POLICY as ALIGNMENT_POLICY
                    from .corridor_geometry import POLICY as GEOMETRY_POLICY

                    profile_configuration = {
                        **profile_configuration,
                        "decoder": {**POLICY, "version": "shape-decoder/2.9"},
                        "opening_policy": opening_policy,
                        "local_wall_tracking": TRACKING_POLICY,
                        "region_policy": region_policy,
                        "corridor_refinement": CORRIDOR_POLICY,
                        "passage_refinement": PASSAGE_POLICY,
                        "door_geometry": DOOR_POLICY,
                        "opening_alignment": ALIGNMENT_POLICY,
                        "enclosed_geometry": GEOMETRY_POLICY,
                    }
                for threshold in CONFIG["region_thresholds"]:
                    document, detail = refined_decode(
                        native,
                        native_raw,
                        source,
                        evidence_preprocessing,
                        working_gray=gray,
                        working_metadata=preprocessing,
                        evidence_to_working=matrix,
                        region_threshold=threshold,
                        opening_policy=opening_policy,
                        region_policy=region_policy,
                        door_policy=(
                            "observed-jambs" if opening_policy == "corridor-passages" else "legacy"
                        ),
                        opening_alignment=opening_policy == "corridor-passages",
                    )
                    if opening_policy == "corridor-passages":
                        from .corridor_geometry import decode as enclosed_decode

                        document, geometry_detail, _ = enclosed_decode(
                            native,
                            native_raw,
                            source,
                            evidence_preprocessing,
                            working_metadata=preprocessing,
                            evidence_to_working=matrix,
                            baseline_result=(document, detail),
                            opening_alignment=True,
                        )
                        detail = {
                            **detail,
                            "region_boxes": geometry_detail.get(
                                "region_boxes", detail["region_boxes"]
                            ),
                            "opening_evidence": geometry_detail.get(
                                "opening_evidence",
                                geometry_detail.get("baseline_alignment_evidence")
                                or detail["opening_evidence"],
                            ),
                            "enclosed_geometry": geometry_detail,
                            "version": "shape-decoder/2.9",
                        }
                    alternatives.append(document)
                    diagnostics.append({"region_threshold": threshold, **detail})
            if getattr(adapter, "last_auxiliary", None) is not None:
                np.savez_compressed(
                    output / "native-auxiliary-masks.npz",
                    probabilities=adapter.last_auxiliary,
                    channels=np.asarray(adapter.metadata["channels"]),
                )
        elif backend == "classical":
            boxes, openings, detail = classical(gray)
            alternatives = [
                authoring_document(source, preprocessing, boxes, openings, origin="regularized")
            ]
            diagnostics = [detail]
        elif backend == "manual":
            alternatives = [authoring_document(source, preprocessing, [], [])]
            status = "manual_required"
        else:
            raise ValueError("Unknown shape backend")
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        failure = f"{type(error).__name__}: {error}"
        alternatives = [authoring_document(source, preprocessing, [], [])]
        status = "manual_required"
    from .room_geometry import as_rooms, decode_image, POLICY as ROOM_POLICY

    if backend == "learned" and profile != "baseline" and not failure:
        observed, room_detail = decode_image(image, source, preprocessing)
        if observed is not None:
            alternatives = [observed]
            diagnostics = [{"observed_rooms": room_detail}]
        else:
            diagnostics = [{**d, "observed_rooms": room_detail} for d in diagnostics]
        profile_configuration = {**(profile_configuration or {}), "room_geometry": ROOM_POLICY}
    alternatives = [as_rooms(document) for document in alternatives]
    inference_seconds = time.perf_counter() - inference_started
    if not alternatives[0]["topology"]["regions"]:
        status = "manual_required"
    revision_material = json.dumps(
        {
            "source": source["image_sha256"],
            "preprocessing": preprocessing,
            "backend": backend,
            "model": model_metadata and model_metadata["checkpoint_sha256"],
            "config": CONFIG,
        },
        sort_keys=True,
    ).encode()
    if profile_configuration is not None:
        revision_material += json.dumps(
            {
                "profile": profile,
                "configuration": profile_configuration,
                "evidence_preprocessing": evidence_preprocessing,
            },
            sort_keys=True,
        ).encode()
    elif profile != "baseline":
        revision_material += json.dumps({"requested_profile": profile}, sort_keys=True).encode()
    if normalization is not None:
        revision_material += json.dumps(normalization, sort_keys=True).encode()
    revision = "proposal_" + hashlib.sha256(revision_material).hexdigest()[:20]
    for index, document in enumerate(alternatives):
        document["revision_id"] = revision + f"_{index}"
        inverse = np.asarray(preprocessing["working_to_original"])
        evidence = []
        for collection, kind in [("regions", "region"), ("openings", "opening_marker")]:
            for entity in document["topology"][collection]:
                points = np.asarray(entity["geometry"]["points_px"])
                if not len(points):
                    continue
                mapped = np.c_[points, np.ones(len(points))] @ inverse.T
                eid = "evidence_" + entity["id"]
                entity["geometry"]["evidence_ids"] = [eid]
                evidence.append(
                    {"id": eid, "kind": kind, "points_px": (mapped[:, :2] / mapped[:, 2:]).tolist()}
                )
        document["image_evidence"]["items"] = evidence
        errors = validate_authoring(document)
        if errors:
            raise ValueError("Generated invalid authoring document: " + "; ".join(errors))
    result = {
        "schema_version": "playablesketch-shape-proposals/1.0",
        "status": status,
        "backend": backend,
        "model": model_metadata,
        "source_sha256": source["image_sha256"],
        "authoring_revision_id": alternatives[0]["revision_id"],
        "profile": profile if backend == "learned" else "baseline",
        "profile_configuration": profile_configuration,
        "evidence_preprocessing": evidence_preprocessing,
        "input_normalization": normalization,
        "profile_config_sha256": (
            hashlib.sha256(json.dumps(profile_configuration, sort_keys=True).encode()).hexdigest()
            if profile_configuration
            else None
        ),
        "configuration": CONFIG,
        "config_sha256": hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest(),
        "preprocessing": preprocessing,
        "grid": grid_info,
        "elapsed_seconds": time.perf_counter() - started,
        "inference_seconds": inference_seconds,
        "failure": failure,
        "review_required": True,
        "metric_layout_created": False,
        "numeric_ocr_called": False,
        "authoring": alternatives[0],
        "alternatives": alternatives[1:],
        "diagnostics": diagnostics,
        "human_correction_time_seconds": None,
    }
    write_json(output / "authoring.json", result["authoring"])
    write_json(output / "proposals.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Shape-only proposals CLI/API. No OCR imports, calls, associations or fake text."
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["learned", "classical", "manual"], default="learned")
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="baseline",
        help="Refined profiles are experimental and always require review.",
    )
    parser.add_argument(
        "--normalize-ink",
        action="store_true",
        help="Experimental image-only paper contrast normalization.",
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--reason")
    args = parser.parse_args()
    result = run(
        args.image,
        args.output,
        args.backend,
        args.checkpoint,
        args.expected_sha256,
        args.reason,
        args.profile,
        args.normalize_ink,
    )
    print(json.dumps({k: result[k] for k in ("status", "backend", "elapsed_seconds", "failure")}))
