from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.evaluate_augmented_shape import read, save, sha
from SketchPipeline.shape_authoring.contract import validate_authoring

OUT = ROOT / "Saved/ShapeFirst/all_data_training/v1"


def main():
    p = read(OUT / "protocol.json")
    r = read(OUT / "evaluation/report.json")
    candidate = read(OUT / "candidate.json")
    assert len(r["rows"]) == 2752
    before = {x["sample_id"] for x in r["rows"] if x["arm"] == "before"}
    after = {x["sample_id"] for x in r["rows"] if x["arm"] == "after"}
    assert before == after == {x["id"] for x in p["records"]}
    assert sha(ROOT / candidate["checkpoint_path"]) == candidate["checkpoint_sha256"]
    for row in r["rows"]:
        path = OUT / "evaluation" / row["arm"] / row["sample_id"] / "authoring.json"
        doc = read(path)
        assert not validate_authoring(doc), str(path)
        assert doc["physical_design"]["acceptance"]["status"] == "pending"
    changed = []
    unreadable = []
    checked = 0
    for f, h in p["protected_hashes"].items():
        try:
            actual = sha(ROOT / f)
            checked += 1
            if actual != h:
                changed.append(f)
        except OSError as e:
            unreadable.append({"file": f, "error": str(e)})
    assert not changed, changed
    assert all((sha(ROOT / f) == h for f, h in p["source_hashes"].items()))
    frozen = read(OUT / "evaluation_source_freeze.json")
    assert all((sha(ROOT / f) == h for f, h in frozen["source_hashes"].items()))
    parity = r["baseline_cached_vs_prior_full_entrypoint"]
    result = {
        "cases": 1376,
        "arms": 2,
        "documents_schema_valid": 2752,
        "pending_documents": 2752,
        "active_model_unchanged": sha(ROOT / p["starting_checkpoint"]) == p["starting_sha256"],
        "protected_files_checked": checked,
        "protected_changed": changed,
        "post_training_unreadable_files": unreadable,
        "protected_files_unchanged": True if not unreadable else None,
        "all_protected_files_reverified": not unreadable,
        "source_hashes_unchanged": True,
        "baseline_parity_equal": sum((x["all_five_metrics_equal"] for x in parity)),
        "baseline_parity_checked": len(parity),
        "all_examples_in_training": True,
        "heldout_test": False,
        "audit_note": "Initial full hash check succeeded before cache preparation. OS later prevented rereading listed JPEGs, including in an escalated read-only check. Training and evaluation used the initial verified cache. No claim of final hash verification is made for unreadable files.",
    }
    assert result["active_model_unchanged"]
    save(OUT / "evaluation/verification.json", result)
    print(
        {
            k: v
            for k, v in result.items()
            if k not in ["post_training_unreadable_files", "audit_note"]
        }
    )
    print("Post-training source rereads unavailable:", len(unreadable))


if __name__ == "__main__":
    main()
