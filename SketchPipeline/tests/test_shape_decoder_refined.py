import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.contract import validate_authoring
from SketchPipeline.shape_authoring.decoder import boundary_graph
from SketchPipeline.shape_authoring.decoder_refined import (
    canonical_frame,
    decode,
    opening_candidates,
)
from SketchPipeline.shape_authoring.synthetic import render


def fixture(style="door", axis=1):
    gray = np.full((256, 256), 255, np.uint8)
    boxes = [
        {"type": "room", "bounds_px": [20, 20, 128, 236]},
        {"type": "room", "bounds_px": [128, 20, 236, 236]},
    ]
    cv2.line(gray, (128, 20), (128, 236), 35, 3)
    if style != "solid":
        for lo, hi in [(65, 89), (150, 174)]:
            cv2.line(gray, (128, lo), (128, hi), 255, 7)
            if style in ("door", "one_sided", "single_tick"):
                for y in (lo,) if style == "single_tick" else (lo, hi):
                    cv2.line(gray, (119, y), (128 if style == "one_sided" else 137, y), 35, 2)
    if style == "stray":
        for x, y in [(113, 65), (142, 89), (115, 150), (142, 174)]:
            cv2.line(gray, (x - 4, y), (x + 4, y), 35, 2)
    if style == "digits":
        for text, y in [("120", 65), ("200", 150)]:
            cv2.putText(gray, text, (145, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, 35, 1)
    masks = np.zeros((6, 256, 256), np.float32)
    if axis == 0:
        gray = gray.T.copy()
        boxes = [
            {
                **b,
                "bounds_px": [
                    b["bounds_px"][1],
                    b["bounds_px"][0],
                    b["bounds_px"][3],
                    b["bounds_px"][2],
                ],
            }
            for b in boxes
        ]
    return (gray, masks, boundary_graph(boxes)[0])


class RefinedDecoderTests(unittest.TestCase):

    def test_two_doors_and_both_orientations_with_raw_geometry_provenance(self):
        for axis in (0, 1):
            gray, masks, segments = fixture("door", axis)
            openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "paired_raw")
            self.assertEqual(len(openings), 2, detail)
            self.assertTrue(all((p["type"] == "door" for p in openings)))
            self.assertTrue(
                all((p["evidence"]["basis"] == "paired_raw_geometry" for p in openings))
            )

    def test_no_automatic_door_from_gap_single_tick_one_sided_ticks_stray_or_digits(self):
        for name in ("solid", "gap", "single_tick", "one_sided", "stray", "digits"):
            for axis in (0, 1):
                with self.subTest(name=name, axis=axis):
                    gray, masks, segments = fixture(name, axis)
                    openings, detail = opening_candidates(
                        segments, gray, masks, np.eye(3), "paired_raw"
                    )
                    self.assertEqual(openings, [], detail)

    def test_false_semantic_tick_response_cannot_override_missing_physical_markers(self):
        for name in ("solid", "gap", "single_tick", "one_sided", "digits"):
            gray, masks, segments = fixture(name)
            masks[3] = 1
            openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "paired_raw")
            self.assertEqual(openings, [], detail)

    def test_model_center_mode_keeps_missing_semantics_unresolved(self):
        gray, masks, segments = fixture()
        openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "model_center")
        self.assertEqual(openings, [])
        self.assertTrue(detail["candidates"])

    def test_faint_periodic_grid_does_not_fill_a_real_door_gap(self):
        gray, masks, segments = fixture()
        gray[gray < 100] = 70
        grid = np.full(gray.shape, 255, np.uint8)
        for t in range(7, 256, 13):
            cv2.line(grid, (t, 0), (t, 255), 210, 1)
            cv2.line(grid, (0, t), (255, t), 210, 1)
        gray = np.minimum(gray, grid)
        openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "paired_raw")
        self.assertEqual(len(openings), 2, detail)

    def test_clear_opening_does_not_need_an_unstated_four_stroke_width(self):
        gray, masks, segments = fixture("solid")
        cv2.line(gray, (128, 75), (128, 93), 255, 7)
        for y in (75, 93):
            cv2.line(gray, (119, y), (137, y), 35, 2)
            masks[3, y - 1 : y + 2, 127:130] = 0.9
        openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "model_center")
        self.assertEqual(len(openings), 1, detail)

    def test_center_response_does_not_require_semantic_activation_along_both_legs(self):
        gray, masks, segments = fixture()
        for y in (65, 89, 150, 174):
            masks[3, y - 1 : y + 2, 127:130] = 0.9
        openings, detail = opening_candidates(segments, gray, masks, np.eye(3), "model_center")
        self.assertEqual(len(openings), 2, detail)
        self.assertTrue(
            all((p["evidence"]["basis"] == "model_center_and_paired_ink" for p in openings))
        )

    def test_no_opening_without_two_region_owners(self):
        gray, masks, segments = fixture()
        segments = {key: [0] for key in segments}
        openings, _ = opening_candidates(segments, gray, masks, np.eye(3), "paired_raw")
        self.assertEqual(openings, [])

    def test_paired_raw_openings_are_consistent_when_image_is_resampled(self):
        gray, masks, segments = fixture()
        normalized = []
        for factor in (1, 2, 3):
            size = (256 * factor, 256 * factor)
            native = cv2.resize(gray, size, interpolation=cv2.INTER_NEAREST)
            probabilities = np.zeros((6, *native.shape), np.float32)
            forward = np.array(
                [[factor, 0, (factor - 1) / 2], [0, factor, (factor - 1) / 2], [0, 0, 1.0]]
            )
            openings, detail = opening_candidates(
                segments, native, probabilities, forward, "paired_raw"
            )
            self.assertEqual(len(openings), 2, detail)
            normalized.append(np.array([[p["start"], p["end"]] for p in openings]))
        for value in normalized[1:]:
            np.testing.assert_allclose(value, normalized[0], atol=1.5)

    def test_canonical_regions_do_not_change_with_resampled_exact_masks(self):
        gray, masks, spec = render(2001, "clean")
        documents = []
        for factor in (1, 2):
            native = cv2.resize(gray, (256 * factor, 256 * factor), interpolation=cv2.INTER_NEAREST)
            probabilities = (
                np.stack(
                    [
                        cv2.resize(c, (256 * factor, 256 * factor), interpolation=cv2.INTER_NEAREST)
                        for c in masks
                    ]
                ).astype(np.float32)
                / 255
            )
            forward = np.array(
                [[factor, 0, (factor - 1) / 2], [0, factor, (factor - 1) / 2], [0, 0, 1.0]]
            )
            metadata = {
                "working_size_px": [256 * factor] * 2,
                "original_to_working": forward.tolist(),
                "working_to_original": np.linalg.inv(forward).tolist(),
            }
            source = {
                "image_path": "synthetic.png",
                "image_sha256": "0" * 64,
                "width_px": 256,
                "height_px": 256,
            }
            document, detail = decode(native, probabilities, source, metadata)
            self.assertEqual(validate_authoring(document), [])
            self.assertEqual(len(document["topology"]["regions"]), len(spec["regions"]), detail)
            self.assertEqual(len(document["topology"]["openings"]), len(spec["openings"]), detail)
            documents.append(document)
        for a, b in zip(documents[0]["topology"]["regions"], documents[1]["topology"]["regions"]):
            np.testing.assert_allclose(
                a["geometry"]["points_px"], b["geometry"]["points_px"], atol=1.5
            )

    def test_invalid_mode_and_non_aligned_frames_are_rejected(self):
        gray, masks, segments = fixture()
        with self.assertRaises(ValueError):
            opening_candidates(segments, gray, masks, np.eye(3), "unknown")
        with self.assertRaises(ValueError):
            opening_candidates(
                segments, gray, masks, np.array([[1, 0.1, 0], [0, 1, 0], [0, 0, 1.0]])
            )
        with self.assertRaises(ValueError):
            opening_candidates(segments, gray, masks, np.diag([-1, 1, 1]))
        with self.assertRaises(ValueError):
            opening_candidates(segments, gray, masks, np.diag([0, 1, 1]))
        with self.assertRaises(ValueError):
            canonical_frame(gray, masks, gray, np.zeros((3, 3)))


if __name__ == "__main__":
    unittest.main()
