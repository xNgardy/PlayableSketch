import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.perception.structural import suppress_grid, classify_lines, structural_lines
from SketchPipeline.experiments.geometry_vlm import parse_output, image_support, proposal_geometry
from SketchPipeline.experiments.geometry_vlm_guided import output_schema
from SketchPipeline.perception.run import predict
from SketchPipeline.tests.test_perception import StubOCR
from SketchPipeline.experiments.geometry_report import count_f1


class StructuralTests(unittest.TestCase):

    def test_opt_in_profile_keeps_ocr_and_baseline_revision_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.png"
            image = np.full((320, 480, 3), 250, np.uint8)
            cv2.rectangle(image, (30, 70), (440, 280), (30, 30, 30), 3)
            Image.fromarray(image).save(path)
            with patch(
                "SketchPipeline.perception.run.load_json", side_effect=AssertionError("No GT")
            ):
                baseline, *_ = predict(path, StubOCR())
                explicit, *_ = predict(path, StubOCR(), geometry_profile="baseline")
                grid, working, _, masks = predict(path, StubOCR(), geometry_profile="grid")
            self.assertEqual(baseline, explicit)
            self.assertEqual(baseline["texts"], grid["texts"])
            self.assertNotEqual(baseline["revision_id"], grid["revision_id"])
            self.assertEqual(working["geometry"]["structural_experiment"]["profile"], "grid")
            self.assertIn("grid_suppression", masks)

    def test_grid_suppression_preserves_dark_wall_and_door_gap(self):
        image = np.full((320, 320), 250, np.uint8)
        for x in range(0, 320, 24):
            cv2.line(image, (x, 0), (x, 319), 225, 1)
            cv2.line(image, (0, x), (319, x), 225, 1)
        cv2.line(image, (48, 40), (48, 135), 40, 3)
        cv2.line(image, (48, 185), (48, 280), 40, 3)
        result, mask, info = suppress_grid(image)
        self.assertGreater(info["suppressed_pixels"], 1000)
        self.assertEqual(int(result[100, 48]), 40)
        self.assertEqual(int(result[160, 48]), 250)
        self.assertGreater(int(result[100, 24]), int(image[100, 24]))
        self.assertTrue(np.array_equal(image[100, 48], result[100, 48]))

    def test_sparse_walls_do_not_trigger_grid_erasure(self):
        image = np.full((320, 320), 250, np.uint8)
        for x in [30, 105, 190, 280]:
            cv2.line(image, (x, 20), (x, 300), 210, 2)
        result, mask, info = suppress_grid(image)
        self.assertTrue(np.array_equal(result, image))
        self.assertEqual(info["suppressed_pixels"], 0)

    def test_thin_gray_rail_is_excluded_but_black_wall_retained(self):
        image = np.full((320, 320), 250, np.uint8)
        cv2.line(image, (40, 30), (40, 290), 30, 4)
        cv2.line(image, (180, 30), (180, 290), 160, 1)
        lines = [
            dict(id="wall", start=[40, 30], end=[40, 290], role="wall_candidate"),
            dict(id="rail", start=[180, 30], end=[180, 290], role="wall_candidate"),
        ]
        classified = classify_lines(image, lines)
        self.assertEqual([x["id"] for x in structural_lines(classified)], ["wall"])
        self.assertEqual(lines[1]["role"], "wall_candidate")

    def test_same_ink_annotation_is_not_falsely_claimed_as_solved(self):
        image = np.full((320, 320), 250, np.uint8)
        cv2.line(image, (60, 20), (60, 290), 30, 3)
        cv2.line(image, (180, 20), (180, 290), 30, 3)
        lines = [
            dict(id=str(x), start=[x, 20], end=[x, 290], role="wall_candidate") for x in [60, 180]
        ]
        self.assertEqual(len(structural_lines(classify_lines(image, lines))), 2)


class VLMContractTests(unittest.TestCase):

    def test_failed_predictions_stay_in_f1_reference_denominator(self):
        successful = {"metrics": {"openings": {"true_positive": 2, "predicted": 2, "reference": 2}}}
        failed = {
            "status": "failed",
            "metrics": {"openings": {"true_positive": 0, "predicted": 0, "reference": 2}},
        }
        self.assertAlmostEqual(count_f1([successful, failed]), 2 / 3)
        self.assertEqual(count_f1([failed]), 0)

    def payload(self):
        return dict(
            keep_walls=[], keep_openings=[], walls=[[0, 10, 1000, 10]], openings=[], regions=[]
        )

    def test_strict_parse_fenced_json_and_no_code_execution(self):
        value = self.payload()
        self.assertEqual(parse_output("```json\n" + json.dumps(value) + "\n```"), value)
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            parse_output('__import__("os").system("echo invalid")')

    def test_reject_invalid_model_coordinates_and_partial_json(self):
        for coords in [[0, 0, 1001, 10], [0, 0, float("nan"), 10], [True, 1, 4, 5], [0, 0, 0, 0]]:
            value = self.payload()
            value["walls"] = [coords]
            with self.assertRaises(ValueError):
                parse_output(json.dumps(value))
        with self.assertRaises(ValueError):
            parse_output('{"walls":[]}')

    def test_missing_image_support_vetoes_hallucinated_wall(self):
        image = np.full((320, 320), 255, np.uint8)
        self.assertEqual(image_support(image, [20, 20], [280, 20]), 0)
        working = {
            "geometry": {"dominant_rotation_degrees": 0, "recovery_lines": {}},
            "line_detectors": {},
        }
        result = proposal_geometry(self.payload(), working, image, ([], []))
        self.assertEqual(result["line_detectors"]["lsd"], [])
        self.assertFalse(result["vlm_gate"][0]["accepted"])

    def test_unknown_supplied_ids_are_not_silently_accepted(self):
        payload = self.payload()
        payload["keep_walls"] = ["fake"]
        with self.assertRaises(ValueError):
            proposal_geometry(payload, {}, np.full((32, 32), 255, np.uint8), ([], []))

    def test_vlm_noop_preserves_recovery_and_existing_topology(self):
        wall = dict(
            id="wall-1", start=[10, 10], end=[90, 10], axis="horizontal", role="wall_candidate"
        )
        recovery = dict(
            id="recovered", start=[90, 10], end=[100, 10], axis="horizontal", role="unknown"
        )
        topology = {"existing_evidence": "must survive a no-op"}
        working = {
            "line_detectors": {"lsd": [wall]},
            "gaps": [],
            "geometry": {"recovery_lines": {"lsd": [recovery]}},
            "topology": topology,
        }
        parsed = dict(keep_walls=["wall-1"], keep_openings=[], walls=[], openings=[], regions=[])
        result = proposal_geometry(
            parsed, working, np.full((128, 128), 255, np.uint8), ([wall], [])
        )
        self.assertEqual(result["geometry"]["recovery_lines"]["lsd"], [recovery])
        self.assertEqual(result["topology"], topology)
        self.assertTrue(result["vlm_noop_preserved_evidence"])

    def test_guided_schema_uses_supplied_ids_not_reference_geometry(self):
        schema = output_schema(["image-wall-1"], ["image-gap-1"])
        self.assertEqual(
            schema["properties"]["keep_walls"]["properties"], {"image-wall-1": {"type": "boolean"}}
        )
        self.assertEqual(schema["properties"]["keep_openings"]["required"], ["image-gap-1"])
        self.assertEqual(output_schema([], [])["properties"]["keep_walls"]["properties"], {})


if __name__ == "__main__":
    unittest.main()
