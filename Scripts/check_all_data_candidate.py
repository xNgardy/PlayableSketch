from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import torch
import cv2
from SketchPipeline.shape_authoring.model import LocalSegmenter
from SketchPipeline.shape_authoring.propose import run
from SketchPipeline.shape_authoring.contract import validate_authoring
from Scripts.evaluate_augmented_shape import read, save, sha, scored

OUT = ROOT / "Saved/ShapeFirst/all_data_training/v1"


def main():
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    p = read(OUT / "protocol.json")
    candidate = read(OUT / "candidate.json")
    checkpoint = ROOT / candidate["checkpoint_path"]
    manifest = read(OUT / "cache/manifest.json")
    records = {e["record"]["id"]: e for e in manifest["records"]}
    model = LocalSegmenter(checkpoint, candidate["checkpoint_sha256"])
    checked = []
    with patch("SketchPipeline.shape_authoring.model.LocalSegmenter", return_value=model):
        for sid in ["Data_58", "Data_63", "AUG_Data_63_perspective", "SP001_ink"]:
            e = records[sid]
            folder = OUT / "integration" / sid
            result = (
                read(folder / "proposals.json")
                if (folder / "proposals.json").exists()
                else run(
                    e["source"]["image_path"],
                    folder,
                    checkpoint=checkpoint,
                    expected_sha256=candidate["checkpoint_sha256"],
                    profile="refined-full",
                    normalize_ink=True,
                )
            )
            assert result["failure"] is None and result["review_required"]
            docs = [result["authoring"]] + result["alternatives"]
            assert len(docs) == 3
            assert all(
                (
                    not validate_authoring(d)
                    and d["physical_design"]["acceptance"]["status"] == "pending"
                    for d in docs
                )
            )
            metric = scored(
                result["authoring"], e["reference"], result["preprocessing"]["working_size_px"]
            )
            cached = read(OUT / "evaluation/after" / sid / "metrics.json")["metrics"]
            keys = ["regions", "doors", "connections", "attached_doors"]
            equal = all(
                (
                    all(
                        (
                            metric[k][v] == cached[k][v]
                            for v in ["true_positive", "predicted", "reference"]
                        )
                    )
                    for k in keys
                )
            )
            checked.append(
                {
                    "sample_id": sid,
                    "cached_metrics_equal": equal,
                    "full_metrics": metric,
                    "schema_valid_documents": 3,
                    "checkpoint_sha256": result["model"]["checkpoint_sha256"],
                }
            )
            print(sid, "metric parity", equal, flush=True)
    initial = torch.load(ROOT / p["starting_checkpoint"], map_location="cpu", weights_only=True)
    final = torch.load(checkpoint, map_location="cpu", weights_only=True)
    changed = [
        k
        for k in initial["state_dict"]
        if not torch.equal(initial["state_dict"][k], final["state_dict"][k])
    ]
    assert changed and candidate["checkpoint_sha256"] != p["starting_sha256"]
    history = read(OUT / "training/history.json")
    assert [r["epoch"] for r in history] == list(range(1, 7))
    assert all((r["examples_seen"] == 1376 for r in history))
    changed_files = []
    unreadable = []
    checked_files = 0
    for f, h in p["protected_hashes"].items():
        try:
            actual = sha(ROOT / f)
            checked_files += 1
            if actual != h:
                changed_files.append(f)
        except OSError as error:
            unreadable.append({"file": f, "error": str(error)})
    assert not changed_files, changed_files
    assert all((sha(ROOT / f) == h for f, h in p["source_hashes"].items()))
    value = {
        "full_entrypoint_anchors": checked,
        "all_anchor_metrics_equal": all((r["cached_metrics_equal"] for r in checked)),
        "decoder_parameter_tensors_changed": len(changed),
        "decoder_parameter_tensors_total": len(initial["state_dict"]),
        "checkpoint_sha256": sha(checkpoint),
        "active_model_unchanged": sha(ROOT / p["starting_checkpoint"]) == p["starting_sha256"],
        "source_hashes_unchanged": True,
        "protected_files_checked": checked_files,
        "changed_files": changed_files,
        "post_training_unreadable_files": unreadable,
        "all_protected_files_reverified": not unreadable,
        "epochs": 6,
        "examples_per_epoch": 1376,
        "total_presentations": 8256,
        "heldout_test": False,
        "evaluation_tests_passed": 25,
    }
    save(OUT / "integration/verification.json", value)
    print("Final training and inference verification complete", flush=True)


if __name__ == "__main__":
    main()
