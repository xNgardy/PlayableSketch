import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from SketchPipeline.shape_authoring.jobs import ShapeJobs, ShapeJobError
from SketchPipeline.shape_authoring.contract import validate_authoring
from SketchPipeline.shape_authoring.server import make_handler


class WorkspaceTests(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manager = ShapeJobs(self.root / "jobs")
        self.job = self.manager.sample()["job_id"]
        self.doc = self.manager.proposals(self.job)["authoring"]
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": None,
                "request": {},
            },
        )
        self.assertEqual(self.sizing["status"], "ready", self.sizing["issues"])

    def tearDown(self):
        self.manager.close()
        self.temporary.cleanup()

    def body(self):
        return {
            "base_revision_id": self.doc["revision_id"],
            "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
            "base_workspace_revision_id": self.manager.workspace(self.job)["revision_id"],
        }

    def save_meta(self, state):
        return self.manager.save_workspace(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_workspace_revision_id": self.manager.workspace(self.job)["revision_id"],
                "state": state,
            },
        )

    def test_sample_is_explicit_manual_example_and_real_sizing(self):
        data = self.manager.proposals(self.job)
        self.assertEqual(data["backend"], "manual")
        self.assertFalse(data["numeric_ocr_called"])
        self.assertTrue(self.manager.status(self.job)["is_sample"])
        self.assertEqual(len(self.doc["topology"]["regions"]), 3)
        self.assertEqual(len(self.doc["topology"]["openings"]), 2)
        self.assertEqual(validate_authoring(self.doc), [])

    def test_names_roles_persist_without_mutating_source_proposals(self):
        state = {
            "names": {"sample_west": "Studio"},
            "start_room_id": "sample_west",
            "goal_room_id": "sample_east",
        }
        saved = self.save_meta(state)
        self.manager.close()
        self.manager = ShapeJobs(self.root / "jobs")
        self.assertEqual(self.manager.workspace(self.job)["state"], state)
        self.assertEqual(self.manager.proposals(self.job)["authoring"], self.doc)

    def test_confirmation_is_new_exact_snapshot_and_not_export(self):
        self.save_meta(
            {"names": {"sample_west": "Studio"}, "start_room_id": None, "goal_room_id": None}
        )
        accepted = self.manager.confirm_plan(self.job, self.body())
        self.assertNotEqual(
            accepted["authoring"]["revision_id"], self.sizing["authoring"]["revision_id"]
        )
        self.assertEqual(validate_authoring(accepted["authoring"]), [])
        self.assertEqual(
            accepted["authoring"]["physical_design"]["acceptance"]["status"], "accepted"
        )
        self.assertFalse(accepted["delivery_ready"])
        self.assertEqual(self.manager.workspace(self.job)["confirmation"], accepted)
        self.assertEqual(
            self.manager.sizing_preview(self.job)["authoring"]["physical_design"]["acceptance"][
                "status"
            ],
            "pending",
        )

    def test_size_change_invalidates_confirmation_and_old_body(self):
        body = self.body()
        self.manager.confirm_plan(self.job, body)
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
                "request": {
                    "edits": [{"entity_id": "sample_west", "parameter": "width_cm", "value": 800}]
                },
            },
        )
        self.assertIsNone(self.manager.workspace(self.job)["confirmation"])
        with self.assertRaises(ShapeJobError) as error:
            self.manager.confirm_plan(self.job, body)
        self.assertEqual(error.exception.status, 409)

    def test_metadata_change_invalidates_confirmation_and_rejects_bad_roles(self):
        self.manager.confirm_plan(self.job, self.body())
        self.save_meta({"names": {}, "start_room_id": "sample_west", "goal_room_id": "sample_east"})
        self.assertIsNone(self.manager.workspace(self.job)["confirmation"])
        with self.assertRaises(ShapeJobError):
            self.save_meta({"names": {}, "start_room_id": "missing_room", "goal_room_id": None})
        with self.assertRaises(ShapeJobError):
            self.save_meta(
                {"names": {}, "start_room_id": "sample_west", "goal_room_id": "sample_west"}
            )

    def test_removed_named_region_does_not_poison_future_metadata(self):
        self.save_meta(
            {
                "names": {"sample_west": "Studio"},
                "start_room_id": "sample_west",
                "goal_room_id": None,
            }
        )
        state = copy.deepcopy(self.manager.proposals(self.job)["edit_state"])
        state["boxes"] = [b for b in state["boxes"] if b["id"] != "sample_west"]
        state["openings"] = [o for o in state["openings"] if "sample_west" not in o["entity_ids"]]
        edited = self.manager.edit(self.job, dict(state, base_revision_id=self.doc["revision_id"]))
        self.doc = edited["authoring"]
        current = self.manager.workspace(self.job)
        self.assertEqual(current["state"]["names"], {})
        self.assertIsNone(current["state"]["start_room_id"])
        self.save_meta(
            {"names": {"sample_east": "Hall"}, "start_room_id": None, "goal_room_id": None}
        )

    def test_unresolved_saved_connection_blocks_confirmation(self):
        state = copy.deepcopy(self.manager.proposals(self.job)["edit_state"])
        state["boxes"][0]["bounds_px"][2] -= 10
        edited = self.manager.edit(self.job, dict(state, base_revision_id=self.doc["revision_id"]))
        self.doc = edited["authoring"]
        self.assertTrue(edited["diagnostics"])
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
                "request": {"reset_bindings": True},
            },
        )
        with self.assertRaises(ShapeJobError):
            self.manager.confirm_plan(self.job, self.body())

    def test_workspace_http_assets_and_confirmation(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/bootstrap") as r:
                token = json.load(r)["token"]
            for path, part in [
                ("/", 'id="upload"'),
                ("/workspace.js", "sizeRequest"),
                ("/workspace.css", ".work-grid"),
            ]:
                with urlopen(base + path) as r:
                    self.assertIn(part.encode(), r.read())
            endpoint = base + f"/shape-jobs/{self.job}/confirm"
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(endpoint, data=json.dumps(self.body()).encode()))
            self.assertEqual(error.exception.code, 403)
            with urlopen(
                Request(
                    endpoint,
                    data=json.dumps(self.body()).encode(),
                    headers={
                        "X-Shape-Token": token,
                        "Content-Type": "application/json",
                        "Origin": base,
                    },
                )
            ) as r:
                self.assertFalse(json.load(r)["delivery_ready"])
            with urlopen(base + f"/shape-jobs/{self.job}/workspace") as r:
                self.assertIsNotNone(json.load(r)["confirmation"])
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(
                        endpoint,
                        data=b"[]",
                        headers={"X-Shape-Token": token, "Content-Type": "application/json"},
                    )
                )
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
