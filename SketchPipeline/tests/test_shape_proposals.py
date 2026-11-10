import builtins
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import cv2
import numpy as np
from SketchPipeline.shape_authoring.contract import validate_authoring
from SketchPipeline.shape_authoring.decoder import (
    boundary_graph,
    opening_candidates,
    authoring_document,
)
from SketchPipeline.shape_authoring.jobs import ShapeJobs, ShapeJobError
from SketchPipeline.shape_authoring.propose import run, prepare_image, DEFAULT_LOCK
from SketchPipeline.shape_authoring.server import make_handler
from SketchPipeline.shape_authoring.synthetic import render, freeze

ROOT = Path(__file__).resolve().parents[2]


def wait(manager, identifier):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        value = manager.status(identifier)
        if value.get("manual_available"):
            return value
        time.sleep(0.03)
    raise AssertionError("Job did not reach editable state")


class ShapeProposalTests(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image = self.root / "input.png"
        image, _, _ = render(2001, "wavy")
        cv2.imwrite(str(self.image), image)

    def tearDown(self):
        self.temporary.cleanup()

    def test_manual_and_model_missing_keep_source_without_observations(self):
        before = self.image.read_bytes()
        for backend in ("manual", "learned"):
            output = self.root / backend
            result = run(self.image, output, backend, checkpoint=self.root / "missing.pt")
            self.assertEqual(result["status"], "manual_required")
            self.assertEqual(validate_authoring(result["authoring"]), [])
            self.assertFalse(result["numeric_ocr_called"])
            self.assertTrue((output / "working.png").exists())
            self.assertFalse((output / "observations.json").exists())
        self.assertEqual(self.image.read_bytes(), before)

    def test_blank_image_remains_editable(self):
        cv2.imwrite(str(self.image), np.full((256, 256), 255, np.uint8))
        result = run(self.image, self.root / "blank", "manual")
        self.assertEqual(result["status"], "manual_required")
        self.assertEqual(validate_authoring(result["authoring"]), [])

    def test_profiles_are_explicit_and_unknown_profiles_are_rejected(self):
        with self.assertRaises(ValueError):
            run(self.image, self.root / "unknown", profile="unknown")
        with self.assertRaises(ShapeJobError):
            ShapeJobs(self.root / "bad", profile="unknown")
        result = run(self.image, self.root / "manual", "manual", profile="refined")
        self.assertEqual(result["profile"], "baseline")

    def test_synthetic_supervision_and_parent_groups(self):
        image, masks, spec = render(2005, "grid")
        self.assertEqual(masks.shape, (6, 256, 256))
        self.assertEqual(set(np.unique(masks)), {0, 255})
        p = freeze(self.root / "protocol")
        self.assertFalse(set(p["train_parent_seeds"]) & set(p["development_parent_seeds"]))
        self.assertEqual(p, freeze(self.root / "protocol"))

    def test_gap_without_ticks_and_single_tick_cannot_create_door(self):
        boxes = [
            {"type": "room", "bounds_px": [20, 20, 128, 236]},
            {"type": "room", "bounds_px": [128, 20, 236, 236]},
        ]
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (128, 20), (128, 236), 0, 3)
        cv2.line(gray, (128, 90), (128, 120), 255, 7)
        segments, _ = boundary_graph(boxes)
        for tick_count in (0, 1):
            if tick_count:
                cv2.line(gray, (120, 89), (136, 89), 0, 2)
            openings, diagnostics = opening_candidates(segments, gray)
            self.assertEqual(openings, [])
            self.assertTrue(diagnostics)

    def test_two_doors_are_distinct_and_require_two_regions(self):
        boxes = [
            {"type": "room", "bounds_px": [20, 20, 128, 236]},
            {"type": "room", "bounds_px": [128, 20, 236, 236]},
        ]
        gray = np.full((256, 256), 255, np.uint8)
        cv2.line(gray, (128, 20), (128, 236), 0, 3)
        for lo, hi in [(65, 89), (150, 174)]:
            cv2.line(gray, (128, lo), (128, hi), 255, 7)
            for y in (lo, hi):
                cv2.line(gray, (119, y), (137, y), 0, 2)
        proposals, _ = opening_candidates(boundary_graph(boxes)[0], gray)
        self.assertEqual(len(proposals), 2)
        proposals, _ = opening_candidates(boundary_graph(boxes[:1])[0], gray)
        self.assertEqual(proposals, [])

    @unittest.skipUnless(DEFAULT_LOCK.exists(), "Run the local training pilot first")
    def test_real_model_without_ocr_and_checksum_rejection(self):
        lock = json.loads(DEFAULT_LOCK.read_text())
        checkpoint = ROOT / lock["checkpoint_path"]
        if not checkpoint.exists():
            self.skipTest("Trained local checkpoint unavailable")
        try:
            import torch
        except ImportError:
            self.skipTest("Isolated PyTorch runtime unavailable")
        torch.set_num_threads(4)
        original_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name in (
                "SketchPipeline.perception.ocr",
                "SketchPipeline.perception.numeric",
                "rapidocr",
            ):
                raise AssertionError("Numeric OCR is forbidden in shape proposals")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guard):
            result = run(
                self.image,
                self.root / "learned",
                checkpoint=checkpoint,
                expected_sha256=lock["checkpoint_sha256"],
            )
        self.assertIsNone(result["failure"])
        self.assertEqual(result["model"]["checkpoint_sha256"], lock["checkpoint_sha256"])
        self.assertTrue((self.root / "learned/model-masks.npz").exists())
        self.assertEqual(validate_authoring(result["authoring"]), [])
        bad = run(
            self.image, self.root / "checksum", checkpoint=checkpoint, expected_sha256="0" * 64
        )
        self.assertEqual(bad["status"], "manual_required")
        self.assertIn("checksum mismatch", bad["failure"])

    def test_timeout_retains_image_and_explicit_failure(self):
        manager = ShapeJobs(self.root / "jobs", timeout=0.001)
        try:
            job = manager.start(self.image.read_bytes(), "drawing.png")
            state = wait(manager, job["job_id"])
            self.assertEqual(state["status"], "manual_required")
            self.assertIn("timeout", state["failure"])
            self.assertTrue(manager.image(job["job_id"]))
            self.assertEqual(manager.proposals(job["job_id"])["backend"], "manual")
        finally:
            manager.close()

    def test_worker_executable_unavailable_still_opens_manual_plan(self):
        manager = ShapeJobs(self.root / "jobs", python=str(self.root / "missing-python"))
        try:
            job = manager.start(self.image.read_bytes(), "drawing.png")
            state = wait(manager, job["job_id"])
            self.assertEqual(state["status"], "manual_required")
            self.assertIn("Worker unavailable", state["failure"])
            self.assertEqual(validate_authoring(manager.proposals(job["job_id"])["authoring"]), [])
        finally:
            manager.close()

    @unittest.skipUnless(DEFAULT_LOCK.exists(), "Run the local training pilot first")
    def test_refined_profile_uses_native_evidence_and_keeps_the_review_frame(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Isolated PyTorch runtime unavailable")
        torch.set_num_threads(4)
        result = run(self.image, self.root / "refined", profile="refined-full")
        self.assertIsNone(result["failure"])
        self.assertEqual(result["profile"], "refined-full")
        self.assertEqual(result["evidence_preprocessing"]["working_size_px"], [512, 512])
        self.assertEqual(result["authoring"]["image_evidence"]["working_size_px"], [256, 256])
        self.assertFalse(result["profile_configuration"]["human_automation_ready"])
        self.assertEqual(validate_authoring(result["authoring"]), [])
        self.assertTrue((self.root / "refined/evidence.png").exists())
        observed = result["diagnostics"][0].get("observed_rooms", {})
        self.assertEqual(
            len(result["alternatives"]), 0 if observed.get("status") == "proposed" else 2
        )

    @unittest.skipUnless(DEFAULT_LOCK.exists(), "Run the local training pilot first")
    def test_job_worker_propagates_and_persists_refined_profile(self):
        try:
            import torch
        except ImportError:
            self.skipTest("Isolated PyTorch runtime unavailable")
        manager = ShapeJobs(self.root / "jobs", profile="refined-full")
        try:
            record = manager.start(self.image.read_bytes(), "drawing.png")
            state = wait(manager, record["job_id"])
            self.assertEqual(state["profile"], "refined-full")
            result = manager.proposals(record["job_id"])
            self.assertEqual(result["profile"], "refined-full")
            self.assertIsNone(result["failure"])
            self.assertEqual(validate_authoring(result["authoring"]), [])
        finally:
            manager.close()

    def test_manual_authoring_saves_reopens_stable_ids_and_rejects_stale_edit(self):
        manager = ShapeJobs(self.root / "jobs")
        try:
            job = manager.start(self.image.read_bytes(), "drawing.png", "manual")
            identifier = job["job_id"]
            wait(manager, identifier)
            original = manager.proposals(identifier)["authoring"]
            boxes = [
                {"id": "my_room_a", "type": "room", "bounds_px": [20, 20, 128, 236]},
                {"id": "my_room_b", "type": "room", "bounds_px": [128, 20, 236, 236]},
            ]
            openings = [
                {
                    "id": "my_door",
                    "type": "door",
                    "entity_ids": ["my_room_a", "my_room_b"],
                    "points_px": [[128, 70], [128, 95]],
                }
            ]
            saved = manager.edit(
                identifier,
                {"base_revision_id": original["revision_id"], "boxes": boxes, "openings": openings},
            )
            self.assertEqual(validate_authoring(saved["authoring"]), [])
            self.assertEqual(
                {r["id"] for r in saved["authoring"]["topology"]["regions"]},
                {"my_room_a", "my_room_b"},
            )
            self.assertEqual(saved["authoring"]["topology"]["openings"][0]["id"], "my_door")
            self.assertEqual(
                saved["authoring"]["physical_design"]["acceptance"]["status"], "pending"
            )
            again = manager.edit(
                identifier,
                {
                    "base_revision_id": saved["authoring"]["revision_id"],
                    "boxes": list(reversed(boxes)),
                    "openings": openings,
                },
            )
            self.assertEqual(
                {w["id"] for w in saved["authoring"]["topology"]["walls"]},
                {w["id"] for w in again["authoring"]["topology"]["walls"]},
            )
            with self.assertRaises(ShapeJobError):
                manager.edit(
                    identifier, {"base_revision_id": original["revision_id"], "boxes": boxes}
                )
            with self.assertRaises(ShapeJobError):
                manager.retry(identifier)
        finally:
            manager.close()
        reopened = ShapeJobs(self.root / "jobs")
        try:
            self.assertEqual(reopened.proposals(identifier)["authoring"], again["authoring"])
        finally:
            reopened.close()

    def test_resize_retains_stale_opening_input_and_reports_conflict(self):
        manager = ShapeJobs(self.root / "jobs")
        try:
            j = manager.start(self.image.read_bytes(), "drawing.png", "manual")
            identifier = j["job_id"]
            wait(manager, identifier)
            base = manager.proposals(identifier)["authoring"]
            boxes = [
                {"id": "a", "type": "room", "bounds_px": [20, 20, 100, 236]},
                {"id": "b", "type": "room", "bounds_px": [128, 20, 236, 236]},
            ]
            openings = [
                {
                    "id": "door",
                    "type": "door",
                    "entity_ids": ["a", "b"],
                    "points_px": [[128, 70], [128, 95]],
                }
            ]
            saved = manager.edit(
                identifier,
                {"base_revision_id": base["revision_id"], "boxes": boxes, "openings": openings},
            )
            self.assertEqual(saved["edit_state"]["openings"], openings)
            self.assertEqual(len(saved["diagnostics"]), 1)
            self.assertEqual(saved["authoring"]["topology"]["openings"], [])
        finally:
            manager.close()

    def test_http_upload_token_and_editable_manual_job(self):
        manager = ShapeJobs(self.root / "jobs")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(url + "/api/bootstrap") as response:
                bootstrap = json.load(response)
            body = self.image.read_bytes()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url + "/shape-jobs", body, method="POST"))
            self.assertEqual(error.exception.code, 403)
            request = Request(
                url + "/shape-jobs",
                body,
                headers={
                    "X-Shape-Token": bootstrap["token"],
                    "X-File-Name": "drawing.png",
                    "X-Shape-Backend": "manual",
                },
                method="POST",
            )
            with urlopen(request) as response:
                job = json.load(response)
            wait(manager, job["job_id"])
            with urlopen(url + "/shape-jobs/" + job["job_id"] + "/proposals") as response:
                result = json.load(response)
            self.assertEqual(validate_authoring(result["authoring"]), [])
            with urlopen(url + "/shape-jobs/" + job["job_id"] + "/image") as response:
                self.assertEqual(response.headers["Content-Type"], "image/png")
        finally:
            server.shutdown()
            server.server_close()
            manager.close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
