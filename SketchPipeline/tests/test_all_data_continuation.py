import unittest
import numpy as np
from Scripts.train_all_shape_data import records, human_labels, replay_reference, ROOT, sha
from Scripts.evaluate_augmented_shape import transform_reference


class AllDataContinuationTests(unittest.TestCase):

    def test_every_source_and_former_holdout_view_is_included(self):
        inventory = records()
        ids = {r["id"] for r in inventory}
        self.assertEqual(len(ids), len(inventory))
        for n in range(1, 71):
            self.assertIn(f"Data_{n}", ids)
            for profile in ["rotate", "perspective", "lighting", "capture", "combined"]:
                self.assertIn(f"AUG_Data_{n}_{profile}", ids)
        self.assertIn("Data_66", ids)
        self.assertIn("CX001", ids)
        self.assertIn("control_2000_wavy", ids)

    def test_audited_endpoint_and_stroke_are_corrected_without_editing_source(self):
        paths = [
            ROOT / "Data/ground_truth/structural_v1/Data_63.structural.json",
            ROOT / "Data/annotations/v1/Data_63.observations.json",
        ]
        before = [sha(p) for p in paths]
        labels = human_labels(63)
        self.assertEqual(
            next((g for g in labels["gaps"] if g["id"] == "g003"))["end_px"], [1127.0, 644.0]
        )
        self.assertEqual(labels["lines"]["l0038"]["end_px"], [1174.0, 642.0])
        self.assertEqual(before, [sha(p) for p in paths])

    def test_replay_reference_transfers_all_owners_and_both_axes(self):
        spec = {
            "regions": [{"id": "a", "type": "room", "bounds_px": [0, 0, 50, 50]}],
            "openings": [
                {
                    "id": "d",
                    "type": "door",
                    "axis": 1,
                    "fixed": 50,
                    "interval": [10, 20],
                    "entity_ids": ["a", "b"],
                }
            ],
        }
        reference = replay_reference(spec)
        self.assertEqual(reference["openings"][0]["points_px"], [[50, 10], [50, 20]])
        result = transform_reference(reference, np.array([[2, 0, 3], [0, 2, 7], [0, 0, 1]]))
        self.assertEqual(result["openings"][0]["entity_ids"], ["a", "b"])
        self.assertEqual(result["openings"][0]["points_px"], [[103.0, 27.0], [103.0, 47.0]])


if __name__ == "__main__":
    unittest.main()
