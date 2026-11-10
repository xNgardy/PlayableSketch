import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.door_geometry import opening_candidates, detect_pairs


class DoorGeometryTests(unittest.TestCase):

    def scene(self, closed=False):
        image = np.full((256, 256), 255, np.uint8)
        for a, b in [
            ((30, 128), (100, 128)),
            ((120, 128), (230, 128)),
            ((100, 116), (100, 140)),
            ((120, 116), (120, 140)),
        ]:
            cv2.line(image, a, b, 0, 2)
        if closed:
            cv2.line(image, (100, 128), (120, 128), 0, 2)
        return image

    def test_perpendicular_pair_with_clear_gap_is_a_door(self):
        doors, _ = opening_candidates(
            [], {((30.0, 128.0), (230.0, 128.0)): [0, 1]}, self.scene(), np.eye(3)
        )
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["type"], "door")
        self.assertEqual(doors[0]["entity_indices"], [0, 1])

    def test_occupied_gap_is_not_a_door(self):
        self.assertEqual(detect_pairs(self.scene(closed=True))[0], [])

    def test_one_jamb_or_parallel_rails_are_not_door(self):
        image = self.scene()
        image[113:144, 117:124] = 255
        self.assertEqual(detect_pairs(image)[0], [])
        image = np.full((256, 256), 255, np.uint8)
        for y in [110, 140]:
            cv2.line(image, (50, y), (200, y), 0, 2)
        self.assertEqual(detect_pairs(image)[0], [])

    def test_missing_regions_preserve_unattached_evidence(self):
        doors, detail = opening_candidates([], {}, self.scene(), np.eye(3))
        self.assertEqual(doors, [])
        self.assertTrue(any((q["status"] == "unattached" for q in detail["candidates"])))

    def test_door_upgrades_passage_and_preserves_existing_door(self):
        seg = ((30.0, 128.0), (230.0, 128.0))
        old = {
            "segment": seg,
            "entity_indices": [0, 1],
            "start": [100.0, 128.0],
            "end": [120.0, 128.0],
            "type": "open_passage",
        }
        doors, _ = opening_candidates([old], {seg: [0, 1]}, self.scene(), np.eye(3))
        self.assertEqual([d["type"] for d in doors], ["door"])
        old["type"] = "door"
        doors, _ = opening_candidates([old], {seg: [0, 1]}, self.scene(), np.eye(3))
        self.assertEqual(doors, [old])


if __name__ == "__main__":
    unittest.main()


class DoorAttachmentGuards(unittest.TestCase):

    def test_open_corridor_corners_do_not_count_as_crossing_jambs(self):
        image = np.full((256, 256), 255, np.uint8)
        for a, b in [
            ((30, 128), (100, 128)),
            ((120, 128), (230, 128)),
            ((100, 128), (100, 240)),
            ((120, 128), (120, 240)),
        ]:
            cv2.line(image, a, b, 0, 2)
        self.assertEqual(detect_pairs(image)[0], [])

    def test_ambiguous_region_pair_is_not_assigned(self):
        image = DoorGeometryTests().scene()
        segments = {
            ((30.0, 127.0), (230.0, 127.0)): [0, 1],
            ((30.0, 129.0), (230.0, 129.0)): [2, 3],
        }
        doors, detail = opening_candidates([], segments, image, np.eye(3))
        self.assertEqual(doors, [])
        self.assertTrue(any((q.get("reason") == "ambiguous_owners" for q in detail["candidates"])))

    def test_scaled_evidence_coordinates_attach_to_canonical_wall(self):
        image = DoorGeometryTests().scene()
        segment = ((15.0, 64.0), (115.0, 64.0))
        doors, _ = opening_candidates([], {segment: [0, 1]}, image, np.diag([2.0, 2.0, 1.0]))
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["start"][1], 64.0)
