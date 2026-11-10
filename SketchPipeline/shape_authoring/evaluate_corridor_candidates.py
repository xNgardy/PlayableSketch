import hashlib
import json
from pathlib import Path
from .experiment_corridor_recovery import run_case, ARMS, ROOT
from .model import LocalSegmenter
from .synthetic import write_json
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary


def main():
    output = ROOT / "Saved/ShapeFirst/corridor_recovery_experiment/v1/regression"
    output.mkdir(parents=True, exist_ok=False)
    study = ROOT / "Saved/ShapeFirst/dinov2/v1"
    protocol = json.loads((study / "protocol.json").read_text())
    lock = json.loads(
        (ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json").read_text()
    )
    adapter = LocalSegmenter(ROOT / lock["checkpoint_path"], lock["checkpoint_sha256"])
    paths = [
        Path(__file__).with_name(n)
        for n in [
            "corridor_candidates.py",
            "corridor_zoom.py",
            "experiment_corridor_recovery.py",
            "evaluate_corridor_candidates.py",
        ]
    ]
    write_json(
        output / "freeze.json",
        {
            "source_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
            },
            "checkpoint_sha256": lock["checkpoint_sha256"],
            "labels_used_for_prediction": False,
            "training_run": False,
            "scope": "Retrospective development comparison; deneme_1 used for policy development. No blind generalization claim.",
        },
    )
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    saved = []
    for folder in folders:
        origin = folder.parent.parent.name
        sample = folder.parent.name
        dest = output / origin / sample
        _, old = run_case(folder, dest, adapter)
        saved.append((origin, sample, dest, old))
        print("predicted", origin, sample, flush=True)
    rows = []
    for origin, sample, dest, old in saved:
        ref = (
            reference(int(sample.split("_")[1]), old["preprocessing"])
            if origin == "human"
            else synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
        )
        role = protocol["groups"][sample]["split"] if origin == "human" else "synthetic_control"
        for arm in ARMS:
            pred = json.loads((dest / (arm + ".json")).read_text())
            metrics = score(pred["authoring"], ref, old["preprocessing"]["working_size_px"])
            rows.append(
                {
                    "sample_id": sample,
                    "origin": origin,
                    "role": role,
                    "arm": arm,
                    "status": "needs_attention",
                    "elapsed_seconds": pred["summary"]["elapsed_decode_seconds"],
                    "metrics": metrics,
                    "has_region_reference": bool(ref["regions"]),
                    "owner_reference_count": sum((bool(o["entity_ids"]) for o in ref["openings"])),
                }
            )
    summaries = {
        arm: {
            role: summary([r for r in rows if r["arm"] == arm and r["role"] == role])
            for role in ["train", "validation", "test", "synthetic_control"]
        }
        for arm in ARMS
    }
    write_json(
        output / "report.json",
        {"case_count": len(saved), "summary": summaries, "rows": rows, "production_changed": False},
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    main()
