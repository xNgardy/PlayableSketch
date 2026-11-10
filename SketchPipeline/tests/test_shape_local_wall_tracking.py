import unittest
import numpy as np
from SketchPipeline.shape_authoring.local_wall_tracking import opening_candidates
from SketchPipeline.shape_authoring.opening_ablation import experiment
from SketchPipeline.tests import test_opening_ablation as fixtures


class IntegratedTrackingTests(unittest.TestCase):

    def test_matches_frozen_B_on_physical_door(self):
        args = fixtures.OpeningAblationTests().scene()
        actual, _ = opening_candidates(*args[:4])
        expected, _ = experiment(*args, tracking=True)
        geometry = lambda proposals: [
            (p["segment"], p["start"], p["end"], p["type"]) for p in proposals
        ]
        self.assertEqual(geometry(actual), geometry(expected))

    def test_rejects_incidental_gap(self):
        args = fixtures.OpeningAblationTests().scene(ticks=False)
        actual, _ = opening_candidates(*args[:4])
        self.assertEqual(actual, [])

    def test_rejects_closed_tick_marked_wall(self):
        args = fixtures.OpeningAblationTests().scene(clear=False)
        actual, _ = opening_candidates(*args[:4])
        self.assertEqual(actual, [])

    def test_model_center_mode_does_not_enable_raw_fallback(self):
        args = fixtures.OpeningAblationTests().scene()
        args[2][3] = 0
        strict, _ = opening_candidates(*args[:4], mode="model_center")
        paired, _ = opening_candidates(*args[:4], mode="paired_raw")
        self.assertEqual(strict, [])
        self.assertEqual(len(paired), 1)

    def test_requires_two_owners(self):
        args = list(fixtures.OpeningAblationTests().scene())
        args[0] = {key: [0] for key in args[0]}
        actual, _ = opening_candidates(*args[:4])
        self.assertEqual(actual, [])


if __name__ == "__main__":
    unittest.main()
