import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from SketchPipeline.shape_authoring.human_supervision import (
    structural_labels,
    weak_targets,
    ROOT,
    CURATION,
)
from SketchPipeline.shape_authoring.human_error_review import reference
from SketchPipeline.shape_authoring.pilot import human_reference
from SketchPipeline.shape_authoring.contrast import normalize_ink

TORCH = importlib.util.find_spec("torch") is not None


class HumanGeometrySupervisionTests(unittest.TestCase):

    def test_photo_statistics_exclude_white_letterbox_padding(self):
        gray = np.full((128, 128), 255, np.uint8)
        gray[32:96, 32:96] = 170
        gray[50:55, 40:85] = 70
        normalized, info = normalize_ink(gray, [32, 32, 96, 96])
        self.assertTrue(info["applied"])
        self.assertEqual(info["paper_level"], 170)
        self.assertEqual(normalized.shape, gray.shape)
        self.assertEqual(info["geometry_transform"], "identity")
        self.assertTrue(np.all(normalized[32:48, 32:96] == 255))
        self.assertTrue(np.all(normalized[50:55, 40:85] < 100))

    def test_white_digital_drawing_is_pixel_identical(self):
        gray = np.full((128, 128), 255, np.uint8)
        gray[32:36, 20:100] = 20
        normalized, info = normalize_ink(gray)
        self.assertFalse(info["applied"])
        self.assertTrue(np.array_equal(gray, normalized))

    @unittest.skipUnless(TORCH, "Requires the isolated training runtime")
    def test_optional_photo_input_preserves_source_and_review_coordinates(self):
        from SketchPipeline.shape_authoring.propose import run, DEFAULT_LOCK

        lock = json.loads(DEFAULT_LOCK.read_text())
        if not (ROOT / lock["checkpoint_path"]).exists():
            self.skipTest("Local checkpoint unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / "photo.png"
            gray = np.full((150, 240), 170, np.uint8)
            cv2.rectangle(gray, (20, 20), (220, 130), 40, 3)
            cv2.line(gray, (120, 20), (120, 130), 40, 3)
            cv2.imwrite(str(source), gray)
            original = source.read_bytes()
            raw = run(source, folder / "raw", profile="refined-full")
            adapted = run(source, folder / "normalized", profile="refined-full", normalize_ink=True)
            self.assertIsNone(adapted["failure"])
            self.assertIsNone(raw["input_normalization"])
            self.assertTrue(adapted["input_normalization"]["raw"]["applied"])
            self.assertEqual(raw["preprocessing"], adapted["preprocessing"])
            self.assertEqual(raw["evidence_preprocessing"], adapted["evidence_preprocessing"])
            self.assertEqual(
                (folder / "raw/working.png").read_bytes(),
                (folder / "normalized/working.png").read_bytes(),
            )
            self.assertEqual(source.read_bytes(), original)
            self.assertNotEqual(raw["authoring_revision_id"], adapted["authoring_revision_id"])
            self.assertFalse(adapted["numeric_ocr_called"])

    @unittest.skipUnless(TORCH, "Requires the isolated training runtime")
    def test_marker_only_optimizer_cannot_change_backbone_or_region_outputs(self):
        import torch
        from SketchPipeline.shape_authoring.model import ShapeUNet
        from SketchPipeline.shape_authoring.train_human import configure_adaptation

        torch.manual_seed(1)
        model = ShapeUNet(width=2)
        configure_adaptation(model, "marker_heads_only", "cpu")
        before = {k: v.detach().clone() for k, v in model.state_dict().items()}
        inputs = torch.rand((1, 2, 32, 32))
        outputs = model(inputs).detach()
        optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=0.01)
        optimizer.zero_grad()
        model(inputs).sum().backward()
        optimizer.step()
        for name, old in before.items():
            current = model.state_dict()[name]
            if name.startswith("head."):
                self.assertTrue(torch.equal(old[[0, 1, 2, 5]], current[[0, 1, 2, 5]]))
            else:
                self.assertTrue(torch.equal(old, current), name)
        self.assertFalse(torch.equal(before["head.bias"][3:5], model.head.bias[3:5]))
        self.assertTrue(torch.equal(outputs[:, [0, 1, 2, 5]], model(inputs)[:, [0, 1, 2, 5]]))

    def metadata(self):
        return {
            "working_size_px": [256, 256],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }

    def labels(self):
        return {
            "regions": [],
            "strokes": [{"kind": "wall", "line_ids": ["a"]}],
            "lines": {"a": {"start_px": [30, 50], "end_px": [210, 50]}},
            "junctions": [],
            "gaps": [],
            "distractor_polygons": [[[90, 90], [150, 90], [150, 125], [90, 125]]],
        }

    def test_unannotated_space_is_not_dense_background_ground_truth(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (30, 50), (210, 50), 20, 3)
        target, known, info = weak_targets(gray, self.metadata(), self.labels())
        self.assertTrue(target[0, 50, 100] > 0)
        self.assertEqual(float(known[:, 200, 200].sum()), 0.0)
        self.assertEqual(float(known[1:3].sum()), 0.0)
        self.assertFalse(info["human_dense_ground_truth"])

    def test_verified_text_ink_is_negative_without_reading_text(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.rectangle(gray, (100, 100), (120, 115), 0, 2)
        target, known, info = weak_targets(gray, self.metadata(), self.labels())
        self.assertEqual(target[3, 100, 110], 0)
        self.assertEqual(known[3, 100, 110], 1)
        self.assertFalse(info["numeric_transcription_used"])

    def test_wall_marker_protection_prevents_text_polygon_from_erasing_positive_ink(self):
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (30, 50), (210, 50), 20, 3)
        labels = self.labels()
        labels["distractor_polygons"] = [[[20, 40], [220, 40], [220, 60], [20, 60]]]
        target, known, info = weak_targets(gray, self.metadata(), labels)
        self.assertEqual(target[0, 50, 100], 1)
        self.assertEqual(known[0, 50, 100], 1)

    def test_incidental_break_is_not_an_opening_reference_or_positive_marker(self):
        gray = np.full((256, 256), 255, np.uint8)
        labels = self.labels()
        labels["gaps"] = [{"kind": "incidental", "start_px": [60, 60], "end_px": [64, 60]}]
        target, known, _ = weak_targets(gray, self.metadata(), labels)
        self.assertEqual(float(target[5].sum()), 0.0)
        self.assertEqual(target[3, 60, 62], 0)
        self.assertGreater(known[3, 60, 62], 0)
        metadata = {"working_size_px": [1211, 1177], "original_to_working": np.eye(3).tolist()}
        self.assertEqual(len(human_reference(41, metadata)["openings"]), 3)
        self.assertEqual(len(reference(41, metadata)["openings"]), 3)

    def test_curated_region_labels_do_not_mutate_original_annotations(self):
        path = ROOT / "Data/annotations/v1/Data_3.annotations.json"
        before = path.read_bytes()
        labels = structural_labels(3)
        self.assertEqual(len(labels["regions"]), 2)
        self.assertNotIn("texts", labels)
        self.assertNotIn("dimensions", labels)
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn("regions", json.loads(before))
        self.assertEqual(len(structural_labels(8)["regions"]), 3)

    def test_fixed_group_split_excludes_reserved_evaluation_from_training(self):
        path = ROOT / "Saved/ShapeFirst/human_adaptation/v1/protocol.json"
        if not path.exists():
            self.skipTest("Requires the frozen local adaptation protocol")
        protocol = json.loads(path.read_text())
        train = set(protocol["human_splits"]["train"])
        val = set(protocol["human_splits"]["validation"])
        test = set(protocol["human_splits"]["test"])
        self.assertFalse(train & val or train & test or val & test)
        self.assertEqual(len(train | val | test), 50)
        self.assertFalse(
            set(protocol["reserved_development_evaluation_ids"])
            & set(protocol["previously_inspected_diagnostic_ids"])
        )
        self.assertFalse(protocol["writer_holdout"])
        self.assertIn("tablet_author_01", protocol["leakage_audit"]["writer_train_test_overlap"])

    @unittest.skipUnless(TORCH, "Requires the isolated training runtime")
    def test_unknown_pixels_have_zero_loss_gradient(self):
        import torch
        from SketchPipeline.shape_authoring.train_human import masked_loss

        logits = torch.zeros((1, 6, 8, 8), requires_grad=True)
        target = torch.zeros_like(logits)
        target[0, 3, 3, 3] = 1
        known = torch.zeros_like(logits)
        known[0, 3, 3, 3] = 1
        loss = masked_loss(logits, target, known)
        loss.backward()
        gradient = logits.grad.detach().numpy()
        self.assertNotEqual(gradient[0, 3, 3, 3], 0)
        gradient[0, 3, 3, 3] = 0
        self.assertTrue(np.all(gradient == 0))

    @unittest.skipUnless(TORCH, "Requires the isolated training runtime")
    def test_empty_supervision_is_zero_and_finite(self):
        import torch
        from SketchPipeline.shape_authoring.train_human import masked_loss

        logits = torch.ones((1, 6, 8, 8), requires_grad=True)
        loss = masked_loss(logits, torch.zeros_like(logits), torch.zeros_like(logits))
        self.assertEqual(float(loss.detach()), 0)
        loss.backward()
        self.assertTrue(torch.all(logits.grad == 0))


if __name__ == "__main__":
    unittest.main()
