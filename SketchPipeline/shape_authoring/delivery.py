import copy
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import hashlib
import io
import json
import re
import shutil
import uuid
import zipfile
from .contract import validate_authoring
from .errors import ShapeJobError
from .names import region_names
from .sizing import digest
from SketchPipeline.validation.validate import as_validated, validate_document, load_json

AGENT = {"radius_cm": 40.0, "half_height_cm": 90.0, "clearance_cm": 10.0}
REVISION = re.compile("^metric-[0-9TZ]+-[a-f0-9]{12}$")


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def gameplay_preflight(draft):
    if draft["validation_mode"] != "gameplay":
        return {"requested": False, "passed": None, "engine_checks": "not_run", "agent": AGENT}
    from shapely.geometry import box, Point
    from shapely.ops import unary_union

    layout = draft["layout"]
    points = {v["id"]: v["position_cm"] for v in layout["vertices"]}
    bounds = {}
    for r in layout["rooms"] + layout["corridors"]:
        p = [points[i] for i in r["boundary_vertex_ids"]]
        bounds[r["id"]] = (
            min((p[0] for p in p)),
            min((p[1] for p in p)),
            max((p[0] for p in p)),
            max((p[1] for p in p)),
        )
    obstacles = []
    required_height = 2 * AGENT["half_height_cm"] + AGENT["clearance_cm"]
    for wall in layout["walls"]:
        a, b = [points[wall[k]] for k in ("start_vertex_id", "end_vertex_id")]
        axis = 0 if wall["axis"] == "x" else 1
        length = b[axis] - a[axis]
        half = wall["thickness_cm"] / 2
        intervals = sorted(
            (
                (
                    o["center_offset_cm"] - o["clear_width_cm"] / 2,
                    o["center_offset_cm"] + o["clear_width_cm"] / 2,
                )
                for o in layout["openings"]
                if o["wall_id"] == wall["id"] and o["clear_height_cm"] >= required_height
            )
        )
        solid = []
        position = 0.0
        for lo, hi in intervals:
            if lo > position:
                solid.append((position, lo))
            position = max(position, hi)
        if position < length:
            solid.append((position, length))
        for lo, hi in solid:
            obstacles.append(
                box(a[0] + lo, a[1] - half, a[0] + hi, a[1] + half)
                if axis == 0
                else box(a[0] - half, a[1] + lo, a[0] + half, a[1] + hi)
            )
    radius = AGENT["radius_cm"] + AGENT["clearance_cm"]
    floor = unary_union([box(*b) for b in bounds.values()])
    safe = floor.buffer(-radius, join_style=2)
    if obstacles:
        safe = safe.difference(unary_union(obstacles).buffer(radius, join_style=2))
    parts = list(safe.geoms) if hasattr(safe, "geoms") else [safe]
    centers = {r: Point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for r, b in bounds.items()}
    start = draft["start_room_id"]
    room_ids = [r["id"] for r in layout["rooms"]]
    component = next((p for p in parts if p.covers(centers[start])), None)
    blocked = [r for r in room_ids if component is None or not component.covers(centers[r])]
    return {
        "requested": True,
        "passed": not blocked,
        "blocked_room_ids": blocked,
        "agent": AGENT,
        "required_height_cm": required_height,
        "method": "Conservative rectangle-floor support and inflated 2D wall union, room-center connectivity. Runtime collision/grid/Pawn checks still required.",
        "engine_checks": "not_run",
    }


def prepare_draft(preview, authoring, state):
    draft = copy.deepcopy(preview["canonical"])
    draft.update(
        revision_id=authoring["revision_id"], parent_revision_id=authoring["parent_revision_id"]
    )
    mode = state.get("validation_mode", "geometry_only")
    if mode not in ("geometry_only", "gameplay"):
        raise ShapeJobError("Choose geometry-only or playable delivery.")
    draft["validation_mode"] = mode
    names = region_names(authoring["topology"]["regions"])
    for r in draft["layout"]["rooms"] + draft["layout"]["corridors"]:
        source_id = preview.get("region_sources", {}).get(r["id"], r["id"])
        r["name"] = state["names"].get(source_id, names[source_id])
        r["role"] = "none"
    draft["start_room_id"] = state.get("start_room_id")
    draft["goal_room_id"] = state.get("goal_room_id")
    for r in draft["layout"]["rooms"]:
        if r["id"] == draft["start_room_id"]:
            r["role"] = "start"
        if r["id"] == draft["goal_room_id"]:
            r["role"] = "goal"
    check = validate_document(draft)
    if not check["metric_valid"]:
        raise ShapeJobError(
            "Review Start/Goal, connectivity and plan geometry before confirming. "
            + "; ".join((i["message"] for i in check["issues"]))
        )
    preflight = gameplay_preflight(draft)
    if preflight.get("passed") is False:
        raise ShapeJobError(
            "This plan does not have enough player clearance between the selected rooms. Widen the route or choose geometry-only delivery."
        )
    return (draft, preflight)


def payload(record):
    return {
        k: record[k]
        for k in [
            "schema_version",
            "authoring",
            "canonical_draft",
            "workspace_state",
            "source_bindings",
            "agent_preflight",
        ]
    }


def multipart(data, content_type):
    if (
        not content_type.startswith("multipart/form-data;")
        or len(content_type) > 500
        or "\r" in content_type
        or ("\n" in content_type)
    ):
        raise ShapeJobError("Use a multipart image upload.", 415)
    message = BytesParser(policy=default).parsebytes(
        ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + data
    )
    fields = {}
    if not message.is_multipart():
        raise ShapeJobError("Invalid multipart upload.")
    for part in message.iter_parts():
        key = part.get_param("name", header="content-disposition")
        if key not in ("image", "config") or key in fields or part.is_multipart():
            raise ShapeJobError("Expected one image and optional mode configuration.")
        fields[key] = (part.get_payload(decode=True), part.get_filename())
    if "image" not in fields or not fields["image"][1]:
        raise ShapeJobError("Choose an image.")
    if "config" in fields:
        config = json.loads(fields["config"][0])
        if (
            not isinstance(config, dict)
            or set(config) - {"mode"}
            or config.get("mode", "inference") not in ("inference", "shape-first")
        ):
            raise ShapeJobError(
                "Runtime uploads use shape-first mode; model settings are server-owned."
            )
    return fields["image"]


class DeliveryMixin:

    def runtime_alias(self, identifier):
        with self.lock:
            record = self.jobs[self.folder(identifier).name]
            if not record.get("runtime_job_id"):
                record["runtime_job_id"] = (
                    "Job_"
                    + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    + "_"
                    + uuid.uuid4().hex[:10]
                )
                self._persist(record)
            return record["runtime_job_id"]

    def resolve_runtime(self, alias):
        with self.lock:
            if alias in self.jobs:
                return alias
            for identifier, r in self.jobs.items():
                if r.get("runtime_job_id") == alias:
                    return identifier
        raise ShapeJobError("Unknown runtime job.", 404)

    def approved_snapshot(self, identifier, confirmation_id=None):
        current = self.workspace(identifier)
        confirmation = current["confirmation"]
        if not confirmation or (
            confirmation_id is not None and confirmation["confirmation_id"] != confirmation_id
        ):
            raise ShapeJobError(
                "The plan changed or has not been confirmed. Review and confirm the current plan.",
                409,
            )
        if confirmation.get("schema_version") != "shape-confirmed-snapshot/1.0":
            raise ShapeJobError("Confirm this plan again to enable validated delivery.", 409)
        if digest(payload(confirmation)) != confirmation.get("snapshot_sha256"):
            raise ShapeJobError("The confirmed snapshot failed its integrity check.", 409)
        proposal = self.proposals(identifier)["authoring"]
        sizing = self.sizing_preview(identifier)
        expected = {
            "topology": digest(proposal),
            "sizing": digest(sizing),
            "workspace": digest(current["state"]),
        }
        if expected != confirmation["source_bindings"]:
            raise ShapeJobError(
                "The saved plan or sizes changed. Confirm the current snapshot again.", 409
            )
        record = self.jobs[identifier]
        source = self.folder(identifier) / record["source_name"]
        actual = checksum(source.read_bytes())
        if (
            actual != record["source_sha256"]
            or actual != confirmation["authoring"]["image_evidence"]["source"]["image_sha256"]
        ):
            raise ShapeJobError("The original image changed. Start a new analysis.", 409)
        if validate_authoring(confirmation["authoring"]):
            raise ShapeJobError("The confirmed authoring document is invalid.", 409)
        return confirmation

    def export_plan(self, identifier, body):
        from .jobs import atomic_json

        with self.lock:
            confirmation = self.approved_snapshot(identifier, body.get("confirmation_id"))
            if not body.get("confirmation_id"):
                raise ShapeJobError("Choose the exact confirmed plan.", 409)
            mode = confirmation["canonical_draft"]["validation_mode"]
            if body.get("validation_mode", mode) != mode:
                raise ShapeJobError("Delivery mode changed. Review and confirm it first.", 409)
            draft = copy.deepcopy(confirmation["canonical_draft"])
            check = validate_document(draft)
            preflight = gameplay_preflight(draft)
            if not check["metric_valid"] or preflight.get("passed") is False:
                raise ShapeJobError(
                    "The confirmed geometry or player clearance is no longer valid.", 409
                )
            folder = self.folder(identifier)
            index_path = folder / "exports/index.json"
            index = load_json(index_path) if index_path.exists() else {}
            cid = confirmation["confirmation_id"]
            if cid in index:
                self._export_files(identifier, index[cid]["revision_id"])
                self.select_export(identifier, index[cid])
                return copy.deepcopy(index[cid])
            revision = (
                "metric-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + digest({"snapshot": confirmation["snapshot_sha256"], "mode": mode})[:12]
            )
            draft["parent_revision_id"] = draft["revision_id"]
            draft["revision_id"] = revision
            canonical = as_validated(draft, "Local user")
            if not validate_document(canonical)["exportable"]:
                raise ShapeJobError("Strict canonical export failed.", 409)
            directory = folder / "exports" / revision
            temporary = folder / ("export-staging-" + uuid.uuid4().hex)
            temporary.mkdir()
            canonical_bytes = encoded(canonical)
            authoring_bytes = encoded(confirmation["authoring"])
            if len(canonical_bytes) > 2 * 1024 * 1024:
                shutil.rmtree(temporary)
                raise ShapeJobError("This layout exceeds the runtime import size limit.")
            manifest = {
                "schema_version": "shape-export-bundle/1.0",
                "confirmation_id": cid,
                "snapshot_sha256": confirmation["snapshot_sha256"],
                "source_sha256": canonical["source"]["image_sha256"],
                "shape_job_id": identifier,
                "runtime_job_id": self.runtime_alias(identifier),
                "runtime_revision_id": revision,
                "canonical_revision_id": canonical["revision_id"],
                "authoring_revision_id": confirmation["authoring"]["revision_id"],
                "validation_mode": mode,
                "provenance": "Design presets, proportions and user choices, never image ground-truth measurements. No OCR observations were fabricated.",
                "model": self.proposals(identifier).get("model"),
                "analysis_context": self.jobs[identifier].get("analysis_context"),
                "preflight": preflight,
                "engine_geometry": "not_run",
                "navigation": "not_run",
                "automatic_training_ingestion": False,
                "files": {
                    "validated-layout.json": checksum(canonical_bytes),
                    "authoring.json": checksum(authoring_bytes),
                },
            }
            manifest_bytes = encoded(manifest)
            readme = b"PlayableSketch Unreal bundle\n\nImport validated-layout.json with the existing canonical Unreal importer.\nAuthoring and manifest preserve design provenance; no source image or OCR file is required to generate this metric plan.\nGeometry-only exports do not promise playability. Gameplay preflight is conservative; Unreal still checks actual geometry, collision and Pawn traversal.\n"
            try:
                (temporary / "validated-layout.json").write_bytes(canonical_bytes)
                (temporary / "authoring.json").write_bytes(authoring_bytes)
                (temporary / "manifest.json").write_bytes(manifest_bytes)
                memory = io.BytesIO()
                with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in [
                        ("validated-layout.json", canonical_bytes),
                        ("authoring.json", authoring_bytes),
                        ("manifest.json", manifest_bytes),
                        ("README.txt", readme),
                    ]:
                        archive.writestr(
                            zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data
                        )
                bundle = memory.getvalue()
                (temporary / "unreal-bundle.zip").write_bytes(bundle)
                result = {
                    "schema_version": "shape-export-record/1.0",
                    "confirmation_id": cid,
                    "revision_id": revision,
                    "runtime_job_id": manifest["runtime_job_id"],
                    "validation_mode": mode,
                    "canonical_sha256": checksum(canonical_bytes),
                    "bundle_sha256": checksum(bundle),
                    "manifest_sha256": checksum(manifest_bytes),
                    "snapshot_sha256": confirmation["snapshot_sha256"],
                    "delivery_ready": True,
                    "engine_checks": "not_run",
                    "download_url": f"/shape-jobs/{identifier}/bundle?revision_id={revision}",
                    "layout_url": f"/shape-jobs/{identifier}/layout?revision_id={revision}",
                }
                (temporary / "export-record.json").write_bytes(encoded(result))
                directory.parent.mkdir(exist_ok=True)
                temporary.rename(directory)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
            index[cid] = result
            atomic_json(index_path, index)
            self.select_export(identifier, result)
            return copy.deepcopy(result)

    def _export_files(self, identifier, revision):
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise ShapeJobError("Choose an explicit export revision.", 409)
        confirmation = self.approved_snapshot(identifier)
        folder = self.folder(identifier) / "exports" / revision
        if not (folder / "export-record.json").exists():
            raise ShapeJobError("Unknown export revision.", 404)
        record = load_json(folder / "export-record.json")
        if (
            record["confirmation_id"] != confirmation["confirmation_id"]
            or record["snapshot_sha256"] != confirmation["snapshot_sha256"]
        ):
            raise ShapeJobError(
                "This export belongs to an older plan. Export the newly confirmed snapshot.", 409
            )
        for filename, key in [
            ("validated-layout.json", "canonical_sha256"),
            ("unreal-bundle.zip", "bundle_sha256"),
            ("manifest.json", "manifest_sha256"),
        ]:
            if checksum((folder / filename).read_bytes()) != record[key]:
                raise ShapeJobError("The saved export failed its checksum.", 409)
        canonical = load_json(folder / "validated-layout.json")
        if not validate_document(canonical)["exportable"]:
            raise ShapeJobError("The saved canonical layout is invalid.", 409)
        return (folder, record, canonical)

    def selected_layout(self, identifier, revision):
        with self.lock:
            return copy.deepcopy(self._export_files(identifier, revision)[2])

    def selected_layout_bytes(self, identifier, revision):
        with self.lock:
            return (
                self._export_files(identifier, revision)[0] / "validated-layout.json"
            ).read_bytes()

    def export_bundle(self, identifier, revision):
        with self.lock:
            return (self._export_files(identifier, revision)[0] / "unreal-bundle.zip").read_bytes()

    def select_export(self, identifier, record):
        from .jobs import atomic_json

        atomic_json(self.root / "runtime-selection.json", {"shape_job_id": identifier, **record})

    def runtime_selection(self):
        with self.lock:
            path = self.root / "runtime-selection.json"
            if not path.exists():
                raise ShapeJobError("Export a confirmed plan first.", 409)
            record = load_json(path)
            self._export_files(record["shape_job_id"], record["revision_id"])
            return record

    def runtime_status(self, alias):
        with self.lock:
            identifier = self.resolve_runtime(alias)
            record = self.status(identifier)
            accepted = None
            if record.get("manual_available"):
                current = self.workspace(identifier)["confirmation"]
                index_path = self.folder(identifier) / "exports/index.json"
                if current and index_path.exists():
                    accepted = load_json(index_path).get(current["confirmation_id"])
                if accepted:
                    self._export_files(identifier, accepted["revision_id"])
            return {
                "job_id": self.runtime_alias(identifier),
                "shape_job_id": identifier,
                "mode": "shape-first/1.0",
                "state": (
                    "exported"
                    if accepted
                    else (
                        "processing"
                        if record["status"] in ("queued", "processing")
                        else "needs_review"
                    )
                ),
                "stage": "shape-first",
                "accepted_revision_id": accepted["revision_id"] if accepted else None,
                "error": record.get("failure") or "",
            }
