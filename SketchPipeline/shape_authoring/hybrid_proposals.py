import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from .hybrid_model import HybridModel, DEFAULT_PACKAGE, native_input
from .hybrid_geometry import authoring_from_prediction, POLICY
from .decoder import authoring_document
from .contract import validate_authoring
from .synthetic import write_json


def run(image, output, checkpoint=None, expected_sha256=None, normalize_ink=False):
    if normalize_ink:
        raise ValueError("Hybrid inference uses its own trained input features")
    started = time.perf_counter()
    image = Path(image).resolve()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "proposals.json").exists():
        raise ValueError("Output already has proposals; use a new directory.")
    native, native_metadata = native_input(image)
    gray = cv2.resize(native, (256, 256), interpolation=cv2.INTER_AREA)
    preprocessing = dict(native_metadata)
    forward = np.diag([0.25, 0.25, 1.0]) @ np.asarray(native_metadata["original_to_working"])
    preprocessing.update(
        working_size_px=[256, 256],
        original_to_working=forward.tolist(),
        working_to_original=np.linalg.inv(forward).tolist(),
        automatic_deskew_degrees=native_metadata.get("automatic_deskew_degrees", 0),
    )
    source = {
        "image_path": str(image),
        "image_sha256": native_metadata["source_sha256"],
        "width_px": native_metadata["original_size_px"][0],
        "height_px": native_metadata["original_size_px"][1],
    }
    cv2.imwrite(str(output / "working.png"), gray)
    cv2.imwrite(str(output / "cleaned.png"), gray)
    cv2.imwrite(str(output / "grid-mask.png"), np.zeros_like(gray))
    cv2.imwrite(str(output / "evidence.png"), native)
    metadata = None
    failure = None
    detail = {}
    configuration = {
        "version": "hybrid-unet-yolo11/1.0",
        "geometry": POLICY,
        "experimental": True,
        "human_automation_ready": False,
        "review_required": True,
    }
    try:
        model = HybridModel(checkpoint or DEFAULT_PACKAGE, expected_sha256)
        metadata = model.metadata
        configuration["parameters"] = model.config["parameters"]
        prediction = model.predict(image)
        np.savez_compressed(
            output / "model-masks.npz",
            native_wall_probability=prediction["wall_probability"],
            channels=np.asarray(["wall"]),
        )
        cv2.imwrite(str(output / "wall-mask.png"), np.uint8(prediction["wall_probability"] * 255))
        write_json(
            output / "model-detections.json",
            {
                "regions": prediction["regions"],
                "door_boxes": prediction["door_boxes"],
                "door_attached": prediction["door_attached"],
                "model": metadata,
            },
        )
        document, detail = authoring_from_prediction(prediction, source, preprocessing)
    except (OSError, ImportError, RuntimeError, ValueError, KeyError, cv2.error) as error:
        failure = f"{type(error).__name__}: {error}"
        document = authoring_document(source, preprocessing, [], [])
        detail = {"status": "manual_required", "reason": failure}
    revision = (
        "proposal_"
        + hashlib.sha256(
            json.dumps(
                {
                    "source": source["image_sha256"],
                    "model": metadata,
                    "configuration": configuration,
                    "preprocessing": preprocessing,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:20]
        + "_0"
    )
    document["revision_id"] = revision
    evidence = []
    inverse = np.asarray(preprocessing["working_to_original"])
    for collection, kind in [("regions", "region"), ("openings", "opening_marker")]:
        for entity in document["topology"][collection]:
            points = np.asarray(entity["geometry"]["points_px"])
            p = np.c_[points, np.ones(len(points))] @ inverse.T
            eid = "evidence_" + entity["id"]
            entity["geometry"]["evidence_ids"] = [eid]
            evidence.append({"id": eid, "kind": kind, "points_px": (p[:, :2] / p[:, 2:]).tolist()})
    document["image_evidence"]["items"] = evidence
    errors = validate_authoring(document)
    if errors:
        raise ValueError("Invalid hybrid authoring document: " + "; ".join(errors))
    status = (
        "needs_attention" if document["topology"]["regions"] and not failure else "manual_required"
    )
    result = {
        "schema_version": "playablesketch-shape-proposals/1.0",
        "status": status,
        "backend": "learned",
        "model": metadata,
        "source_sha256": source["image_sha256"],
        "authoring_revision_id": revision,
        "profile": "hybrid",
        "profile_configuration": configuration,
        "evidence_preprocessing": native_metadata,
        "input_normalization": None,
        "profile_config_sha256": hashlib.sha256(
            json.dumps(configuration, sort_keys=True).encode()
        ).hexdigest(),
        "configuration": configuration,
        "config_sha256": hashlib.sha256(
            json.dumps(configuration, sort_keys=True).encode()
        ).hexdigest(),
        "preprocessing": preprocessing,
        "grid": {"status": "not_applied"},
        "elapsed_seconds": time.perf_counter() - started,
        "inference_seconds": time.perf_counter() - started,
        "failure": failure,
        "review_required": True,
        "metric_layout_created": False,
        "numeric_ocr_called": False,
        "authoring": document,
        "alternatives": [],
        "diagnostics": [{"hybrid_geometry": detail}],
        "human_correction_time_seconds": None,
    }
    write_json(output / "authoring.json", document)
    write_json(output / "proposals.json", result)
    return result
