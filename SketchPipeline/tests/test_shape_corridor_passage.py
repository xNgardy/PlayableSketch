import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.corridor_refinement import refine
from SketchPipeline.shape_authoring.passage_refinement import opening_candidates
from SketchPipeline.shape_authoring.region_recovery import structural_ink


class CorridorPassageTests(unittest.TestCase):

    def corridor_scene(self):
        gray = np.full((256, 256), 255, np.uint8)
        for x in [100, 120]:
            cv2.line(gray, (x, 60), (x, 140), 0, 2)
        p = np.zeros((6, 256, 256), np.float32)
        p[0, 60:141, 99:102] = 1
        p[0, 60:141, 119:122] = 1
        rejected = [
            {
                "code": "UNSUPPORTED_RECOVERY",
                "type": "corridor_segment",
                "bounds_px": [100.0, 65.0, 128.0, 135.0],
                "area_px": 200,
                "fill": 0.7,
                "model_mean": 0.99,
            }
        ]
        return (gray, p, rejected)

    def test_parallel_walls_recover_misfitted_corridor(self):
        gray, p, rejected = self.corridor_scene()
        _, masks = structural_ink(gray)
        boxes, records = refine([], rejected, p, gray, masks)
        self.assertEqual(len(boxes), 1)
        self.assertLessEqual(boxes[0]["bounds_px"][2], 122)
        self.assertEqual(records[0]["action"], "parallel_wall_refit")

    def test_model_wall_hallucination_on_blank_does_not_recover_corridor(self):
        gray, p, rejected = self.corridor_scene()
        gray[:] = 255
        _, masks = structural_ink(gray)
        boxes, _ = refine([], rejected, p, gray, masks)
        self.assertEqual(boxes, [])

    def test_recovery_does_not_insert_overlapping_region(self):
        gray, p, rejected = self.corridor_scene()
        _, masks = structural_ink(gray)
        existing = [{"type": "room", "bounds_px": [80.0, 50.0, 150.0, 150.0], "model_score": 0.99}]
        boxes, _ = refine(existing, rejected, p, gray, masks)
        self.assertEqual(boxes, existing)

    def test_coherent_wall_blocks_hallucinated_interface(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (40, 128), (210, 128), 0, 2)
        p = np.zeros((6, 256, 256), np.float32)
        p[5, 124:133, 40:211] = 1
        proposals, detail = opening_candidates(
            {((40.0, 128.0), (210.0, 128.0)): [0, 1]},
            gray,
            p,
            np.eye(3),
            region_types=["room", "corridor_segment"],
        )
        self.assertEqual(proposals, [])
        self.assertGreaterEqual(detail["passage_candidates"][0]["coherent_crossing_wall"], 0.8)

    def test_blank_without_learned_interface_does_not_create_passage(self):
        gray = np.full((256, 256), 255, np.uint8)
        p = np.zeros((6, 256, 256), np.float32)
        proposals, _ = opening_candidates(
            {((40.0, 128.0), (210.0, 128.0)): [0, 1]},
            gray,
            p,
            np.eye(3),
            region_types=["room", "corridor_segment"],
        )
        self.assertEqual(proposals, [])

    def test_open_interface_with_clear_ink_is_supported(self):
        gray = np.full((256, 256), 255, np.uint8)
        p = np.zeros((6, 256, 256), np.float32)
        p[5, 124:133, 40:81] = 1
        proposals, _ = opening_candidates(
            {((40.0, 128.0), (80.0, 128.0)): [0, 1]},
            gray,
            p,
            np.eye(3),
            region_types=["room", "corridor_segment"],
        )
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "open_passage")


if __name__ == "__main__":
    unittest.main()
