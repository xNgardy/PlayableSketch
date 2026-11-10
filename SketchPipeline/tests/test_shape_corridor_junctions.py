import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.corridor_junctions import add_observed_passages


class CorridorJunctionTests(unittest.TestCase):

    def setUp(self):
        self.gray = np.full((256, 256), 255, np.uint8)
        self.segment = ((120.0, 130.0), (120.0, 150.0))
        self.segments = {self.segment: [0, 1]}

    def propose(self, gray=None, recovered=(1,), proposals=()):
        return add_observed_passages(
            list(proposals),
            self.segments,
            self.gray if gray is None else gray,
            np.eye(3),
            recovered,
        )[0]

    def test_clear_recovered_interface_is_passage_without_model(self):
        result = self.propose()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "open_passage")
        self.assertEqual(result[0]["entity_indices"], [0, 1])

    def test_closed_interface_is_not_connected(self):
        cv2.line(self.gray, (120, 130), (120, 150), 0, 2)
        self.assertEqual(self.propose(), [])

    def test_partial_obstruction_is_not_full_width_passage(self):
        cv2.line(self.gray, (120, 135), (120, 145), 0, 2)
        self.assertEqual(self.propose(), [])

    def test_existing_or_non_recovered_interface_is_unchanged(self):
        self.assertEqual(self.propose(recovered=()), [])
        p = {"segment": self.segment, "type": "door"}
        self.assertEqual(self.propose(proposals=[p]), [p])

    def test_scaled_evidence_checks_correct_wall_location(self):
        cv2.line(self.gray, (60, 65), (60, 75), 0, 2)
        result, _ = add_observed_passages([], self.segments, self.gray, np.diag([0.5, 0.5, 1]), [1])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()


class CanonicalOwnershipTests(unittest.TestCase):

    def test_recovery_cannot_assign_wall_to_three_regions(self):
        from SketchPipeline.shape_authoring.corridor_junctions import append_manifold_regions

        box = lambda b: {"type": "room", "bounds_px": b}
        existing = [box([0, 0, 10, 20]), box([0, 10, 10, 30])]
        recovered = [{"type": "corridor_segment", "bounds_px": [10, 10, 20, 20]}]
        result, rejected = append_manifold_regions(existing, recovered)
        self.assertEqual(result, existing)
        self.assertEqual(rejected[0]["reason"], "more_than_two_boundary_owners")

    def test_valid_two_owner_turn_is_kept(self):
        from SketchPipeline.shape_authoring.corridor_junctions import append_manifold_regions

        existing = [{"type": "corridor_segment", "bounds_px": [0, 0, 10, 20]}]
        addition = [{"type": "corridor_segment", "bounds_px": [10, 10, 20, 20]}]
        result, rejected = append_manifold_regions(existing, addition)
        self.assertEqual(result, existing + addition)
        self.assertEqual(rejected, [])
