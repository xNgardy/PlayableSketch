import hashlib, json
from pathlib import Path
import cv2, numpy as np
from .dino_model import ROOT, sha
from .propose import run
from .human_supervision import source_image
from .decoder_refined import decode
from .door_geometry import POLICY
from .contract import validate_authoring
from .synthetic import write_json
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary, signature

OUT = ROOT / "Saved/ShapeFirst/door_geometry/v5/full"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    old = ROOT / "Saved/ShapeFirst/dinov2/v1"
    protocol = json.loads((old / "protocol.json").read_text())
    addon = json.loads((ROOT / "Data/synthetic/corridor_addon_v1/manifest.json").read_text())
    lock = json.loads(
        (ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json").read_text()
    )
    checkpoint = ROOT / lock["checkpoint_path"]
    paths = [
        Path(__file__).with_name(n)
        for n in ["door_geometry.py", "decoder_refined.py", "evaluate_door_geometry.py"]
    ]
    write_json(
        OUT / "freeze.json",
        {
            "policy": POLICY,
            "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
            "checkpoint_sha256": sha(checkpoint),
            "training_run": False,
            "scope": "Retrospective development comparison, policy developed on new validation photos. No blind claim; same masks and region geometry in both arms.",
        },
    )
    for path in paths:
        dst = OUT / "source_snapshot" / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(path.read_bytes())
    cases = []
    for folder in sorted((old / "evaluation/human").glob("Data_*/dino")):
        cases.append(
            ("human", folder.parent.name, protocol["groups"][folder.parent.name]["split"], folder)
        )
    for entry in addon["samples"]:
        if entry["origin"] != "human":
            continue
        sample = entry["id"]
        n = int(sample.split("_")[1])
        role = entry["split"]
        if role == "validation":
            folder = (
                ROOT / "Saved/ShapeFirst/dinov2/corridor_addon/v1/validation/epoch_0/new" / sample
            )
        elif role == "test":
            folder = (
                ROOT
                / "Saved/ShapeFirst/dinov2/corridor_addon/v1/reserved_evaluation_corrected/new_test"
                / sample
                / "baseline"
            )
        else:
            cached = ROOT / "Saved/ShapeFirst/door_geometry/v1/full/new_inputs" / sample
            if (cached / "proposals.json").exists():
                folder = cached
            else:
                folder = OUT / "new_inputs" / sample
                run(
                    source_image(n),
                    folder,
                    checkpoint=checkpoint,
                    expected_sha256=lock["checkpoint_sha256"],
                    profile="refined-full",
                    normalize_ink=True,
                )
        cases.append(("new_human", sample, role, folder))
    for folder in sorted((old / "evaluation/synthetic").glob("*/dino")):
        cases.append(("synthetic", folder.parent.name, "synthetic_control", folder))
    saved = []
    for i, (origin, sample, role, folder) in enumerate(cases):
        old_result = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as z:
            prob = z["native_probabilities"]
        matrix = np.asarray(old_result["preprocessing"]["original_to_working"]) @ np.asarray(
            old_result["evidence_preprocessing"]["working_to_original"]
        )
        for arm, policy in [("baseline", "legacy"), ("observed", "observed-jambs")]:
            doc, detail = decode(
                gray,
                prob,
                old_result["authoring"]["image_evidence"]["source"],
                old_result["evidence_preprocessing"],
                working_gray=working,
                working_metadata=old_result["preprocessing"],
                evidence_to_working=matrix,
                region_policy="supported-corridors",
                opening_policy="corridor-passages",
                door_policy=policy,
            )
            assert not validate_authoring(doc), (sample, arm)
            dest = OUT / origin / sample / arm
            dest.mkdir(parents=True)
            write_json(dest / "prediction.json", {"authoring": doc, "decoder": detail})
        saved.append((origin, sample, role, folder, old_result))
        if i % 10 == 0:
            print("predicted", i, sample, flush=True)
    rows = []
    changes = []
    for origin, sample, role, folder, old_result in saved:
        ref = (
            synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
            if origin == "synthetic"
            else reference(int(sample.split("_")[1]), old_result["preprocessing"])
        )
        docs = []
        for arm in ["baseline", "observed"]:
            doc = json.loads((OUT / origin / sample / arm / "prediction.json").read_text())[
                "authoring"
            ]
            docs.append(doc)
            rows.append(
                {
                    "sample_id": sample,
                    "origin": origin,
                    "role": role,
                    "arm": arm,
                    "status": "needs_attention",
                    "elapsed_seconds": 0.0,
                    "metrics": score(doc, ref, old_result["preprocessing"]["working_size_px"]),
                    "has_region_reference": bool(ref["regions"]),
                    "owner_reference_count": sum((bool(g["entity_ids"]) for g in ref["openings"])),
                }
            )
        if signature(docs[0]) != signature(docs[1]):
            changes.append({"origin": origin, "sample": sample, "role": role})
    summaries = {
        arm: {
            origin: {
                role: summary(
                    [
                        r
                        for r in rows
                        if r["origin"] == origin and r["role"] == role and (r["arm"] == arm)
                    ]
                )
                for role in (
                    ["synthetic_control"]
                    if origin == "synthetic"
                    else ["train", "validation", "test"]
                )
            }
            for origin in ["human", "new_human", "synthetic"]
        }
        for arm in ["baseline", "observed"]
    }
    report = {
        "case_count": len(saved),
        "summary": summaries,
        "rows": rows,
        "changed_cases": changes,
        "training_run": False,
        "region_geometry_frozen_between_arms": True,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps({"cases": len(saved), "changed": changes}), flush=True)


if __name__ == "__main__":
    main()
