import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile
from SketchPipeline.shape_authoring.jobs import ShapeJobs, ShapeJobError
from SketchPipeline.shape_authoring.server import make_handler
from SketchPipeline.validation.validate import validate_document
from Scripts.start_runtime import local_service, launch_arguments


class DeliveryTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = ShapeJobs(self.root / "jobs")
        self.job = self.manager.sample()["job_id"]
        self.doc = self.manager.proposals(self.job)["authoring"]
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": None,
                "request": {},
            },
        )

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def confirm(self, mode="geometry_only"):
        workspace = self.manager.workspace(self.job)
        workspace = self.manager.save_workspace(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_workspace_revision_id": workspace["revision_id"],
                "state": {
                    "names": {"sample_west": "Studio"},
                    "start_room_id": "sample_west" if mode == "gameplay" else None,
                    "goal_room_id": "sample_east" if mode == "gameplay" else None,
                    "validation_mode": mode,
                },
            },
        )
        return self.manager.confirm_plan(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
                "base_workspace_revision_id": workspace["revision_id"],
            },
        )

    def export(self, confirmation):
        return self.manager.export_plan(
            self.job, {"confirmation_id": confirmation["confirmation_id"]}
        )

    def test_requires_exact_current_confirmation(self):
        with self.assertRaises(ShapeJobError):
            self.manager.export_plan(self.job, {"confirmation_id": "unapproved"})
        self.confirm()
        with self.assertRaises(ShapeJobError):
            self.manager.export_plan(self.job, {})

    def test_geometry_bundle_is_strict_validated_and_truthful(self):
        confirmed = self.confirm()
        record = self.export(confirmed)
        data = self.manager.export_bundle(self.job, record["revision_id"])
        canonical = self.manager.selected_layout(self.job, record["revision_id"])
        self.assertTrue(validate_document(canonical)["exportable"])
        self.assertEqual(canonical["validation_mode"], "geometry_only")
        self.assertEqual(
            canonical["observation_document_id"], confirmed["authoring"]["document_id"]
        )
        self.assertEqual(canonical["validation"]["engine_geometry"], "not_run")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"validated-layout.json", "authoring.json", "manifest.json", "README.txt"},
            )
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["automatic_training_ingestion"])
            self.assertEqual(
                archive.read("validated-layout.json"),
                self.manager.selected_layout_bytes(self.job, record["revision_id"]),
            )
            for file, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(file)).hexdigest(), digest)
        self.assertTrue(
            all(
                (
                    not x["provenance"]["evidence_ids"]
                    for group in canonical["layout"].values()
                    for x in group
                )
            )
        )

    def test_repeated_export_is_immutable_and_runtime_selected(self):
        c = self.confirm("gameplay")
        a = self.export(c)
        b = self.export(c)
        self.assertEqual(a, b)
        self.assertEqual(self.manager.runtime_selection()["revision_id"], a["revision_id"])
        status = self.manager.runtime_status(a["runtime_job_id"])
        self.assertEqual(status["state"], "exported")
        self.assertEqual(status["accepted_revision_id"], a["revision_id"])
        self.assertEqual(
            self.manager.selected_layout(self.job, a["revision_id"])["revision_id"],
            a["revision_id"] + "-accepted",
        )

    def test_mode_cannot_change_after_confirmation(self):
        c = self.confirm()
        with self.assertRaises(ShapeJobError):
            self.manager.export_plan(
                self.job, {"confirmation_id": c["confirmation_id"], "validation_mode": "gameplay"}
            )

    def test_geometry_only_allows_narrow_door_but_gameplay_rejects(self):
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
                "request": {
                    "edits": [
                        {
                            "entity_id": "sample_door_west",
                            "parameter": "clear_width_cm",
                            "value": 60,
                        }
                    ]
                },
            },
        )
        exported = self.export(self.confirm())
        old = (
            self.manager.folder(self.job)
            / "exports"
            / exported["revision_id"]
            / "validated-layout.json"
        ).read_bytes()
        with self.assertRaises(ShapeJobError):
            self.confirm("gameplay")
        self.assertEqual(
            (
                self.manager.folder(self.job)
                / "exports"
                / exported["revision_id"]
                / "validated-layout.json"
            ).read_bytes(),
            old,
        )

    def test_narrow_corridor_blocks_gameplay(self):
        self.sizing = self.manager.sizing(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_sizing_revision_id": self.sizing["authoring"]["revision_id"],
                "request": {
                    "edits": [{"entity_id": "sample_gallery", "parameter": "width_cm", "value": 80}]
                },
            },
        )
        self.assertEqual(self.sizing["status"], "ready")
        with self.assertRaises(ShapeJobError):
            self.confirm("gameplay")

    def test_sizing_tamper_without_revision_change_is_rejected(self):
        c = self.confirm()
        path = self.manager.folder(self.job) / "sizing-latest.json"
        s = json.loads(path.read_text())
        s["authoring"]["physical_design"]["values"][0]["value"] += 1
        path.write_text(json.dumps(s))
        with self.assertRaises(ShapeJobError):
            self.export(c)

    def test_source_and_bundle_checksum_tamper_are_rejected(self):
        c = self.confirm()
        e = self.export(c)
        path = self.manager.folder(self.job) / "exports" / e["revision_id"] / "unreal-bundle.zip"
        path.write_bytes(b"bad")
        with self.assertRaises(ShapeJobError):
            self.manager.export_bundle(self.job, e["revision_id"])
        source = self.manager.folder(self.job) / "source.png"
        source.write_bytes(b"changed")
        with self.assertRaises(ShapeJobError):
            self.export(c)

    def test_old_revision_rejected_after_edit_but_prior_files_retained(self):
        c = self.confirm()
        e = self.export(c)
        path = (
            self.manager.folder(self.job) / "exports" / e["revision_id"] / "validated-layout.json"
        )
        before = path.read_bytes()
        w = self.manager.workspace(self.job)
        self.manager.save_workspace(
            self.job,
            {
                "base_revision_id": self.doc["revision_id"],
                "base_workspace_revision_id": w["revision_id"],
                "state": {
                    "names": {"sample_east": "Changed"},
                    "start_room_id": None,
                    "goal_room_id": None,
                },
            },
        )
        with self.assertRaises(ShapeJobError):
            self.manager.selected_layout(self.job, e["revision_id"])
        self.assertEqual(path.read_bytes(), before)

    def test_restart_keeps_selected_snapshot_and_alias(self):
        c = self.confirm("gameplay")
        e = self.export(c)
        before = self.manager.selected_layout_bytes(self.job, e["revision_id"])
        self.manager.close()
        self.manager = ShapeJobs(self.root / "jobs")
        self.assertEqual(self.manager.selected_layout_bytes(self.job, e["revision_id"]), before)
        self.assertEqual(self.manager.resolve_runtime(e["runtime_job_id"]), self.job)

    def test_failed_archive_does_not_publish_partial_export(self):
        c = self.confirm()
        with patch(
            "SketchPipeline.shape_authoring.delivery.zipfile.ZipFile",
            side_effect=OSError("controlled archive failure"),
        ):
            with self.assertRaises(OSError):
                self.export(c)
        self.assertFalse((self.manager.folder(self.job) / "exports/index.json").exists())
        self.assertFalse((self.manager.root / "runtime-selection.json").exists())
        self.assertFalse(list(self.manager.folder(self.job).glob("export-staging-*")))

    def test_launcher_accepts_only_loopback_and_selects_without_pasting_ids(self):
        for value in [
            "https://127.0.0.1:8772",
            "http://example.com:8772",
            "http://127.0.0.1:8772/path",
        ]:
            with self.assertRaises(ValueError):
                local_service(value)
        e = self.export(self.confirm("gameplay"))
        args = launch_arguments(Path("runtime.app"), "http://127.0.0.1:8772", e)
        self.assertIn("-RuntimeJob=" + e["runtime_job_id"], args)
        self.assertIn("-RuntimeRevision=" + e["revision_id"], args)

    def test_delivery_http_download_and_runtime_protocol(self):
        c = self.confirm("gameplay")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_port}"
            with urlopen(root + "/api/bootstrap") as response:
                bootstrap = json.load(response)
            self.assertEqual(bootstrap["mode"], "shape-first/1.0")
            request = Request(
                root + f"/shape-jobs/{self.job}/export",
                data=json.dumps({"confirmation_id": c["confirmation_id"]}).encode(),
                headers={"Content-Type": "application/json", "X-Shape-Token": bootstrap["token"]},
            )
            with urlopen(request) as response:
                record = json.load(response)
            with urlopen(root + record["download_url"]) as response:
                self.assertEqual(
                    hashlib.sha256(response.read()).hexdigest(), record["bundle_sha256"]
                )
            with urlopen(root + "/jobs/" + record["runtime_job_id"]) as response:
                self.assertEqual(json.load(response)["accepted_revision_id"], record["revision_id"])
            with urlopen(
                root
                + "/jobs/"
                + record["runtime_job_id"]
                + "/layout?revision_id="
                + record["revision_id"]
            ) as response:
                self.assertEqual(
                    hashlib.sha256(response.read()).hexdigest(), record["canonical_sha256"]
                )
            with self.assertRaises(HTTPError) as error:
                urlopen(root + "/jobs/" + record["runtime_job_id"] + "/layout")
            self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
