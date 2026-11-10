from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from SketchPipeline.preprocessing.prepare import decode, MAX_BYTES
from .contract import validate_authoring
from .decoder import authoring_document, boundary_graph
from .propose import PROFILE_NAMES
from .synthetic import write_json
from .errors import ShapeJobError
from .workspace import WorkspaceMixin
from .delivery import DeliveryMixin

ROOT = Path(__file__).resolve().parents[2]
IDENTIFIER = re.compile("^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    write_json(temporary, value)
    temporary.replace(path)


class ShapeJobs(DeliveryMixin, WorkspaceMixin):

    def __init__(
        self,
        root,
        timeout=45,
        python=None,
        profile="baseline",
        checkpoint=None,
        expected_sha256=None,
        normalize_ink=False,
    ):
        if profile not in PROFILE_NAMES:
            raise ShapeJobError("Unknown proposal profile")
        if (
            not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or (timeout > 300)
        ):
            raise ShapeJobError("Worker timeout must be between 0 and 300 seconds")
        model_config = {"normalize_ink": bool(normalize_ink)}
        if checkpoint is not None:
            path = Path(checkpoint).resolve()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected_sha256 and digest != expected_sha256:
                raise ShapeJobError("Shape model checksum mismatch")
            model_config.update(checkpoint=str(path), expected_sha256=digest)
        elif expected_sha256 is not None:
            raise ShapeJobError("A checksum requires an explicit checkpoint")
        if profile == "hybrid":
            from .hybrid_model import validate_package, DEFAULT_PACKAGE

            try:
                package = checkpoint or DEFAULT_PACKAGE
                _, _, digest = validate_package(package, expected_sha256)
            except (OSError, ValueError, KeyError) as error:
                raise ShapeJobError(str(error)) from error
            if normalize_ink:
                raise ShapeJobError("Hybrid inference uses its own trained input features")
            model_config.update(checkpoint=str(Path(package).resolve()), expected_sha256=digest)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.python = python or sys.executable
        self.profile = profile
        self.model_config = model_config
        self.lock = threading.RLock()
        self.jobs = {}
        self.processes = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shape-proposals")
        for path in self.root.glob("shape_*/job.json"):
            record = json.loads(path.read_text())
            if record["status"] in ("queued", "processing"):
                record.update(
                    status="interrupted",
                    failure="Server stopped; retry to analyze the retained source.",
                )
                atomic_json(path, record)
            self.jobs[record["job_id"]] = record

    def folder(self, identifier):
        if identifier not in self.jobs:
            raise ShapeJobError("Unknown shape job", 404)
        return self.root / identifier

    def status(self, identifier):
        with self.lock:
            return copy.deepcopy(self.jobs[self.folder(identifier).name])

    def _persist(self, record):
        atomic_json(self.root / record["job_id"] / "job.json", record)

    def start(self, data, filename, backend="learned"):
        if backend not in ("learned", "classical", "manual"):
            raise ShapeJobError("Unknown shape backend")
        filename = Path(str(filename).replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg") or not data or len(data) > MAX_BYTES:
            raise ShapeJobError("Upload a JPEG or PNG up to 20 MB", 413)
        with self.lock:
            if sum((j["status"] in ("queued", "processing") for j in self.jobs.values())) >= 3:
                raise ShapeJobError("The analysis queue is full", 429)
            identifier = "shape_" + uuid.uuid4().hex
            folder = self.root / identifier
            folder.mkdir()
            source = folder / ("source" + suffix)
            source.write_bytes(data)
            try:
                decode(source)
            except Exception:
                source.unlink()
                folder.rmdir()
                raise ShapeJobError("The file is not a readable JPEG or PNG")
            record = {
                "schema_version": "shape-job/1.0",
                "mode": "shape-first/1.0",
                "job_id": identifier,
                "filename": filename,
                "backend": backend,
                "status": "queued",
                "attempt": 1,
                "profile": self.profile,
                "model_config": copy.deepcopy(self.model_config),
                "source_name": source.name,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "created_at_unix": time.time(),
                "failure": None,
                "manual_available": False,
            }
            self.jobs[identifier] = record
            self._persist(record)
            self.pool.submit(self._execute, identifier)
            return copy.deepcopy(record)

    def _execute(self, identifier):
        with self.lock:
            record = self.jobs[identifier]
            if record["status"] == "cancelled":
                return
            record.update(status="processing", failure=None)
            self._persist(record)
            from .job_context import analysis_context

            record["mode"] = "shape-first/1.0"
            record["analysis_context"] = analysis_context(record)
            atomic_json(
                self.root / identifier / f"attempt-{record['attempt']}-context.json",
                record["analysis_context"],
            )
            self._persist(record)
            folder = self.folder(identifier)
            output = folder / f"attempt_{record['attempt']}"
            command = [
                self.python,
                "-m",
                "SketchPipeline.shape_authoring.propose",
                "--image",
                str(folder / record["source_name"]),
                "--output",
                str(output),
                "--backend",
                record["backend"],
                "--profile",
                record.get("profile", "baseline"),
            ]
            config = record.get("model_config", {})
            if config.get("checkpoint"):
                command.extend(
                    [
                        "--checkpoint",
                        config["checkpoint"],
                        "--expected-sha256",
                        config["expected_sha256"],
                    ]
                )
            if config.get("normalize_ink"):
                command.append("--normalize-ink")
            started = time.perf_counter()
            failure = None
            process = None
            stdout = b""
            stderr = b""
            try:
                process = subprocess.Popen(
                    command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                self.processes[identifier] = process
            except OSError as error:
                failure = f"Worker unavailable: {error}"
        if process is not None:
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                if process.returncode:
                    failure = "Worker failed: " + stderr.decode(errors="replace")[-1500:]
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                failure = f"Model timeout after {self.timeout:g} seconds"
        with self.lock:
            cancelled = record["status"] == "cancelled"
        if cancelled or failure:
            from .propose import run

            fallback = folder / f"manual_{record['attempt']}"
            run(
                folder / record["source_name"],
                fallback,
                "manual",
                reason="Cancelled by user" if cancelled else failure,
            )
            output = fallback
        result = json.loads((output / "proposals.json").read_text())
        (folder / f"attempt_{record['attempt']}.stdout.log").write_bytes(stdout)
        (folder / f"attempt_{record['attempt']}.stderr.log").write_bytes(stderr)
        with self.lock:
            self.processes.pop(identifier, None)
            record.update(
                status="cancelled" if cancelled else result["status"],
                failure=failure or result["failure"],
                output_directory=output.name,
                elapsed_seconds=time.perf_counter() - started,
                manual_available=True,
                authoring_revision_id=result["authoring_revision_id"],
            )
            self._persist(record)

    def cancel(self, identifier):
        with self.lock:
            record = self.jobs[self.folder(identifier).name]
            if record["status"] not in ("queued", "processing"):
                return copy.deepcopy(record)
            was_queued = record["status"] == "queued"
            record["status"] = "cancelled"
            self._persist(record)
            process = self.processes.get(identifier)
            if process is not None:
                process.kill()
            if was_queued:
                self.pool.submit(self._queued_manual, identifier)
            return copy.deepcopy(record)

    def _queued_manual(self, identifier):
        from .propose import run

        folder = self.folder(identifier)
        record = self.jobs[identifier]
        output = folder / f"manual_{record['attempt']}"
        result = run(folder / record["source_name"], output, "manual", reason="Cancelled by user")
        with self.lock:
            record.update(
                output_directory=output.name,
                manual_available=True,
                authoring_revision_id=result["authoring_revision_id"],
            )
            self._persist(record)

    def retry(self, identifier):
        with self.lock:
            record = self.jobs[self.folder(identifier).name]
            if record["status"] in ("queued", "processing") or identifier in self.processes:
                raise ShapeJobError("Analysis is still running", 409)
            if record["status"] == "cancelled" and (not record.get("manual_available")):
                raise ShapeJobError("Cancellation is still preparing the manual plan", 409)
            if (self.folder(identifier) / "draft-latest.json").exists() or (
                self.folder(identifier) / "sizing-latest.json"
            ).exists():
                raise ShapeJobError(
                    "This job contains manual edits. Start a new job to preserve them.", 409
                )
            record.update(
                status="queued", attempt=record["attempt"] + 1, failure=None, manual_available=False
            )
            self._persist(record)
            self.pool.submit(self._execute, identifier)
            return copy.deepcopy(record)

    def proposals(self, identifier):
        with self.lock:
            record = self.jobs[self.folder(identifier).name]
            if not record.get("manual_available"):
                raise ShapeJobError("Analysis is not ready", 409)
            folder = self.folder(identifier)
            result = json.loads(
                (folder / record["output_directory"] / "proposals.json").read_text()
            )
            pointer = folder / "draft-latest.json"
            if pointer.exists():
                draft = json.loads(pointer.read_text())
                result["authoring"] = draft["authoring"]
                result["edit_state"] = draft["edit_state"]
                result["edit_diagnostics"] = draft["diagnostics"]
                result["authoring_revision_id"] = draft["authoring"]["revision_id"]
            return result

    def image(self, identifier):
        record = self.status(identifier)
        if not record.get("manual_available"):
            raise ShapeJobError("Image is not ready", 409)
        return (self.folder(identifier) / record["output_directory"] / "working.png").read_bytes()

    def sizing_preview(self, identifier):
        from .sizing import topology_key

        with self.lock:
            current = self.proposals(identifier)["authoring"]
            path = self.folder(identifier) / "sizing-latest.json"
            if not path.exists():
                return {"status": "not_sized", "topology_revision_id": current["revision_id"]}
            result = json.loads(path.read_text())
            if result["topology_key"] != topology_key(current):
                result["status"] = "needs_attention"
                result["preview_is_stale"] = True
                result["issues"] = [
                    {
                        "code": "topology_changed",
                        "message": "The plan changed. Review size bindings before applying previous choices.",
                        "entity_ids": [],
                    }
                ]
            return result

    def sizing(self, identifier, body):
        from .sizing import recompute

        with self.lock:
            current = self.proposals(identifier)["authoring"]
            folder = self.folder(identifier)
            if body.get("base_revision_id") != current["revision_id"]:
                raise ShapeJobError("The plan changed. Reload before changing sizes.", 409)
            path = folder / "sizing-latest.json"
            previous = json.loads(path.read_text()) if path.exists() else None
            expected = previous["authoring"]["revision_id"] if previous else None
            if body.get("base_sizing_revision_id") != expected:
                raise ShapeJobError("Sizes changed. Reload before saving.", 409)
            if set(body) - {"base_revision_id", "base_sizing_revision_id", "request"}:
                raise ShapeJobError("Unknown sizing request field")
            result = recompute(current, body.get("request", {}), previous)
            if result["authoring"]["revision_id"] == current["revision_id"]:
                result["authoring"]["parent_revision_id"] = current["revision_id"]
                result["authoring"]["revision_id"] = "sizing_" + uuid.uuid4().hex
                result["authoring"]["physical_design"]["acceptance"] = {
                    "status": "pending",
                    "revision_id": None,
                    "reviewer": None,
                }
            atomic_json(
                folder
                / (result["authoring"]["revision_id"] + "-" + uuid.uuid4().hex + "-sizes.json"),
                result,
            )
            atomic_json(path, result)
            return result

    def edit(self, identifier, body):
        with self.lock:
            current = self.proposals(identifier)
            base = current["authoring"]
            if body.get("base_revision_id") != base["revision_id"]:
                raise ShapeJobError("Draft changed. Reload before saving.", 409)
            boxes = body.get("boxes")
            openings = body.get("openings", [])
            if (
                not isinstance(boxes, list)
                or len(boxes) > 200
                or (not isinstance(openings, list))
                or (len(openings) > 400)
            ):
                raise ShapeJobError("Invalid edit collections")
            width, height = base["image_evidence"]["working_size_px"]
            seen = set()
            for box in boxes:
                if (
                    not {"id", "type", "bounds_px"} <= set(box)
                    or set(box) - {"id", "type", "bounds_px", "points_px"}
                    or box["type"]
                    not in (
                        "room",
                        "corridor_segment",
                    )
                ):
                    raise ShapeJobError("Each region needs an ID, type and rectangular bounds")
                if (
                    not isinstance(box["id"], str)
                    or not IDENTIFIER.fullmatch(box["id"])
                    or box["id"] in seen
                ):
                    raise ShapeJobError("Region IDs must be unique")
                seen.add(box["id"])
                bounds = box["bounds_px"]
                if (
                    not isinstance(bounds, list)
                    or len(bounds) != 4
                    or any(
                        (
                            isinstance(v, bool)
                            or not isinstance(v, (float, int))
                            or (not math.isfinite(v))
                            for v in bounds
                        )
                    )
                ):
                    raise ShapeJobError("Finite rectangular coordinates required")
                x, y, X, Y = bounds
                if not (0 <= x < X <= width and 0 <= y < Y <= height):
                    raise ShapeJobError("Rectangle lies outside the image")
                if "points_px" in box:
                    from shapely.geometry import Polygon

                    raw_points = box["points_px"]
                    if not isinstance(raw_points, list) or not 4 <= len(raw_points) <= 64:
                        raise ShapeJobError("A room needs 4 to 64 orthogonal corners")
                    try:
                        points = [np_points([p, p])[0] for p in raw_points]
                        polygon = Polygon(points)
                    except (TypeError, ValueError):
                        raise ShapeJobError("Finite room corner coordinates required")
                    if (
                        not polygon.is_valid
                        or polygon.area <= 0
                        or list(polygon.bounds) != bounds
                        or any(
                            a == b or a[0] != b[0] and a[1] != b[1]
                            for a, b in zip(points, points[1:] + points[:1])
                        )
                    ):
                        raise ShapeJobError(
                            "Room corners must form a simple orthogonal polygon within its bounds"
                        )
            from shapely.geometry import Polygon
            from .room_geometry import polygon_points

            polygons = [Polygon(polygon_points(box)) for box in boxes]
            for i, polygon in enumerate(polygons):
                if any(polygon.intersection(other).area > 1e-9 for other in polygons[i + 1 :]):
                    raise ShapeJobError("Region interiors overlap")
            segments, _ = boundary_graph(boxes)
            proposals = []
            unresolved = []
            opening_ids = set()
            for opening in openings:
                if set(opening) != {"id", "type", "entity_ids", "points_px"} or opening[
                    "type"
                ] not in ("door", "open_passage"):
                    raise ShapeJobError("Invalid opening edit")
                if (
                    not isinstance(opening["id"], str)
                    or not IDENTIFIER.fullmatch(opening["id"])
                    or opening["id"] in opening_ids
                ):
                    raise ShapeJobError("Opening IDs must be unique")
                opening_ids.add(opening["id"])
                points = np_points(opening["points_px"])
                owners = opening["entity_ids"]
                if not isinstance(owners, list) or len(owners) != 2 or len(set(owners)) != 2:
                    raise ShapeJobError("Choose two regions for the opening")
                match = None
                original = next(
                    (o for o in base["topology"]["openings"] if o["id"] == opening["id"]), None
                )
                raster_tolerance = (
                    1.1 if original and original["geometry"]["points_px"] == points else 0.01
                )
                for key, indices in segments.items():
                    if {boxes[i]["id"] for i in indices} != set(owners) or len(indices) != 2:
                        continue
                    axis = 0 if key[0][1] == key[1][1] else 1
                    if all(
                        (
                            abs(p[1 - axis] - key[0][1 - axis]) < raster_tolerance
                            and key[0][axis] <= p[axis] <= key[1][axis]
                            for p in points
                        )
                    ):
                        match = (key, indices, axis)
                        break
                if match is None:
                    unresolved.append(
                        {
                            "id": opening["id"],
                            "message": "This opening no longer fits on its shared wall.",
                        }
                    )
                    continue
                key, indices, axis = match
                p, q = sorted(points, key=lambda p: p[axis])
                p, q = (copy.deepcopy(p), copy.deepcopy(q))
                p[1 - axis] = q[1 - axis] = key[0][1 - axis]
                if p == q:
                    raise ShapeJobError("Opening length must be positive")
                if any(
                    (
                        old["segment"] == key
                        and min(old["end"][axis], q[axis]) > max(old["start"][axis], p[axis])
                        for old in proposals
                    )
                ):
                    raise ShapeJobError("Openings on the same wall overlap")
                proposals.append(
                    {
                        "id": opening["id"],
                        "segment": key,
                        "entity_indices": indices,
                        "start": p,
                        "end": q,
                        "type": opening["type"],
                    }
                )
            document = authoring_document(
                base["image_evidence"]["source"],
                current["preprocessing"],
                boxes,
                proposals,
                origin="user",
            )
            document = preserve_ids(document, base, boxes, proposals)
            document["document_id"] = base["document_id"]
            document["parent_revision_id"] = base["revision_id"]
            document["revision_id"] = "edit_" + uuid.uuid4().hex
            if validate_authoring(document):
                raise ShapeJobError("Edited plan violates the authoring contract")
            diagnostics = unresolved
            draft = {
                "authoring": document,
                "edit_state": {"boxes": boxes, "openings": openings},
                "diagnostics": diagnostics,
                "saved_at_unix": time.time(),
                "correction_telemetry": body.get("correction_telemetry"),
            }
            folder = self.folder(identifier)
            atomic_json(folder / (document["revision_id"] + ".json"), draft)
            atomic_json(folder / "draft-latest.json", draft)
            return draft

    def close(self):
        with self.lock:
            for process in self.processes.values():
                process.kill()
        self.pool.shutdown(wait=True, cancel_futures=True)


def np_points(value):
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any((not isinstance(p, list) or len(p) != 2 for p in value))
    ):
        raise ShapeJobError("Opening requires two endpoints")
    if any(
        (
            isinstance(v, bool) or not isinstance(v, (float, int)) or (not math.isfinite(v))
            for p in value
            for v in p
        )
    ):
        raise ShapeJobError("Opening endpoints must be finite")
    return value


def preserve_ids(document, base, boxes, proposals):

    def remap(value, mapping):
        if isinstance(value, dict):
            return {k: remap(v, mapping) for k, v in value.items()}
        if isinstance(value, list):
            return [remap(v, mapping) for v in value]
        return mapping.get(value, value) if isinstance(value, str) else value

    top = document["topology"]
    old = base["topology"]
    mapping = {r["id"]: b["id"] for r, b in zip(top["regions"], boxes)}
    mapping.update({o["id"]: p["id"] for o, p in zip(top["openings"], proposals)})
    document = remap(document, mapping)
    top = document["topology"]

    def wall_signatures(topology):
        junctions = {j["id"]: j["geometry"]["points_px"][0] for j in topology["junctions"]}
        regions = {r["id"]: r for r in topology["regions"]}
        signatures = {}
        for wall in topology["walls"]:
            a, b = [junctions[wall[k]] for k in ("start_junction_id", "end_junction_id")]
            axis = 0 if a[1] == b[1] else 1
            sides = []
            for owner in wall["entity_ids"]:
                points = regions[owner]["geometry"]["points_px"]
                normal = 1 - axis
                low = min((p[normal] for p in points))
                high = max((p[normal] for p in points))
                side = (
                    "min"
                    if abs(a[normal] - low) < 0.01
                    else "max" if abs(a[normal] - high) < 0.01 else "interior"
                )
                sides.append((owner, side))
            signature = (axis, tuple(sorted(sides)))
            signatures.setdefault(signature, []).append(wall["id"])
        return signatures

    old_signatures = wall_signatures(old)
    new_signatures = wall_signatures(top)
    wall_mapping = {}
    for signature, ids in new_signatures.items():
        previous = old_signatures.get(signature, [])
        for identifier in ids:
            wall_mapping[identifier] = (
                previous[0] if len(ids) == len(previous) == 1 else "wall_" + uuid.uuid4().hex
            )
    document = remap(document, wall_mapping)
    top = document["topology"]
    old_connections = {tuple(sorted(c["entity_ids"])): c["id"] for c in old["connections"]}
    document = remap(
        document,
        {
            c["id"]: old_connections.get(
                tuple(sorted(c["entity_ids"])), "connection_" + uuid.uuid4().hex
            )
            for c in top["connections"]
        },
    )
    top = document["topology"]

    def node_signatures(topology):
        result = {j["id"]: [] for j in topology["junctions"]}
        for wall in topology["walls"]:
            result[wall["start_junction_id"]].append((wall["id"], "start"))
            result[wall["end_junction_id"]].append((wall["id"], "end"))
        return {tuple(sorted(incident)): identifier for identifier, incident in result.items()}

    old_nodes = node_signatures(old)
    new_nodes = node_signatures(top)
    document = remap(
        document,
        {
            identifier: old_nodes.get(signature, "junction_" + uuid.uuid4().hex)
            for signature, identifier in new_nodes.items()
        },
    )
    document["image_evidence"]["items"] = copy.deepcopy(base["image_evidence"]["items"])
    for key, values in document["topology"].items():
        previous = {v["id"]: v for v in old[key]}
        for entity in values:
            original = previous.get(entity["id"])
            if original and original["geometry"]["points_px"] == entity["geometry"]["points_px"]:
                entity["geometry"] = copy.deepcopy(original["geometry"])
    return document
