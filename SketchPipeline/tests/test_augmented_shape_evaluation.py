import copy
import unittest
from unittest.mock import patch
import numpy as np
from Scripts.evaluate_augmented_shape import transform_reference, scored, source_reference
from SketchPipeline.preprocessing.prepare import project


class AugmentedShapeEvaluationTests(unittest.TestCase):

    def test_new20_structural_transfer_keeps_source_and_owner_semantics(self):
        from Scripts.extend_augmented_shape import transfer_structural

        raw = {
            "regions": [{"region_id": "room", "polygon_px": [[0, 0], [20, 0], [20, 30], [0, 30]]}],
            "openings": [
                {
                    "id": "g",
                    "kind": "door",
                    "start_px": [20, 10],
                    "end_px": [20, 15],
                    "entity_ids": ["room", "corridor"],
                }
            ],
            "image_sha256": "old",
            "notes": [],
            "metric_validated": False,
        }
        original = copy.deepcopy(raw)
        matrix = np.array([[0.9, 0.03, 25], [-0.02, 0.85, 19], [0.0001, -0.0002, 1.0]])
        result = transfer_structural(raw, matrix, "new")
        self.assertEqual(raw, original)
        self.assertEqual(result["openings"][0]["entity_ids"], ["room", "corridor"])
        self.assertEqual(result["openings"][0]["kind"], "door")
        self.assertFalse(result["metric_validated"])
        restored = transfer_structural(result, np.linalg.inv(matrix), "old")
        np.testing.assert_allclose(
            restored["regions"][0]["polygon_px"], raw["regions"][0]["polygon_px"], atol=1e-08
        )
        np.testing.assert_allclose(
            restored["openings"][0]["end_px"], raw["openings"][0]["end_px"], atol=1e-08
        )

    def reference(self):
        return {
            "regions": [
                {
                    "id": "a",
                    "type": "room",
                    "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
                    "bounds_px": [0, 0, 100, 100],
                },
                {
                    "id": "b",
                    "type": "room",
                    "polygon": [[100, 0], [200, 0], [200, 100], [100, 100]],
                    "bounds_px": [100, 0, 200, 100],
                },
            ],
            "openings": [
                {
                    "id": "g",
                    "type": "door",
                    "points_px": [[100, 30], [100, 50]],
                    "entity_ids": ["a", "b"],
                }
            ],
            "approximate_human_labels": False,
        }

    def test_projective_transfer_preserves_owners_and_round_trips(self):
        original = self.reference()
        before = copy.deepcopy(original)
        matrix = np.array([[0.9, 0.03, 25], [-0.02, 0.85, 19], [0.0001, -0.0002, 1.0]])
        transferred = transform_reference(original, matrix)
        self.assertEqual(original, before)
        self.assertEqual(transferred["openings"][0]["entity_ids"], ["a", "b"])
        restored = transform_reference(transferred, np.linalg.inv(matrix))
        np.testing.assert_allclose(
            restored["regions"][0]["polygon"], original["regions"][0]["polygon"], atol=1e-08
        )
        np.testing.assert_allclose(
            restored["openings"][0]["points_px"], original["openings"][0]["points_px"], atol=1e-08
        )

    def test_door_location_does_not_imply_correct_owners(self):
        reference = self.reference()
        document = {
            "topology": {
                "regions": [
                    {"id": r["id"], "type": r["type"], "geometry": {"points_px": r["polygon"]}}
                    for r in reference["regions"]
                ],
                "openings": [
                    {
                        "id": "p",
                        "type": "door",
                        "geometry": {"points_px": [[100, 30], [100, 50]]},
                        "entity_ids": ["a", "missing"],
                    }
                ],
            }
        }
        metric = scored(document, reference, [200, 100])
        self.assertEqual(metric["doors"]["true_positive"], 1)
        self.assertEqual(metric["connections"]["true_positive"], 0)
        self.assertEqual(metric["attached_doors"]["true_positive"], 0)
        self.assertFalse(metric["exact_topology"])

    def test_synthetic_source_uses_explicit_owners_without_cm_geometry(self):
        parent = {
            "source_origin": "synthetic",
            "source_files": {
                "side_path": {"path": "side.json"},
                "metric_path": {"path": "metric.json"},
            },
        }
        annotation = {
            "regions": [
                {
                    "region_id": "a",
                    "kind": "room",
                    "polygon_px": [[0, 0], [10, 0], [10, 10], [0, 10]],
                }
            ],
            "gaps": [
                {
                    "id": "g",
                    "kind": "door",
                    "start_px": [10, 3],
                    "end_px": [10, 5],
                    "opening_candidate_id": "o",
                }
            ],
        }
        metric = {
            "layout": {
                "openings": [
                    {
                        "id": "o",
                        "connected_entities": [{"id": "a"}, {"id": "far_owner"}],
                        "clear_width_cm": 999999,
                    }
                ]
            }
        }
        with patch(
            "Scripts.evaluate_augmented_shape.read",
            side_effect=lambda p: annotation if p.name == "side.json" else metric,
        ):
            result = source_reference(parent)
        self.assertEqual(result["openings"][0]["entity_ids"], ["a", "far_owner"])
        self.assertEqual(result["openings"][0]["points_px"], [[10, 3], [10, 5]])
        self.assertNotIn("clear_width_cm", result["openings"][0])


if __name__ == "__main__":
    unittest.main()
