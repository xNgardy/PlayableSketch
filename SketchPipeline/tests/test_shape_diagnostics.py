import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import project
from SketchPipeline.shape_authoring.diagnostic_preprocessing import (
    letterbox,
    map_probabilities,
    prepare_variant,
    suggest_crop,
)

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class DiagnosticPreprocessingTests(unittest.TestCase):

    def metadata(self, width, height):
        return {
            "working_size_px": [width, height],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
            "transform_chain": [],
        }

    def test_letterbox_preserves_aspect_pixels_and_roundtrip(self):
        gray = np.arange(80 * 160, dtype=np.uint8).reshape(80, 160)
        original = self.metadata(160, 80)
        before = copy.deepcopy(original)
        padded, metadata = letterbox(gray, original, 256)
        self.assertEqual(metadata["diagnostic_content_bounds_px"], [48, 88, 208, 168])
        np.testing.assert_array_equal(padded[88:168, 48:208], gray)
        self.assertTrue(np.all(padded[:88] == 255))
        points = np.array([[0, 0], [159, 79], [55, 30]], float)
        mapped = project(points, metadata["original_to_working"])
        np.testing.assert_allclose(mapped, points + [48, 88])
        np.testing.assert_allclose(project(mapped, metadata["working_to_original"]), points)
        self.assertEqual(original, before)

    def test_padding_predictions_do_not_become_source_evidence(self):
        original = self.metadata(160, 80)
        _, padded = letterbox(np.zeros((80, 160), np.uint8), original, 256)
        masks = np.ones((6, 256, 256), np.float32)
        mapped, coverage = map_probabilities(masks, padded, original)
        self.assertEqual(mapped.shape, (6, 80, 160))
        self.assertTrue(coverage.all())
        self.assertTrue(np.all(mapped == 1))

    def test_crop_coverage_and_marker_mapping(self):
        original = self.metadata(160, 80)
        cropped = self.metadata(80, 40)
        cropped["original_to_working"] = [[1, 0, -40], [0, 1, -20], [0, 0, 1]]
        cropped["working_to_original"] = [[1, 0, 40], [0, 1, 20], [0, 0, 1]]
        _, padded = letterbox(np.zeros((40, 80), np.uint8), cropped, 128)
        masks = np.zeros((6, 128, 128), np.float32)
        x, y = project([[70, 40]], padded["original_to_working"])[0].astype(int)
        masks[:, y, x] = 1
        mapped, coverage = map_probabilities(masks, padded, original)
        self.assertEqual(int(coverage.sum()), 80 * 40)
        self.assertTrue(np.all(mapped[:, 40, 70] == 1))
        self.assertFalse(coverage[0, 0])
        self.assertFalse(coverage[79, 159])

    def test_baseline_variant_is_independent_and_pixel_identical(self):
        gray = np.full((80, 160), 120, np.uint8)
        metadata = self.metadata(160, 80)
        result, returned = prepare_variant(None, {"name": "baseline_256"}, gray, metadata)
        np.testing.assert_array_equal(result, gray)
        result[0, 0] = 0
        returned["working_size_px"][0] = 99
        self.assertEqual(gray[0, 0], 120)
        self.assertEqual(metadata["working_size_px"][0], 160)

    def test_image_only_crop_abstains_on_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "blank.png"
            cv2.imwrite(str(image), np.full((400, 800), 255, np.uint8))
            crop, report = suggest_crop(image)
            self.assertIsNone(crop)
            self.assertEqual(report["status"], "abstained")

    def test_crop_retains_observed_long_strokes_with_margin(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "plan.png"
            gray = np.full((800, 1000), 255, np.uint8)
            cv2.rectangle(gray, (300, 200), (700, 600), 0, 4)
            cv2.imwrite(str(image), gray)
            crop, report = suggest_crop(image)
            self.assertEqual(report["status"], "candidate")
            self.assertLess(crop[0], 300)
            self.assertLess(crop[1], 200)
            self.assertGreater(crop[2], 700)
            self.assertGreater(crop[3], 600)

    @unittest.skipUnless(TORCH_AVAILABLE, "Diagnostic scoring uses the isolated model runtime")
    def test_positive_probes_do_not_treat_unannotated_background_as_truth(self):
        from SketchPipeline.shape_authoring.diagnose import positive_probe_metrics

        masks = np.zeros((6, 64, 64), np.float32)
        masks[:, 40:, 40:] = 1
        observations = {"lines": [{"id": "line_a", "start_px": [10, 10], "end_px": [20, 10]}]}
        annotations = {"strokes": [{"kind": "wall", "line_ids": ["line_a"]}], "junctions": []}
        metrics = positive_probe_metrics(
            masks,
            {"regions": []},
            observations,
            annotations,
            self.metadata(64, 64),
            np.ones((64, 64), np.uint8),
        )
        self.assertEqual(metrics["wall"]["hits"], 0)
        self.assertGreater(metrics["wall"]["positive_probes"], 0)
        self.assertNotIn("precision", metrics["wall"])
        self.assertNotIn("iou", metrics["wall"])

    @unittest.skipUnless(TORCH_AVAILABLE, "Native decoder audit uses the isolated model runtime")
    def test_native_scoring_projection_keeps_false_positives_outside_original(self):
        from SketchPipeline.shape_authoring.diagnostic_decoder_audit import document_in_frame

        baseline = self.metadata(160, 80)
        _, native = letterbox(np.zeros((80, 160), np.uint8), baseline, 256)
        document = {
            "topology": {
                "regions": [
                    {
                        "geometry": {
                            "points_px": [[0, 0], [20, 20]],
                            "points_normalized": [[0, 0], [20 / 256, 20 / 256]],
                        }
                    }
                ]
            },
            "image_evidence": {},
        }
        original = copy.deepcopy(document)
        transformed = document_in_frame(document, native, baseline)
        self.assertEqual(
            transformed["topology"]["regions"][0]["geometry"]["points_px"][0], [-48.0, -88.0]
        )
        self.assertEqual(document, original)

    @unittest.skipUnless(TORCH_AVAILABLE, "Decoder control uses the isolated model runtime")
    def test_exact_synthetic_masks_exercise_decoder_without_a_model_prediction(self):
        from SketchPipeline.shape_authoring.diagnose import decode_masks
        from SketchPipeline.shape_authoring.synthetic import render

        gray, masks, specification = render(2001, "clean")
        source = {
            "image_path": "fixture.png",
            "image_sha256": "0" * 64,
            "width_px": 256,
            "height_px": 256,
        }
        document, _ = decode_masks(
            masks.astype(np.float32) / 255.0, gray, self.metadata(256, 256), source
        )
        self.assertEqual(len(document["topology"]["regions"]), len(specification["regions"]))
        self.assertEqual(len(document["topology"]["openings"]), len(specification["openings"]))
        self.assertEqual(document["physical_design"]["acceptance"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
