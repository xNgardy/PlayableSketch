import copy
from collections import Counter
import unittest
import numpy as np
from SketchPipeline.shape_authoring.train_corridor_addon import grouped_sample, eligible, objective


class CorridorAddonTrainingTests(unittest.TestCase):

    def records(self):
        return [
            {"pool": pool, "group": str(g), "split": "train"}
            for pool in ["historical", "new_human", "complex"]
            for g in range(3)
            for _ in range(g + 1)
        ]

    def test_sampling_has_fixed_mix_and_rejects_holdout(self):
        rows = self.records()
        selected = grouped_sample(rows, np.random.default_rng(10))
        self.assertEqual(
            Counter((rows[i]["pool"] for i in selected)),
            {"historical": 120, "new_human": 32, "complex": 8},
        )
        rows[0]["split"] = "test"
        with self.assertRaises(ValueError):
            grouped_sample(rows, np.random.default_rng(10))

    def test_more_views_do_not_increase_parent_sampling_weight(self):
        rows = self.records()
        counts = Counter()
        rng = np.random.default_rng(1)
        for _ in range(100):
            for i in grouped_sample(rows, rng):
                if rows[i]["pool"] == "new_human":
                    counts[rows[i]["group"]] += 1
        self.assertLess(max(counts.values()) / min(counts.values()), 1.2)

    def test_guard_rejects_old_regression_despite_new_improvement(self):
        base = {
            g: {k: {"f1": 0.8, "precision": 0.9} for k in ["regions", "attached_openings", "doors"]}
            for g in ["old", "new", "synthetic"]
        }
        improved = copy.deepcopy(base)
        improved["new"]["regions"]["f1"] = 1.0
        self.assertTrue(eligible(improved, base)[0])
        self.assertGreater(objective(improved), objective(base))
        improved["old"]["attached_openings"]["f1"] = 0.7
        self.assertFalse(eligible(improved, base)[0])


class MarkerFreezeTests(unittest.TestCase):

    def test_optimizer_cannot_change_geometry_weights(self):
        import torch
        from SketchPipeline.shape_authoring.dino_model import DinoDecoder
        from SketchPipeline.shape_authoring.train_corridor_markers import configure, ACTIVE, FIXED

        torch.set_num_threads(4)
        torch.manual_seed(4)
        model = DinoDecoder(8)
        before = {k: v.clone() for k, v in model.state_dict().items()}
        configure(model)
        optimizer = torch.optim.AdamW(
            [model.head.weight, model.head.bias], lr=0.001, weight_decay=0.0
        )
        model(torch.randn(1, 4, 384, 4, 4), torch.randn(1, 2, 32, 32))[:, ACTIVE].mean().backward()
        optimizer.step()
        for key, value in model.state_dict().items():
            if key.startswith("head."):
                self.assertTrue(torch.equal(value[FIXED], before[key][FIXED]))
            else:
                self.assertTrue(torch.equal(value, before[key]))
        self.assertFalse(torch.equal(model.head.weight[ACTIVE], before["head.weight"][ACTIVE]))


if __name__ == "__main__":
    unittest.main()


class DeskewMetadataTests(unittest.TestCase):

    def test_real_rotated_photo_metadata_is_json_serializable(self):
        import json
        from SketchPipeline.shape_authoring.propose import prepare_image
        from SketchPipeline.shape_authoring.dino_model import ROOT

        _, metadata = prepare_image(ROOT / "Data/Data_66.png")
        encoded = json.dumps(metadata)
        self.assertTrue(encoded)
        for step in metadata["transform_chain"]:
            for size in step.get("size_px", []):
                self.assertIs(type(size), int)
