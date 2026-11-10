import copy
import unittest
from pathlib import Path
from SketchPipeline.import_bridge.export_legacy import export_legacy
from SketchPipeline.validation.validate import load_json

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "Data" / "import_examples"


class LegacyExportTests(unittest.TestCase):

    def setUp(self):
        self.document = load_json(EXAMPLES / "legacy_two_rooms.validated.json")
        self.observations = load_json(EXAMPLES / "legacy_two_rooms.observations.json")

    def test_exact_conversion(self):
        original = copy.deepcopy(self.document)
        output = export_legacy(self.document, self.observations)
        self.assertEqual(output, load_json(EXAMPLES / "legacy_two_rooms.legacy-import.json"))
        self.assertEqual(output["rooms"][0]["width_cm"], 435)
        self.assertEqual(output["rooms"][0]["min_cm"], [10, 10])
        self.assertEqual(output["connections"][0]["door_a"]["offset_cm"], 290)
        self.assertEqual(output["connections"][0]["expected_corridor_min_cm"], [445, 200])
        self.assertEqual(self.document, original)

    def test_all_photo_references_are_rejected_as_unsupported(self):
        for n in range(1, 9):
            folder = ROOT / "Data" / "ground_truth" / "v1"
            with self.subTest(case=n), self.assertRaises(ValueError):
                export_legacy(
                    load_json(folder / f"Data_{n}.validated.json"),
                    load_json(folder / f"Data_{n}.observations.json"),
                )

    def test_incomplete_and_conflicting_drafts_rejected(self):
        for n in (9, 10):
            folder = ROOT / "Data" / "ground_truth" / "v1"
            with self.subTest(case=n), self.assertRaises(ValueError):
                export_legacy(
                    load_json(folder / f"Data_{n}.draft.json"),
                    load_json(folder / f"Data_{n}.observations.json"),
                )

    def test_missing_gameplay_roles_rejected(self):
        self.document.update(validation_mode="geometry_only", start_room_id=None, goal_room_id=None)
        for room in self.document["layout"]["rooms"]:
            room["role"] = "none"
        with self.assertRaises(ValueError):
            export_legacy(self.document, self.observations)

    def test_fractional_legacy_dimensions_are_not_rounded(self):
        for vertex in self.document["layout"]["vertices"]:
            if vertex["position_cm"][0] == 0:
                vertex["position_cm"][0] = -0.5
        self.document["layout"]["dimensions"][0]["value_cm"] = 455.5
        with self.assertRaisesRegex(ValueError, "whole centimeters"):
            export_legacy(self.document, self.observations)

    def test_vertical_corridor_export(self):
        d = self.document
        points = {v["id"]: v for v in d["layout"]["vertices"]}
        lengths = {
            w["id"]: abs(
                points[w["end_vertex_id"]]["position_cm"][0]
                - points[w["start_vertex_id"]]["position_cm"][0]
            )
            + abs(
                points[w["end_vertex_id"]]["position_cm"][1]
                - points[w["start_vertex_id"]]["position_cm"][1]
            )
            for w in d["layout"]["walls"]
        }
        for vertex in points.values():
            x, y = vertex["position_cm"]
            vertex["position_cm"] = [-y, x]
        for wall in d["layout"]["walls"]:
            wall["axis"] = "y" if wall["axis"] == "x" else "x"
            if tuple(points[wall["start_vertex_id"]]["position_cm"]) > tuple(
                points[wall["end_vertex_id"]]["position_cm"]
            ):
                wall["start_vertex_id"], wall["end_vertex_id"] = (
                    wall["end_vertex_id"],
                    wall["start_vertex_id"],
                )
                for opening in d["layout"]["openings"]:
                    if opening["wall_id"] == wall["id"]:
                        opening["center_offset_cm"] = (
                            lengths[wall["id"]] - opening["center_offset_cm"]
                        )
        for measurement in d["layout"]["dimensions"]:
            target = measurement["target"]
            if target["type"] == "region_span":
                target["axis"] = "y" if target["axis"] == "x" else "x"
            elif target["type"] == "opening_offset":
                target["side"] = {"east": "north", "west": "south"}[target["side"]]
        output = export_legacy(d, self.observations)
        self.assertEqual(output["rooms"][0]["min_cm"], [-590, 10])
        self.assertEqual(output["connections"][0]["expected_corridor_min_cm"], [-400, 445])
        self.assertEqual(output["connections"][0]["expected_corridor_max_cm"], [-200, 1065])
        self.assertEqual(output["connections"][0]["door_a"]["side"], "north")

    def test_room_array_order_does_not_change_roles_or_bounds(self):
        self.document["layout"]["rooms"].reverse()
        output = export_legacy(self.document, self.observations)
        self.assertEqual(output["start_room_id"], "rA")
        self.assertEqual(output["connections"][0]["expected_corridor_min_cm"], [445, 200])

    def test_unequal_door_widths_rejected(self):
        opening = self.document["layout"]["openings"][0]
        opening["clear_width_cm"] = 140
        for m in self.document["layout"]["dimensions"]:
            if m["target"] == {"type": "opening_width", "opening_id": opening["id"]}:
                m["value_cm"] = 140
        with self.assertRaisesRegex(ValueError, "shared door width"):
            export_legacy(self.document, self.observations)


if __name__ == "__main__":
    unittest.main()
