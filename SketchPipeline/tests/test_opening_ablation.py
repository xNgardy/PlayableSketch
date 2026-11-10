import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.opening_ablation import experiment, wall_path


class OpeningAblationTests(unittest.TestCase):

    def scene(self, ticks=True, clear=True):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (128, 20), (128, 236), 0, 2)
        if clear:
            cv2.line(gray, (128, 98), (128, 126), 255, 5)
        if ticks:
            for y in (96, 128):
                cv2.line(gray, (120, y), (136, y), 0, 2)
        prob = np.zeros((6, 256, 256), np.float32)
        end = np.zeros((256, 256), np.float32)
        for y in (96, 128):
            cv2.circle(prob[3], (128, y), 4, 1.0, -1)
            cv2.circle(end, (128, y), 3, 1.0, -1)
        segments = {((128.0, 20.0), (128.0, 236.0)): [0, 1]}
        return (segments, gray, prob, np.eye(3), end)

    def test_physical_door_and_ablation_combinations(self):
        for a, b in [(True, False), (False, True), (True, True)]:
            proposals, _ = experiment(*self.scene(), endpoint_first=a, tracking=b)
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["type"], "door")

    def test_endpoint_predictions_do_not_make_incidental_break_a_door(self):
        for a, b in [(True, False), (False, True), (True, True)]:
            proposals, _ = experiment(*self.scene(ticks=False), endpoint_first=a, tracking=b)
            self.assertEqual(proposals, [])

    def test_ticks_on_continuous_wall_do_not_make_door(self):
        proposals, _ = experiment(*self.scene(clear=False), endpoint_first=True, tracking=True)
        self.assertEqual(proposals, [])

    def test_interpolated_path_does_not_create_ink(self):
        structural = np.zeros((256, 256), np.uint8)
        path = wall_path(structural, 1, 128, 20, 236, 13)
        self.assertTrue(np.all(path == 128))
        self.assertEqual(int(structural.sum()), 0)

    def test_tracking_follows_bounded_curved_wall(self):
        structural = np.zeros((256, 256), np.uint8)
        for y in range(20, 237):
            structural[y, round(122 + (y - 20) / 216 * 12)] = 1
        path = wall_path(structural, 1, 128, 20, 236, 13)
        self.assertLess(path[0], 125)
        self.assertGreater(path[-1], 131)
        self.assertTrue(np.all(np.abs(np.diff(path)) <= 1.00001))
        self.assertTrue(np.all(np.abs(path - 128) <= 13))

    def test_curved_door_recovered_without_second_model_endpoint(self):
        segments, gray, prob, matrix, end = self.scene()
        gray[:] = 255
        cv2.line(gray, (122, 20), (122, 96), 0, 2)
        cv2.line(gray, (134, 128), (134, 236), 0, 2)
        cv2.line(gray, (114, 96), (130, 96), 0, 2)
        cv2.line(gray, (126, 128), (142, 128), 0, 2)
        prob[:] = 0
        end[:] = 0
        cv2.circle(prob[3], (122, 96), 4, 1.0, -1)
        cv2.circle(end, (122, 96), 3, 1.0, -1)
        control, _ = experiment(segments, gray, prob, matrix, end)
        tracked, detail = experiment(segments, gray, prob, matrix, end, tracking=True)
        self.assertEqual(control, [])
        self.assertEqual(len(tracked), 1)
        added = [c for c in detail["experimental_candidates"] if c["status"] == "proposed"]
        self.assertTrue(added[0]["strong_raw"])
        self.assertFalse(added[0]["model_supported"])


if __name__ == "__main__":
    unittest.main()
