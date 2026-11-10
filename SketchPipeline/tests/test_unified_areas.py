import unittest
import cv2, numpy as np
from SketchPipeline.shape_authoring.unified_areas import (
    largest_rectangle,
    partition,
    classify_interfaces,
)


class UnifiedAreaTests(unittest.TestCase):

    def test_rectangle_partition_preserves_l_shape_without_overlap(self):
        mask = np.zeros((60, 60), np.uint8)
        mask[5:50, 5:15] = 1
        mask[40:50, 15:50] = 1
        parts = partition(mask, 50, 4)
        self.assertEqual(len(parts), 2)
        cover = np.zeros_like(mask)
        for x, y, X, Y in parts:
            cover[y:Y, x:X] += 1
        np.testing.assert_array_equal(cover, mask)

    def test_blank_has_no_rectangle(self):
        self.assertEqual(largest_rectangle(np.zeros((12, 12), np.uint8)), (0, None))

    def test_touching_rectangles_do_not_connect_through_closed_wall(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (128, 20), (128, 230), 0, 3)
        boxes = [
            {"type": "room", "bounds_px": [20.0, 20.0, 128.0, 230.0]},
            {"type": "room", "bounds_px": [128.0, 20.0, 230.0, 230.0]},
        ]
        openings, _ = classify_interfaces(
            boxes, gray, np.zeros((6, 256, 256), np.float32), np.eye(3)
        )
        self.assertEqual(openings, [])

    def test_clear_shared_boundary_has_one_two_owner_opening(self):
        gray = np.full((256, 256), 255, np.uint8)
        boxes = [
            {"type": "room", "bounds_px": [20.0, 20.0, 128.0, 230.0]},
            {"type": "room", "bounds_px": [128.0, 20.0, 230.0, 230.0]},
        ]
        openings, _ = classify_interfaces(
            boxes, gray, np.zeros((6, 256, 256), np.float32), np.eye(3)
        )
        self.assertEqual(len(openings), 1)
        self.assertEqual(openings[0]["entity_indices"], [0, 1])
        self.assertEqual(openings[0]["type"], "open_passage")


if __name__ == "__main__":
    unittest.main()


class UnifiedOwnershipTests(unittest.TestCase):

    def test_one_door_is_referenced_by_both_rooms(self):
        from SketchPipeline.shape_authoring.decoder import authoring_document, boundary_graph

        boxes = [
            {"type": "room", "bounds_px": [20.0, 20.0, 128.0, 230.0]},
            {"type": "room", "bounds_px": [128.0, 20.0, 230.0, 230.0]},
        ]
        segment = next((s for s, o in boundary_graph(boxes)[0].items() if len(o) == 2))
        door = {
            "segment": segment,
            "entity_indices": [0, 1],
            "start": [128.0, 100.0],
            "end": [128.0, 120.0],
            "type": "door",
        }
        doc = authoring_document(
            {
                "image_path": "probe.png",
                "image_sha256": "0" * 64,
                "width_px": 256,
                "height_px": 256,
            },
            {
                "working_size_px": [256, 256],
                "working_to_original": np.eye(3).tolist(),
                "original_to_working": np.eye(3).tolist(),
            },
            boxes,
            [door],
        )
        self.assertEqual(len(doc["topology"]["openings"]), 1)
        opening = doc["topology"]["openings"][0]
        self.assertEqual(set(opening["entity_ids"]), {r["id"] for r in doc["topology"]["regions"]})
        self.assertTrue(
            all((opening["support_wall_id"] in r["wall_ids"] for r in doc["topology"]["regions"]))
        )

    def test_observed_rooms_need_no_corridor_class_and_detached_rooms_stay_detached(self):
        from SketchPipeline.shape_authoring.unified_areas import decode_observed

        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (20, 30), (100, 120), 0, 2)
        cv2.rectangle(gray, (150, 140), (230, 230), 0, 2)
        source = {
            "image_path": "probe.png",
            "image_sha256": "0" * 64,
            "width_px": 256,
            "height_px": 256,
        }
        metadata = {
            "working_size_px": [256, 256],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        doc, _ = decode_observed(
            gray,
            np.zeros((6, 256, 256), np.float32),
            source,
            metadata,
            working_gray=gray,
            working_metadata=metadata,
            evidence_to_working=np.eye(3),
        )
        self.assertEqual(len(doc["topology"]["regions"]), 2)
        self.assertEqual(doc["topology"]["openings"], [])
        self.assertTrue(all((r["type"] == "room" for r in doc["topology"]["regions"])))


class HolePreservationTests(unittest.TestCase):

    def test_only_grain_holes_are_filled_not_large_enclosures(self):
        from SketchPipeline.shape_authoring.unified_areas import fill_small_holes

        mask = np.ones((50, 50), np.uint8)
        mask[10:30, 10:30] = 0
        mask[40, 40] = 0
        result = fill_small_holes(mask, 16)
        self.assertEqual(result[40, 40], 1)
        np.testing.assert_array_equal(result[10:30, 10:30], np.zeros((20, 20), np.uint8))
