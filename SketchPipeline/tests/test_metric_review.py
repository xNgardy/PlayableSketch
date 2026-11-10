from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from SketchPipeline.review.metric_store import MetricReviewStore
from SketchPipeline.review.server import ReviewError, make_handler
from SketchPipeline.tests.test_metric_pipeline import prepare
from SketchPipeline.tests.test_topology_review import two_rooms, state_with
from SketchPipeline.tests.test_topology import wall
from SketchPipeline.tests.test_metric_solver import fixture, relation
from SketchPipeline.validation.validate import validate_document


class MetricReviewTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.topology, self.path, self.obs, self.bindings = prepare(self.root)
        self.store = MetricReviewStore(self.topology)
        self.state = {
            "bindings": deepcopy(self.bindings),
            "names": {},
            "validation_mode": "geometry_only",
            "start_room_id": None,
            "goal_room_id": None,
            "semantics_confirmed": True,
        }

    def tearDown(self):
        self.topology.uploads.close()
        self.tmp.cleanup()

    def save(self, state=None, base=None):
        return self.store.transact("Data_1", base, "save", state or self.state)

    def test_initial_draft_has_evidence_separate_previews_and_pending_types(self):
        loaded = self.store.load("Data_1")
        self.assertFalse(loaded["state"]["semantics_confirmed"])
        self.assertFalse(loaded["report"]["validation"]["metric_valid"])
        self.assertEqual(loaded["observations"]["texts"][0]["raw_text"], "600 cm")
        self.assertIsNotNone(loaded["text_boxes"][0]["polygon_review_px"])
        self.assertTrue(loaded["targets"])

    def test_explicit_accept_and_download_only_latest_exact_snapshot(self):
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")
        saved = self.save()
        rid = saved["base_revision_id"]
        self.assertTrue(saved["report"]["validation"]["metric_valid"])
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")
        accepted = self.store.transact("Data_1", rid, "accept", reviewer="Test reviewer")
        output = self.store.export("Data_1")
        self.assertTrue(validate_document(output, json.loads(self.obs.read_text()))["exportable"])
        self.assertEqual(output["kind"], "validated_layout")
        self.assertEqual(output["review"]["reviewer"], "Test reviewer")
        self.assertEqual(output["validation"]["navigation"], "not_run")
        accepted_path = (
            self.store.output / "Data_1" / "revisions" / (accepted["base_revision_id"] + ".json")
        )
        old_bytes = accepted_path.read_bytes()
        changed = deepcopy(self.state)
        changed["names"][next(iter(changed["bindings"]["region_kinds"]))] = "New room name"
        self.save(changed, accepted["base_revision_id"])
        self.assertEqual(accepted_path.read_bytes(), old_bytes)
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")

    def test_800_to600_preserves_raw_ocr_and_command_lineage(self):
        raw = self.obs.read_bytes()
        wrong = deepcopy(self.state)
        wrong["bindings"]["dimensions"][0]["value_cm"] = 800
        first = self.save(wrong)
        fixed = self.save(self.state, first["base_revision_id"])
        self.assertEqual(self.obs.read_bytes(), raw)
        record = self.store.latest("Data_1")
        self.assertEqual(record["parent_revision_id"], first["base_revision_id"])
        self.assertIn("dim1", record["command"]["affected_entity_ids"])
        self.assertEqual(
            record["state"]["bindings"]["dimensions"][0]["provenance"]["method"], "user_correction"
        )
        self.assertEqual(record["state"]["bindings"]["dimensions"][0]["value_cm"], 600)
        self.assertTrue(fixed["report"]["validation"]["metric_valid"])

    def test_conflict_rejected_until_one_confirmed_label_is_corrected(self):
        state = deepcopy(self.state)
        conflict = deepcopy(state["bindings"]["dimensions"][0])
        conflict.update(id="opposite-width", value_cm=450)
        conflict["provenance"]["evidence_ids"] = []
        state["bindings"]["dimensions"].append(conflict)
        first = self.save(state)
        self.assertEqual(first["draft"]["status"], "conflicting")
        with self.assertRaises(ReviewError) as error:
            self.store.transact("Data_1", first["base_revision_id"], "accept", reviewer="Test")
        self.assertEqual(error.exception.status, 422)
        state["bindings"]["dimensions"][-1]["value_cm"] = 600
        fixed = self.save(state, first["base_revision_id"])
        self.assertTrue(fixed["report"]["validation"]["metric_valid"])
        self.store.transact("Data_1", fixed["base_revision_id"], "accept", reviewer="Test")

    def test_three_missing_measurements_cannot_be_filled_by_acceptance(self):
        state = deepcopy(self.state)
        for d in state["bindings"]["dimensions"][3:]:
            d.update(value_cm=None, state="missing")
        first = self.save(state)
        self.assertEqual(first["report"]["status"], "underdetermined")
        with self.assertRaises(ReviewError):
            self.store.transact("Data_1", first["base_revision_id"], "accept", reviewer="Test")
        self.assertEqual(
            [d["value_cm"] for d in self.store.latest("Data_1")["state"]["bindings"]["dimensions"]][
                -3:
            ],
            [None] * 3,
        )
        fixed = self.save(self.state, first["base_revision_id"])
        self.assertTrue(fixed["report"]["validation"]["metric_valid"])

    def test_wrong_target_then_fix_recomputes(self):
        state = deepcopy(self.state)
        d = state["bindings"]["dimensions"][0]
        d["target"]["axis"] = "y"
        first = self.save(state)
        self.assertFalse(first["report"]["validation"]["metric_valid"])
        fixed = self.save(self.state, first["base_revision_id"])
        self.assertTrue(fixed["report"]["validation"]["metric_valid"])

    def test_undo_redo_immutable_commands_restore_metric_results(self):
        first = self.save()
        changed = deepcopy(self.state)
        changed["bindings"]["dimensions"][-1]["value_cm"] = 100
        second = self.save(changed, first["base_revision_id"])
        undo = self.store.transact("Data_1", second["base_revision_id"], "undo")
        self.assertEqual(undo["draft"]["layout"]["openings"][0]["center_offset_cm"], 260)
        redo = self.store.transact("Data_1", undo["base_revision_id"], "redo")
        self.assertEqual(redo["draft"]["layout"]["openings"][0]["center_offset_cm"], 160)
        self.assertEqual(self.store.latest("Data_1")["command"]["type"], "redo")
        self.assertNotEqual(redo["base_revision_id"], second["base_revision_id"])

    def test_stale_async_preview_or_save_does_not_overwrite_newer_revision(self):
        first = self.save()
        second = self.save(self.state, first["base_revision_id"])
        for action in ("save", "preview", "accept", "undo", "redo"):
            with self.subTest(action=action), self.assertRaises(ReviewError) as error:
                self.store.transact(
                    "Data_1", first["base_revision_id"], action, self.state, reviewer="Test"
                )
            self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.latest("Data_1")["revision_id"], second["base_revision_id"])

    def test_settings_recompute_and_gameplay_roles(self):
        state = deepcopy(self.state)
        state["bindings"]["settings"] = {"door_height_cm": 210, "wall_height_cm": 320}
        saved = self.save(state)
        self.assertEqual(saved["draft"]["layout"]["openings"][0]["clear_height_cm"], 210)
        state["validation_mode"] = "gameplay"
        blocked = self.save(state, saved["base_revision_id"])
        self.assertFalse(blocked["report"]["validation"]["metric_valid"])
        state["start_room_id"], state["goal_room_id"] = list(state["bindings"]["region_kinds"])
        passed = self.save(state, blocked["base_revision_id"])
        self.assertTrue(passed["report"]["validation"]["metric_valid"], passed["draft"]["issues"])

    def test_semantic_confirmation_and_reviewer_are_required(self):
        state = deepcopy(self.state)
        state["semantics_confirmed"] = False
        first = self.save(state)
        with self.assertRaises(ReviewError):
            self.store.transact("Data_1", first["base_revision_id"], "accept", reviewer="Test")
        second = self.save(self.state, first["base_revision_id"])
        for name in (None, " ", 123):
            with self.assertRaises(ReviewError):
                self.store.transact("Data_1", second["base_revision_id"], "accept", reviewer=name)

    def test_topology_edit_invalidates_export_and_resets_bindings(self):
        first = self.save()
        accepted = self.store.transact(
            "Data_1", first["base_revision_id"], "accept", reviewer="Test"
        )
        new = self.topology.save(
            "Data_1", two_rooms(), self.bindings["topology_revision_id"], "accept"
        )
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")
        with self.assertRaises(ReviewError):
            self.store.transact("Data_1", accepted["base_revision_id"], "save", self.state)
        loaded = self.store.load("Data_1")
        self.assertTrue(loaded["topology_reset"])
        self.assertEqual(loaded["state"]["bindings"]["dimensions"], [])
        self.assertEqual(loaded["state"]["bindings"]["topology_revision_id"], new["revision_id"])

    def test_changed_original_or_observations_block_accepted_download(self):
        first = self.save()
        self.store.transact("Data_1", first["base_revision_id"], "accept", reviewer="Test")
        self.obs.write_text(self.obs.read_text() + " ")
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")

    def test_ignore_nonmeasurement_keeps_observations_and_is_undoable(self):
        state = deepcopy(self.state)
        d = state["bindings"]["dimensions"].pop()
        evidence = d["provenance"]["evidence_ids"][0]
        state["bindings"]["ignored_texts"] = [
            {"evidence_id": evidence, "reason": "User rejected this OCR text as nonmeasurement."}
        ]
        first = self.save(state)
        self.assertNotIn(
            evidence,
            [
                e
                for d in first["draft"]["layout"]["dimensions"]
                for e in d["provenance"]["evidence_ids"]
            ],
        )
        self.assertIn(evidence, [t["id"] for t in first["observations"]["texts"]])
        invalid = deepcopy(self.state)
        invalid["bindings"]["ignored_texts"] = state["bindings"]["ignored_texts"]
        with self.assertRaises(ReviewError):
            self.save(invalid, first["base_revision_id"])

    def test_unsaved_accept_payload_and_tampered_snapshot_rejected(self):
        first = self.save()
        changed = deepcopy(self.state)
        changed["names"]["r001"] = "Changed"
        with self.assertRaises(ReviewError):
            self.store.transact(
                "Data_1", first["base_revision_id"], "accept", changed, reviewer="Test"
            )
        record = self.store.latest("Data_1")
        path = self.store.output / "Data_1" / "revisions" / (record["revision_id"] + ".json")
        data = json.loads(path.read_text())
        data["state"]["names"]["r001"] = "tampered"
        path.write_text(json.dumps(data))
        with self.assertRaises(ReviewError):
            self.store.load("Data_1")

    def corridor_state(self):
        doc = fixture(8)
        layout = doc["layout"]
        vertices = {v["id"]: v["position_cm"] for v in layout["vertices"]}
        lines = []
        openings = []

        def px(point):
            return [10 + point[0] / 10, 100 - point[1] / 10]

        for edge in layout["walls"]:
            a, b = (vertices[edge[k]] for k in ("start_vertex_id", "end_vertex_id"))
            axis = 0 if edge["axis"] == "x" else 1
            intervals = sorted(
                (
                    (
                        a[axis] + o["center_offset_cm"] - o["clear_width_cm"] / 2,
                        a[axis] + o["center_offset_cm"] + o["clear_width_cm"] / 2,
                        o,
                    )
                    for o in layout["openings"]
                    if o["wall_id"] == edge["id"]
                )
            )
            cursor = a[axis]
            for lo, hi, opening in intervals + [(b[axis], b[axis], None)]:
                p, q = (list(a), list(a))
                p[axis] = cursor
                q[axis] = lo
                if lo > cursor:
                    lines.append(
                        wall(
                            "physical" + str(len(lines)),
                            px(p),
                            px(q),
                            "horizontal" if axis == 0 else "vertical",
                        )
                    )
                if opening:
                    p, q = (list(a), list(a))
                    p[axis] = lo
                    q[axis] = hi
                    openings.append(
                        {
                            "id": opening["id"],
                            "start": px(p),
                            "end": px(q),
                            "axis": "horizontal" if axis == 0 else "vertical",
                            "decision": "approved",
                            "kind": opening["type"],
                        }
                    )
                cursor = hi
        revision = self.topology.save(
            "Data_1", state_with(lines, openings), self.bindings["topology_revision_id"], "accept"
        )
        state = deepcopy(self.state)
        bindings = state["bindings"]
        bindings["topology_revision_id"] = revision["revision_id"]
        ids = {"rA": "r001", "rB": "r002", "c0": "r003"}
        bindings["region_kinds"] = {"r001": "room", "r002": "room", "r003": "corridor"}
        bindings["dimensions"] = deepcopy(layout["dimensions"])
        for d in bindings["dimensions"]:
            if "region_id" in d["target"]:
                d["target"]["region_id"] = ids[d["target"]["region_id"]]
            d["provenance"].update(
                method="user_correction",
                evidence_ids=[],
                note="Explicit controlled Data8 reference measurement.",
            )
        bindings["ignored_texts"] = [
            {
                "evidence_id": f"t{i}",
                "reason": "Placeholder OCR label belongs to the original two-room unit-test seed, not the corridor fixture.",
            }
            for i in range(1, 7)
        ]
        bindings["relations"] = [
            relation("center", "d0", "centered_opening"),
            relation("entrance", "o-c0-rB", "full_span_opening"),
        ]
        return state

    def test_data8_door_move_keeps_near_edge_and_support_local_offsets_distinct(self):
        state = self.corridor_state()
        first = self.save(state)
        self.assertTrue(first["report"]["validation"]["metric_valid"], first["draft"]["issues"])
        offset = next(
            (
                d
                for d in state["bindings"]["dimensions"]
                if d["target"].get("opening_id") == "d0" and d["target"]["type"] == "opening_offset"
            )
        )
        offset["value_cm"] = 320
        moved = self.save(state, first["base_revision_id"])
        self.assertTrue(moved["report"]["validation"]["metric_valid"], moved["draft"]["issues"])
        opening = next((o for o in moved["draft"]["layout"]["openings"] if o["id"] == "d0"))
        self.assertEqual(opening["center_offset_cm"], 100)
        right = next((r for r in moved["draft"]["layout"]["rooms"] if r["id"] == "r002"))
        vertices = {v["id"]: v["position_cm"] for v in moved["draft"]["layout"]["vertices"]}
        self.assertEqual(min((vertices[v][1] for v in right["boundary_vertex_ids"])), 90)

    def test_data10_type_missing_room_width_depth_corridor_width_require_user_values(self):
        state = self.corridor_state()
        missing = []
        for d in state["bindings"]["dimensions"]:
            t = d["target"]
            if t["type"] == "region_span" and (
                t["region_id"] == "r002" or (t["region_id"] == "r003" and t["axis"] == "y")
            ):
                missing.append((d, d["value_cm"]))
                d.update(value_cm=None, state="missing")
        self.assertEqual(len(missing), 3)
        saved = self.save(state)
        self.assertEqual(saved["report"]["status"], "underdetermined")
        with self.assertRaises(ReviewError):
            self.store.transact("Data_1", saved["base_revision_id"], "accept", reviewer="Test")
        for d, value in missing:
            d.update(value_cm=value, state="confirmed")
        fixed = self.save(state, saved["base_revision_id"])
        self.assertTrue(fixed["report"]["validation"]["metric_valid"], fixed["draft"]["issues"])
        accepted = self.store.transact(
            "Data_1", fixed["base_revision_id"], "accept", reviewer="Test"
        )
        self.assertEqual(accepted["status"], "accepted")

    def test_topology_wall_delete_undo_never_exports_old_metric_snapshot(self):
        first = self.save()
        accepted = self.store.transact(
            "Data_1", first["base_revision_id"], "accept", reviewer="Test"
        )
        state = two_rooms()
        state["walls"].pop()
        revision = self.topology.save(
            "Data_1", state, self.bindings["topology_revision_id"], "save_draft"
        )
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")
        with self.assertRaises(ReviewError):
            self.store.transact("Data_1", accepted["base_revision_id"], "undo")
        self.topology.save("Data_1", two_rooms(), revision["revision_id"], "accept")
        self.assertTrue(self.store.load("Data_1")["topology_reset"])
        with self.assertRaises(ReviewError):
            self.store.export("Data_1")

    def test_download_revision_id_must_match_displayed_snapshot(self):
        first = self.save()
        a = self.store.transact("Data_1", first["base_revision_id"], "accept", reviewer="Test")
        saved = self.save(self.state, a["base_revision_id"])
        b = self.store.transact("Data_1", saved["base_revision_id"], "accept", reviewer="Test")
        with self.assertRaises(ReviewError):
            self.store.export("Data_1", a["base_revision_id"])
        self.assertEqual(
            self.store.export("Data_1", b["base_revision_id"])["kind"], "validated_layout"
        )

    def test_metric_http_routes_session_gate_and_download(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.topology))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"

        def get(path):
            with urlopen(url + path) as response:
                return response.read()

        try:
            token = json.loads(get("/api/bootstrap"))["token"]
            self.assertIn(b"Accept metric layout", get("/metric.html"))
            self.assertIn(b"dimensionTarget", get("/metric.js"))
            self.assertEqual(json.loads(get("/api/metric?case=Data_1"))["status"], "unsaved")
            payload = {"case_id": "Data_1", "base_revision_id": None, "state": self.state}
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(
                        url + "/api/metric/save",
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                )
            self.assertEqual(error.exception.code, 403)
            with urlopen(
                Request(
                    url + "/api/metric/save",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "X-Review-Token": token},
                )
            ) as response:
                saved = json.load(response)
            payload = {
                "case_id": "Data_1",
                "base_revision_id": saved["base_revision_id"],
                "reviewer": "HTTP tester",
            }
            with urlopen(
                Request(
                    url + "/api/metric/accept",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "X-Review-Token": token},
                )
            ) as response:
                accepted = json.load(response)
            exported = json.loads(get("/api/metric/export?case=Data_1"))
            self.assertEqual(exported["kind"], "validated_layout")
            self.assertEqual(accepted["status"], "accepted")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
