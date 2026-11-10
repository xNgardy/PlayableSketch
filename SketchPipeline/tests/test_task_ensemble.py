import unittest
import cv2, numpy as np
from SketchPipeline.shape_authoring.task_ensemble import guided_doors


class TaskEnsembleTests(unittest.TestCase):

    def scene(self, closed=False):
        gray = np.full((256, 256), 255, np.uint8)
        for a, b in [
            ((20, 128), (100, 128)),
            ((120, 128), (236, 128)),
            ((100, 116), (100, 140)),
            ((120, 116), (120, 140)),
        ]:
            cv2.line(gray, a, b, 0, 2)
        if closed:
            cv2.line(gray, (100, 128), (120, 128), 0, 2)
        peaks = np.zeros_like(gray, dtype=np.float32)
        for p in [(100, 128), (120, 128)]:
            cv2.circle(peaks, p, 2, 0.9, -1)
        boxes = [
            {"type": "room", "bounds_px": [20.0, 20.0, 236.0, 128.0]},
            {"type": "room", "bounds_px": [20.0, 128.0, 236.0, 236.0]},
        ]
        return (gray, peaks, boxes)

    def test_endpoint_pair_requires_physical_jambs_and_gap(self):
        gray, p, boxes = self.scene()
        doors, _ = guided_doors([], boxes, gray, p, np.eye(3))
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["entity_indices"], [0, 1])
        gray, p, boxes = self.scene(True)
        self.assertEqual(guided_doors([], boxes, gray, p, np.eye(3))[0], [])

    def test_high_confidence_on_blank_does_not_manufacture_door(self):
        gray, p, boxes = self.scene()
        gray[:] = 255
        self.assertEqual(guided_doors([], boxes, gray, p, np.eye(3))[0], [])

    def test_detector_cannot_create_regions_or_connect_missing_owner(self):
        gray, p, boxes = self.scene()
        before = [b.copy() for b in boxes]
        self.assertEqual(guided_doors([], boxes[:1], gray, p, np.eye(3))[0], [])
        guided_doors([], boxes, gray, p, np.eye(3))
        self.assertEqual(boxes, before)

    def test_existing_door_is_retained_without_duplicate(self):
        gray, p, boxes = self.scene()
        segment = ((20.0, 128.0), (236.0, 128.0))
        old = {
            "segment": segment,
            "entity_indices": [0, 1],
            "start": [100.0, 128.0],
            "end": [120.0, 128.0],
            "type": "door",
        }
        doors, _ = guided_doors([old], boxes, gray, p, np.eye(3))
        self.assertEqual(doors, [old])


class LocalEndpointViewTests(unittest.TestCase):

    def test_native_tile_coordinates_are_restored_without_ground_truth(self):
        from SketchPipeline.shape_authoring.task_ensemble import endpoint_tiles

        class Detector:

            def predict(self, a, b):
                self.last_auxiliary = np.zeros((8, *a.shape), np.float32)
                self.last_auxiliary[6, 64, 64] = 1

        gray = np.full((512, 512), 255, np.uint8)
        prob = np.zeros((512, 512), np.float32)
        boxes = [
            {"type": "room", "bounds_px": [20.0, 20.0, 256.0, 490.0]},
            {"type": "room", "bounds_px": [256.0, 20.0, 490.0, 490.0]},
        ]
        fused, records = endpoint_tiles(boxes, gray, gray, Detector(), prob, np.eye(3))
        self.assertEqual(len(records), 1)
        x, y, X, Y = records[0]["bounds_native"]
        self.assertEqual(fused[y + 64, x + 64], 1)
        self.assertFalse(records[0]["ground_truth_used"])
        self.assertEqual(prob.sum(), 0)

    def test_no_shared_boundary_means_no_label_guided_crop(self):
        from SketchPipeline.shape_authoring.task_ensemble import endpoint_tiles

        class Detector:

            def predict(self, a, b):
                raise AssertionError("No inference expected")

        gray = np.full((512, 512), 255, np.uint8)
        prob = np.zeros_like(gray, dtype=np.float32)
        result, records = endpoint_tiles(
            [{"type": "room", "bounds_px": [10.0, 10.0, 100.0, 100.0]}],
            gray,
            gray,
            Detector(),
            prob,
            np.eye(3),
        )
        np.testing.assert_array_equal(result, prob)
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
