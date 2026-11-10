import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.corridor_candidates import recover, overlap


def room(bounds):
    return {"type": "room", "bounds_px": bounds, "model_score": 1.0}


class CorridorCandidateTests(unittest.TestCase):

    def straight(self):
        gray = np.full((256, 256), 255, np.uint8)
        for x in (100, 120):
            cv2.line(gray, (x, 60), (x, 140), 0, 1)
        return (gray, [room([70, 20, 150, 60]), room([70, 140, 150, 180])])

    def test_parallel_observed_walls_connect_open_room_faces(self):
        gray, boxes = self.straight()
        result, _ = recover(gray, boxes)
        self.assertEqual(result[-1]["bounds_px"], [100.0, 60, 120.0, 140])
        self.assertEqual(len(result), 3)

    def test_closed_face_blocks_connection(self):
        gray, boxes = self.straight()
        cv2.line(gray, (100, 60), (120, 60), 0, 2)
        result, _ = recover(gray, boxes)
        self.assertEqual(result, boxes)

    def test_blank_and_unanchored_walls_do_not_create_regions(self):
        gray, boxes = self.straight()
        result, _ = recover(np.full_like(gray, 255), boxes)
        self.assertEqual(result, boxes)
        result, _ = recover(gray, boxes[:1])
        self.assertEqual(result, boxes[:1])

    def test_l_bend_uses_two_nonoverlapping_segments(self):
        gray = np.full((256, 256), 255, np.uint8)
        for a, b in [
            ((100, 60), (100, 150)),
            ((120, 60), (120, 130)),
            ((120, 130), (180, 130)),
            ((100, 150), (180, 150)),
        ]:
            cv2.line(gray, a, b, 0, 1)
        boxes = [room([70, 20, 150, 60]), room([180, 110, 220, 170])]
        straight, _ = recover(gray, boxes, bends=False)
        result, _ = recover(gray, boxes, bends=True)
        self.assertEqual(straight, boxes)
        self.assertEqual(len(result), 4)
        self.assertEqual(overlap(result[2]["bounds_px"], result[3]["bounds_px"]), 0)
        self.assertEqual(result[2]["bounds_px"][0], result[3]["bounds_px"][2])


if __name__ == "__main__":
    unittest.main()
