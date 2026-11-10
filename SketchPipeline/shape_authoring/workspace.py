import copy
import json
import time
import uuid
from .errors import ShapeJobError
from .names import region_names


class WorkspaceMixin:

    def workspace(self, identifier):
        with self.lock:
            current = self.proposals(identifier)["authoring"]
            folder = self.folder(identifier)
            path = folder / "workspace.json"
            data = (
                json.loads(path.read_text())
                if path.exists()
                else {
                    "revision_id": None,
                    "state": {"names": {}, "start_room_id": None, "goal_room_id": None},
                }
            )
            valid_ids = {r["id"] for r in current["topology"]["regions"]} | {
                o["id"] for o in current["topology"]["openings"]
            }
            rooms = {r["id"] for r in current["topology"]["regions"] if r["type"] == "room"}
            data["state"]["names"] = {
                k: v for k, v in data["state"]["names"].items() if k in valid_ids
            }
            for role in ["start_room_id", "goal_room_id"]:
                if data["state"][role] not in rooms:
                    data["state"][role] = None
            confirmation = folder / "confirmation-latest.json"
            accepted = json.loads(confirmation.read_text()) if confirmation.exists() else None
            sizes = folder / "sizing-latest.json"
            sizing = json.loads(sizes.read_text()) if sizes.exists() else None
            valid = bool(
                accepted
                and accepted.get("schema_version") == "shape-confirmed-snapshot/1.0"
                and sizing
                and (sizing["status"] == "ready")
                and (accepted["topology_revision_id"] == current["revision_id"])
                and (accepted["sizing_revision_id"] == sizing["authoring"]["revision_id"])
                and (accepted["workspace_revision_id"] == data["revision_id"])
            )
            return {
                **data,
                "confirmation": accepted if valid else None,
                "delivery_ready": False,
                "export_available": valid,
            }

    def save_workspace(self, identifier, body):
        from .jobs import atomic_json

        with self.lock:
            doc = self.proposals(identifier)["authoring"]
            current = self.workspace(identifier)
            if (
                body.get("base_revision_id") != doc["revision_id"]
                or body.get("base_workspace_revision_id") != current["revision_id"]
            ):
                raise ShapeJobError("The plan changed. Reload before saving.", 409)
            state = body.get("state")
            if (
                not isinstance(state, dict)
                or not {"names", "start_room_id", "goal_room_id"} <= set(state)
                or set(state) - {"names", "start_room_id", "goal_room_id", "validation_mode"}
            ):
                raise ShapeJobError("Invalid plan details.")
            if state.get("validation_mode", "geometry_only") not in ("geometry_only", "gameplay"):
                raise ShapeJobError("Choose geometry-only or playable delivery.")
            ids = {r["id"] for r in doc["topology"]["regions"]} | {
                o["id"] for o in doc["topology"]["openings"]
            }
            if (
                not isinstance(state["names"], dict)
                or not set(state["names"]) <= ids
                or any(
                    (
                        not isinstance(s, str) or not 1 <= len(s.strip()) <= 80
                        for s in state["names"].values()
                    )
                )
            ):
                raise ShapeJobError("Names must be between 1 and 80 characters.")
            rooms = {r["id"] for r in doc["topology"]["regions"] if r["type"] == "room"}
            for role in ["start_room_id", "goal_room_id"]:
                if state[role] is not None and state[role] not in rooms:
                    raise ShapeJobError("Choose a room for Start and Goal.")
            if (
                state["start_room_id"] is not None
                and state["start_room_id"] == state["goal_room_id"]
            ):
                raise ShapeJobError("Start and Goal must be different rooms.")
            data = {"revision_id": "workspace_" + uuid.uuid4().hex, "state": copy.deepcopy(state)}
            atomic_json(self.folder(identifier) / (data["revision_id"] + ".json"), data)
            atomic_json(self.folder(identifier) / "workspace.json", data)
            return self.workspace(identifier)

    def confirm_plan(self, identifier, body):
        from .jobs import atomic_json
        from .contract import accept_revision
        from .sizing import topology_key
        from SketchPipeline.validation.validate import validate_document

        with self.lock:
            current = self.proposals(identifier)
            doc = current["authoring"]
            workspace = self.workspace(identifier)
            sizing = self.sizing_preview(identifier)
            if (
                body.get("base_revision_id") != doc["revision_id"]
                or body.get("base_sizing_revision_id")
                != sizing.get("authoring", {}).get("revision_id")
                or body.get("base_workspace_revision_id") != workspace["revision_id"]
            ):
                raise ShapeJobError("The plan changed. Review it again before confirming.", 409)
            if current.get("edit_diagnostics"):
                raise ShapeJobError("Resolve the highlighted connections before confirming.")
            if (
                sizing.get("status") != "ready"
                or sizing.get("preview_is_stale")
                or sizing.get("topology_key") != topology_key(doc)
            ):
                raise ShapeJobError("Resolve size conflicts before confirming.")
            check = validate_document(sizing["preview"]["canonical"])
            if not check["metric_valid"]:
                raise ShapeJobError("This plan needs geometry correction.")
            snapshot = copy.deepcopy(sizing["authoring"])
            for entities in snapshot["topology"].values():
                for entity in entities:
                    entity["geometry"]["state"] = "confirmed"
            default_names = region_names(snapshot["topology"]["regions"])
            for region in snapshot["topology"]["regions"]:
                region["name"] = workspace["state"]["names"].get(
                    region["id"], default_names[region["id"]]
                )
            sizing_revision = snapshot["revision_id"]
            snapshot["parent_revision_id"] = sizing_revision
            snapshot["revision_id"] = "review_" + uuid.uuid4().hex
            for value in snapshot["physical_design"]["values"]:
                value["authoring_revision_id"] = snapshot["revision_id"]
                value["binding_revision_id"] = snapshot["revision_id"]
            snapshot = accept_revision(snapshot, "Local user")
            from .delivery import prepare_draft, payload
            from .sizing import digest

            canonical_draft, preflight = prepare_draft(
                sizing["preview"], snapshot, workspace["state"]
            )
            record = {
                "confirmation_id": "confirmed_" + uuid.uuid4().hex,
                "topology_revision_id": doc["revision_id"],
                "sizing_revision_id": sizing_revision,
                "workspace_revision_id": workspace["revision_id"],
                "authoring": snapshot,
                "workspace_state": workspace["state"],
                "confirmed_at_unix": time.time(),
                "delivery_ready": False,
                "schema_version": "shape-confirmed-snapshot/1.0",
                "canonical_draft": canonical_draft,
                "agent_preflight": preflight,
                "source_bindings": {
                    "topology": digest(doc),
                    "sizing": digest(sizing),
                    "workspace": digest(workspace["state"]),
                },
                "message": "Your plan is confirmed and saved. Export the validated bundle for Unreal.",
            }
            record["snapshot_sha256"] = digest(payload(record))
            atomic_json(self.folder(identifier) / (record["confirmation_id"] + ".json"), record)
            atomic_json(self.folder(identifier) / "confirmation-latest.json", record)
            return record

    def sample(self):
        import cv2
        import numpy as np
        from .propose import run
        from .jobs import atomic_json

        with self.lock:
            identifier = "shape_" + uuid.uuid4().hex
            folder = self.root / identifier
            folder.mkdir()
            gray = np.full((420, 600), 255, np.uint8)
            for a, b in [
                ((60, 70), (560, 70)),
                ((60, 350), (560, 350)),
                ((60, 70), (60, 350)),
                ((560, 70), (560, 350)),
                ((260, 70), (260, 350)),
                ((360, 70), (360, 350)),
            ]:
                cv2.line(gray, a, b, 30, 3)
            for x, y, Y in [(260, 170, 220), (360, 240, 290)]:
                cv2.line(gray, (x, y), (x, Y), 255, 7)
                for t in [y, Y]:
                    cv2.line(gray, (x - 9, t), (x + 9, t), 30, 3)
            source = folder / "source.png"
            cv2.imwrite(str(source), gray)
            result = run(source, folder / "attempt_1", "manual", reason="Editable sample plan.")
            record = {
                "job_id": identifier,
                "filename": "Courtyard sketch",
                "backend": "manual",
                "status": "needs_attention",
                "attempt": 1,
                "profile": "baseline",
                "model_config": {},
                "source_name": "source.png",
                "source_sha256": result["source_sha256"],
                "created_at_unix": time.time(),
                "failure": None,
                "manual_available": True,
                "output_directory": "attempt_1",
                "authoring_revision_id": result["authoring_revision_id"],
                "is_sample": True,
            }
            self.jobs[identifier] = record
            atomic_json(folder / "job.json", record)
            matrix = np.asarray(result["preprocessing"]["original_to_working"])

            def point(p):
                q = matrix @ np.r_[p, 1.0]
                return (q[:2] / q[2]).tolist()

            boxes = []
            for rid, kind, bounds in [
                ("sample_west", "room", [60, 70, 260, 350]),
                ("sample_gallery", "room", [260, 70, 360, 350]),
                ("sample_east", "room", [360, 70, 560, 350]),
            ]:
                a, b = (point(bounds[:2]), point(bounds[2:]))
                boxes.append({"id": rid, "type": kind, "bounds_px": a + b})
            openings = [
                {
                    "id": rid,
                    "type": "door",
                    "entity_ids": owners,
                    "points_px": [point([x, y]), point([x, Y])],
                }
                for rid, owners, x, y, Y in [
                    ("sample_door_west", ["sample_west", "sample_gallery"], 260, 170, 220),
                    ("sample_door_east", ["sample_gallery", "sample_east"], 360, 240, 290),
                ]
            ]
            self.edit(
                identifier,
                {
                    "base_revision_id": result["authoring_revision_id"],
                    "boxes": boxes,
                    "openings": openings,
                },
            )
            return self.status(identifier)
