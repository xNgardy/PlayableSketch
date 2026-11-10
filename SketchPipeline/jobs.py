from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from SketchPipeline.pipeline import (
    configuration,
    runtime_identity,
    verify_manifest,
    artifact,
    VERSION,
)
from SketchPipeline.preprocessing.prepare import decode, MAX_BYTES
from SketchPipeline.review.server import ReviewError, atomic_json, digest, file_hash
from SketchPipeline.validation.validate import load_json

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile("^Job_[0-9TZ]+_[a-f0-9]{10}$")


class JobManager:

    def __init__(self, store, metric_store, *, worker_command=None):
        self.store, self.metric = (store, metric_store)
        self.root = store.output / "jobs"
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.cancel_flags = {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sketch-job")
        self.worker_command = worker_command
        for folder in sorted(self.root.glob("Job_*")):
            if not ID.fullmatch(folder.name) or not (folder / "job.json").exists():
                continue
            try:
                record = load_json(folder / "job.json")
                if record["job_id"] != folder.name or record.get(
                    "source_path", "source.png"
                ) not in ("source.png", "source.jpg", "source.jpeg"):
                    raise ValueError("Job identity mismatch")
                if record["state"] in ("uploaded", "processing"):
                    record.update(
                        state="failed",
                        stage="interrupted",
                        error="Service restarted before processing completed. Retry creates a new job.",
                    )
                    atomic_json(folder / "job.json", record)
                self.jobs[folder.name] = record
                if record["state"] == "needs_review":
                    self.register(folder.name)
            except (ValueError, KeyError, OSError) as error:
                record = {
                    "job_id": folder.name,
                    "state": "failed",
                    "stage": "artifact_integrity",
                    "error": str(error),
                }
                self.jobs[folder.name] = record

    def persist(self, identifier):
        atomic_json(self.root / identifier / "job.json", self.jobs[identifier])

    def register(self, identifier):
        folder = self.root / identifier
        manifest = verify_manifest(folder)
        case = self.store._load_case(folder / "prediction", identifier)
        case["label"] = self.jobs[identifier]["filename"]
        if manifest["execution_mode"] == "manual":
            case["notice"] = (
                "Manual preparation selected. Draw or correct the plan, then approve its pixel topology."
            )
        with self.store.lock:
            self.store.cases[identifier] = case

    def start(self, data, filename, config=None, *, parent_job_id=None):
        try:
            config = configuration(config)
        except ValueError as error:
            raise ReviewError(str(error)) from error
        if not isinstance(filename, str):
            raise ReviewError("Image filename required")
        name = filename.replace("\\", "/").rsplit("/", 1)[-1][:160]
        ext = Path(name).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            raise ReviewError("Only JPEG and PNG drawings are supported", 415)
        if not data or len(data) > MAX_BYTES:
            raise ReviewError("Upload a JPEG/PNG image up to 20 MB", 413)
        runtime = runtime_identity()
        sha = hashlib.sha256(data).hexdigest()
        logical_config = {
            k: v for k, v in config.items() if k not in ("cache_policy", "timeout_seconds")
        }
        logical_id = digest({"image_sha256": sha, "config": logical_config, "runtime": runtime})
        with self.lock:
            if self.closed:
                raise ReviewError("Job worker is closing", 503)
            if config["cache_policy"] == "reuse_job":
                for identifier, job in self.jobs.items():
                    if job.get("logical_id") == logical_id and job["state"] == "needs_review":
                        try:
                            verify_manifest(self.root / identifier)
                        except (OSError, ValueError):
                            continue
                        return {
                            **self.status(identifier),
                            "cache_hit": True,
                            "execution": "existing_job_reuse; no inference run",
                        }
            if sum((j["state"] in ("uploaded", "processing") for j in self.jobs.values())) >= 3:
                raise ReviewError("Job queue is full", 429)
            identifier = (
                "Job_"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "_"
                + uuid.uuid4().hex[:10]
            )
            folder = self.root / identifier
            folder.mkdir()
            image = folder / ("source" + ext)
            try:
                image.write_bytes(data)
                decode(image)
            except Exception as error:
                shutil.rmtree(folder)
                raise ReviewError(
                    "The image could not be decoded. Use JPEG/PNG from 16×16 px to 40 MP.", 422
                ) from error
            record = {
                "schema_version": "playablesketch-job/1.0",
                "job_id": identifier,
                "state": "uploaded",
                "stage": "queued",
                "filename": name,
                "source_path": image.name,
                "source_sha256": sha,
                "logical_id": logical_id,
                "config": config,
                "runtime": runtime,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "parent_job_id": parent_job_id,
                "requires_review": True,
                "exported_revision_id": None,
            }
            self.jobs[identifier] = record
            self.cancel_flags[identifier] = threading.Event()
            self.persist(identifier)
            self.pool.submit(self.process, identifier)
            return {**deepcopy(record), "cache_hit": False}

    def process(self, identifier):
        folder = self.root / identifier
        flag = self.cancel_flags[identifier]
        with self.lock:
            if flag.is_set():
                return
            self.jobs[identifier].update(state="processing", stage="starting_worker")
            self.persist(identifier)
            config = deepcopy(self.jobs[identifier]["config"])
        process = None
        try:
            command = (
                self.worker_command(folder)
                if self.worker_command
                else [
                    sys.executable,
                    "-m",
                    "SketchPipeline.pipeline",
                    "worker",
                    "--job-dir",
                    str(folder),
                ]
            )
            with (folder / "worker.log").open("wb") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                start = time.monotonic()
                while process.poll() is None:
                    timed_out = time.monotonic() - start > config["timeout_seconds"]
                    if flag.wait(0.1) or timed_out:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2)
                        with self.lock:
                            self.jobs[identifier].update(
                                state="cancelled" if flag.is_set() else "failed",
                                stage="cancelled" if flag.is_set() else "timeout",
                                error=(
                                    "Cancelled by user"
                                    if flag.is_set()
                                    else "Processing timeout. Retry creates a new job."
                                ),
                            )
                            self.persist(identifier)
                        return
                if process.returncode != 0:
                    raise RuntimeError(f"Worker exited {process.returncode}; see worker.log")
            if flag.is_set():
                return
            manifest = verify_manifest(folder)
            self.register(identifier)
            with self.lock:
                if flag.is_set():
                    with self.store.lock:
                        self.store.cases.pop(identifier, None)
                    return
                self.jobs[identifier].update(
                    state="needs_review",
                    stage="topology_review",
                    execution_mode=manifest["execution_mode"],
                )
                self.persist(identifier)
        except Exception as error:
            with self.lock:
                if not flag.is_set():
                    self.jobs[identifier].update(
                        state="failed", stage="worker_failed", error=str(error)
                    )
                    self.persist(identifier)
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

    def status(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                raise ReviewError("Unknown job", 404)
            result = deepcopy(self.jobs[identifier])
        folder = self.root / identifier
        if result["state"] == "processing" and (folder / "progress.json").exists():
            result["progress"] = load_json(folder / "progress.json")
            result["stage"] = result["progress"]["stage"]
        if result["state"] == "needs_review":
            try:
                verify_manifest(folder)
                topology = self.store.latest(identifier)
                metric = self.metric.latest(identifier)
                result["case_id"] = identifier
                result["review_url"] = "/?case=" + identifier
                if topology and topology["status"] == "reviewed":
                    result["stage"] = "metric_review"
                    result["review_url"] = "/metric.html?case=" + identifier
                    if metric and metric["topology_revision_sha256"] == topology["revision_sha256"]:
                        result["current_metric_revision_id"] = metric["revision_id"]
                        result["metric_status"] = metric["draft"]["status"]
                        if metric["status"] == "accepted":
                            self.metric.sources(identifier)
                            result["state"] = (
                                "exported"
                                if result.get("exported_revision_id") == metric["revision_id"]
                                else "validated"
                            )
                            result["stage"] = "accepted"
                            result["accepted_revision_id"] = metric["revision_id"]
            except (ValueError, OSError, KeyError) as error:
                result.update(state="failed", stage="artifact_integrity", error=str(error))
        return result

    def cancel(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                raise ReviewError("Unknown job", 404)
            if self.jobs[identifier]["state"] not in ("uploaded", "processing"):
                raise ReviewError("Only active jobs can be cancelled", 409)
            self.cancel_flags[identifier].set()
            self.jobs[identifier].update(
                state="cancelled", stage="cancelled", error="Cancelled by user"
            )
            self.persist(identifier)
        return self.status(identifier)

    def retry(self, identifier):
        status = self.status(identifier)
        if status["state"] not in ("failed", "cancelled"):
            raise ReviewError("Retry is for failed/cancelled jobs", 409)
        if "config" not in status:
            raise ReviewError("Corrupt job metadata cannot be retried", 409)
        config = deepcopy(status["config"])
        config["cache_policy"] = "fresh"
        image = self.root / identifier / status["source_path"]
        if file_hash(image) != status["source_sha256"]:
            raise ReviewError("Retry source changed", 409)
        return self.start(image.read_bytes(), status["filename"], config, parent_job_id=identifier)

    def ready(self, identifier):
        status = self.status(identifier)
        if status["state"] not in ("needs_review", "validated", "exported"):
            raise ReviewError("Job is not ready for review", 409)
        return status

    def snapshot_metric(self, record):
        identifier = record["case_id"]
        folder = self.root / identifier
        verify_manifest(folder)
        parent = folder / "metric_revisions"
        parent.mkdir(exist_ok=True)
        destination = parent / record["revision_id"]
        pending = Path(tempfile.mkdtemp(prefix=".pending-metric-", dir=parent))
        try:
            documents = {
                "draft.json": record["draft"],
                "solver-report.json": record["report"],
                "corrections.json": record["state"],
            }
            if record["validated"] is not None:
                documents["accepted.json"] = record["validated"]
            for name, document in documents.items():
                atomic_json(pending / name, document)
            manifest = {
                "schema_version": "playablesketch-job-revision/1.0",
                "job_id": identifier,
                "metric_revision_id": record["revision_id"],
                "topology_revision_id": record["topology_revision_id"],
                "metric_review_sha256": record["sha256"],
                "metric_input_sha256": digest(record["state"]),
                "run_manifest_sha256": file_hash(folder / "manifest.json"),
                "stage_attempts": ["association", "solve", "semantics", "validation"],
                "acceptance": record["status"],
                "artifacts": {
                    name: artifact(
                        pending / name,
                        pending,
                        "metric_review",
                        record["revision_id"],
                        digest(record["state"]),
                    )
                    for name in documents
                },
            }
            atomic_json(pending / "manifest.json", manifest)
            pending.rename(destination)
        finally:
            shutil.rmtree(pending, ignore_errors=True)

    def export(self, identifier, revision_id):
        self.ready(identifier)
        if not isinstance(revision_id, str) or not re.fullmatch(
            "metric-[0-9TZ]+-[a-f0-9]{12}", revision_id
        ):
            raise ReviewError("Select an exact accepted metric revision", 409)
        layout = self.metric.export(identifier, revision_id)
        sources = self.metric.sources(identifier)
        observations = deepcopy(sources[3])
        observations["source"]["image_path"] = str(
            (sources[1].parent / observations["source"]["image_path"]).resolve()
        )
        folder = self.root / identifier
        exports = folder / "exports"
        exports.mkdir(exist_ok=True)
        target = exports / revision_id
        with self.lock:
            if not target.exists():
                pending = Path(tempfile.mkdtemp(prefix=".pending-export-", dir=exports))
                try:
                    for name, document in (
                        ("layout.json", layout),
                        ("observations.json", observations),
                    ):
                        atomic_json(pending / name, document)
                    report = self.metric.latest(identifier)
                    if report["revision_id"] != revision_id:
                        raise ReviewError("Metric revision changed during export", 409)
                    atomic_json(pending / "solver-report.json", report["report"])
                    receipt = {
                        "schema_version": "playablesketch-job-export/1.0",
                        "job_id": identifier,
                        "metric_revision_id": revision_id,
                        "accepted_layout_revision_id": layout["revision_id"],
                        "topology_revision_id": sources[2]["revision_id"],
                        "run_manifest_sha256": file_hash(folder / "manifest.json"),
                        "source_image_sha256": layout["source"]["image_sha256"],
                        "artifacts": {
                            name: artifact(pending / name, pending, "accepted_export", revision_id)
                            for name in ("layout.json", "observations.json", "solver-report.json")
                        },
                    }
                    atomic_json(pending / "manifest.json", receipt)
                    pending.rename(target)
                finally:
                    shutil.rmtree(pending, ignore_errors=True)
            receipt = load_json(target / "manifest.json")
            if (
                receipt.get("run_manifest_sha256") != file_hash(folder / "manifest.json")
                or receipt.get("source_image_sha256") != layout["source"]["image_sha256"]
                or receipt.get("schema_version") != "playablesketch-job-export/1.0"
                or (receipt.get("job_id") != identifier)
                or (receipt.get("metric_revision_id") != revision_id)
                or (
                    set(receipt.get("artifacts", {}))
                    != {"layout.json", "observations.json", "solver-report.json"}
                )
            ):
                raise ReviewError("Invalid accepted export manifest", 409)
            for name, entry in receipt["artifacts"].items():
                if entry["path"] != name or file_hash(target / name) != entry["sha256"]:
                    raise ReviewError("Published export integrity mismatch", 409)
            if load_json(target / "layout.json") != layout:
                raise ReviewError("Published export does not match selected snapshot", 409)
            self.jobs[identifier]["exported_revision_id"] = revision_id
            self.persist(identifier)
        return layout

    def close(self):
        with self.lock:
            self.closed = True
            for identifier, job in self.jobs.items():
                if job["state"] in ("uploaded", "processing"):
                    self.cancel_flags[identifier].set()
                    job.update(state="cancelled", stage="service_shutdown")
                    self.persist(identifier)
        self.pool.shutdown(wait=True)
