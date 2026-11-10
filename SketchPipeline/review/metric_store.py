from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid
from jsonschema import ValidationError
from SketchPipeline.association.associate import span_catalog, transform_points
from SketchPipeline.evaluation.review import validate_telemetry
from SketchPipeline.association.topology import load_review
from SketchPipeline.metric import reconstruct
from SketchPipeline.review.server import ReviewError, atomic_json, digest
from SketchPipeline.validation.validate import load_json, validate_document, as_validated

VERSION = "playablesketch-metric-review/1.0"


class MetricReviewStore:

    def __init__(self, topology_store):
        self.topology = topology_store
        self.output = topology_store.output / "metric"

    def sources(self, case_id):
        case = self.topology.case(case_id)
        revision = self.topology.latest(case_id)
        if not revision or revision["status"] != "reviewed":
            raise ReviewError("Approve the current pixel topology before metric review.", 409)
        path = self.topology.output / case_id / "revisions" / (revision["revision_id"] + ".json")
        observation_paths = [
            Path(p) for p in case["sources"] if Path(p).name == "observations.json"
        ]
        if len(observation_paths) != 1:
            raise ReviewError("Linked observations are missing.", 409)
        observations_path = observation_paths[0]
        try:
            verified, observations, transform = load_review(
                path, observations_path, revision["revision_id"]
            )
        except (ValueError, OSError, KeyError) as error:
            raise ReviewError("Topology/source verification failed: " + str(error), 409) from error
        return (path, observations_path, verified, observations, transform)

    def latest(self, case_id):
        self.topology.case(case_id)
        pointer = self.output / case_id / "latest.json"
        if not pointer.exists():
            return None
        rid = load_json(pointer)["revision_id"]
        if not isinstance(rid, str) or not re.fullmatch("metric-[0-9TZ]+-[a-f0-9]{12}", rid):
            raise ReviewError("Invalid metric revision pointer.", 409)
        record = load_json(pointer.parent / "revisions" / (rid + ".json"))
        if record.get("revision_id") != rid or record.get("sha256") != digest(
            {k: v for k, v in record.items() if k != "sha256"}
        ):
            raise ReviewError("Metric revision integrity check failed.", 409)
        return record

    def initial_state(self, revision):
        settings = {}
        if hasattr(self.topology, "jobs"):
            settings = deepcopy(
                self.topology.jobs.jobs.get(revision["case_id"], {})
                .get("config", {})
                .get("settings", {})
            )
        return {
            "bindings": {
                "settings": settings,
                "schema_version": "playablesketch-metric-input/1.0",
                "topology_revision_id": revision["revision_id"],
                "region_kinds": {r["id"]: "room" for r in revision["topology"]["regions"]},
                "dimensions": [],
                "relations": [],
                "ignored_texts": [],
                "hypothesis_budget": 4,
            },
            "names": {},
            "validation_mode": "geometry_only",
            "start_room_id": None,
            "goal_room_id": None,
            "semantics_confirmed": False,
        }

    def compute(self, case_id, state, sources=None):
        if not isinstance(state, dict) or set(state) != {
            "bindings",
            "names",
            "validation_mode",
            "start_room_id",
            "goal_room_id",
            "semantics_confirmed",
        }:
            raise ReviewError("Invalid metric review state.")
        if (
            not isinstance(state["bindings"], dict)
            or not isinstance(state["names"], dict)
            or (not isinstance(state["semantics_confirmed"], bool))
        ):
            raise ReviewError("Invalid semantic metadata.")
        if state["validation_mode"] not in ("geometry_only", "gameplay"):
            raise ReviewError("Invalid validation mode.")
        sources = sources or self.sources(case_id)
        path, obs_path, revision, observations, transform = sources
        if state["bindings"].get("topology_revision_id") != revision["revision_id"]:
            raise ReviewError(
                "Topology changed. Reopen metric review and rebind measurements.", 409
            )
        try:
            draft, report = reconstruct(path, obs_path, state["bindings"])
        except (ValueError, KeyError, TypeError, ValidationError) as error:
            raise ReviewError("Metric input could not be solved: " + str(error)) from error
        if hasattr(self.topology, "jobs") and case_id in self.topology.jobs.jobs:
            draft["document_id"] = "metric-" + self.topology.jobs.jobs[case_id]["logical_id"][:32]
        regions = {r["id"]: r for r in draft["layout"]["rooms"] + draft["layout"]["corridors"]}
        if set(state["names"]) - regions.keys():
            raise ReviewError("Unknown named region.")
        for rid, name in state["names"].items():
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
                raise ReviewError("Region names must be 1–200 characters.")
            regions[rid]["name"] = name.strip()
        for role in ("start", "goal"):
            rid = state[role + "_room_id"]
            if rid is not None and (
                not isinstance(rid, str) or rid not in {r["id"] for r in draft["layout"]["rooms"]}
            ):
                raise ReviewError("Start/Goal must reference existing rooms.")
            draft[role + "_room_id"] = rid
            for r in draft["layout"]["rooms"]:
                if r["id"] == rid:
                    r["role"] = role
        draft["validation_mode"] = state["validation_mode"]
        if not state["semantics_confirmed"]:
            draft["issues"].append(
                {
                    "code": "SKETCH_REVIEW_REQUIRED",
                    "severity": "error",
                    "element_ids": list(regions),
                    "message": "Confirm the room/corridor types before acceptance.",
                }
            )
        checked = validate_document(draft, observations)
        draft["issues"] = checked["issues"]
        draft["validation"]["metric"] = "passed" if checked["metric_valid"] else "failed"
        if not checked["metric_valid"] and draft["status"] != "conflicting":
            draft["status"] = "needs_review"
        report.update(validation=checked, reconstruction_status=draft["status"])
        pixels = report["pixel_topology"]
        targets, truncated = span_catalog(draft, pixels)
        text_boxes = [
            {
                "id": t["id"],
                "polygon_review_px": (
                    None
                    if t["polygon_px"] is None
                    else (transform_points(t["polygon_px"], transform) * [1, -1]).tolist()
                ),
            }
            for t in observations["texts"]
        ]
        return {
            "draft": draft,
            "report": report,
            "targets": targets,
            "target_budget_exhausted": truncated,
            "observations": observations,
            "text_boxes": text_boxes,
            "frame": revision["frame"],
        }

    def load(self, case_id):
        with self.topology.lock:
            sources = self.sources(case_id)
            latest = self.latest(case_id)
            compatible = (
                latest
                and latest["topology_revision_id"] == sources[2]["revision_id"]
                and (latest["topology_revision_sha256"] == sources[2]["revision_sha256"])
            )
            state = deepcopy(latest["state"] if compatible else self.initial_state(sources[2]))
            result = self.compute(case_id, state, sources)
            return {
                **result,
                "case_id": case_id,
                "state": state,
                "base_revision_id": latest["revision_id"] if latest else None,
                "status": latest["status"] if compatible else "unsaved",
                "can_undo": bool(compatible and latest["undo"]),
                "can_redo": bool(compatible and latest["redo"]),
                "topology_reset": bool(latest and (not compatible)),
            }

    @staticmethod
    def affected(before, after):
        ids = set()
        if before is None:
            return sorted(after["bindings"]["region_kinds"])
        for group in ("dimensions", "relations", "ignored_texts"):
            key = "evidence_id" if group == "ignored_texts" else "id"
            a, b = [{x[key]: x for x in s["bindings"].get(group, [])} for s in (before, after)]
            ids.update((k for k in a.keys() | b.keys() if a.get(k) != b.get(k)))
        for group in ("region_kinds",):
            a, b = (s["bindings"][group] for s in (before, after))
            ids.update((k for k in a.keys() | b.keys() if a.get(k) != b.get(k)))
        if any(
            (
                before[k] != after[k]
                for k in (
                    "names",
                    "validation_mode",
                    "start_room_id",
                    "goal_room_id",
                    "semantics_confirmed",
                )
            )
        ):
            ids.update(after["bindings"]["region_kinds"])
        if before["bindings"].get("settings") != after["bindings"].get("settings"):
            ids.add("settings")
        if before["bindings"].get("origin_vertex_id") != after["bindings"].get("origin_vertex_id"):
            ids.add("origin")
        return sorted(ids)

    def transact(
        self, case_id, base_revision_id, action, state=None, reviewer=None, telemetry=None
    ):
        try:
            telemetry = validate_telemetry(telemetry)
        except ValueError as error:
            raise ReviewError(str(error)) from error
        if action not in ("save", "undo", "redo", "accept", "preview"):
            raise ReviewError("Unknown metric action.")
        with self.topology.lock:
            sources = self.sources(case_id)
            latest = self.latest(case_id)
            if base_revision_id != (latest["revision_id"] if latest else None):
                raise ReviewError("A newer metric revision exists. Reload before editing.", 409)
            compatible = (
                latest
                and latest["topology_revision_id"] == sources[2]["revision_id"]
                and (latest["topology_revision_sha256"] == sources[2]["revision_sha256"])
            )
            previous = deepcopy(latest["state"]) if compatible else self.initial_state(sources[2])
            undo = deepcopy(latest["undo"]) if compatible else []
            redo = deepcopy(latest["redo"]) if compatible else []
            if action in ("undo", "redo", "accept") and (not compatible):
                raise ReviewError("Save a draft bound to the current topology first.", 409)
            if action in ("undo", "redo"):
                stack, other = (undo, redo) if action == "undo" else (redo, undo)
                if not stack:
                    raise ReviewError("Nothing to " + action, 409)
                state = stack.pop()
                other.append(previous)
            elif action == "accept":
                if state is not None and state != previous:
                    raise ReviewError("Save changes before acceptance.", 409)
                state = previous
            elif not isinstance(state, dict):
                raise ReviewError("Review state required.")
            result = self.compute(case_id, state, sources)
            if action == "preview":
                return {**result, "base_revision_id": base_revision_id}
            if action == "save" and previous is not None:
                undo.append(previous)
                redo = []
            validated = None
            if action == "accept":
                if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 200:
                    raise ReviewError("Enter the reviewer's name.")
                try:
                    validated = as_validated(
                        result["draft"], reviewer.strip(), result["observations"]
                    )
                except ValueError as error:
                    raise ReviewError(
                        "Resolve all metric checks before acceptance.", 422
                    ) from error
            rid = (
                "metric-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + uuid.uuid4().hex[:12]
            )
            result["draft"].update(revision_id=rid, parent_revision_id=base_revision_id)
            if validated is not None:
                validated.update(revision_id=rid + "-accepted", parent_revision_id=rid)
            current_sources = self.sources(case_id)
            if current_sources[2]["revision_sha256"] != sources[2]["revision_sha256"]:
                raise ReviewError("Topology changed while computing.", 409)
            record = {
                "schema_version": VERSION,
                "case_id": case_id,
                "revision_id": rid,
                "parent_revision_id": base_revision_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "topology_revision_id": sources[2]["revision_id"],
                "topology_revision_sha256": sources[2]["revision_sha256"],
                "state": deepcopy(state),
                "status": "accepted" if validated else "draft",
                "command": {
                    "type": action,
                    "base_revision_id": base_revision_id,
                    "affected_entity_ids": self.affected(previous, state),
                },
                "undo": undo[-100:],
                "redo": redo[-100:],
                "draft": result["draft"],
                "report": result["report"],
                "validated": validated,
            }
            if telemetry is not None:
                record["telemetry"] = telemetry
            record["sha256"] = digest(record)
            folder = self.output / case_id
            atomic_json(folder / "revisions" / (rid + ".json"), record)
            if hasattr(self.topology, "jobs") and case_id in self.topology.jobs.jobs:
                self.topology.jobs.snapshot_metric(record)
            atomic_json(folder / "latest.json", {"revision_id": rid})
            return {
                **result,
                "state": deepcopy(state),
                "base_revision_id": rid,
                "status": record["status"],
                "can_undo": bool(undo),
                "can_redo": bool(redo),
                "command": record["command"],
            }

    def export(self, case_id, expected_revision_id=None):
        with self.topology.lock:
            sources = self.sources(case_id)
            record = self.latest(case_id)
            if expected_revision_id is not None and (
                not record or record["revision_id"] != expected_revision_id
            ):
                raise ReviewError(
                    "The displayed metric revision is stale. Reload before download.", 409
                )
            if (
                not record
                or record["status"] != "accepted"
                or record["topology_revision_sha256"] != sources[2]["revision_sha256"]
            ):
                raise ReviewError(
                    "Only the latest accepted current metric revision can be downloaded.", 409
                )
            recomputed = self.compute(case_id, record["state"], sources)
            expected = as_validated(
                recomputed["draft"],
                record["validated"]["review"]["reviewer"],
                recomputed["observations"],
            )
            expected.update(
                revision_id=record["revision_id"] + "-accepted",
                parent_revision_id=record["revision_id"],
            )
            if (
                expected != record["validated"]
                or not validate_document(expected, recomputed["observations"])["exportable"]
            ):
                raise ReviewError(
                    "Accepted metric snapshot no longer matches its recomputed inputs.", 409
                )
            return deepcopy(record["validated"])
