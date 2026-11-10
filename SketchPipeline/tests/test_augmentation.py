from collections import Counter
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.synthetic.augment import (
    DEFAULT_OUTPUT,
    PROFILES,
    augment_pixels,
    audit,
    parameters,
    project,
    read,
    render,
    sha,
    sources,
    transfer,
)


class AugmentationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.bundles = sources()
        cls.by_id = {b["sample"]["id"]: b for b in cls.bundles}

    def test_full_batch_preserves_every_source_and_metric_condition(self):
        report = audit(DEFAULT_OUTPUT, self.bundles)
        self.assertEqual(
            (report["source_images"], report["new_images"], report["combined_images"]),
            (120, 600, 720),
        )
        self.assertEqual(report["augmented_text_regions"], 9680)
        self.assertEqual(
            report["metric_status_counts"], dict(valid=540, conflicting=25, incomplete=35)
        )
        self.assertEqual(report["base_plan_groups"], 80)

    def test_pixel_and_annotation_homography_agree_at_a_known_landmark(self):
        pixels = np.full((80, 100, 3), 255, np.uint8)
        pixels[28:33, 18:23] = 0
        matrix = np.array([[1.0, 0, 11], [0, 1.0, 7], [0, 0, 1.0]])
        _, settings = parameters("landmark", "rotate", 100, 80)
        warped = augment_pixels(pixels, matrix, settings)
        doc = {
            "lines": [{"start_px": [20, 30], "end_px": [20, 31]}],
            "texts": [
                {"polygon_px": [[18, 28], [22, 28], [22, 32], [18, 32]], "parsed_value_cm": 120}
            ],
        }
        moved = transfer(doc, matrix)
        self.assertEqual(moved["lines"][0]["start_px"], [31, 37])
        self.assertEqual(moved["texts"][0]["parsed_value_cm"], 120)
        self.assertTrue(np.all(warped[37, 31] == 0))
        self.assertEqual(doc["lines"][0]["start_px"], [20, 30])

    def test_unknown_pixel_primitive_fails_instead_of_silently_staying_untransformed(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized pixel field"):
            transfer({"unexpected_center_px": [100, 200]}, np.eye(3))

    def test_full_source_canvas_is_retained_and_mapping_is_invertible(self):
        for bundle in self.bundles:
            w, h = (bundle["obs"]["frame"]["width_px"], bundle["obs"]["frame"]["height_px"])
            corners = [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
            for profile in PROFILES:
                H, settings = parameters(bundle["sample"]["id"], profile, w, h)
                points = project(corners, H)
                self.assertTrue(all((0 <= x <= w - 1 and 0 <= y <= h - 1 for x, y in points)))
                self.assertTrue(
                    np.allclose(project(points, np.linalg.inv(H)), corners, atol=0.0001)
                )
                self.assertGreater(np.linalg.det(H), 0)
                if profile in ["lighting", "capture"]:
                    self.assertTrue(np.array_equal(H, np.eye(3)))

    def test_deterministic_reproduction_for_human_and_synthetic_pixels(self):
        for source_id in ["Data_41", "SX003_ink"]:
            with tempfile.TemporaryDirectory() as temp:
                generated = render(self.by_id[source_id], "combined", Path(temp))
                saved = next(
                    (
                        s
                        for s in read(DEFAULT_OUTPUT / "manifest.json")["samples"]
                        if s["id"] == generated["id"]
                    )
                )
                self.assertEqual(generated["image_sha256"], saved["image_sha256"])
                for key in ["observations_path", "annotations_path", "metric_path"]:
                    self.assertEqual(
                        read(Path(temp) / generated[key]), read(DEFAULT_OUTPUT / saved[key])
                    )

    def test_synthetic_masks_follow_the_image_geometry_without_noise(self):
        source = self.by_id["SX003_ink"]
        original_render = read(source["manifest_path"].parent / source["sample"]["rendering_path"])
        for profile in ["perspective", "lighting", "combined"]:
            meta = read(DEFAULT_OUTPUT / "transforms" / f"AUG_SX003_ink_{profile}.json")
            H = np.array(meta["source_to_augmented"])
            w, h = meta["output_size_px"]
            for name, path in meta["masks"].items():
                with Image.open(
                    source["manifest_path"].parent / original_render["masks"][name]
                ) as im:
                    expected = cv2.warpPerspective(
                        np.asarray(im), H, (w, h), flags=cv2.INTER_LINEAR, borderValue=0
                    )
                with Image.open(DEFAULT_OUTPUT / path) as im:
                    self.assertTrue(np.array_equal(expected, np.asarray(im)))

    def test_conflicts_and_unresolved_values_are_never_repaired(self):
        for source_id, status in [
            ("Data_9", "conflicting"),
            ("Data_49", "conflicting"),
            ("Data_10", "incomplete"),
            ("Data_50", "incomplete"),
        ]:
            original = self.by_id[source_id]["draft"]
            for profile in PROFILES:
                sid = f"AUG_{source_id}_{profile}"
                copied = read(DEFAULT_OUTPUT / "metric" / f"{sid}.draft.json")
                self.assertEqual(copied["layout"], original["layout"])
                self.assertEqual(copied["review"]["status"], "pending")
                meta = read(DEFAULT_OUTPUT / "transforms" / f"{sid}.json")
                self.assertFalse(meta["validation"]["metric_valid"])
        for profile in PROFILES:
            copied = read(DEFAULT_OUTPUT / "metric" / f"AUG_Data_50_{profile}.draft.json")
            self.assertTrue(any((None in v["position_cm"] for v in copied["layout"]["vertices"])))

    def test_original_and_all_styles_share_a_development_group(self):
        samples = read(DEFAULT_OUTPUT / "manifest_with_originals.json")["samples"]
        group = {s["id"]: s["base_plan_id"] for s in samples}
        self.assertEqual(
            {
                group[f"AUG_SP002_{style}_{profile}"]
                for style in ["ink", "pencil", "photo"]
                for profile in PROFILES
            },
            {"SP002"},
        )
        self.assertEqual({s["split"] for s in samples}, {"development"})
        self.assertEqual(
            Counter((s["source_origin"] for s in samples if s["origin"] == "augmented")),
            dict(human=250, synthetic=350),
        )


if __name__ == "__main__":
    unittest.main()
