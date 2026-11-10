import json
import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.opening_alignment import align_interval, door_conflicts
from SketchPipeline.shape_authoring.passage_refinement import opening_candidates
from SketchPipeline.shape_authoring.corridor_junctions import add_observed_passages


class OpeningAlignmentTests(unittest.TestCase):

    def scene(self, lo=100.8, hi=119.2, closed=False, vertical=False):
        gray = np.full((256, 256), 255, np.uint8)
        for a, b in [
            ((20, 128), (100, 128)),
            ((120, 128), (236, 128)),
            ((100, 116), (100, 140)),
            ((120, 116), (120, 140)),
        ]:
            cv2.line(gray, a, b, 0, 2)
        if closed:
            cv2.line(gray, (100, 128), (120, 128), 0, 3)
        prob = np.zeros((6, 256, 256), np.float32)
        prob[3] = 0.9
        prob[5] = 0.9
        segment = ((lo, 128.0), (hi, 128.0))
        if vertical:
            gray = gray.T.copy()
            prob = prob.transpose(0, 2, 1).copy()
            segment = tuple(((p[1], p[0]) for p in segment))
        return (gray, prob, {segment: [0, 1]})

    def test_small_verified_overhang_is_attached_in_both_axes(self):
        for vertical in [False, True]:
            gray, prob, segments = self.scene(vertical=vertical)
            proposals, detail = opening_candidates(
                segments,
                gray,
                prob,
                np.eye(3),
                region_types=["room", "corridor_segment"],
                align_doors=True,
            )
            self.assertEqual([p["type"] for p in proposals], ["door"], detail)
            p = proposals[0]
            axis = 1 if vertical else 0
            self.assertGreaterEqual(p["start"][axis], 100.8)
            self.assertLessEqual(p["end"][axis], 119.2)
            self.assertEqual(p["entity_indices"], [0, 1])
            json.dumps(p["evidence"].get("alignment", {}))

    def test_large_overhang_remains_unresolved_and_cannot_be_a_passage(self):
        gray, prob, segments = self.scene(103.0, 117.0)
        proposals, detail = opening_candidates(
            segments,
            gray,
            prob,
            np.eye(3),
            region_types=["room", "corridor_segment"],
            align_doors=True,
        )
        self.assertEqual(proposals, [], detail)
        proposals, fallback = add_observed_passages(
            proposals, segments, gray, np.eye(3), [1], door_evidence=detail
        )
        self.assertEqual(proposals, [])
        self.assertTrue(
            any((r["reason"] == "paired_door_evidence_unresolved" for r in fallback["interfaces"]))
        )

    def test_legacy_option_keeps_previous_behavior(self):
        gray, prob, segments = self.scene(103.0, 117.0)
        proposals, _ = opening_candidates(
            segments, gray, prob, np.eye(3), region_types=["room", "corridor_segment"]
        )
        self.assertTrue(any((p["type"] == "open_passage" for p in proposals)))

    def test_closed_wall_cannot_pass_even_with_high_model_responses(self):
        gray, prob, segments = self.scene(closed=True)
        proposals, _ = opening_candidates(
            segments,
            gray,
            prob,
            np.eye(3),
            region_types=["room", "corridor_segment"],
            align_doors=True,
        )
        self.assertEqual(proposals, [])

    def test_one_sided_jambs_do_not_create_a_door(self):
        gray, prob, segments = self.scene()
        gray[115:126, 97:124] = 255
        proposals, _ = opening_candidates(
            segments,
            gray,
            prob,
            np.eye(3),
            region_types=["room", "corridor_segment"],
            align_doors=True,
        )
        self.assertFalse(any((p["type"] == "door" for p in proposals)))

    def test_one_owner_cannot_receive_an_aligned_door(self):
        gray, prob, segments = self.scene()
        segments = {s: [0] for s in segments}
        proposals, _ = opening_candidates(
            segments, gray, prob, np.eye(3), region_types=["room"], align_doors=True
        )
        self.assertEqual(proposals, [])

    def test_tolerance_is_in_evidence_pixels_after_scaling_and_translation(self):
        segment = ((10.0, 20.0), (30.0, 20.0))
        matrix = np.array([[2.0, 0, 13.0], [0, 2.0, 7.0], [0, 0, 1.0]])
        result, detail = align_interval(segment, [0, 1], [9.25, 30.5], matrix, {segment: [0, 1]})
        self.assertEqual(result, [10.0, 30.0])
        self.assertAlmostEqual(detail["endpoint_overshoot_evidence_px"], 1.5)
        self.assertIsNone(
            align_interval(segment, [0, 1], [8.9, 30.5], matrix, {segment: [0, 1]})[0]
        )

    def test_clipping_cannot_discard_a_large_fraction_of_narrow_door(self):
        s = ((10.0, 20.0), (15.0, 20.0))
        result, detail = align_interval(s, [0, 1], [9.0, 16.0], np.eye(3), {s: [0, 1]})
        self.assertIsNone(result)
        self.assertEqual(detail["reason"], "insufficient_retained_width")

    def test_competing_shared_wall_owner_blocks_alignment(self):
        s = ((10.0, 20.0), (30.0, 20.0))
        other = ((30.0, 20.0), (50.0, 20.0))
        result, detail = align_interval(
            s, [0, 1], [15.0, 31.0], np.eye(3), {s: [0, 1], other: [0, 2]}
        )
        self.assertIsNone(result)
        self.assertEqual(detail["reason"], "competing_shared_boundary_owners")

    def test_unresolved_evidence_blocks_only_its_own_wall(self):
        s = ((10.0, 20.0), (30.0, 20.0))
        other = ((10.0, 40.0), (30.0, 40.0))
        evidence = {
            "baseline": {
                "candidates": [
                    {
                        "segment": s,
                        "paired_door_evidence": True,
                        "ticks": [{"position_px": 12}, {"position_px": 25}],
                        "status": "needs_attention",
                    }
                ]
            }
        }
        self.assertTrue(door_conflicts(s, [10, 20], [30, 20], evidence, np.eye(3)))
        self.assertFalse(door_conflicts(other, [10, 40], [30, 40], evidence, np.eye(3)))

    def test_unmarked_open_passage_remains_possible(self):
        gray = np.full((256, 256), 255, np.uint8)
        prob = np.zeros((6, 256, 256), np.float32)
        prob[5] = 0.9
        s = {((40.0, 128.0), (80.0, 128.0)): [0, 1]}
        proposals, _ = opening_candidates(
            s, gray, prob, np.eye(3), region_types=["room", "corridor_segment"], align_doors=True
        )
        self.assertEqual([p["type"] for p in proposals], ["open_passage"])


if __name__ == "__main__":
    unittest.main()
