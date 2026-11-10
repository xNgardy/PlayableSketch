import copy, json, time
from functools import partial
from pathlib import Path
import cv2, numpy as np
from .dino_model import ROOT, sha
from .unified_areas import decode, decode_observed, POLICY
from .contract import validate_authoring
from .synthetic import write_json
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary

OUT = ROOT / "Saved/ShapeFirst/unified_areas/v3/full"
PREVIOUS = ROOT / "Saved/ShapeFirst/door_geometry/v5/full"
ARMS = ["baseline", "rename_only", "unified_masks", "unified_sum", "observed_rectangles"]


def cases():
    old = ROOT / "Saved/ShapeFirst/dinov2/v1"
    p = json.loads((old / "protocol.json").read_text())
    for folder in sorted((old / "evaluation/human").glob("Data_*/dino")):
        yield ("human", folder.parent.name, p["groups"][folder.parent.name]["split"], folder)
    addon = json.loads((ROOT / "Data/synthetic/corridor_addon_v1/manifest.json").read_text())
    for e in addon["samples"]:
        if e["origin"] != "human":
            continue
        sample = e["id"]
        role = e["split"]
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
            folder = ROOT / "Saved/ShapeFirst/door_geometry/v1/full/new_inputs" / sample
        yield ("new_human", sample, role, folder)
    for folder in sorted((old / "evaluation/synthetic").glob("*/dino")):
        yield ("synthetic", folder.parent.name, "synthetic_control", folder)


def area_iou(document, ref, size):
    width, height = size
    masks = []
    for polygons in [
        [r["geometry"]["points_px"] for r in document["topology"]["regions"]],
        [
            (
                r["polygon"]
                if "polygon" in r
                else [
                    [r["bounds_px"][0], r["bounds_px"][1]],
                    [r["bounds_px"][2], r["bounds_px"][1]],
                    [r["bounds_px"][2], r["bounds_px"][3]],
                    [r["bounds_px"][0], r["bounds_px"][3]],
                ]
            )
            for r in ref["regions"]
        ],
    ]:
        mask = np.zeros((height, width), np.uint8)
        for polygon in polygons:
            cv2.fillPoly(mask, [np.rint(polygon).astype(np.int32)], 1)
        masks.append(mask > 0)
    union = (masks[0] | masks[1]).sum()
    return float((masks[0] & masks[1]).sum() / union) if union and ref["regions"] else None


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("unified_areas.py")]
    write_json(
        OUT / "freeze.json",
        {
            "policy": POLICY,
            "arms": ARMS,
            "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
            "weights_retrained": False,
            "production_changed": False,
            "labels_used_for_prediction": False,
            "scope": "Retrospective development comparison. Existing two semantic heads merged at inference, or observed-only enclosure geometry. Neither is retrained single-class segmentation.",
        },
    )
    for p in paths:
        dest = OUT / "source_snapshot" / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    saved = []
    for i, (origin, sample, role, folder) in enumerate(cases()):
        old = json.loads((folder / "proposals.json").read_text())
        m = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )
        with np.load(folder / "model-masks.npz") as z:
            prob = z["native_probabilities"]
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        baseline = json.loads((PREVIOUS / origin / sample / "observed/prediction.json").read_text())
        renamed = copy.deepcopy(baseline)
        for n, r in enumerate(renamed["authoring"]["topology"]["regions"], 1):
            r.update(type="room", name=f"Room {n}")
        predictions = {"baseline": baseline, "rename_only": renamed}
        for arm, fn in [
            ("unified_masks", decode),
            ("unified_sum", partial(decode, fusion="sum")),
            ("observed_rectangles", decode_observed),
        ]:
            started = time.perf_counter()
            doc, detail = fn(
                gray,
                prob,
                old["authoring"]["image_evidence"]["source"],
                old["evidence_preprocessing"],
                working_gray=working,
                working_metadata=old["preprocessing"],
                evidence_to_working=m,
            )
            predictions[arm] = {
                "authoring": doc,
                "decoder": detail,
                "seconds": time.perf_counter() - started,
            }
        for arm, prediction in predictions.items():
            assert not validate_authoring(prediction["authoring"]), (
                sample,
                arm,
                validate_authoring(prediction["authoring"]),
            )
            dest = OUT / origin / sample / arm
            dest.mkdir(parents=True)
            write_json(dest / "prediction.json", prediction)
        saved.append((origin, sample, role, old, folder))
        if i % 10 == 0:
            print("predicted", i, sample, flush=True)
    rows = []
    for origin, sample, role, old, folder in saved:
        ref = (
            synthetic_reference(
                ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
            )
            if origin == "synthetic"
            else reference(int(sample.split("_")[1]), old["preprocessing"])
        )
        for arm in ARMS:
            pred = json.loads((OUT / origin / sample / arm / "prediction.json").read_text())
            doc = pred["authoring"]
            row = {
                "sample_id": sample,
                "origin": origin,
                "role": role,
                "arm": arm,
                "status": "needs_attention" if doc["topology"]["regions"] else "manual_required",
                "elapsed_seconds": pred.get("seconds", 0.0),
                "metrics": score(doc, ref, old["preprocessing"]["working_size_px"]),
                "has_region_reference": bool(ref["regions"]),
                "owner_reference_count": sum((bool(o["entity_ids"]) for o in ref["openings"])),
                "area_iou": area_iou(doc, ref, old["preprocessing"]["working_size_px"]),
            }
            rows.append(row)
    summaries = {}
    for arm in ARMS:
        summaries[arm] = {}
        for origin in ["human", "new_human", "synthetic"]:
            selected = [r for r in rows if r["arm"] == arm and r["origin"] == origin]
            s = summary(selected)
            ious = [r["area_iou"] for r in selected if r["area_iou"] is not None]
            s["mean_area_iou"] = float(np.mean(ious)) if ious else None
            summaries[arm][origin] = s
    write_json(
        OUT / "report.json",
        {
            "case_count": len(saved),
            "summary": summaries,
            "rows": rows,
            "production_changed": False,
            "training_run": False,
            "reference_partition_not_changed": True,
        },
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    main()
