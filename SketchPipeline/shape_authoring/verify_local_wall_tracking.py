import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import cv2
import numpy as np
from .decoder_refined import decode
from .evaluate_region_recovery import signature
from .contract import validate_authoring
from .dino_region_audit import ROOT, sha
from .jobs import ShapeJobs
from .synthetic import write_json


def verify(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    study = ROOT / "Saved/ShapeFirst/dinov2/v1"
    frozen = ROOT / "Saved/ShapeFirst/dinov2/opening_ablation/v1/full"
    paths = [
        "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt",
        "SketchPipeline/shape_authoring/models.lock.json",
        "SketchPipeline/shape_authoring/decoder.py",
    ]
    protected = {p: sha(ROOT / p) for p in paths}
    inputs = {}
    replays = []
    for folder in sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    ):
        category = folder.parent.parent.name
        sample = folder.parent.name
        for name in ["model-masks.npz", "working.png", "evidence.png", "proposals.json"]:
            inputs[str((folder / name).relative_to(ROOT))] = sha(folder / name)
        old = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as f:
            native = f["native_probabilities"]
        matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )
        kwargs = dict(
            working_gray=working, working_metadata=old["preprocessing"], evidence_to_working=matrix
        )
        args = (
            gray,
            native,
            old["authoring"]["image_evidence"]["source"],
            old["evidence_preprocessing"],
        )
        legacy, legacy_detail = decode(*args, **kwargs)
        current, detail = decode(*args, **kwargs, opening_policy="local-tracking")
        expected = json.loads(
            (frozen / category / sample / "B_tracking/prediction.json").read_text()
        )["authoring"]
        control = json.loads((frozen / category / sample / "control/prediction.json").read_text())[
            "authoring"
        ]
        assert signature(legacy) == signature(control), sample + " legacy changed"
        assert signature(current) == signature(expected), sample + " B integration changed"
        assert not validate_authoring(current), sample
        assert detail["version"] == "shape-decoder/2.5"
        replays.append(
            {
                "sample": sample,
                "legacy_equals_frozen_control": True,
                "integrated_equals_frozen_B": True,
                "contract_valid": True,
            }
        )
    write_json(output / "replay.json", replays)
    write_json(output / "input-freeze.json", inputs)
    manager = ShapeJobs(
        output / "jobs",
        timeout=120,
        profile="refined-full",
        checkpoint=ROOT / paths[0],
        expected_sha256=protected[paths[0]],
        normalize_ink=True,
    )
    workers = []
    try:
        for n in [23, 25, 31]:
            job = manager.start((ROOT / f"Data/Data_{n}.png").read_bytes(), f"Data_{n}.png")
            deadline = time.monotonic() + 125
            while manager.status(job["job_id"])["status"] in ("queued", "processing"):
                if time.monotonic() > deadline:
                    raise TimeoutError("Worker " + str(n))
                time.sleep(0.1)
            status = manager.status(job["job_id"])
            result = manager.proposals(job["job_id"])
            assert result["failure"] is None, status
            expected = json.loads(
                (frozen / f"human/Data_{n}/B_tracking/prediction.json").read_text()
            )["authoring"]
            assert signature(result["authoring"]) == signature(expected), n
            assert result["profile_configuration"]["opening_policy"] == "local-tracking"
            assert result["diagnostics"][0]["version"] == "shape-decoder/2.5"
            assert (
                not result["numeric_ocr_called"]
                and result["authoring"]["physical_design"]["acceptance"]["status"] == "pending"
            )
            folder = output / "jobs" / job["job_id"] / status["output_directory"]
            with np.load(folder / "model-masks.npz") as f:
                actual = f["native_probabilities"]
            with np.load(study / f"evaluation/human/Data_{n}/dino/model-masks.npz") as f:
                previous = f["native_probabilities"]
            difference = float(np.max(np.abs(actual - previous)))
            assert difference == 0.0, difference
            workers.append(
                {
                    "sample": f"Data_{n}",
                    "job_id": job["job_id"],
                    "openings": len(result["authoring"]["topology"]["openings"]),
                    "matches_frozen_B": True,
                    "max_native_mask_difference": difference,
                    "acceptance": "pending",
                    "numeric_ocr_called": False,
                    "decoder_version": "shape-decoder/2.5",
                }
            )
            write_json(output / "worker-smoke.json", workers)
            print(json.dumps(workers[-1]), flush=True)
    finally:
        manager.close()
    changed = [p for p, h in {**protected, **inputs}.items() if sha(ROOT / p) != h]
    assert not changed, changed
    sources = [
        Path(__file__),
        Path(__file__).with_name("local_wall_tracking.py"),
        Path(__file__).with_name("decoder_refined.py"),
        Path(__file__).with_name("propose.py"),
    ]
    for source in sources:
        dest = output / "source_snapshot" / source.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, dest)
    write_json(
        output / "verification.json",
        {
            "cached_replays": len(replays),
            "all_match_frozen_B": True,
            "legacy_control_unchanged": True,
            "real_workers": workers,
            "protected_files_unchanged": protected,
            "cached_files_checked": len(inputs),
            "changed": changed,
            "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
            "browser_tested": False,
            "default_model_promoted": False,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    verify(args.output)
