from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from PIL import Image
from SketchPipeline.jobs import JobManager
from SketchPipeline.pipeline import analyze, configuration, verify_manifest
from SketchPipeline.review.metric_store import MetricReviewStore
from SketchPipeline.review.server import ReviewStore, ReviewError, make_handler
from SketchPipeline.tests.test_topology import perimeter
from SketchPipeline.tests.test_topology_review import state_with
from SketchPipeline.tests.test_metric_solver import dimension
from SketchPipeline.validation.validate import validate_document, load_json


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (220, 120), "white").save(stream, format="PNG")
    return stream.getvalue()


def wait_job(jobs, identifier):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = jobs.status(identifier)
        if result["state"] not in ("uploaded", "processing"):
            return result
        time.sleep(0.05)
    raise AssertionError("Job did not reach a terminal/review state")


def ready_state(store, jobs, identifier):
    revision = store.save(identifier, state_with(perimeter(10, 10, 110, 110)), None, "accept")
    loaded = jobs.metric.load(identifier)
    state = loaded["state"]
    rid = next(iter(state["bindings"]["region_kinds"]))
    state["bindings"]["dimensions"] = [
        dimension("width", {"type": "region_span", "region_id": rid, "axis": "x"}, 600),
        dimension("depth", {"type": "region_span", "region_id": rid, "axis": "y"}, 400),
    ]
    state["semantics_confirmed"] = True
    return state


class JobTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "run").mkdir()
        self.store = ReviewStore(self.root / "run", self.root / "review")
        self.metric = MetricReviewStore(self.store)
        self.jobs = JobManager(self.store, self.metric)
        self.store.jobs = self.jobs

    def tearDown(self):
        self.jobs.close()
        self.store.uploads.close()
        self.temp.cleanup()

    def start(self, **options):
        config = {"mode": "manual", **options}
        job = self.jobs.start(image_bytes(), "drawing.png", config)
        return (job, wait_job(self.jobs, job["job_id"]))

    def test_real_worker_atomic_artifacts_and_restart_registration(self):
        initial, finished = self.start()
        self.assertEqual(initial["state"], "uploaded")
        self.assertEqual(finished["state"], "needs_review")
        folder = self.jobs.root / initial["job_id"]
        manifest = verify_manifest(folder)
        self.assertEqual(manifest["execution_mode"], "manual")
        self.assertFalse((folder / "exports").exists())
        self.assertFalse(
            self.store.load(initial["job_id"])["analysis"]["validation"]["ready_to_review"]
        )
        self.jobs.close()
        other = ReviewStore(self.store.run, self.store.output)
        restored = JobManager(other, MetricReviewStore(other))
        try:
            self.assertIn(initial["job_id"], other.cases)
            self.assertEqual(restored.status(initial["job_id"])["state"], "needs_review")
        finally:
            restored.close()
            other.uploads.close()

    def test_selected_accept_export_and_correction_return_to_needs_review(self):
        _, job = self.start(settings={"wall_height_cm": 320, "door_height_cm": 210})
        identifier = job["job_id"]
        state = ready_state(self.store, self.jobs, identifier)
        self.assertEqual(state["bindings"]["settings"]["wall_height_cm"], 320)
        saved = self.metric.transact(identifier, None, "save", state)
        with self.assertRaises(ReviewError):
            self.jobs.export(identifier, saved["base_revision_id"])
        accepted = self.metric.transact(
            identifier, saved["base_revision_id"], "accept", reviewer="Controlled test"
        )
        self.assertEqual(self.jobs.status(identifier)["state"], "validated")
        layout = self.jobs.export(identifier, accepted["base_revision_id"])
        self.assertTrue(
            validate_document(
                layout, load_json(self.jobs.root / identifier / "prediction/observations.json")
            )["exportable"]
        )
        self.assertEqual(self.jobs.status(identifier)["state"], "exported")
        export_dir = self.jobs.root / identifier / "exports" / accepted["base_revision_id"]
        before = (export_dir / "manifest.json").read_bytes()
        self.assertEqual(self.jobs.export(identifier, accepted["base_revision_id"]), layout)
        self.assertEqual((export_dir / "manifest.json").read_bytes(), before)
        state["bindings"]["dimensions"][0]["value_cm"] = None
        state["bindings"]["dimensions"][0]["state"] = "missing"
        self.metric.transact(identifier, accepted["base_revision_id"], "save", state)
        self.assertEqual(self.jobs.status(identifier)["state"], "needs_review")
        with self.assertRaises(ReviewError):
            self.jobs.export(identifier, accepted["base_revision_id"])
        self.assertEqual((export_dir / "manifest.json").read_bytes(), before)

    def test_conflicts_do_not_enter_layout_endpoint(self):
        _, job = self.start()
        identifier = job["job_id"]
        state = ready_state(self.store, self.jobs, identifier)
        bad = deepcopy(state["bindings"]["dimensions"][0])
        bad.update(id="bad", value_cm=450)
        state["bindings"]["dimensions"].append(bad)
        saved = self.metric.transact(identifier, None, "save", state)
        self.assertEqual(saved["draft"]["status"], "conflicting")
        with self.assertRaises(ReviewError):
            self.jobs.export(identifier, saved["base_revision_id"])

    def test_explicit_cache_reuses_only_matching_intact_job(self):
        _, first = self.start()
        initial = self.jobs.start(
            image_bytes(), "again.png", {"mode": "manual", "cache_policy": "reuse_job"}
        )
        self.assertEqual(initial["job_id"], first["job_id"])
        self.assertTrue(initial["cache_hit"])
        _, fresh = self.start()
        self.assertNotEqual(fresh["job_id"], first["job_id"])
        self.assertEqual(
            self.jobs.jobs[first["job_id"]]["logical_id"],
            self.jobs.jobs[fresh["job_id"]]["logical_id"],
        )
        documents = []
        for job in (first, fresh):
            state = ready_state(self.store, self.jobs, job["job_id"])
            documents.append(
                self.metric.transact(job["job_id"], None, "save", state)["draft"]["document_id"]
            )
        self.assertEqual(*documents)
        _, changed = self.start(settings={"wall_height_cm": 350})
        self.assertNotEqual(changed["job_id"], first["job_id"])
        self.assertNotEqual(
            self.jobs.jobs[changed["job_id"]]["logical_id"],
            self.jobs.jobs[first["job_id"]]["logical_id"],
        )

    def test_changed_prediction_blocks_status_reuse_and_export(self):
        _, job = self.start()
        identifier = job["job_id"]
        path = self.jobs.root / identifier / "prediction/observations.json"
        path.write_text(path.read_text() + " ")
        self.assertEqual(self.jobs.status(identifier)["state"], "failed")
        with self.assertRaises(ReviewError):
            self.jobs.export(identifier, "metric-20261021T120000Z-123456789abc")

    def test_corrupt_inputs_rejected_without_partial_jobs(self):
        for data, name in ((b"no", "x.png"), (image_bytes(), "x.svg")):
            with self.assertRaises(ReviewError):
                self.jobs.start(data, name)
        self.assertEqual(self.jobs.jobs, {})
        for config in (
            [],
            {"timeout_seconds": True},
            {"settings": {"wall_height_cm": float("nan")}},
            {"mode": "replay"},
            {"extra": 1},
        ):
            with self.assertRaises(ValueError):
                configuration(config)

    def test_cancel_timeout_crash_retry_preserve_old_jobs(self):
        self.jobs.worker_command = lambda folder: [
            sys.executable,
            "-c",
            "import time;time.sleep(5)",
        ]
        job = self.jobs.start(image_bytes(), "slow.png", {"mode": "manual"})
        self.jobs.cancel(job["job_id"])
        self.assertEqual(wait_job(self.jobs, job["job_id"])["state"], "cancelled")
        self.jobs.worker_command = lambda folder: [sys.executable, "-c", "raise SystemExit(3)"]
        failed = self.jobs.retry(job["job_id"])
        result = wait_job(self.jobs, failed["job_id"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["parent_job_id"], job["job_id"])
        self.jobs.worker_command = lambda folder: [
            sys.executable,
            "-c",
            "import time;time.sleep(5)",
        ]
        timeout = self.jobs.start(
            image_bytes(), "timeout.png", {"mode": "manual", "timeout_seconds": 1}
        )
        result = wait_job(self.jobs, timeout["job_id"])
        self.assertEqual(result["stage"], "timeout")
        self.assertNotIn(timeout["job_id"], self.store.cases)
        self.jobs.worker_command = None
        retried = self.jobs.retry(timeout["job_id"])
        self.assertEqual(wait_job(self.jobs, retried["job_id"])["state"], "needs_review")
        self.assertEqual(self.jobs.status(timeout["job_id"])["state"], "failed")

    def test_cli_replay_is_explicit_and_hash_linked(self):
        _, job = self.start()
        source = self.jobs.root / job["job_id"] / "source.png"
        prediction = source.parent / "prediction"
        target = self.root / "replay"
        target.mkdir()
        shutil.copyfile(source, target / "source.png")
        report = analyze(target / "source.png", target, {"mode": "manual"}, replay=prediction)
        self.assertEqual(report["execution_mode"], "replay")
        self.assertTrue(report["replay_source_hashes"])
        self.assertFalse((target / "exports").exists())
        self.assertEqual(report["deferred_stages"]["solve"], "requires confirmed metric bindings")
        (target / "source.png").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            verify_manifest(target)

    def test_restart_marks_processing_interrupted(self):
        self.jobs.close()
        identifier = "Job_20261021T120000Z_123456789a"
        folder = self.jobs.root / identifier
        folder.mkdir()
        (folder / "job.json").write_text(json.dumps({"job_id": identifier, "state": "processing"}))
        manager = JobManager(self.store, self.metric)
        try:
            self.assertEqual(manager.status(identifier)["stage"], "interrupted")
        finally:
            manager.close()

    def test_multipart_job_api_and_readonly_manifest_routes(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(url + "/api/bootstrap") as response:
                token = json.load(response)["token"]
            boundary = "PipelineBoundary"
            body = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="config"\r\n\r\n{{"mode":"manual"}}\r\n--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="draw.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
                + image_bytes()
                + f"\r\n--{boundary}--\r\n".encode()
            )
            req = Request(
                url + "/jobs",
                data=body,
                headers={
                    "X-Review-Token": token,
                    "Content-Type": "multipart/form-data; boundary=" + boundary,
                },
            )
            with urlopen(req) as response:
                job = json.load(response)
                self.assertEqual(response.status, 202)
            identifier = job["job_id"]
            wait_job(self.jobs, identifier)
            for route in ("manifest", "evidence", "draft"):
                with urlopen(url + f"/jobs/{identifier}/{route}") as response:
                    self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as error:
                urlopen(url + f"/jobs/{identifier}/layout")
            self.assertEqual(error.exception.code, 409)
            with self.assertRaises(HTTPError) as error:
                urlopen(
                    Request(
                        url + "/jobs",
                        data=body,
                        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                    )
                )
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
