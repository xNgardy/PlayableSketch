import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from .decoder_refined import decode
from .contract import validate_authoring
from .synthetic import write_json
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary, signature

ROOT = Path(__file__).resolve().parents[2]


def predict(folder):
    old = json.loads((folder / "proposals.json").read_text())
    matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
        old["evidence_preprocessing"]["working_to_original"]
    )
    with np.load(folder / "model-masks.npz") as z:
        masks = z["native_probabilities"]
    doc, detail = decode(
        cv2.imread(str(folder / "evidence.png"), 0),
        masks,
        old["authoring"]["image_evidence"]["source"],
        old["evidence_preprocessing"],
        working_gray=cv2.imread(str(folder / "working.png"), 0),
        working_metadata=old["preprocessing"],
        evidence_to_working=matrix,
        opening_policy="corridor-passages",
        region_policy="supported-corridors",
    )
    assert not validate_authoring(doc)
    return (doc, detail, old)


def main():
    out = ROOT / "Saved/ShapeFirst/corridor_junctions/v1/regression"
    out.mkdir(parents=True, exist_ok=False)
    study = ROOT / "Saved/ShapeFirst/dinov2/v1"
    protocol = json.loads((study / "protocol.json").read_text())
    paths = [
        Path(__file__).with_name(n)
        for n in [
            "decoder_refined.py",
            "corridor_candidates.py",
            "corridor_junctions.py",
            "evaluate_corridor_junctions.py",
        ]
    ]
    freeze = {
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
        "scope": "Retrospective development evaluation; not blind. Cached model masks, no training or new inference.",
    }
    write_json(out / "freeze.json", freeze)
    for p in paths:
        dest = out / "source_snapshot" / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    saved = []
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    for folder in folders:
        origin = folder.parent.parent.name
        sample = folder.parent.name
        dest = out / origin / sample
        dest.mkdir(parents=True)
        doc, detail, old = predict(folder)
        write_json(dest / "prediction.json", {"authoring": doc, "decoder": detail})
        saved.append((origin, sample, dest, old))
    rows = []
    changed = []
    for origin, sample, dest, old in saved:
        ref = (
            reference(int(sample.split("_")[1]), old["preprocessing"])
            if origin == "human"
            else synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
        )
        role = protocol["groups"][sample]["split"] if origin == "human" else "synthetic_control"
        before = json.loads(
            (
                ROOT
                / "Saved/ShapeFirst/corridor_recovery_experiment/v1/regression"
                / origin
                / sample
                / "baseline.json"
            ).read_text()
        )["authoring"]
        after = json.loads((dest / "prediction.json").read_text())["authoring"]
        if signature(before) != signature(after):
            changed.append({"origin": origin, "sample": sample})
        for arm, doc in [("before", before), ("after", after)]:
            rows.append(
                {
                    "sample_id": sample,
                    "origin": origin,
                    "role": role,
                    "arm": arm,
                    "status": "needs_attention",
                    "elapsed_seconds": 0.0,
                    "metrics": score(doc, ref, old["preprocessing"]["working_size_px"]),
                    "has_region_reference": bool(ref["regions"]),
                    "owner_reference_count": sum((bool(o["entity_ids"]) for o in ref["openings"])),
                }
            )
    summaries = {
        arm: {
            role: summary([r for r in rows if r["arm"] == arm and r["role"] == role])
            for role in ["train", "validation", "test", "synthetic_control"]
        }
        for arm in ["before", "after"]
    }
    write_json(
        out / "report.json",
        {"case_count": len(saved), "changed_cases": changed, "summary": summaries, "rows": rows},
    )
    print(json.dumps({"case_count": len(saved), "changed_cases": changed, "summary": summaries}))


if __name__ == "__main__":
    main()
