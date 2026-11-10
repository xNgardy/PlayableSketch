import copy
import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.decoder import (
    region_boxes as legacy_regions,
    boundary_graph,
    iou,
)
from SketchPipeline.shape_authoring.decoder_refined import decode, opening_candidates
from SketchPipeline.shape_authoring.region_recovery import (
    region_boxes,
    joint_regularize,
    structural_ink,
    supported_barrier,
)
from SketchPipeline.shape_authoring.contract import validate_authoring


def walls(gray):
    probabilities = np.zeros((6, *gray.shape), np.float32)
    probabilities[0, gray < 100] = 0.95
    return probabilities


class SupportedRegionTests(unittest.TestCase):

    def test_joint_shared_wall_repairs_small_overlap_instead_of_dropping_room(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (20, 20), (236, 236), 0, 2)
        cv2.line(gray, (128, 20), (128, 236), 0, 2)
        probabilities = walls(gray)
        ink, axis = structural_ink(gray)
        boxes = [
            {"type": "room", "bounds_px": [20, 20, 134, 236], "model_score": 0.95},
            {"type": "room", "bounds_px": [125, 20, 236, 236], "model_score": 0.9},
        ]
        original = copy.deepcopy(boxes)
        fixed, detail = joint_regularize(boxes, gray.shape, probabilities, ink, axis)
        self.assertEqual(len(fixed), 2)
        self.assertEqual(boxes, original)
        self.assertEqual(fixed[0]["bounds_px"][2], fixed[1]["bounds_px"][0])
        self.assertAlmostEqual(fixed[0]["bounds_px"][2], 128, delta=1)
        self.assertEqual(iou(fixed[0]["bounds_px"], fixed[1]["bounds_px"]), 0)
        self.assertTrue(detail["joint_boundary_pairs"])

    def test_t_junction_is_solved_as_one_shared_boundary_group(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (20, 20), (236, 236), 0, 2)
        cv2.line(gray, (128, 20), (128, 236), 0, 2)
        cv2.line(gray, (128, 128), (236, 128), 0, 2)
        probabilities = walls(gray)
        ink, axis = structural_ink(gray)
        boxes = [
            {"type": "room", "bounds_px": b, "model_score": 0.9 - i * 0.01}
            for i, b in enumerate([[20, 20, 134, 236], [125, 20, 236, 128], [130, 128, 236, 236]])
        ]
        fixed, _ = joint_regularize(boxes, gray.shape, probabilities, ink, axis)
        reversed_result, _ = joint_regularize(
            list(reversed(boxes)), gray.shape, probabilities, ink, axis
        )
        self.assertEqual(fixed, reversed_result)
        self.assertEqual(len(fixed), 3)
        for i, box in enumerate(fixed):
            for other in fixed[i + 1 :]:
                self.assertEqual(iou(box["bounds_px"], other["bounds_px"]), 0)
        self.assertEqual(
            len([owners for owners in boundary_graph(fixed)[0].values() if len(owners) == 2]), 3
        )

    def test_deep_overlap_is_not_repaired_as_a_shared_wall(self):
        gray = np.full((256, 256), 255, np.uint8)
        probability = walls(gray)
        ink, axis = structural_ink(gray)
        boxes = [
            {"type": "room", "bounds_px": [20, 20, 160, 236], "model_score": 0.95},
            {"type": "room", "bounds_px": [80, 20, 236, 236], "model_score": 0.9},
        ]
        result, detail = joint_regularize(boxes, gray.shape, probability, ink, axis)
        self.assertEqual(len(result), 1)
        self.assertEqual(detail["joint_boundary_pairs"], [])
        self.assertEqual(len(detail["unresolved_overlaps"]), 1)

    def test_small_corridor_requires_two_observed_parallel_walls(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (100, 100), (100, 128), 0, 2)
        cv2.line(gray, (120, 100), (120, 128), 0, 2)
        probability = walls(gray)
        probability[2, 105:124, 105:116] = 0.95
        before = probability.copy()
        self.assertEqual(legacy_regions(probability, gray)[0], [])
        result, rejected, detail = region_boxes(probability, gray)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "corridor_segment")
        self.assertEqual(len(detail["supported_components"]), 1)
        self.assertTrue(np.array_equal(before, probability))
        blank = np.full(gray.shape, 255, np.uint8)
        self.assertEqual(region_boxes(probability, blank)[0], [])

    def test_fragmented_room_is_recovered_only_with_bounding_wall_support(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (40, 40), (100, 100), 0, 2)
        probability = walls(gray)
        probability[1, 45:95, 45:95] = 0.95
        probability[1, 45:75, 45:75] = 0
        self.assertEqual(legacy_regions(probability, gray)[0], [])
        result, _, detail = region_boxes(probability, gray)
        self.assertEqual(len(result), 1)
        self.assertTrue(detail["supported_components"][0]["was_irregular"])
        self.assertEqual(region_boxes(probability, np.full_like(gray, 255))[0], [])

    def test_high_semantic_response_on_numeric_text_does_not_recover_small_corridor(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.putText(gray, "120", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.35, 0, 1)
        probability = walls(gray)
        probability[2, 110:121, 100:120] = 0.99
        result, _, _ = region_boxes(probability, gray)
        self.assertEqual(result, [])

    def stacked(self, transpose=False, ticks=True):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (20, 20), (236, 236), 0, 2)
        cv2.line(gray, (20, 128), (236, 128), 0, 2)
        cv2.line(gray, (85, 128), (110, 128), 255, 5)
        if ticks:
            for x in [85, 110]:
                cv2.line(gray, (x, 120), (x, 136), 0, 2)
        probability = walls(gray)
        probability[1, 24:232, 24:232] = 0.95
        for x in [85, 110]:
            cv2.circle(probability[3], (x, 128), 4, 0.95, -1)
        if transpose:
            return (gray.T.copy(), probability.transpose(0, 2, 1).copy())
        return (gray, probability)

    def test_round_endpoint_heatmaps_split_regions_in_both_orientations(self):
        for transpose in [False, True]:
            gray, probability = self.stacked(transpose)
            ink, axis = structural_ink(gray)
            barrier, closures = supported_barrier(probability, gray, ink, axis, 2)
            self.assertTrue(closures)
            result, _, _ = region_boxes(probability, gray)
            self.assertEqual(len(result), 2)
            openings, _ = opening_candidates(
                boundary_graph(result)[0], gray, probability, np.eye(3)
            )
            self.assertEqual(len(openings), 1)

    def test_false_marker_heatmap_cannot_create_physical_door(self):
        for transpose in [False, True]:
            gray, probability = self.stacked(transpose, ticks=False)
            boxes, _, _ = region_boxes(probability, gray)
            openings, _ = opening_candidates(boundary_graph(boxes)[0], gray, probability, np.eye(3))
            self.assertEqual(openings, [])

    def test_public_decoder_contract_and_explicit_legacy_control(self):
        gray, probability = self.stacked(True)
        metadata = {
            "working_size_px": [256, 256],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        source = {
            "image_path": "test.png",
            "image_sha256": "0" * 64,
            "width_px": 256,
            "height_px": 256,
        }
        result, detail = decode(gray, probability, source, metadata)
        self.assertEqual(validate_authoring(result), [])
        self.assertEqual(detail["version"], "shape-decoder/2.4")
        self.assertEqual(result["physical_design"]["acceptance"]["status"], "pending")
        _, legacy = decode(gray, probability, source, metadata, region_policy="legacy")
        self.assertEqual(legacy["version"], "shape-decoder/2.3")
        with self.assertRaises(ValueError):
            decode(gray, probability, source, metadata, region_policy="unknown")


if __name__ == "__main__":
    unittest.main()
