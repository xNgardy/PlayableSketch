import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np

TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(TORCH, "Requires the isolated local training runtime")
class DinoShapeTests(unittest.TestCase):

    def test_letterbox_preserves_full_non_square_drawing_without_center_crop(self):
        from SketchPipeline.shape_authoring.dino_model import prepare_tensors

        gray = np.full((80, 160), 255, np.uint8)
        gray[20:60, 0:5] = 0
        gray[20:60, -5:] = 0
        rgb, ink, frame = prepare_tensors(gray)
        self.assertEqual(rgb.shape, (3, 448, 448))
        self.assertEqual(ink.shape, (2, 256, 256))
        self.assertEqual(
            frame, {"square_side": 160, "top": 40, "left": 0, "height": 80, "width": 160}
        )
        self.assertGreater(ink[0, :, 0].max(), 0.9)
        self.assertGreater(ink[0, :, -1].max(), 0.9)
        self.assertEqual(float(ink[0, :60].max()), 0.0)
        with self.assertRaises(ValueError):
            prepare_tensors(gray.astype(np.float32))
        with self.assertRaises(ValueError):
            prepare_tensors(gray, gray[:20])

    def test_auxiliary_head_contract_keeps_logical_boundary_separate_from_wall(self):
        from SketchPipeline.shape_authoring.dino_model import decoder_channels

        maps = np.zeros((8, 16, 16), np.float32)
        maps[1] = 0.9
        maps[6, 4, 4] = 0.8
        maps[7, :, 8] = 1
        result = decoder_channels(maps)
        self.assertEqual(result.shape, (6, 16, 16))
        self.assertAlmostEqual(float(result[3, 4, 4]), 0.8)
        self.assertTrue(np.all(result[1, :, 8] == 0))
        self.assertTrue(np.all(result[0] == 0))
        self.assertTrue(np.array_equal(maps[1], np.full((16, 16), 0.9, np.float32)))
        with self.assertRaises(ValueError):
            decoder_channels(maps[:6])

    def test_incidental_gap_never_creates_positive_endpoint_label(self):
        from SketchPipeline.shape_authoring.dino_experiment import auxiliary_targets

        gray = np.full((256, 256), 255, np.uint8)
        target = np.zeros((6, 256, 256), np.float32)
        known = np.zeros_like(target)
        labels = {
            "regions": [{"polygon_px": [[20, 20], [220, 20], [220, 220], [20, 220]]}],
            "gaps": [
                {"kind": "door", "start_px": [20, 50], "end_px": [20, 70]},
                {"kind": "incidental", "start_px": [220, 100], "end_px": [220, 106]},
                {"kind": "open_passage", "start_px": [100, 20], "end_px": [120, 20]},
            ],
        }
        output, weights = auxiliary_targets(
            gray, {"original_to_working": np.eye(3).tolist()}, labels, target, known
        )
        self.assertEqual(output[6, 50, 20], 1)
        self.assertEqual(output[6, 70, 20], 1)
        self.assertEqual(output[6, 100, 220], 0)
        self.assertEqual(output[6, 20, 100], 0)
        self.assertEqual(output[7, 50, 20], 1)
        self.assertEqual(output[0, 50, 20], 0)
        self.assertEqual(float(weights[:, 128, 128].sum()), 0.0)

    def test_synthetic_logical_boundary_spans_real_door_gap(self):
        from SketchPipeline.shape_authoring.dino_experiment import synthetic_targets
        from SketchPipeline.shape_authoring.synthetic import render

        gray, masks, spec = render(1002, "clean")
        target, known = synthetic_targets(masks, spec)
        door = next((o for o in spec["openings"] if o["type"] == "door"))
        center = int(round(sum(door["interval"]) / 2))
        fixed = int(door["fixed"])
        x, y = (center, fixed) if door["axis"] == 0 else (fixed, center)
        self.assertEqual(target[7, y, x], 1)
        self.assertEqual(target[0, y, x], 0)
        self.assertTrue(np.all(known == 1))

    def test_unknown_auxiliary_pixels_have_zero_gradient(self):
        import torch
        from SketchPipeline.shape_authoring.dino_experiment import masked_loss

        logits = torch.zeros((1, 8, 8, 8), requires_grad=True)
        target = torch.zeros_like(logits)
        known = torch.zeros_like(logits)
        target[0, 6, 2, 3] = 1
        known[0, 6, 2, 3] = 1
        masked_loss(logits, target, known, [1] * 8).backward()
        gradient = logits.grad.clone()
        self.assertNotEqual(float(gradient[0, 6, 2, 3]), 0)
        gradient[0, 6, 2, 3] = 0
        self.assertTrue(torch.all(gradient == 0))

    def test_frozen_encoder_receives_no_gradient_while_decoder_trains(self):
        import torch
        from SketchPipeline.shape_authoring.dino_model import DinoDecoder, extract_features

        class Encoder(torch.nn.Module):

            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.ones(1))

            def get_intermediate_layers(self, x, n, reshape):
                return tuple(((x.mean() * self.weight).expand(len(x), 384, 32, 32) for _ in n))

        torch.set_num_threads(4)
        encoder = Encoder()
        decoder = DinoDecoder(width=8)
        features = extract_features(encoder, torch.rand((1, 3, 448, 448)))
        decoder(features, torch.rand((1, 2, 256, 256))).square().mean().backward()
        self.assertIsNone(encoder.weight.grad)
        self.assertIsNotNone(decoder.head.weight.grad)

    def test_attachment_metric_penalizes_correct_location_with_wrong_owners(self):
        from SketchPipeline.shape_authoring.dino_experiment import attached_counts

        row = {
            "metrics": {"openings": {"predicted": 2}, "attachment_correct": 1},
            "reference_has_regions": True,
            "attachment_reference_count": 3,
        }
        metric = attached_counts([row])
        self.assertEqual(metric["precision"], 0.5)
        self.assertEqual(metric["recall"], 1 / 3)

    def test_endpoint_diagnostics_do_not_use_reference_guided_peak_search(self):
        from SketchPipeline.shape_authoring.dino_keypoints import endpoint_peaks

        probability = np.zeros((32, 32), np.float32)
        probability[4:8, 4:8] = 0.6
        probability[6, 5] = 0.9
        probability[20:24, 20:24] = 0.7
        probability[21, 22] = 0.95
        self.assertEqual(endpoint_peaks(probability), [[5, 6], [22, 21]])
        self.assertEqual(endpoint_peaks(np.zeros((32, 32), np.float32)), [])
        with self.assertRaises(ValueError):
            endpoint_peaks(np.full((4, 4), np.nan))

    def test_real_pretrained_backbone_loads_offline_and_dispatches_via_public_api(self):
        import torch
        from SketchPipeline.shape_authoring.dino_model import (
            ROOT,
            LOCK,
            ARCHITECTURE,
            CHANNELS,
            DinoDecoder,
            sha,
            verify_dependencies,
        )

        try:
            verify_dependencies()
        except FileNotFoundError:
            self.skipTest("Run setup_dino --download for the real backbone integration test")
        from SketchPipeline.shape_authoring.propose import run
        from SketchPipeline.shape_authoring.contract import validate_authoring

        torch.set_num_threads(4)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            checkpoint = folder / "decoder.pt"
            source = folder / "drawing.png"
            model = DinoDecoder(width=8)
            torch.save(
                {
                    "architecture": ARCHITECTURE,
                    "channels": CHANNELS,
                    "width": 8,
                    "state_dict": model.state_dict(),
                    "backbone_lock_sha256": sha(LOCK),
                },
                checkpoint,
            )
            gray = np.full((128, 200), 255, np.uint8)
            cv2.rectangle(gray, (20, 20), (180, 108), 0, 2)
            cv2.imwrite(str(source), gray)
            with patch("torch.hub.load", side_effect=AssertionError("No implicit downloads")):
                result = run(
                    source,
                    folder / "output",
                    checkpoint=checkpoint,
                    expected_sha256=sha(checkpoint),
                    profile="refined-full",
                )
            self.assertIsNone(result["failure"])
            self.assertEqual(validate_authoring(result["authoring"]), [])
            self.assertEqual(result["model"]["architecture"], ARCHITECTURE)
            self.assertTrue(result["model"]["backbone_frozen"])
            self.assertFalse(result["numeric_ocr_called"])
            self.assertEqual(
                result["authoring"]["physical_design"]["acceptance"]["status"], "pending"
            )
            with np.load(folder / "output/native-auxiliary-masks.npz") as data:
                self.assertEqual(data["probabilities"].shape, (8, 512, 512))
            bad = run(
                source,
                folder / "bad",
                checkpoint=checkpoint,
                expected_sha256="0" * 64,
                profile="refined-full",
            )
            self.assertIsNotNone(bad["failure"])
            self.assertEqual(bad["status"], "manual_required")

    def test_job_checkpoint_configuration_is_pinned_and_survives_restart_retry(self):
        import torch
        from SketchPipeline.shape_authoring.model import ShapeUNet, ARCHITECTURE
        from SketchPipeline.shape_authoring.synthetic import CHANNELS
        from SketchPipeline.shape_authoring.jobs import ShapeJobs, ShapeJobError
        from SketchPipeline.tests.test_shape_proposals import wait

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            checkpoint = folder / "model.pt"
            source = folder / "photo.png"
            torch.save(
                {
                    "architecture": ARCHITECTURE,
                    "channels": CHANNELS,
                    "width": 2,
                    "state_dict": ShapeUNet(2).state_dict(),
                },
                checkpoint,
            )
            gray = np.full((120, 180), 170, np.uint8)
            cv2.rectangle(gray, (20, 20), (160, 100), 30, 2)
            cv2.imwrite(str(source), gray)
            manager = ShapeJobs(
                folder / "jobs", checkpoint=checkpoint, profile="refined-full", normalize_ink=True
            )
            try:
                job = manager.start(source.read_bytes(), "photo.png")
                wait(manager, job["job_id"])
                self.assertTrue(
                    manager.proposals(job["job_id"])["input_normalization"]["raw"]["applied"]
                )
                config = manager.status(job["job_id"])["model_config"]
                self.assertEqual(config["checkpoint"], str(checkpoint.resolve()))
                self.assertTrue(config["expected_sha256"])
            finally:
                manager.close()
            reopened = ShapeJobs(folder / "jobs")
            try:
                self.assertEqual(reopened.status(job["job_id"])["model_config"], config)
                reopened.retry(job["job_id"])
                wait(reopened, job["job_id"])
                self.assertEqual(
                    reopened.proposals(job["job_id"])["model"]["checkpoint_sha256"],
                    config["expected_sha256"],
                )
            finally:
                reopened.close()
            with self.assertRaises(ShapeJobError):
                ShapeJobs(folder / "bad", checkpoint=checkpoint, expected_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
