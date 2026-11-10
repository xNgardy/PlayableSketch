import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.perception.numeric import parse_numeric
from SketchPipeline.perception.ocr import (
    RapidOCRAdapter,
    choose_reading,
    group_units,
    rectify_crop,
    rotation_matrix,
)
from SketchPipeline.perception.geometry import (
    dominant_rotation,
    gap_evidence,
    line_evidence,
    merge_centerlines,
    text_mask,
)
from SketchPipeline.perception.evaluate import evaluate, polygon_iou, covered_length, greedy_pairs
from SketchPipeline.perception.run import predict, run_single, run_dataset, DEFAULT_MANIFEST
from SketchPipeline.preprocessing.prepare import InputError, project
from SketchPipeline.validation.validate import load_json, validate_document


def reading(raw, score=0.9):
    return {"raw_text": raw, "score": score, "parsed": parse_numeric(raw), "rotation_degrees": 0}


def line(id, start, end, role="wall_candidate", axis="vertical"):
    return {"id": id, "start": start, "end": end, "role": role, "axis": axis}


class NumericTests(unittest.TestCase):

    def test_explicit_cm_spacing_door_marker_and_decimal_policy(self):
        for raw, value in [
            ("700 cm", 700),
            ("700cm", 700),
            (" D120 CM ", 120),
            ("120.5 cm", 120.5),
            ("120,5 cm", 120.5),
            (".5 cm", 0.5),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_numeric(raw)["value_cm"], value)
        self.assertTrue(parse_numeric("D 120 cm")["door_marker"])

    def test_unitless_unsupported_and_invalid_are_not_converted(self):
        for raw, code in [
            ("700", "SKETCH_UNIT_MISSING"),
            ("2.5m", "SKETCH_UNIT_UNSUPPORTED"),
            ("10 ft", "SKETCH_UNIT_UNSUPPORTED"),
            ("10 inches", "SKETCH_UNIT_UNSUPPORTED"),
            ("h00cm", "SKETCH_NUMBER_UNREADABLE"),
            ("600cm garbage", "SKETCH_NUMBER_UNREADABLE"),
            ("0 cm", "SKETCH_NUMBER_OUT_OF_RANGE"),
            ("-2 cm", "SKETCH_NUMBER_UNREADABLE"),
        ]:
            with self.subTest(raw=raw):
                result = parse_numeric(raw)
                self.assertIsNone(result["value_cm"])
                self.assertEqual(result["issue"], code)

    def test_explicit_ambiguity_is_not_a_confirmed_number(self):
        result = parse_numeric("600/800 cm")
        self.assertIsNone(result["value_cm"])
        self.assertEqual(result["alternatives_cm"], [600, 800])
        selected = choose_reading([reading("600 cm", 0.91), reading("800 cm", 0.9)])
        self.assertIsNone(selected["parsed"]["value_cm"])
        self.assertEqual(selected["parsed"]["issue"], "SKETCH_NUMBER_AMBIGUOUS")

    def test_confidence_not_geometry_and_low_scores_remain_unknown(self):
        result = choose_reading([reading("700 cm", 0.2)])
        self.assertIsNone(result["parsed"]["value_cm"])
        self.assertEqual(result["parsed"]["issue"], "SKETCH_OCR_LOW_CONFIDENCE")
        self.assertEqual(choose_reading([reading("", 0.9)])["raw_text"], "[unreadable]")

    def test_join_multiline_number_and_unit_without_losing_parts(self):
        number = {
            "id": "f001",
            "polygon_working": [[0, 0], [80, 0], [80, 40], [0, 40]],
            "chosen": reading("400"),
        }
        unit = {
            "id": "f002",
            "polygon_working": [[20, 45], [70, 45], [70, 70], [20, 70]],
            "chosen": reading("cm"),
        }
        result = group_units([number, unit])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["chosen"]["parsed"]["value_cm"], 400)
        self.assertEqual(result[0]["fragment_ids"], ["f001", "f002"])
        far = copy.deepcopy(unit)
        far["polygon_working"] = [[400, 400], [450, 400], [450, 450], [400, 450]]
        self.assertEqual(len(group_units([number, far])), 2)


class CropFrameTests(unittest.TestCase):

    def test_vertical_detection_fallback_maps_and_deduplicates_proposals(self):
        adapter = RapidOCRAdapter.__new__(RapidOCRAdapter)
        fragment = np.array([[[40, 150], [90, 150], [90, 300], [40, 300]]], dtype=float)
        full_rotated = np.array([[[70, 89], [300, 89], [300, 139], [70, 139]]], dtype=float)
        outputs = iter([SimpleNamespace(boxes=fragment), SimpleNamespace(boxes=full_rotated)])
        adapter.detector = lambda image: next(outputs)
        boxes = adapter.detect(np.full((500, 180, 3), 255, np.uint8))
        self.assertEqual(len(boxes), 1)
        np.testing.assert_allclose(boxes[0], [[40, 70], [90, 70], [90, 300], [40, 300]])
        self.assertEqual(len(adapter.detection_debug["passes"]), 2)

    def test_all_rotated_raster_pixels_and_inverse_frames(self):
        rng = np.random.default_rng(22)
        image = rng.integers(0, 255, (40, 70, 3), dtype=np.uint8)
        crop, matrix = rectify_crop(image, [[10, 5], [59, 5], [59, 34], [10, 34]])
        for k in range(4):
            rotated = np.rot90(crop, k)
            local = rotation_matrix(k, crop.shape[1], crop.shape[0])
            for x, y in [(0, 0), (crop.shape[1] - 1, crop.shape[0] - 1), (17, 13)]:
                u, v = project([[x, y]], local)[0].astype(int)
                np.testing.assert_array_equal(rotated[v, u], crop[y, x])
            total = local @ matrix
            np.testing.assert_allclose(
                project(project([[10, 5], [59, 34]], total), np.linalg.inv(total)),
                [[10, 5], [59, 34]],
                atol=1e-08,
            )

    def test_perspective_crop_expected_corner_positions(self):
        image = np.full((150, 200, 3), 255, np.uint8)
        polygon = [[20, 10], [160, 20], [170, 100], [10, 110]]
        crop, matrix = rectify_crop(image, polygon)
        h, w = crop.shape[:2]
        np.testing.assert_allclose(
            project(polygon, matrix), [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], atol=1e-05
        )
        with self.assertRaises(InputError):
            rectify_crop(image, [[1, 1]] * 4)


class GeometryTests(unittest.TestCase):

    def test_double_edges_merge_but_real_gap_and_parallel_wall_survive(self):
        raw = [
            {"start": [20, 99], "end": [120, 99]},
            {"start": [20, 103], "end": [120, 103]},
            {"start": [160, 101], "end": [260, 101]},
            {"start": [20, 125], "end": [120, 125]},
        ]
        merged = merge_centerlines(raw, 0, 1000)
        self.assertEqual(len(merged), 3)
        self.assertTrue(
            any(
                (
                    abs(segment["start"][1] - 101) < 0.1 and abs(segment["end"][0] - 120) < 0.1
                    for segment in merged
                )
            )
        )
        self.assertFalse(
            any((segment["start"][0] < 120 and segment["end"][0] > 160 for segment in merged))
        )

    def test_rotation_estimate_uses_long_axis_lines(self):
        r = np.deg2rad(6)
        v = np.array([np.cos(r), np.sin(r)])
        raw = [
            {"start": [0, 0], "end": (500 * v).tolist()},
            {
                "start": [20, 20],
                "end": (np.array([20, 20]) + 400 * np.array([-v[1], v[0]])).tolist(),
            },
        ]
        self.assertAlmostEqual(dominant_rotation(raw, 1000), 6, places=6)

    def test_text_mask_retains_crossing_long_stroke(self):
        gray = np.full((200, 400), 255, np.uint8)
        gray[98:103, :] = 20
        gray[130:140, 150:160] = 20
        raw = [{"start": [0, 100], "end": [399, 100]}]
        masked, text, protected = text_mask(
            gray, [[[100, 80], [200, 80], [200, 150], [100, 150]]], raw, 400
        )
        self.assertEqual(masked[100, 150], 20)
        self.assertEqual(masked[135, 155], 255)
        self.assertEqual(gray[135, 155], 20)

    def test_gap_with_ticks_is_candidate_but_small_break_is_unresolved(self):
        lines = [
            line("a", [100, 10], [100, 100]),
            line("b", [100, 160], [100, 300]),
            line("t1", [80, 100], [120, 100], "unknown", "horizontal"),
            line("t2", [80, 160], [120, 160], "unknown", "horizontal"),
        ]
        text = [{"id": "t001", "polygon_working": [[120, 115], [160, 115], [160, 145], [120, 145]]}]
        gaps = gap_evidence(lines, text, (400, 400))
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["role"], "opening_candidate")
        self.assertIsNone(gaps[0]["width_cm"])
        small = [line("a", [100, 10], [100, 100]), line("b", [100, 103], [100, 300])]
        gaps = gap_evidence(small, [], (400, 400))
        self.assertTrue(all((g["role"] == "unresolved_gap" for g in gaps)))

    def test_text_mask_does_not_invent_white_rectangle_edges(self):
        gray = np.full((160, 240), 180, np.uint8)
        gray[70:80, 90:100] = 20
        masked, _, _ = text_mask(gray, [[[50, 40], [180, 40], [180, 120], [50, 120]]], [], 240)
        self.assertTrue(np.all(masked[40, 50:181] == 180))
        self.assertEqual(masked[75, 95], 180)

    def test_both_line_detectors_produce_evidence_on_synthetic_walls(self):
        gray = np.full((400, 500), 240, np.uint8)
        cv2.rectangle(gray, (40, 40), (460, 360), 20, 5)
        outputs, meta, masks = line_evidence(gray, [])
        for method in ("hough", "lsd"):
            self.assertGreaterEqual(
                sum((segment["role"] == "wall_candidate" for segment in outputs[method])), 4
            )
        self.assertEqual(gray.shape, masks["wall_input"].shape)


class MetricTests(unittest.TestCase):

    def test_one_to_one_text_matching_prevents_duplicate_credit(self):
        polygon = [[0, 0], [100, 0], [100, 30], [0, 30]]
        self.assertEqual(polygon_iou(polygon, polygon), 1)
        pairs = greedy_pairs([polygon, polygon], [polygon], polygon_iou, 0.3)
        self.assertEqual(len(pairs), 1)

    def test_wall_coverage_handles_manual_fragment_granularity(self):
        whole = [{"start": [0, 0], "end": [100, 0]}]
        split = [{"start": [0, 0], "end": [50, 0]}, {"start": [50, 0], "end": [100, 0]}]
        self.assertEqual(covered_length(whole, split, 1)["coverage"], 1)
        opposite = [{"start": [20, -50], "end": [20, 50]}]
        self.assertEqual(covered_length(whole, opposite, 10)["coverage"], 0)
        self.assertIsNone(covered_length([], whole, 1)["coverage"])

    def test_wrong_number_not_counted_as_exact_even_with_correct_box(self):
        reference = load_json(DEFAULT_MANIFEST.parent / "Data_1.observations.json")
        side = load_json(DEFAULT_MANIFEST.parent / "Data_1.annotations.json")
        pred = copy.deepcopy(reference)
        pred["texts"][0]["parsed_value_cm"] = 800
        working = {"line_detectors": {"hough": [], "lsd": []}, "gaps": []}
        result = evaluate(pred, working, reference, side)
        self.assertEqual(result["text"]["true_positive"], 2)
        self.assertEqual(result["text"]["numeric_exact_correct"], 1)


class StubOCR:
    runtime = {"adapter": "unit-test-stub; not a real OCR score"}
    read_polygons = RapidOCRAdapter.read_polygons

    def detect(self, rgb):
        return [[[10, 10], [120, 10], [120, 40], [10, 40]]]

    def recognize(self, crops):
        return [("700 cm", 0.95) if i % 4 == 0 else ("?", 0.1) for i in range(len(crops))]


class PipelineTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "input.png"
        gray = np.full((200, 300, 3), 255, np.uint8)
        cv2.rectangle(gray, (20, 50), (280, 180), (30, 30, 30), 3)
        Image.fromarray(gray).save(self.path)

    def test_predict_never_reads_annotations_and_outputs_valid_original_frame(self):
        with patch(
            "SketchPipeline.perception.run.load_json",
            side_effect=AssertionError("No ground truth reads during prediction"),
        ):
            obs, working, images, masks = predict(self.path, StubOCR(), max_side=100)
        checked = validate_document(obs)
        self.assertTrue(checked["schema_valid"])
        self.assertEqual(checked["issues"], [])
        self.assertEqual(obs["texts"][0]["method"], "ocr")
        self.assertEqual(obs["region_annotation_status"], "partial")
        self.assertEqual(obs["frame"]["width_px"], 300)
        reading = working["fragments"][0]["readings"][1]
        p = [[20, 60], [150, 90]]
        np.testing.assert_allclose(
            project(project(p, reading["original_to_crop"]), reading["crop_to_original"]),
            p,
            atol=1e-06,
        )

    def test_single_output_paths_remain_valid_after_atomic_rename(self):
        out = self.root / "run"
        run_single(self.path, out, StubOCR())
        obs = load_json(out / "observations.json")
        self.assertEqual((out / obs["source"]["image_path"]).resolve(), self.path.resolve())
        self.assertTrue((out / "crops/f001-r90.png").is_file())
        with self.assertRaises(InputError):
            run_single(self.path, out, StubOCR())

    def test_injected_failure_removes_partial_dataset_without_touching_sources(self):
        out = self.root / "failed"

        def fail(*args, **kwargs):
            raise InputError("Injected model failure")

        with patch("SketchPipeline.perception.run.predict", side_effect=fail):
            with self.assertRaises(InputError):
                run_dataset(DEFAULT_MANIFEST, out, StubOCR())
        self.assertFalse(out.exists())
        self.assertFalse(any((p.name.startswith(".perception-") for p in self.root.iterdir())))

    def test_model_hash_mismatch_rejected_before_inference(self):
        import SketchPipeline.perception.ocr as ocr

        changed = json.loads(ocr.LOCK_PATH.read_text())
        changed["models"]["det"]["sha256"] = "0" * 64
        lock = self.root / "bad-lock.json"
        lock.write_text(json.dumps(changed))
        with patch.object(ocr, "LOCK_PATH", lock):
            with self.assertRaisesRegex(InputError, "hash mismatch"):
                RapidOCRAdapter()


if __name__ == "__main__":
    unittest.main()
