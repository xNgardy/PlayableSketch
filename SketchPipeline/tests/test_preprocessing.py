import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from SketchPipeline.preprocessing.prepare import InputError, decode, exif_matrix, prepare, project
from SketchPipeline.preprocessing.dataset import DEFAULT_MANIFEST, audit, run
from SketchPipeline.validation.validate import load_json


class PreprocessingTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rng = np.random.default_rng(12)
        self.array = rng.integers(0, 255, (80, 120, 3), dtype=np.uint8)
        self.path = self.root / "source.png"
        Image.fromarray(self.array).save(self.path)

    def test_all_exif_orientations_map_actual_pixels(self):
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                exif = Image.Exif()
                exif[274] = orientation
                path = self.root / f"{orientation}.png"
                Image.fromarray(self.array).save(path, exif=exif)
                original, upright, matrix, actual = decode(path)
                self.assertEqual(actual, orientation)
                for x, y in [(0, 0), (119, 0), (119, 79), (0, 79), (41, 31)]:
                    u, v = project([[x, y]], matrix)[0].astype(int)
                    np.testing.assert_array_equal(upright[v, u], original[y, x])
                images, metadata = prepare(path, max_side=64)
                points = [[0, 0], [119, 79], [41, 31]]
                np.testing.assert_allclose(
                    project(
                        project(points, metadata["original_to_working"]),
                        metadata["working_to_original"],
                    ),
                    points,
                    atol=1e-09,
                )

    def test_resize_half_pixel_convention(self):
        _, m = prepare(self.path, max_side=64)
        w, h = m["working_size_px"]
        sx, sy = (w / 120, h / 80)
        np.testing.assert_allclose(
            project([[0, 0], [119, 79]], m["original_to_working"]),
            [[(sx - 1) / 2, (sy - 1) / 2], [119.5 * sx - 0.5, 79.5 * sy - 0.5]],
        )

    def test_crop_after_exif_has_independent_expected_mapping(self):
        exif = Image.Exif()
        exif[274] = 6
        Image.fromarray(self.array).save(self.path, exif=exif)
        images, m = prepare(self.path, crop=[10, 20, 70, 100])
        np.testing.assert_allclose(project([[30, 40]], m["original_to_working"]), [[29, 10]])
        np.testing.assert_array_equal(images["color"][10, 29], self.array[40, 30])

    def test_manual_deskew_preserves_canvas_and_composition(self):
        _, m = prepare(self.path, crop=[10, 5, 110, 75], deskew_degrees=12, max_side=64)
        operations = [s["operation"] for s in m["transform_chain"]]
        self.assertEqual(operations, ["exif", "manual_crop", "manual_deskew", "resize"])
        chain = np.eye(3)
        for s in m["transform_chain"]:
            chain = np.asarray(s["matrix"]) @ chain
        np.testing.assert_allclose(chain, m["original_to_working"])
        self.assertLess(m["round_trip_max_error_px"], 1e-06)

    def test_known_page_corners_land_on_rectangle(self):
        corners = [[10, 5], [110, 9], [103, 73], [15, 70]]
        images, m = prepare(self.path, page_corners=corners, page_aspect_ratio=2, max_side=200)
        w, h = m["working_size_px"]
        np.testing.assert_allclose(
            project(corners, m["original_to_working"]),
            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]],
            atol=1e-05,
        )
        self.assertAlmostEqual((w - 1) / (h - 1), 2, delta=0.02)
        self.assertIsNone(m["metric_scale"])

    def test_no_page_corners_means_no_homography(self):
        _, m = prepare(self.path)
        self.assertEqual([s["operation"] for s in m["transform_chain"]], ["exif"])
        self.assertIn("PAGE_RECTIFICATION_NOT_REQUESTED", m["quality"]["issues"])

    def test_invalid_geometry_options_are_rejected(self):
        cases = [
            {"page_aspect_ratio": 1.4},
            {"page_corners": [[0, 0]] * 4},
            {"page_corners": [[0, 0]] * 4, "page_aspect_ratio": 1.4},
            {"page_corners": [[0, 0], [20, 20], [0, 20], [20, 0]], "page_aspect_ratio": 1},
            {
                "page_corners": [[0, 0], [119, 0], [119, 79], [0, 79]],
                "page_aspect_ratio": 1,
                "crop": [0, 0, 50, 50],
            },
            {"crop": [-1, 0, 50, 50]},
            {"crop": [0, 0, 5, 5]},
            {"max_side": 0},
            {"deskew_degrees": float("nan")},
            {"deskew_degrees": 90},
        ]
        for config in cases:
            with self.subTest(config=config), self.assertRaises(InputError):
                prepare(self.path, **config)

    def test_project_rejects_infinity_and_nonfinite(self):
        for points, matrix in [
            ([[1, 2]], [[1, 0, 0], [0, 1, 0], [0, 0, 0]]),
            ([[float("nan"), 2]], np.eye(3)),
        ]:
            with self.assertRaises(InputError):
                project(points, matrix)

    def test_blank_corrupt_missing_wrong_format_are_errors(self):
        blank = self.root / "blank.png"
        Image.new("RGB", (100, 100), "white").save(blank)
        corrupt = self.root / "corrupt.jpg"
        corrupt.write_bytes(b"not jpeg")
        gif = self.root / "fake.png"
        Image.new("RGB", (100, 100), "white").save(gif, format="GIF")
        for path in [blank, corrupt, gif, self.root / "missing.jpg"]:
            with self.subTest(path=path), self.assertRaises(InputError):
                prepare(path)

    def test_transparent_rgb_does_not_become_ink(self):
        path = self.root / "alpha.png"
        rgba = np.zeros((80, 120, 4), dtype=np.uint8)
        rgba[10:60, 20:90, 3] = 255
        Image.fromarray(rgba).save(path)
        original, upright, _, _ = decode(path)
        np.testing.assert_array_equal(original[0, 0], [255, 255, 255])
        np.testing.assert_array_equal(upright[20, 30], [0, 0, 0])

    def test_soft_warning_keeps_variants(self):
        ramp = np.tile(np.linspace(120, 220, 120, dtype=np.uint8), (80, 1))
        Image.fromarray(ramp).save(self.path)
        images, m = prepare(self.path)
        self.assertIn("IMAGE_SOFT_OR_FAINT", m["quality"]["issues"])
        self.assertEqual(set(images), {"original", "color", "gray", "denoised", "adaptive"})
        self.assertEqual(set(np.unique(images["adaptive"])), {255})

    def test_input_limits_and_invalid_exif(self):
        with (
            patch("SketchPipeline.preprocessing.prepare.MAX_BYTES", 1),
            self.assertRaises(InputError),
        ):
            decode(self.path)
        with (
            patch("SketchPipeline.preprocessing.prepare.MAX_PIXELS", 1),
            self.assertRaises(InputError),
        ):
            decode(self.path)
        with self.assertRaises(InputError):
            exif_matrix(0, 100, 100)


class AnnotationDatasetTests(unittest.TestCase):

    def test_all_ten_sources_annotations_and_metric_statuses(self):
        manifest, samples = audit(DEFAULT_MANIFEST)
        self.assertEqual(len(samples), 10)
        self.assertEqual(sum((s["counts"]["texts"] for s in manifest["samples"])), 56)
        self.assertEqual(
            [s["metric_status"] for s in manifest["samples"]][-2:], ["conflicting", "incomplete"]
        )
        self.assertTrue(
            all(
                (
                    s["writer_id"] is None and s["split"] == "development"
                    for s in manifest["samples"]
                )
            )
        )
        self.assertIn("BLUR_OR_FAINT_STROKES_VISUAL_REVIEW", samples[6][3]["issues"])
        self.assertTrue(all((s[2]["region_annotation_status"] == "complete" for s in samples)))

    def test_sidecar_typo_missing_coverage_and_bad_points_rejected(self):
        side_path = DEFAULT_MANIFEST.parent / "Data_1.annotations.json"
        original = load_json(side_path)
        mutations = []
        x = copy.deepcopy(original)
        x["associations"] = []
        mutations.append(x)
        x = copy.deepcopy(original)
        x["junctions"][0]["point_px"] = [99999, 1]
        mutations.append(x)
        x = copy.deepcopy(original)
        x["strokes"][0]["line_ids"] = []
        mutations.append(x)
        from jsonschema import ValidationError

        for changed in mutations:

            def reader(path):
                return changed if Path(path) == side_path else load_json(path)

            with patch("SketchPipeline.preprocessing.dataset.load_json", side_effect=reader):
                with self.assertRaises((InputError, ValidationError)):
                    audit(DEFAULT_MANIFEST)

    def test_failed_run_never_publishes_partial_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "failed"
            from SketchPipeline.preprocessing import dataset

            real = dataset.prepare
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise InputError("injected decode failure")
                return real(*args, **kwargs)

            with patch.object(dataset, "prepare", side_effect=fail_second):
                with self.assertRaises(InputError):
                    run(DEFAULT_MANIFEST, out, max_side=64)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker"
            marker.write_text("keep")
            with self.assertRaises(InputError):
                run(DEFAULT_MANIFEST, Path(tmp))
            self.assertEqual(marker.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
