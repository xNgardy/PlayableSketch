import unittest
import cv2
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union
from Scripts.hybrid_candidate_inference import regions_from_predictions


class HybridCandidateTests(unittest.TestCase):
    def two_rooms(self):
        barrier = np.zeros((512, 512), np.uint8)
        cv2.rectangle(barrier, (40, 40), (240, 240), 1, 2)
        cv2.rectangle(barrier, (240, 40), (440, 240), 1, 2)
        cv2.line(barrier, (240, 120), (240, 160), 0, 5)
        return barrier.astype(float), [([230, 116, 250, 164], 0.9)]

    def test_observed_door_separates_connected_interiors(self):
        wall, doors = self.two_rooms()
        boxes, rooms, _, attached = regions_from_predictions(
            wall, doors, {"wall_threshold": 0.5, "door_threshold": 0.3, "closing_kernel": 3}
        )
        self.assertEqual((len(boxes), len(rooms)), (1, 2))
        self.assertEqual(attached, [True])

    def test_unmarked_wide_ends_and_narrow_neck_are_one_room(self):
        polygon = unary_union(
            [box(40, 80, 150, 240), box(150, 150, 310, 170), box(310, 80, 450, 240)]
        )
        barrier = np.zeros((512, 512), np.uint8)
        cv2.polylines(barrier, [np.asarray(polygon.exterior.coords, np.int32)], True, 1, 2)
        boxes, rooms, _, _ = regions_from_predictions(
            barrier.astype(float),
            [],
            {"wall_threshold": 0.5, "door_threshold": 0.3, "closing_kernel": 3},
        )
        self.assertEqual((len(boxes), len(rooms)), (0, 1))

    def test_low_confidence_door_does_not_close_an_open_connection(self):
        wall, doors = self.two_rooms()
        doors = [(doors[0][0], 0.1)]
        boxes, rooms, _, _ = regions_from_predictions(
            wall, doors, {"wall_threshold": 0.5, "door_threshold": 0.3, "closing_kernel": 3}
        )
        self.assertEqual((len(boxes), len(rooms)), (0, 1))

    def test_nonfinite_masks_are_rejected(self):
        wall = np.zeros((64, 64))
        wall[0, 0] = np.nan
        with self.assertRaises(ValueError):
            regions_from_predictions(
                wall, [], {"wall_threshold": 0.5, "door_threshold": 0.3, "closing_kernel": 3}
            )

    def test_overlapping_detector_tiles_map_back_and_deduplicate(self):
        import importlib.util

        if importlib.util.find_spec("torchvision") is None:
            self.skipTest("Optional candidate detector environment required")
        from types import SimpleNamespace
        import torch
        from Scripts.hybrid_candidate_inference import door_predictions

        class Detector:
            def __init__(self):
                self.index = 0

            def predict(self, image, **kwargs):
                offsets = [(0, 0), (0, 0), (384, 0), (0, 384), (384, 384)]
                x, y = offsets[self.index]
                self.index += 1
                boxes = torch.tensor([[490 - x, 490 - y, 530 - x, 510 - y]], dtype=torch.float32)
                return [
                    SimpleNamespace(boxes=SimpleNamespace(xyxy=boxes, conf=torch.tensor([0.8])))
                ]

        result = door_predictions(Detector(), np.full((1024, 1024), 255, np.uint8), "cpu")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], [490, 490, 530, 510])

    def test_truncated_internal_tile_detection_is_discarded(self):
        import importlib.util

        if importlib.util.find_spec("torchvision") is None:
            self.skipTest("Optional candidate detector environment required")
        from types import SimpleNamespace
        import torch
        from Scripts.hybrid_candidate_inference import door_predictions

        class Detector:
            def __init__(self):
                self.index = 0

            def predict(self, image, **kwargs):
                self.index += 1
                boxes = (
                    torch.tensor([[1, 200, 20, 225]], dtype=torch.float32)
                    if self.index == 3
                    else torch.empty((0, 4))
                )
                return [
                    SimpleNamespace(
                        boxes=SimpleNamespace(xyxy=boxes, conf=torch.full((len(boxes),), 0.9))
                    )
                ]

        result = door_predictions(Detector(), np.full((1024, 1024), 255, np.uint8), "cpu")
        self.assertEqual(result, [])
