import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import cv2
import numpy as np
from SketchPipeline.shape_authoring.jobs import ShapeJobs, ShapeJobError
from SketchPipeline.shape_authoring.server import make_handler
from SketchPipeline.tests import test_shape_proposals as fixtures


class SizingJobTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = ShapeJobs(self.root / "jobs")
        data = cv2.imencode(".png", np.full((400, 500), 255, np.uint8))[1].tobytes()
        job = self.manager.start(data, "blank.png", backend="manual")
        self.identifier = job["job_id"]
        fixtures.wait(self.manager, self.identifier)
        base = self.manager.proposals(self.identifier)["authoring"]
        self.body = {
            "base_revision_id": base["revision_id"],
            "boxes": [
                {"id": "room_a", "type": "room", "bounds_px": [10, 10, 110, 90]},
                {"id": "room_b", "type": "room", "bounds_px": [110, 10, 210, 90]},
            ],
            "openings": [
                {
                    "id": "door_a",
                    "type": "door",
                    "entity_ids": ["room_a", "room_b"],
                    "points_px": [[110, 30], [110, 50]],
                }
            ],
        }
        self.edited = self.manager.edit(self.identifier, self.body)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def request(self, edits=None, base=None):
        return {
            "base_revision_id": self.edited["authoring"]["revision_id"],
            "base_sizing_revision_id": base,
            "request": {"edits": edits or []},
        }

    def test_sizing_edits_persist_restart_and_do_not_replace_topology(self):
        result = self.manager.sizing(
            self.identifier,
            self.request(
                [{"entity_id": "room_a", "parameter": "width_cm", "value": 800, "locked": True}]
            ),
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            self.manager.proposals(self.identifier)["authoring"], self.edited["authoring"]
        )
        self.manager.close()
        self.manager = ShapeJobs(self.root / "jobs")
        restored = self.manager.sizing_preview(self.identifier)
        self.assertEqual(restored, result)
        with self.assertRaises(ShapeJobError):
            self.manager.retry(self.identifier)

    def test_stale_requests_cannot_overwrite_new_sizes(self):
        request = self.request()
        first = self.manager.sizing(self.identifier, request)
        with self.assertRaises(ShapeJobError) as error:
            self.manager.sizing(self.identifier, request)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(
            self.manager.sizing_preview(self.identifier)["authoring"]["revision_id"],
            first["authoring"]["revision_id"],
        )

    def test_geometry_edit_stales_sizes_and_explicit_reset_recovers(self):
        first = self.manager.sizing(self.identifier, self.request())
        body = copy.deepcopy(self.body)
        body["base_revision_id"] = self.edited["authoring"]["revision_id"]
        body["boxes"][1]["bounds_px"][2] = 230
        self.edited = self.manager.edit(self.identifier, body)
        self.assertTrue(self.manager.sizing_preview(self.identifier)["preview_is_stale"])
        stale = self.manager.sizing(
            self.identifier, self.request(base=first["authoring"]["revision_id"])
        )
        self.assertEqual(stale["status"], "needs_attention")
        request = self.request(base=stale["authoring"]["revision_id"])
        request["request"]["reset_bindings"] = True
        ready = self.manager.sizing(self.identifier, request)
        self.assertEqual(ready["status"], "ready")

    def test_conflicting_edit_retains_last_valid_preview_and_draft(self):
        first = self.manager.sizing(self.identifier, self.request())
        bad = self.manager.sizing(
            self.identifier,
            self.request(
                [
                    {"entity_id": "room_a", "parameter": "depth_cm", "value": 400},
                    {"entity_id": "room_b", "parameter": "depth_cm", "value": 500},
                ],
                first["authoring"]["revision_id"],
            ),
        )
        self.assertEqual(bad["status"], "needs_attention")
        self.assertEqual(bad["preview"], first["preview"])
        self.assertEqual(self.manager.sizing_preview(self.identifier), bad)

    def test_sizing_http_token_conflict_and_svg_preview(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_port}"
            with urlopen(root + "/api/bootstrap") as response:
                token = json.load(response)["token"]
            endpoint = root + f"/shape-jobs/{self.identifier}/sizing"
            payload = json.dumps(self.request()).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
                )
            self.assertEqual(error.exception.code, 403)
            request = Request(
                endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Shape-Token": token,
                    "Origin": root,
                },
            )
            with urlopen(request) as response:
                result = json.load(response)
            self.assertEqual(result["status"], "ready")
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 409)
            with urlopen(endpoint) as response:
                self.assertEqual(
                    json.load(response)["authoring"]["revision_id"],
                    result["authoring"]["revision_id"],
                )
            with urlopen(root + f"/shape-jobs/{self.identifier}/sizing-plan") as response:
                self.assertIn(b"Suggested plan sizes", response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
