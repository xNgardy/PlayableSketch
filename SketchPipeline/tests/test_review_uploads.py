import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image
from SketchPipeline.perception.topology import build_topology
from SketchPipeline.review.server import ReviewError, ReviewStore, make_handler
from SketchPipeline.review.uploads import manual_prediction
from SketchPipeline.tests.test_topology import perimeter
from SketchPipeline.validation.validate import validate_document


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (220, 120), "white").save(stream, format="PNG")
    return stream.getvalue()


def fake_inference(image, output, adapter):
    manual_prediction(image, output, "test preparation")
    working = json.loads((output / "working.json").read_text())
    working.pop("prediction_status")
    (output / "working.json").write_text(json.dumps(working))
    topology = build_topology(perimeter(10, 10, 110, 110), [], (120, 220))
    (output / "topology.json").write_text(json.dumps(topology))


class UploadTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "run").mkdir()
        self.store = ReviewStore(self.root / "run", self.root / "reviews")
        self.store.uploads.adapter = object()

    def tearDown(self):
        self.store.uploads.close()
        self.temp.cleanup()

    def test_invalid_inputs_never_register_a_case(self):
        for data, name, status in [
            (b"not an image", "plan.png", 422),
            (png_bytes(), "plan.svg", 415),
            (b"", "plan.png", 413),
        ]:
            with self.subTest(name=name), self.assertRaises(ReviewError) as error:
                self.store.uploads.start(data, name)
            self.assertEqual(error.exception.status, status)
        self.assertEqual(self.store.cases, {})
        self.assertEqual(list(self.store.uploads.root.iterdir()), [])

    def test_inference_failure_still_opens_manual_review(self):
        with patch(
            "SketchPipeline.perception.run.run_single", side_effect=RuntimeError("OCR unavailable")
        ):
            job = self.store.uploads.start(png_bytes(), "blank.png")
            self.store.uploads.close()
        result = self.store.uploads.status(job["job_id"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["detection"], "manual")
        loaded = self.store.load(result["case_id"])
        self.assertEqual(loaded["state"], {"walls": [], "openings": []})
        self.assertEqual(loaded["status"], "unsaved")
        self.assertFalse(loaded["analysis"]["validation"]["ready_to_review"])
        prediction = self.store.uploads.root / job["job_id"] / "prediction"
        observations = json.loads((prediction / "observations.json").read_text())
        self.assertTrue(validate_document(observations)["schema_valid"])
        self.assertFalse(
            json.loads((prediction / "working.json").read_text())["training_performed"]
        )
        with self.assertRaises(ReviewError):
            self.store.save(result["case_id"], loaded["state"], None, "accept")
        self.assertIsNone(self.store.latest(result["case_id"]))

    def test_every_upload_starts_unreviewed_and_survives_restart(self):
        with patch("SketchPipeline.perception.run.run_single", side_effect=fake_inference):
            jobs = [self.store.uploads.start(png_bytes(), "../same drawing.png") for _ in range(2)]
            self.store.uploads.close()
        ids = [job["job_id"] for job in jobs]
        self.assertNotEqual(*ids)
        for identifier in ids:
            self.assertEqual(self.store.uploads.status(identifier)["detection"], "automatic")
            loaded = self.store.load(identifier)
            self.assertTrue(loaded["analysis"]["validation"]["ready_to_review"])
            self.assertEqual(loaded["status"], "unsaved")
            self.assertIsNone(self.store.latest(identifier))
            self.assertEqual(self.store.case(identifier)["label"], "same drawing.png")
        reviewed = self.store.save(ids[0], self.store.load(ids[0])["state"], None, "accept")
        restored = ReviewStore(self.store.run, self.store.output)
        try:
            self.assertEqual(restored.load(ids[0])["revision_id"], reviewed["revision_id"])
            self.assertEqual(restored.load(ids[1])["status"], "unsaved")
            self.assertEqual(restored.case(ids[1])["label"], "same drawing.png")
        finally:
            restored.uploads.close()

    def test_queue_is_bounded(self):
        entered, release = (threading.Event(), threading.Event())

        def waiting(image, output, adapter):
            entered.set()
            release.wait(5)
            fake_inference(image, output, adapter)

        try:
            with patch("SketchPipeline.perception.run.run_single", side_effect=waiting):
                self.store.uploads.start(png_bytes(), "one.png")
                self.assertTrue(entered.wait(3))
                self.store.uploads.start(png_bytes(), "two.png")
                self.store.uploads.start(png_bytes(), "three.png")
                with self.assertRaises(ReviewError) as error:
                    self.store.uploads.start(png_bytes(), "four.png")
                self.assertEqual(error.exception.status, 429)
                release.set()
                self.store.uploads.close()
        finally:
            release.set()

    def test_http_upload_requires_session_and_returns_review_case(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(base + "/api/bootstrap") as response:
                bootstrap = json.load(response)
            self.assertEqual(bootstrap["cases"], [])
            headers = {"Content-Type": "application/octet-stream", "X-File-Name": "plan%20test.png"}
            for extra in (
                {},
                {"X-Review-Token": bootstrap["token"], "Origin": "https://untrusted.example"},
            ):
                with self.assertRaises(HTTPError) as error:
                    urlopen(
                        Request(
                            base + "/api/upload", data=png_bytes(), headers={**headers, **extra}
                        )
                    )
                self.assertEqual(error.exception.code, 403)
            with patch("SketchPipeline.perception.run.run_single", side_effect=fake_inference):
                with urlopen(
                    Request(
                        base + "/api/upload",
                        data=png_bytes(),
                        headers={**headers, "X-Review-Token": bootstrap["token"]},
                    )
                ) as response:
                    self.assertEqual(response.status, 202)
                    job = json.load(response)
                self.store.uploads.close()
            with urlopen(base + "/api/upload-status?job=" + job["job_id"]) as response:
                completed = json.load(response)
            self.assertTrue(completed["requires_review"])
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/export?case=" + completed["case_id"])
            self.assertEqual(error.exception.code, 409)
            with urlopen(base + "/api/case?case=" + completed["case_id"]) as response:
                self.assertEqual(json.load(response)["status"], "unsaved")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
