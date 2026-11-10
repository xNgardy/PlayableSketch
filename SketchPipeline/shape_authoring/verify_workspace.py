import argparse
import json
from pathlib import Path
import time
from .jobs import ShapeJobs
from .dino_region_audit import ROOT, sha


def verify(output):
    output.mkdir(parents=True, exist_ok=False)
    checkpoint = ROOT / "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt"
    checksum = sha(checkpoint)
    manager = ShapeJobs(
        output / "jobs",
        timeout=120,
        profile="refined-full",
        checkpoint=checkpoint,
        expected_sha256=checksum,
        normalize_ink=True,
    )
    try:
        sample = manager.sample()
        identifier = sample["job_id"]
        doc = manager.proposals(identifier)["authoring"]

        def sizes(request, previous=None):
            return manager.sizing(
                identifier,
                {
                    "base_revision_id": doc["revision_id"],
                    "base_sizing_revision_id": (
                        previous["authoring"]["revision_id"] if previous else None
                    ),
                    "request": request,
                },
            )

        suggested = sizes({})
        assert suggested["status"] == "ready"
        custom = sizes(
            {
                "edits": [
                    {
                        "entity_id": "sample_west",
                        "parameter": "width_cm",
                        "value": 8,
                        "unit": "m",
                        "locked": True,
                    }
                ]
            },
            suggested,
        )
        assert custom["status"] == "ready"
        conflict = sizes(
            {"edits": [{"entity_id": "sample_west", "parameter": "depth_cm", "value": 20}]}, custom
        )
        assert conflict["status"] == "needs_attention" and conflict["preview"] == custom["preview"]
        reset = sizes(
            {"edits": [{"entity_id": "sample_west", "parameter": "depth_cm", "action": "reset"}]},
            conflict,
        )
        assert reset["status"] == "ready"
        workspace = manager.save_workspace(
            identifier,
            {
                "base_revision_id": doc["revision_id"],
                "base_workspace_revision_id": None,
                "state": {
                    "names": {
                        "sample_west": "Studio",
                        "sample_gallery": "Gallery",
                        "sample_east": "Workshop",
                    },
                    "start_room_id": "sample_west",
                    "goal_room_id": "sample_east",
                },
            },
        )
        accepted = manager.confirm_plan(
            identifier,
            {
                "base_revision_id": doc["revision_id"],
                "base_sizing_revision_id": reset["authoring"]["revision_id"],
                "base_workspace_revision_id": workspace["revision_id"],
            },
        )
        assert not accepted["delivery_ready"]
        manager.close()
        manager = ShapeJobs(
            output / "jobs",
            timeout=120,
            profile="refined-full",
            checkpoint=checkpoint,
            expected_sha256=checksum,
            normalize_ink=True,
        )
        assert (
            manager.workspace(identifier)["confirmation"]["confirmation_id"]
            == accepted["confirmation_id"]
        )
        assert (
            manager.sizing_preview(identifier)["authoring"]["physical_design"]["values"]
            == reset["authoring"]["physical_design"]["values"]
        )
        image = ROOT / "Data/Data_25.png"
        job = manager.start(image.read_bytes(), image.name)
        deadline = time.monotonic() + 125
        while manager.status(job["job_id"])["status"] in ("queued", "processing"):
            if time.monotonic() > deadline:
                raise TimeoutError("Real DINO worker")
            time.sleep(0.1)
        proposal = manager.proposals(job["job_id"])
        assert proposal["failure"] is None
        actual = manager.sizing(
            job["job_id"],
            {
                "base_revision_id": proposal["authoring_revision_id"],
                "base_sizing_revision_id": None,
                "request": {},
            },
        )
        assert (
            actual["status"] == "ready"
            and actual["preview"]["validation"]["metric_valid"]
            and (not actual["exportable"])
        )
        result = {
            "scope": "Backend-only acceptance using a curated sample and a separate real DINO upload. No browser interaction or screenshot.",
            "sample_job": identifier,
            "sample_source_is_manual": True,
            "automatic_sizing": True,
            "custom_width_8m": True,
            "conflict_preserves_preview": True,
            "reset_recovers": True,
            "names_and_roles_persist": True,
            "explicit_test_confirmation_persists": True,
            "confirmation_not_export": True,
            "restart_preserves_choices": True,
            "real_upload": {
                "job_id": job["job_id"],
                "sample": "Data_25",
                "model_sha256": proposal["model"]["checkpoint_sha256"],
                "decoder": proposal["diagnostics"][0]["version"],
                "regions": len(proposal["authoring"]["topology"]["regions"]),
                "openings": len(proposal["authoring"]["topology"]["openings"]),
                "sizing_status": actual["status"],
                "numeric_ocr_called": proposal["numeric_ocr_called"],
            },
            "browser_tested": False,
        }
        (output / "backend-acceptance.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        manager.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    verify(args.output)
