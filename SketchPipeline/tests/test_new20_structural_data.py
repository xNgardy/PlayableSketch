import copy
import json
from pathlib import Path
import unittest
import cv2
import numpy as np
from SketchPipeline.fixtures.new20.build_dataset import OUT, REVIEW, ROOT, audit, complex_specs
from SketchPipeline.shape_authoring.synthetic import render


class New20StructuralDataTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((OUT / "manifest.json").read_text())
        cls.entries = {s["id"]: s for s in cls.manifest["samples"]}

    def labels(self, n):
        e = self.entries[f"Data_{n}"]
        return (
            json.loads((OUT / e["annotations_path"]).read_text()),
            json.loads((OUT / e["structural_reference_path"]).read_text()),
        )

    def test_all_files_schema_targets_lineage_and_protected_sources(self):
        protected = json.loads((REVIEW / "source_freeze.json").read_text())["protected_files"]
        report = audit(list(self.entries.values()), protected)
        self.assertEqual(report["schema_valid_samples"], 112)
        self.assertFalse(report["cross_split_parent_or_hash_leakage"])
        self.assertFalse(report["training_run"])

    def test_closed_ends_and_disconnected_rooms_remain_disconnected(self):
        for n, isolated in [(67, "r02"), (70, "r03")]:
            _, ref = self.labels(n)
            self.assertFalse(any((isolated in o["entity_ids"] for o in ref["openings"])))
        ann, ref = self.labels(68)
        self.assertEqual(len(ann["regions"]), 2)
        self.assertEqual(ref["openings"], [])
        _, ref = self.labels(69)
        self.assertFalse(any((set(o["entity_ids"]) == {"r03", "r04"} for o in ref["openings"])))

    def test_actual_four_door_photo_overrides_two_door_guide(self):
        ann, _ = self.labels(64)
        self.assertEqual(sum((g["kind"] == "door" for g in ann["gaps"])), 4)

    def test_holdout_photos_have_no_training_derivatives_or_guide_renders(self):
        for e in self.entries.values():
            if e["origin"] not in ("human_derivative", "guide_render"):
                continue
            self.assertEqual(e["split"], "train")
            parent = next(
                (
                    p
                    for p in self.entries.values()
                    if p["origin"] == "human" and p["base_plan_id"] == e["base_plan_id"]
                )
            )
            self.assertEqual(parent["split"], "train")

    def test_human_unknown_pixels_remain_zero_weight_and_no_sizes_invented(self):
        e = self.entries["Data_51"]
        with np.load(OUT / e["targets_path"]) as z:
            self.assertTrue((z["known"] == 0).any())
            self.assertTrue(((z["known"] > 0) & (z["known"] < 1)).any())
        _, ref = self.labels(51)
        self.assertFalse(ref["physical_dimensions_known"])
        self.assertFalse(ref["metric_validated"])

    def test_custom_renderer_is_deterministic_and_does_not_mutate_spec(self):
        spec, _ = next(complex_specs())
        snapshot = copy.deepcopy(spec)
        image, masks, result = render(spec["seed"], "wavy", 512, specification=spec)
        again, other, _ = render(spec["seed"], "wavy", 512, specification=spec)
        self.assertEqual(spec, snapshot)
        np.testing.assert_array_equal(image, again)
        np.testing.assert_array_equal(masks, other)
        ink = (image < 180).astype(np.uint8)
        nearby = cv2.dilate(ink, np.ones((7, 7), np.uint8))
        foreground = (masks[0] > 0) | (masks[3] > 0)
        self.assertGreater(float(nearby[foreground].mean()), 0.98)


if __name__ == "__main__":
    unittest.main()
