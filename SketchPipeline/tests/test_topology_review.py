from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import numpy as np
from PIL import Image
from SketchPipeline.perception.topology import build_topology
from SketchPipeline.review.server import (
    ReviewError,
    ReviewStore,
    analyze_state,
    file_hash,
    make_handler,
)
from SketchPipeline.tests.test_topology import perimeter, wall


def state_with(lines, openings=()):
    return {
        "walls": [{key: value for key, value in line.items() if key != "role"} for line in lines],
        "openings": list(openings),
    }


def two_rooms(decision="approved"):
    lines = perimeter(10, 10, 110, 110)
    lines += [
        wall("upper", (60, 10), (60, 50), "vertical"),
        wall("lower", (60, 70), (60, 110), "vertical"),
    ]
    opening = {
        "id": "door",
        "start": [60, 50],
        "end": [60, 70],
        "axis": "vertical",
        "kind": "door",
        "decision": decision,
    }
    return state_with(lines, [opening])


def write_case(root):
    folder = root / "prediction" / "Data_1"
    folder.mkdir(parents=True)
    image = Image.new("L", (220, 120), 245)
    image.save(folder / "photo.png")
    image.save(folder / "unmasked_line_input.png")
    topology = build_topology(perimeter(10, 10, 110, 110), [], (120, 220))
    working = {
        "preprocessing": {"working_size_px": [220, 120], "original_to_working": np.eye(3).tolist()},
        "geometry": {"dominant_rotation_degrees": 0},
        "gaps": [],
    }
    observations = {
        "source": {"image_path": "photo.png", "image_sha256": file_hash(folder / "photo.png")}
    }
    for filename, value in (
        ("topology.json", topology),
        ("working.json", working),
        ("observations.json", observations),
    ):
        (folder / filename).write_text(json.dumps(value))
    return ReviewStore(folder.parent, root / "reviews")


class ReviewGeometryTests(unittest.TestCase):

    def test_clean_rectangle_ready_but_still_pixel_only(self):
        result = analyze_state(state_with(perimeter(10, 10, 110, 110)), 220, 120)
        self.assertTrue(result["validation"]["ready_to_review"])
        self.assertEqual(result["topology"]["geometry_mode"], "review_exact")
        self.assertFalse(result["topology"]["metric_layout_created"])

    def test_exact_edits_are_not_healed_by_perception(self):
        state = state_with(
            [
                wall("top", (14, 10), (106, 10), "horizontal"),
                wall("right", (110, 14), (110, 106), "vertical"),
                wall("bottom", (14, 110), (106, 110), "horizontal"),
                wall("left", (10, 14), (10, 106), "vertical"),
            ]
        )
        before = deepcopy(state)
        result = analyze_state(state, 220, 120)
        self.assertEqual(state, before)
        self.assertEqual(result["topology"]["regions"], [])
        self.assertFalse(result["validation"]["ready_to_review"])
        self.assertEqual(result["topology"]["snap_adjustments"], [])

    def test_pending_opening_blocks_acceptance_but_previews_connection(self):
        result = analyze_state(two_rooms("pending"), 220, 120)
        self.assertEqual(len(result["topology"]["region_connectivity_graph"]["edges"]), 1)
        self.assertFalse(result["validation"]["ready_to_review"])
        self.assertIn("OPENING_PENDING", [item["code"] for item in result["validation"]["issues"]])
        self.assertTrue(analyze_state(two_rooms(), 220, 120)["validation"]["ready_to_review"])

    def test_rejecting_opening_never_silently_fills_wall_gap(self):
        state = two_rooms("rejected")
        result = analyze_state(state, 220, 120)
        self.assertFalse(result["validation"]["ready_to_review"])
        self.assertEqual(result["topology"]["region_connectivity_graph"]["edges"], [])
        state["walls"].append(wall("fill", (60, 50), (60, 70), "vertical"))
        self.assertTrue(analyze_state(state, 220, 120)["validation"]["ready_to_review"])

    def test_overlapping_walls_and_unattached_openings_are_blocking(self):
        state = two_rooms()
        state["walls"].append(wall("duplicate", (10, 10), (110, 10), "horizontal"))
        result = analyze_state(state, 220, 120)
        self.assertIn(
            "OVERLAPPING_WALLS", [item["code"] for item in result["validation"]["issues"]]
        )
        state = two_rooms()
        state["openings"][0]["start"] = [61, 50]
        state["openings"][0]["end"] = [61, 70]
        self.assertFalse(analyze_state(state, 220, 120)["validation"]["ready_to_review"])

    def test_rectangle_with_hole_is_unsupported(self):
        state = state_with(perimeter(10, 10, 110, 110) + perimeter(40, 40, 80, 80, "inside"))
        result = analyze_state(state, 220, 120)
        self.assertTrue(any((region["hole_count"] for region in result["topology"]["regions"])))
        self.assertFalse(result["validation"]["ready_to_review"])

    def test_nonfinite_boolean_diagonal_and_duplicate_ids_rejected(self):
        for value in (float("nan"), float("inf"), True, 100000):
            state = state_with(perimeter(10, 10, 110, 110))
            state["walls"][0]["start"][0] = value
            with self.subTest(value=value), self.assertRaises(ReviewError):
                analyze_state(state, 220, 120)
        state = state_with(perimeter(10, 10, 110, 110))
        state["walls"][0]["end"][1] = 13
        with self.assertRaises(ReviewError):
            analyze_state(state, 220, 120)
        state = state_with(perimeter(10, 10, 110, 110))
        state["walls"].append(deepcopy(state["walls"][0]))
        with self.assertRaises(ReviewError):
            analyze_state(state, 220, 120)


class ReviewPersistenceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = write_case(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_draft_and_reviewed_revisions_are_separate_and_immutable(self):
        before = {
            str(path): path.read_bytes() for path in self.store.run.rglob("*") if path.is_file()
        }
        state = self.store.load("Data_1")["state"]
        draft = self.store.save("Data_1", state, None, "save_draft")
        draft_path = self.store.output / "Data_1/revisions" / (draft["revision_id"] + ".json")
        draft_bytes = draft_path.read_bytes()
        reviewed = self.store.save("Data_1", state, draft["revision_id"], "accept")
        self.assertEqual(draft_path.read_bytes(), draft_bytes)
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertEqual(reviewed["parent_revision_id"], draft["revision_id"])
        self.assertEqual(self.store.latest("Data_1")["revision_id"], reviewed["revision_id"])
        self.assertEqual(
            before,
            {str(path): path.read_bytes() for path in self.store.run.rglob("*") if path.is_file()},
        )
        restored = ReviewStore(self.store.run, self.store.output).load("Data_1")
        self.assertEqual(restored["status"], "reviewed")
        np.testing.assert_allclose(
            np.array(restored["frame"]["review_to_original"])
            @ restored["frame"]["original_to_review"],
            np.eye(3),
        )

    def test_invalid_acceptance_is_not_written_but_draft_is_allowed(self):
        state = two_rooms("pending")
        with self.assertRaises(ReviewError) as error:
            self.store.save("Data_1", state, None, "accept")
        self.assertEqual(error.exception.status, 422)
        self.assertIsNone(self.store.latest("Data_1"))
        self.assertEqual(self.store.save("Data_1", state, None, "save_draft")["status"], "draft")

    def test_stale_parent_and_changed_source_are_rejected(self):
        state = self.store.load("Data_1")["state"]
        draft = self.store.save("Data_1", state, None, "save_draft")
        with self.assertRaises(ReviewError) as error:
            self.store.save("Data_1", state, None, "save_draft")
        self.assertEqual(error.exception.status, 409)
        (self.store.run / "Data_1/working.json").write_text("{}")
        with self.assertRaises(ReviewError) as error:
            self.store.save("Data_1", state, draft["revision_id"], "accept")
        self.assertEqual(error.exception.status, 409)

    def test_source_output_and_unknown_case_are_rejected(self):
        with self.assertRaises(ReviewError):
            ReviewStore(self.store.run, self.store.run / "reviews")
        with self.assertRaises(ReviewError):
            self.store.load("../../outside")

    def test_saved_topology_tampering_is_detected(self):
        state = self.store.load("Data_1")["state"]
        reviewed = self.store.save("Data_1", state, None, "accept")
        path = self.store.output / "Data_1/revisions" / (reviewed["revision_id"] + ".json")
        document = json.loads(path.read_text())
        document["topology"]["regions"] = []
        path.write_text(json.dumps(document))
        with self.assertRaises(ReviewError):
            self.store.latest("Data_1")

    def test_api_requires_session_token_and_exports_only_latest_reviewed(self):
        handler = make_handler(self.store)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(url + "/api/bootstrap") as response:
                token = json.load(response)["token"]
            state = self.store.load("Data_1")["state"]
            body = json.dumps(
                {
                    "case_id": "Data_1",
                    "state": state,
                    "action": "accept",
                    "parent_revision_id": None,
                }
            ).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(
                        url + "/api/save", data=body, headers={"Content-Type": "application/json"}
                    )
                )
            self.assertEqual(error.exception.code, 403)
            with urlopen(
                Request(
                    url + "/api/save",
                    data=body,
                    headers={"Content-Type": "application/json", "X-Review-Token": token},
                )
            ) as response:
                reviewed = json.load(response)
            with urlopen(url + "/api/export?case=Data_1") as response:
                self.assertEqual(json.load(response)["revision_id"], reviewed["revision_id"])
            self.store.save("Data_1", state, reviewed["revision_id"], "save_draft")
            with self.assertRaises(HTTPError) as error:
                urlopen(url + "/api/export?case=Data_1")
            self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
