import copy
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from SketchPipeline.shape_authoring.corridor_geometry import infer_regions, decode, enclosed_floor
from SketchPipeline.shape_authoring.decoder import boundary_graph, authoring_document
from SketchPipeline.shape_authoring.contract import validate_authoring


def image_of(bounds):
    floor = np.zeros((512, 512), np.uint8)
    for bounds_row in bounds:
        x, y, X, Y = map(round, bounds_row)
        cv2.rectangle(floor, (x, y), (X, Y), 1, -1)
    edge = floor - cv2.erode(floor, np.ones((3, 3), np.uint8))
    return np.uint8(255 - edge * 255)


class CorridorGeometryTests(unittest.TestCase):

    def boxes(self, bounds):
        return [
            {"type": "room", "bounds_px": list(map(float, b)), "model_score": 0.99} for b in bounds
        ]

    def test_blank_image_abstains_and_does_not_mutate_predictions(self):
        boxes = self.boxes([[20, 20, 150, 150], [300, 300, 450, 450]])
        before = copy.deepcopy(boxes)
        result, detail, _ = infer_regions(np.full((512, 512), 255, np.uint8), boxes)
        self.assertEqual(boxes, before)
        self.assertEqual(result, before)
        self.assertTrue(detail["status"].startswith("abstained"))

    def test_two_closed_isolated_rooms_do_not_gain_corridors(self):
        bounds = [[40, 40, 190, 190], [300, 280, 460, 460]]
        boxes = self.boxes(bounds)
        result, _, _ = infer_regions(image_of(bounds), boxes)
        self.assertEqual(sum((r["type"] == "corridor_segment" for r in result)), 0)
        self.assertEqual(sum((r["type"] == "room" for r in result)), 2)

    def test_long_thin_corridor_is_retained_between_room_faces(self):
        rooms = [[50, 30, 220, 180], [60, 350, 230, 480]]
        result, detail, _ = infer_regions(
            image_of(rooms + [[120, 180, 140, 350]]), self.boxes(rooms)
        )
        corridors = [r for r in result if r["type"] == "corridor_segment"]
        self.assertEqual(len(corridors), 1)
        C = corridors[0]["bounds_px"]
        self.assertGreater(C[3] - C[1], (C[2] - C[0]) * 4)
        self.assertTrue(any((len(v) == 2 for v in boundary_graph(result)[0].values())))

    def test_l_bend_becomes_nonoverlapping_corridor_arms(self):
        rooms = [[30, 30, 180, 180], [330, 310, 480, 470]]
        gray = image_of(rooms + [[90, 180, 125, 365], [125, 330, 330, 365]])
        result, _, _ = infer_regions(gray, self.boxes(rooms))
        corridors = [r for r in result if r["type"] == "corridor_segment"]
        self.assertEqual(len(corridors), 2)
        from SketchPipeline.shape_authoring.corridor_candidates import overlap

        self.assertEqual(overlap(corridors[0]["bounds_px"], corridors[1]["bounds_px"]), 0)
        self.assertTrue(any((len(v) == 2 for v in boundary_graph(corridors)[0].values())))

    def test_dangling_branch_cannot_be_a_two_room_corridor(self):
        rooms = [[30, 30, 180, 180]]
        result, _, _ = infer_regions(image_of(rooms + [[90, 180, 125, 365]]), self.boxes(rooms))
        self.assertEqual(sum((r["type"] == "corridor_segment" for r in result)), 0)

    def test_closed_room_exterior_is_not_enclosed_floor(self):
        bounds = [[40, 40, 190, 190], [300, 280, 460, 460]]
        floor, _, _ = enclosed_floor(image_of(bounds), self.boxes(bounds))
        self.assertEqual(floor[240, 240], 0)
        self.assertEqual(floor[100, 100], 1)

    def test_decoder_abstention_preserves_complete_incumbent_document(self):
        boxes = self.boxes([[30, 30, 180, 180], [330, 310, 480, 470]])
        metadata = {
            "working_size_px": [512, 512],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        source = {
            "image_path": "test.png",
            "image_sha256": "0" * 64,
            "width_px": 512,
            "height_px": 512,
        }
        baseline = authoring_document(source, metadata, boxes, [])
        baseline["topology"]["openings"] = [
            {
                "id": "incumbent",
                "type": "door",
                "entity_ids": ["region_0001", "region_0002"],
                "geometry": {"points_px": [[100, 180], [120, 180]]},
            }
        ]
        with (
            patch(
                "SketchPipeline.shape_authoring.corridor_geometry.passages", return_value=([], {})
            ),
            patch("SketchPipeline.shape_authoring.corridor_geometry.doors", return_value=([], {})),
        ):
            result, detail, _ = decode(
                image_of([b["bounds_px"] for b in boxes]),
                np.zeros((6, 512, 512), np.float32),
                source,
                metadata,
                working_metadata=metadata,
                evidence_to_working=np.eye(3),
                baseline_result=(baseline, {"region_boxes": boxes}),
            )
        self.assertEqual(result, baseline)
        self.assertEqual(detail["status"], "abstained_incumbent_opening_lost")

    def test_output_remains_unaccepted(self):
        rooms = [[50, 30, 220, 180], [60, 350, 230, 480]]
        boxes = self.boxes(rooms)
        metadata = {
            "working_size_px": [512, 512],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        source = {
            "image_path": "test.png",
            "image_sha256": "0" * 64,
            "width_px": 512,
            "height_px": 512,
        }
        baseline = authoring_document(source, metadata, boxes, [])
        result, detail, _ = decode(
            image_of(rooms + [[120, 180, 140, 350]]),
            np.zeros((6, 512, 512), np.float32),
            source,
            metadata,
            working_metadata=metadata,
            evidence_to_working=np.eye(3),
            baseline_result=(baseline, {"region_boxes": boxes}),
        )
        self.assertEqual(result["physical_design"]["acceptance"]["status"], "pending")
        self.assertEqual(validate_authoring(result), [])

    def test_geometry_abstention_cannot_resurrect_withheld_passage(self):
        boxes = self.boxes([[30, 30, 180, 180], [330, 310, 480, 470]])
        metadata = {
            "working_size_px": [512, 512],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        source = {
            "image_path": "test.png",
            "image_sha256": "0" * 64,
            "width_px": 512,
            "height_px": 512,
        }
        baseline = authoring_document(source, metadata, boxes, [])
        baseline["topology"]["openings"] = [
            {
                "id": "stale",
                "type": "open_passage",
                "entity_ids": ["region_0001", "region_0002"],
                "geometry": {"points_px": [[100, 180], [120, 180]]},
            }
        ]
        with (
            patch(
                "SketchPipeline.shape_authoring.corridor_geometry.passages",
                return_value=([], {"withheld": True}),
            ),
            patch("SketchPipeline.shape_authoring.corridor_geometry.doors", return_value=([], {})),
            patch(
                "SketchPipeline.shape_authoring.corridor_geometry.infer_regions",
                return_value=(boxes, {"status": "abstained_test"}, None),
            ),
        ):
            result, detail, _ = decode(
                np.full((512, 512), 255, np.uint8),
                np.zeros((6, 512, 512), np.float32),
                source,
                metadata,
                working_metadata=metadata,
                evidence_to_working=np.eye(3),
                baseline_result=(baseline, {"region_boxes": boxes}),
                opening_alignment=True,
            )
        self.assertEqual(result["topology"]["openings"], [])
        self.assertTrue(detail["baseline_alignment_evidence"]["withheld"])
        self.assertEqual(baseline["topology"]["openings"][0]["id"], "stale")


if __name__ == "__main__":
    unittest.main()
