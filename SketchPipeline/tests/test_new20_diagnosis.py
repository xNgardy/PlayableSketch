import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.diagnose_new20 import (
    oracle_door_stage,
    reference_segments,
    evaluate,
    reference,
    ROOT,
)
from SketchPipeline.shape_authoring import door_geometry


class New20DiagnosisTests(unittest.TestCase):

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
        return (
            gray,
            {((20.0, 128.0), (236.0, 128.0)): [0, 1]},
            np.array([[100.0, 128.0], [120.0, 128.0]]),
        )

    def test_oracle_locations_pass_existing_verifier_on_real_jamb_gap(self):
        gray, segments, points = self.scene()
        result, _ = oracle_door_stage([], segments, gray, np.eye(3), points)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_indices"], [0, 1])

    def test_known_physical_verifier_offset_loophole_is_visible(self):
        gray, segments, points = self.scene(True)
        ordinary, _ = door_geometry.opening_candidates([], segments, gray, np.eye(3))
        oracle, _ = oracle_door_stage([], segments, gray, np.eye(3), points)
        self.assertEqual(ordinary, [])
        self.assertEqual(len(oracle), 1)

    def test_physical_verifier_rejects_solid_thick_barrier(self):
        gray, segments, points = self.scene(True)
        cv2.rectangle(gray, (20, 114), (236, 142), 0, -1)
        self.assertEqual(oracle_door_stage([], segments, gray, np.eye(3), points)[0], [])

    def test_locations_do_not_manufacture_jambs(self):
        gray, segments, points = self.scene()
        gray[:] = 255
        self.assertEqual(oracle_door_stage([], segments, gray, np.eye(3), points)[0], [])

    def test_missing_shared_owner_is_not_supplied_by_oracle(self):
        gray, segments, points = self.scene()
        segments = {key: [0] for key in segments}
        self.assertEqual(oracle_door_stage([], segments, gray, np.eye(3), points)[0], [])

    def test_no_global_production_monkeypatch(self):
        gray, segments, points = self.scene()
        detector = door_geometry.detect_pairs
        ticks = door_geometry.ticks
        before = door_geometry.opening_candidates([], segments, gray, np.eye(3))
        oracle_door_stage([], segments, gray, np.eye(3), points)
        self.assertIs(detector, door_geometry.detect_pairs)
        self.assertIs(ticks, door_geometry.ticks)
        self.assertEqual(before, door_geometry.opening_candidates([], segments, gray, np.eye(3)))

    def test_reference_geometry_derives_owners_without_opening_labels(self):
        regions = [
            {"id": "a", "polygon": [[0, 0], [40, 0], [40, 20], [0, 20]]},
            {"id": "b", "polygon": [[0, 20], [40, 20], [40, 40], [0, 40]]},
        ]
        segments, records = reference_segments(regions)
        self.assertEqual(segments, {((0.0, 20.0), (40.0, 20.0)): [0, 1]})
        self.assertEqual(records[0]["maximum_normal_projection_px"], 0)

    def test_photographed_boundary_projection_is_recorded(self):
        regions = [
            {"id": "a", "polygon": [[0, 0], [40, 0], [40, 22], [0, 18]]},
            {"id": "b", "polygon": [[0, 18], [40, 22], [40, 40], [0, 40]]},
        ]
        segments, records = reference_segments(regions)
        self.assertEqual(segments, {((0.0, 20.0), (40.0, 20.0)): [0, 1]})
        self.assertEqual(records[0]["maximum_normal_projection_px"], 2)

    def test_correct_position_with_wrong_owner_is_reference_unmatched(self):
        region = lambda identifier, pts: {
            "id": identifier,
            "type": "room",
            "geometry": {"points_px": pts},
        }
        polygons = [[[0, 0], [40, 0], [40, 20], [0, 20]], [[0, 20], [40, 20], [40, 40], [0, 40]]]
        doc = {
            "topology": {
                "regions": [region("a", polygons[0]), region("b", polygons[1])],
                "openings": [
                    {
                        "type": "door",
                        "entity_ids": ["a", "missing"],
                        "geometry": {"points_px": [[10, 20], [20, 20]]},
                    }
                ],
            }
        }
        ref = {
            "regions": [
                {"id": "r1", "type": "room", "bounds_px": [0, 0, 40, 20]},
                {"id": "r2", "type": "room", "bounds_px": [0, 20, 40, 40]},
            ],
            "openings": [
                {"type": "door", "entity_ids": ["r1", "r2"], "points_px": [[10, 20], [20, 20]]}
            ],
        }
        m = evaluate(doc, ref, [256, 256])
        self.assertEqual(m["doors"]["true_positive"], 1)
        self.assertEqual(m["connections"]["true_positive"], 0)
        self.assertEqual(m["unmatched_produced_connections"], 1)
        self.assertTrue(m["unmatched_is_not_proven_false"])

    def test_audited_endpoint_override_preserves_source_labels_and_owners(self):
        import json
        from SketchPipeline.shape_authoring.dino_model import sha

        path = ROOT / "Data/ground_truth/structural_v1/Data_63.structural.json"
        before = sha(path)
        metadata = {"original_to_working": np.eye(3).tolist()}
        plain, _ = reference(63, metadata)
        original = next((g for g in plain["openings"] if g["id"] == "g003"))
        overrides = {
            "changes": [
                {
                    "sample_id": "Data_63",
                    "opening_id": "g003",
                    "source_sha256": sha(ROOT / "Data/Data_63.png"),
                    "old": {"end_px": original["end_px"]},
                    "new": {"end_px": [1127.0, 644.0]},
                }
            ]
        }
        corrected, _ = reference(63, metadata, overrides)
        a = next((g for g in plain["openings"] if g["id"] == "g003"))
        b = next((g for g in corrected["openings"] if g["id"] == "g003"))
        self.assertEqual(b["points_px"][1], [1127.0, 644.0])
        self.assertEqual(a["entity_ids"], b["entity_ids"])
        self.assertEqual(a["type"], b["type"])
        self.assertEqual(sha(path), before)


if __name__ == "__main__":
    unittest.main()
