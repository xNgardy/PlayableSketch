import sys
import unittest
from unittest.mock import patch
import numpy as np
from SketchPipeline.shape_authoring import decoder
from SketchPipeline.shape_authoring.dino_region_audit import trace_regions, stage_matches


class DinoRegionAuditTests(unittest.TestCase):

    def inputs(self):
        return (np.zeros((6, 256, 256), np.float32), np.full((256, 256), 255, np.uint8))

    def test_observes_overlap_drop_without_changing_decoder_or_arrays(self):
        probability, gray = self.inputs()
        probability[1, 24:220, 24:126] = 0.95
        probability[2, 24:220, 124:224] = 0.9
        before = probability.copy()
        image = gray.copy()
        regularizer = decoder.regularize_boxes
        profile = sys.getprofile()
        expected, rejected = decoder.region_boxes(probability, gray)
        trace = trace_regions(probability, gray)
        self.assertEqual(trace["final"], expected)
        self.assertEqual(trace["rejected"], rejected)
        self.assertEqual(len(trace["after_snap"]), 2)
        self.assertEqual(len(trace["overlap_drops"]), 1)
        self.assertGreater(trace["overlap_drops"][0]["conflicts"][0]["iou"], 0)
        self.assertTrue(np.array_equal(before, probability))
        self.assertTrue(np.array_equal(image, gray))
        self.assertIs(decoder.regularize_boxes, regularizer)
        self.assertIs(sys.getprofile(), profile)

    def test_small_and_irregular_components_are_logged_before_their_gates(self):
        probability, gray = self.inputs()
        probability[1, 100:110, 100:120] = 0.9
        probability[2, 40:110, 40:55] = 0.9
        probability[2, 95:110, 40:110] = 0.9
        trace = trace_regions(probability, gray)
        self.assertEqual(trace["final"], [])
        gates = {c["first_gate"]: c for c in trace["post_barrier_components"]}
        self.assertIn("minimum_area", gates)
        self.assertIn("rectangular_fill", gates)
        small = gates["minimum_area"]
        self.assertLess(small["area_px"], small["minimum_area_px"])
        irregular = gates["rectangular_fill"]
        self.assertLess(irregular["fill"], irregular["minimum_fill"])

    def test_nms_loss_is_distinct_from_final_overlap_loss(self):
        probability, gray = self.inputs()
        probability[1, 30:150, 30:150] = 0.95
        probability[2, 30:150, 30:150] = 0.9
        trace = trace_regions(probability, gray)
        self.assertEqual(len(trace["fitted"]), 2)
        self.assertEqual(len(trace["after_nms"]), 1)
        self.assertEqual(trace["overlap_drops"], [])
        self.assertEqual(len(trace["final"]), 1)

    def test_profiler_and_patched_global_restore_when_original_raises(self):
        probability, gray = self.inputs()
        profile = sys.getprofile()
        regularizer = decoder.regularize_boxes

        def broken(boxes, shape, stroke=None):
            raise RuntimeError("test failure")

        with patch.object(decoder, "regularize_boxes", broken):
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                trace_regions(probability, gray)
            self.assertIs(decoder.regularize_boxes, broken)
            self.assertIs(sys.getprofile(), profile)
        self.assertIs(decoder.regularize_boxes, regularizer)

    def test_one_merged_component_cannot_count_as_two_reference_regions(self):
        boxes = [{"bounds_px": [0, 0, 100, 100]}]
        reference = [{"bounds_px": [0, 0, 50, 100]}, {"bounds_px": [50, 0, 100, 100]}]
        self.assertEqual(len(stage_matches(boxes, reference)), 1)


if __name__ == "__main__":
    unittest.main()
