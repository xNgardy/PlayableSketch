import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from SketchPipeline.shape_authoring.contract import validate_authoring
from SketchPipeline.shape_authoring.hybrid_model import native_input, validate_package
from SketchPipeline.shape_authoring.propose import run
from SketchPipeline.shape_authoring.sizing import recompute


class HybridIntegrationTests(unittest.TestCase):
    def fixture(self, folder):
        image = folder / "input.png"
        gray = np.full((1024, 1024), 255, np.uint8)
        regions = [
            [[[80, 80], [240, 80], [240, 260], [520, 260], [520, 360], [80, 360]]],
            [[[520, 240], [760, 240], [760, 420], [520, 420]]],
        ]
        for pieces in regions:
            cv2.polylines(gray, [np.asarray(pieces[0], np.int32)], True, 40, 2)
        cv2.imwrite(str(image), gray)
        native, metadata = native_input(image)
        return image, {
            "gray": native,
            "preprocessing": metadata,
            "regions": regions,
            "door_boxes": [[510, 285, 530, 335]],
            "door_attached": [True],
            "wall_probability": np.float32(native < 120),
            "closed_barrier": np.uint8(native < 120),
        }

    def test_neural_profile_preserves_concave_rooms_and_sizing(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image, prediction = self.fixture(folder)
            with patch(
                "SketchPipeline.shape_authoring.hybrid_proposals.HybridModel"
            ) as constructor, patch(
                "SketchPipeline.shape_authoring.model.LocalSegmenter",
                side_effect=AssertionError("Legacy model must not run"),
            ), patch(
                "SketchPipeline.shape_authoring.room_geometry.observe",
                side_effect=AssertionError("Raw parser must not replace neural predictions"),
            ):
                model = constructor.return_value
                model.metadata = {
                    "architecture": "hybrid-unet-yolo11/1.0",
                    "checkpoint_sha256": "a" * 64,
                }
                model.config = {
                    "parameters": {
                        "wall_threshold": 0.35,
                        "door_threshold": 0.5,
                        "closing_kernel": 5,
                    }
                }
                model.predict.return_value = prediction
                result = run(image, folder / "output", profile="hybrid")
            self.assertIsNone(result["failure"])
            self.assertEqual(result["profile"], "hybrid")
            self.assertEqual(len(result["authoring"]["topology"]["regions"]), 2)
            self.assertEqual(len(result["authoring"]["topology"]["openings"]), 1)
            self.assertEqual(validate_authoring(result["authoring"]), [])
            self.assertEqual(recompute(result["authoring"])["status"], "ready")
            self.assertEqual(
                sorted(
                    len(r["geometry"]["points_px"])
                    for r in result["authoring"]["topology"]["regions"]
                ),
                [4, 6],
            )

    def test_failed_model_retains_editable_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image, _ = self.fixture(folder)
            with patch(
                "SketchPipeline.shape_authoring.hybrid_proposals.HybridModel",
                side_effect=RuntimeError("test inference failure"),
            ):
                result = run(image, folder / "output", profile="hybrid")
            self.assertEqual(result["status"], "manual_required")
            self.assertIn("test inference failure", result["failure"])
            self.assertEqual(validate_authoring(result["authoring"]), [])
            self.assertTrue((folder / "output/working.png").exists())

    def test_snapping_preserves_narrow_step_in_one_room(self):
        from SketchPipeline.shape_authoring.hybrid_geometry import regularize_regions

        points = [[20, 20], [100, 20], [100, 60], [106, 60], [106, 100], [20, 100]]
        with patch(
            "SketchPipeline.shape_authoring.hybrid_geometry.orthogonal_contour", return_value=points
        ):
            rooms, _ = regularize_regions([[points]], (256, 256))
        self.assertEqual(len(rooms[0]["points_px"]), 6)
        self.assertEqual({p[0] for p in rooms[0]["points_px"]}, {20, 100, 106})

    def test_grid_partition_removes_overlapping_fits_using_model_evidence(self):
        from shapely.geometry import Polygon
        from SketchPipeline.shape_authoring.hybrid_geometry import partition_regions

        regions = [
            {"points_px": [[10, 10], [60, 10], [60, 90], [10, 90]]},
            {"points_px": [[50, 10], [90, 10], [90, 90], [50, 90]]},
        ]
        masks = [np.zeros((100, 100), np.uint8) for _ in regions]
        masks[0][10:90, 10:50] = 1
        masks[1][10:90, 50:90] = 1
        partition_regions(regions, masks)
        polygons = [Polygon(r["points_px"]) for r in regions]
        self.assertEqual(polygons[0].intersection(polygons[1]).area, 0)
        self.assertEqual(polygons[0].area, 3200)
        self.assertEqual(polygons[1].area, 3200)

    def test_manifest_checks_both_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            weights = {}
            for kind in ["wall", "door"]:
                path = folder / (kind + ".pt")
                path.write_bytes(kind.encode())
                weights[kind] = {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            config = {
                "version": "hybrid-unet-yolo11/1.0",
                **weights,
                "parameters": {"wall_threshold": 0.35, "door_threshold": 0.5, "closing_kernel": 5},
                "input_side": 1024,
                "door_full_and_tiled": True,
            }
            manifest = folder / "model-lock.json"
            manifest.write_text(json.dumps(config))
            validate_package(manifest)
            (folder / "door.pt").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "door checkpoint checksum"):
                validate_package(manifest)
