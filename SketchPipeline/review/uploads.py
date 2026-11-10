from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import threading
import uuid
import cv2
import numpy as np
from SketchPipeline.perception.topology import build_topology
from SketchPipeline.preprocessing.prepare import decode, MAX_BYTES
from SketchPipeline.validation.validate import validate_document


def manual_prediction(image, output, reason):
    original, upright, exif, _ = decode(image)
    h, w = upright.shape[:2]
    scale = min(1.0, 1600 / max(w, h))
    width, height = (max(1, round(w * scale)), max(1, round(h * scale)))
    resized = cv2.resize(upright, (width, height), interpolation=cv2.INTER_AREA)
    sx, sy = (width / w, height / h)
    forward = np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]]) @ exif
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    preprocessing = {
        "source_sha256": sha,
        "source_name": image.name,
        "original_size_px": [original.shape[1], original.shape[0]],
        "working_size_px": [width, height],
        "original_to_working": forward.tolist(),
        "working_to_original": np.linalg.inv(forward).tolist(),
    }
    observations = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": "upload-" + sha[:16],
        "revision_id": "manual-fallback-1",
        "source": {
            "image_path": "../" + image.name,
            "image_sha256": sha,
            "legacy_draft_path": None,
        },
        "units": "px",
        "coordinate_system": "u_right_v_down",
        "frame": {
            "id": "original",
            "width_px": original.shape[1],
            "height_px": original.shape[0],
            "original_to_frame": np.eye(3).tolist(),
        },
        "region_annotation_status": "partial",
        "texts": [],
        "lines": [],
        "opening_candidates": [],
        "issues": [
            {
                "code": "SKETCH_PERCEPTION_UNAVAILABLE",
                "severity": "warning",
                "element_ids": [],
                "message": "Automatic detection was unavailable. Review the image manually.",
            }
        ],
        "notes": [
            "No automated evidence or metric geometry was generated. User review is required."
        ],
    }
    checked = validate_document(observations)
    if not checked["schema_valid"] or checked["issues"]:
        raise ValueError("Invalid manual-review observation artifact.")
    topology = build_topology([], [], (height, width))
    working = {
        "schema_version": "playablesketch-perception/1.2",
        "preprocessing": preprocessing,
        "geometry": {"dominant_rotation_degrees": 0},
        "gaps": [],
        "topology": topology,
        "prediction_status": "manual_review_required",
        "failure_message": str(reason),
        "training_performed": False,
    }
    output.mkdir()
    for filename, document in (
        ("working.json", working),
        ("topology.json", topology),
        ("observations.json", observations),
    ):
        (output / filename).write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    if not cv2.imwrite(
        str(output / "unmasked_line_input.png"), cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
    ):
        raise OSError("Cannot save the review background.")


class UploadManager:

    def __init__(self, store):
        self.store = store
        self.root = store.output / "uploads"
        self.root.mkdir(exist_ok=True)
        self.jobs, self.lock = ({}, threading.Lock())
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sketch-upload")
        self.adapter = None

    def start(self, data, filename):
        from .server import ReviewError, atomic_json

        if not data or len(data) > MAX_BYTES:
            raise ReviewError("Upload a JPEG or PNG image up to 20 MB.", 413)
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:160]
        extension = Path(filename).suffix.lower()
        if extension not in (".jpg", ".jpeg", ".png"):
            raise ReviewError("Only JPEG and PNG drawings are supported.", 415)
        identifier = (
            "Upload_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:10]
        )
        folder = self.root / identifier
        with self.lock:
            if sum((job["status"] in ("queued", "processing") for job in self.jobs.values())) >= 3:
                raise ReviewError("The upload queue is full. Wait for a drawing to finish.", 429)
            folder.mkdir()
            image = folder / ("source" + extension)
            try:
                image.write_bytes(data)
                decode(image)
            except Exception as error:
                shutil.rmtree(folder)
                raise ReviewError(
                    "The image could not be decoded. Use a JPEG/PNG image from 16×16 pixels up to 40 MP.",
                    422,
                ) from error
            job = {
                "job_id": identifier,
                "status": "queued",
                "filename": filename,
                "requires_review": True,
            }
            self.jobs[identifier] = job
            atomic_json(folder / "upload.json", job)
            self.pool.submit(self._process, identifier, image)
            return dict(job)

    def _process(self, identifier, image):
        from .server import atomic_json

        folder, prediction = (image.parent, image.parent / "prediction")
        with self.lock:
            self.jobs[identifier]["status"] = "processing"
        try:
            mode = "automatic"
            try:
                from SketchPipeline.perception.ocr import RapidOCRAdapter
                from SketchPipeline.perception.run import run_single

                if self.adapter is None:
                    self.adapter = RapidOCRAdapter()
                run_single(image, prediction, self.adapter)
                case = self.store._load_case(prediction, identifier)
            except Exception as error:
                if prediction.exists():
                    shutil.rmtree(prediction)
                manual_prediction(image, prediction, error)
                mode = "manual"
                case = self.store._load_case(prediction, identifier)
            with self.store.lock:
                case["label"] = self.jobs[identifier]["filename"]
                self.store.cases[identifier] = case
            with self.lock:
                self.jobs[identifier].update(status="complete", case_id=identifier, detection=mode)
                atomic_json(folder / "upload.json", self.jobs[identifier])
        except Exception:
            with self.lock:
                self.jobs[identifier].update(
                    status="failed",
                    error="The drawing could not be prepared for review. Try another JPEG or PNG image.",
                )
                atomic_json(folder / "upload.json", self.jobs[identifier])

    def status(self, identifier):
        from .server import ReviewError

        with self.lock:
            if identifier not in self.jobs:
                raise ReviewError("Unknown upload job.", 404)
            return dict(self.jobs[identifier])

    def close(self):
        self.pool.shutdown(wait=True)
