import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from SketchPipeline.fixtures.build_references import build_case
from SketchPipeline.validation.validate import as_validated, load_json, validate_document

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "Data" / "ground_truth" / "v1"


def fixture(n=3, kind="validated"):
    return load_json(FIXTURES / f"Data_{n}.{kind}.json")


class ContractTests(unittest.TestCase):

    def codes(self, document, observations=None):
        return {i["code"] for i in validate_document(document, observations)["issues"]}

    def test_ten_observation_documents(self):
        for n in range(1, 11):
            with self.subTest(case=n):
                d = fixture(n, "observations")
                self.assertEqual(self.codes(d), set())
                path = FIXTURES / d["source"]["image_path"]
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), d["source"]["image_sha256"]
                )

    def test_eight_accepted_metric_references(self):
        for n in range(1, 9):
            with self.subTest(case=n):
                report = validate_document(fixture(n), fixture(n, "observations"))
                self.assertTrue(report["exportable"], report)

    def test_drafts_do_not_export(self):
        for n in range(1, 9):
            report = validate_document(fixture(n, "draft"))
            self.assertTrue(report["metric_valid"], report)
            self.assertFalse(report["exportable"])

    def test_negative_references_cannot_be_accepted(self):
        expected = {9: "SKETCH_DIMENSION_CONFLICT", 10: "SKETCH_DIMENSION_MISSING"}
        for n, code in expected.items():
            with self.subTest(case=n):
                draft = fixture(n, "draft")
                report = validate_document(draft, fixture(n, "observations"))
                self.assertTrue(report["schema_valid"])
                self.assertFalse(report["metric_valid"])
                self.assertIn(code, self.codes(draft))
                with self.assertRaises(ValueError):
                    as_validated(draft, "test-reviewer", fixture(n, "observations"))

    def test_all_three_missing_measurements_are_preserved(self):
        d = fixture(10, "draft")
        missing = [m for m in d["layout"]["dimensions"] if m["value_cm"] is None]
        self.assertEqual(len(missing), 3)
        self.assertTrue(all((m["state"] == "missing" for m in missing)))

    def test_shared_wall_exists_once(self):
        d = fixture()
        shared = [w for w in d["layout"]["walls"] if set(w["region_ids"]) == {"rA", "rB"}]
        self.assertEqual(len(shared), 1)
        self.assertEqual(len(d["layout"]["walls"]), 7)

    def test_noded_wall_offset_is_not_room_corner_offset(self):
        d = fixture(8)
        door = next((o for o in d["layout"]["openings"] if o["id"] == "d0"))
        self.assertEqual(door["center_offset_cm"], 100)
        measurement = next(
            (
                m
                for m in d["layout"]["dimensions"]
                if m["target"]["type"] == "opening_offset" and m["target"]["opening_id"] == "d0"
            )
        )
        self.assertEqual(measurement["value_cm"], 300)
        self.assertEqual(self.codes(d), set())

    def test_photo_offsets_keep_written_values_and_derive_centers(self):
        for n, edge, width, center in ((3, 200, 120, 260), (4, 150, 180, 240), (5, 450, 150, 525)):
            with self.subTest(case=n):
                d = fixture(n)
                opening = d["layout"]["openings"][0]
                offset = next(
                    (
                        m
                        for m in d["layout"]["dimensions"]
                        if m["target"]["type"] == "opening_offset"
                    )
                )
                self.assertEqual((offset["basis"], offset["value_cm"]), ("edge_offset", edge))
                self.assertEqual(opening["center_offset_cm"], center)
                self.assertEqual(center - width / 2, edge)
                self.assertTrue(validate_document(d)["exportable"])

    def test_user_example_lower_edge_50_width_120_upper_remaining_30(self):
        d = fixture()
        for vertex in d["layout"]["vertices"]:
            x, y = vertex["position_cm"]
            vertex["position_cm"] = [{0: 0, 600: 400, 1100: 900}[x], {0: 0, 400: 200}[y]]
        d["layout"]["openings"][0]["center_offset_cm"] = 110
        for m in d["layout"]["dimensions"]:
            target = m["target"]
            if target["type"] == "region_span":
                m["value_cm"] = (
                    200 if target["axis"] == "y" else 400 if target["region_id"] == "rA" else 500
                )
            elif target["type"] == "opening_offset":
                m["value_cm"] = 50
        self.assertTrue(validate_document(d)["exportable"])
        opening = d["layout"]["openings"][0]
        self.assertEqual(opening["center_offset_cm"] - opening["clear_width_cm"] / 2, 50)
        self.assertEqual(200 - opening["center_offset_cm"] - opening["clear_width_cm"] / 2, 30)

    def test_edge_and_explicit_center_measurements_do_not_conflict(self):
        d = fixture()
        old = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_offset")
        )
        center = copy.deepcopy(old)
        center.update(id="explicit-center-reference", basis="center_offset", value_cm=260)
        d["layout"]["dimensions"].append(center)
        self.assertTrue(validate_document(d)["exportable"])
        old["value_cm"] = 260
        self.assertIn("SKETCH_DIMENSION_CONFLICT", self.codes(d))

    def test_opposite_corner_measures_to_its_near_edge(self):
        d = fixture()
        offset = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_offset")
        )
        upper = copy.deepcopy(offset)
        upper.update(id="upper-edge-reference", value_cm=80)
        upper["target"]["reference"] = "max_corner"
        d["layout"]["dimensions"].append(upper)
        self.assertTrue(validate_document(d)["exportable"])
        upper["value_cm"] = 140
        self.assertIn("SKETCH_DIMENSION_CONFLICT", self.codes(d))

    def test_unequal_entrance_widths_are_used_for_relative_placement(self):
        d = fixture(8)
        points = {v["id"]: v["position_cm"] for v in d["layout"]["vertices"]}
        right = next((r for r in d["layout"]["rooms"] if r["id"] == "rB"))
        self.assertEqual(min((points[v][1] for v in right["boundary_vertex_ids"])), 70)
        for opening in d["layout"]["openings"]:
            wall = next((w for w in d["layout"]["walls"] if w["id"] == opening["wall_id"]))
            center_y = points[wall["start_vertex_id"]][1] + opening["center_offset_cm"]
            self.assertEqual(center_y, 360)

    def test_corridor_centerline_and_clear_width_are_distinct(self):
        d = fixture(6)
        self.assertTrue(all((o["clear_width_cm"] == 180 for o in d["layout"]["openings"])))
        self.assertEqual(len(d["layout"]["openings"]), 2)
        self.assertTrue(all((o["type"] == "open_passage" for o in d["layout"]["openings"])))

    def test_door_and_corridor_entity_types(self):
        d = fixture(8)
        door = next((o for o in d["layout"]["openings"] if o["type"] == "door"))
        self.assertEqual({e["type"] for e in door["connected_entities"]}, {"room", "corridor"})

    def test_unknown_version_rejected(self):
        d = fixture()
        d["schema_version"] = "playablesketch-layout/2.0"
        self.assertIn("SKETCH_SCHEMA_INVALID", self.codes(d))

    def test_negative_zero_boolean_and_nonfinite_numbers_rejected(self):
        for value in (-1, 0, True, float("nan"), float("inf"), 1e100):
            with self.subTest(value=value):
                d = fixture()
                d["layout"]["openings"][0]["clear_width_cm"] = value
                self.assertIn("SKETCH_SCHEMA_INVALID", self.codes(d))

    def test_unknown_fields_rejected(self):
        d = fixture()
        d["layout"]["walls"][0]["mystery"] = 1
        self.assertIn("SKETCH_SCHEMA_INVALID", self.codes(d))

    def test_missing_endpoint_reference_rejected(self):
        d = fixture()
        d["layout"]["walls"][0]["end_vertex_id"] = "not-found"
        self.assertIn("SKETCH_REFERENCE_MISSING", self.codes(d))

    def test_duplicate_ids_rejected(self):
        d = fixture()
        d["layout"]["vertices"].append(copy.deepcopy(d["layout"]["vertices"][0]))
        self.assertIn("SKETCH_ID_DUPLICATE", self.codes(d))

    def test_duplicate_shared_wall_rejected(self):
        d = fixture()
        wall = copy.deepcopy(d["layout"]["walls"][0])
        wall["id"] = "duplicate-wall"
        d["layout"]["walls"].append(wall)
        self.assertIn("SKETCH_WALL_DUPLICATE", self.codes(d))

    def test_boundary_order_rejected(self):
        d = fixture()
        d["layout"]["rooms"][0]["boundary_wall_ids"].reverse()
        self.assertIn("SKETCH_BOUNDARY_INVALID", self.codes(d))

    def test_wall_ownership_rejected(self):
        d = fixture()
        d["layout"]["walls"][0]["region_ids"] = ["rB"]
        self.assertIn("SKETCH_WALL_OWNERSHIP", self.codes(d))

    def test_out_of_bounds_opening_rejected(self):
        d = fixture()
        d["layout"]["openings"][0]["center_offset_cm"] = 500
        self.assertIn("SKETCH_OPENING_OUT_OF_BOUNDS", self.codes(d))

    def test_overlapping_openings_rejected(self):
        d = fixture()
        opening = copy.deepcopy(d["layout"]["openings"][0])
        opening["id"] = "second-door"
        d["layout"]["openings"].append(opening)
        self.assertIn("SKETCH_OPENING_OVERLAP", self.codes(d))

    def test_too_tall_opening_rejected(self):
        d = fixture()
        d["layout"]["openings"][0]["clear_height_cm"] = 500
        self.assertIn("SKETCH_OPENING_OUT_OF_BOUNDS", self.codes(d))

    def test_dimension_geometry_conflict_rejected(self):
        d = fixture()
        d["layout"]["dimensions"][0]["value_cm"] = 900
        self.assertIn("SKETCH_DIMENSION_CONFLICT", self.codes(d))

    def test_wrong_measurement_basis_rejected(self):
        d = fixture()
        d["layout"]["dimensions"][0]["basis"] = "clear_opening"
        self.assertIn("SKETCH_DIMENSION_BASIS", self.codes(d))

    def test_changed_evidence_identity_rejected(self):
        obs = fixture(3, "observations")
        obs["document_id"] = "wrong"
        self.assertIn("SKETCH_EVIDENCE_INVALID", self.codes(fixture(), obs))

    def test_unknown_evidence_reference_rejected(self):
        d = fixture()
        d["layout"]["dimensions"][0]["provenance"]["evidence_ids"] = ["unknown-text"]
        self.assertIn("SKETCH_REFERENCE_MISSING", self.codes(d, fixture(3, "observations")))

    def test_inferred_measurement_does_not_export(self):
        d = fixture(3, "draft")
        d["layout"]["dimensions"][0]["state"] = "inferred"
        self.assertIn("SKETCH_REVIEW_REQUIRED", self.codes(d))
        with self.assertRaises(ValueError):
            as_validated(d, "test-reviewer", fixture(3, "observations"))

    def test_geometry_only_single_room_requires_no_fake_goal(self):
        self.assertTrue(validate_document(fixture(1))["exportable"])
        d = fixture(1)
        d["validation_mode"] = "gameplay"
        self.assertIn("SKETCH_ROLE_INVALID", self.codes(d))

    def test_unconnected_adjacency_is_not_gameplay_connection(self):
        d = fixture()
        d["layout"]["openings"] = []
        d["layout"]["passages"] = []
        d["layout"]["dimensions"] = [
            m for m in d["layout"]["dimensions"] if not m["target"]["type"].startswith("opening")
        ]
        d["validation_mode"] = "gameplay"
        d["start_room_id"] = "rA"
        d["goal_room_id"] = "rB"
        d["layout"]["rooms"][0]["role"] = "start"
        d["layout"]["rooms"][1]["role"] = "goal"
        self.assertIn("SKETCH_CONNECTIVITY_INVALID", self.codes(d))

    def test_complete_text_annotation_requires_regions(self):
        d = fixture(1, "observations")
        d["region_annotation_status"] = "complete"
        self.assertIn("SKETCH_EVIDENCE_MISSING", self.codes(d))

    def test_outside_pixel_polygon_and_singular_transform_rejected(self):
        d = fixture(1, "observations")
        d["texts"][0]["polygon_px"] = [[0, 0], [1, 0], [100000000.0, 100000000.0]]
        self.assertIn("SKETCH_EVIDENCE_OUT_OF_BOUNDS", self.codes(d))
        d = fixture(1, "observations")
        d["frame"]["original_to_frame"] = [[0, 0, 0]] * 3
        self.assertIn("SKETCH_FRAME_INVALID", self.codes(d))

    def test_acceptance_is_explicit_and_does_not_mutate_input(self):
        d = fixture(1, "draft")
        old = copy.deepcopy(d)
        accepted = as_validated(d, "test-reviewer", fixture(1, "observations"))
        self.assertEqual(d, old)
        self.assertEqual(accepted["parent_revision_id"], d["revision_id"])
        self.assertTrue(validate_document(accepted)["exportable"])
        with self.assertRaises(ValueError):
            as_validated(d, " ")

    def test_acceptance_requires_linked_observations(self):
        with self.assertRaises(ValueError):
            as_validated(fixture(1, "draft"), "test-reviewer")

    def test_global_setting_change_requires_resolved_geometry_refresh(self):
        d = fixture(6)
        d["settings"]["wall_thickness_cm"] = 40
        self.assertIn("SKETCH_SETTINGS_CONFLICT", self.codes(d))
        d = fixture(6)
        d["layout"]["openings"][0]["clear_width_cm"] = 160
        self.assertIn("SKETCH_SETTINGS_CONFLICT", self.codes(d))

    def test_layout_cannot_masquerade_as_observations(self):
        self.assertIn("SKETCH_EVIDENCE_INVALID", self.codes(fixture(), fixture(1)))

    def test_strict_json_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.json"
            for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
                p.write_text(raw)
                with self.assertRaises(ValueError):
                    load_json(p)

    def test_conversion_is_reproducible(self):
        for n in range(1, 11):
            with self.subTest(case=n):
                obs, draft = build_case(n)
                self.assertEqual(obs, fixture(n, "observations"))
                self.assertEqual(draft, fixture(n, "draft"))


if __name__ == "__main__":
    unittest.main()
