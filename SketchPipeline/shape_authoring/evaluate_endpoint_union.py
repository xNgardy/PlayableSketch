import json, time
from pathlib import Path
import cv2, numpy as np, torch
from . import evaluate_task_ensemble as study
from .task_ensemble import decode
from .evaluate_unified_areas import cases
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary
from .contract import validate_authoring
from .synthetic import write_json
from .dino_model import ROOT, sha

OUT = ROOT / "Saved/ShapeFirst/task_ensemble/v3"
PREVIOUS = ROOT / "Saved/ShapeFirst/task_ensemble/v2"
NEW = ["dino_endpoint_union", "dino_roi_union", "unet256_endpoint_union"]


def main():
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    OUT.mkdir(parents=True, exist_ok=False)
    previous = json.loads((PREVIOUS / "report.json").read_text())
    protocol = json.loads((PREVIOUS / "protocol.json").read_text())
    old = json.loads((ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json").read_text())
    write_json(
        OUT / "protocol.json",
        {
            "version": "task-ensemble-union/1.0",
            "new_arms": NEW,
            "existing_arms_report_sha256": sha(PREVIOUS / "report.json"),
            "selection_rule": protocol["selection"],
            "scope": "Sequential development on previously inspected validation corpus; not blind. Endpoint union motivated by complementary validation peaks. No new training or model selection from test scores.",
            "source_sha256": sha(Path(__file__)),
            "training_run": False,
            "production_changed": False,
            "intermediate_map_precision": "Cached specialist maps are float16 restored to float32; active maps float32.",
        },
    )
    saved = []
    for i, (origin, sample, role, folder) in enumerate(cases()):
        r = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as z:
            geometry_maps = z["native_probabilities"]
        with np.load(folder / "native-auxiliary-masks.npz") as z:
            active = z["probabilities"][6]
        cached = ROOT / "Saved/ShapeFirst/task_ensemble/v1" / origin / sample / "ensemble-masks.npz"
        with np.load(cached) as z:
            specialist = z["specialist_endpoints"].astype(np.float32)
        with np.load(PREVIOUS / origin / sample / "roi-endpoints.npz") as z:
            roi = z["probability"].astype(np.float32)
        matrix = np.asarray(r["preprocessing"]["original_to_working"]) @ np.asarray(
            r["evidence_preprocessing"]["working_to_original"]
        )
        for arm in NEW:
            geometry = "unet256" if arm.startswith("unet") else "dino"
            p = json.loads((PREVIOUS / origin / sample / (geometry + "-geometry.json")).read_text())
            probability = np.maximum(active, roi if arm == "dino_roi_union" else specialist)
            start = time.perf_counter()
            doc, detail = decode(
                gray,
                geometry_maps,
                probability,
                r["authoring"]["image_evidence"]["source"],
                r["evidence_preprocessing"],
                working_gray=working,
                working_metadata=r["preprocessing"],
                evidence_to_working=matrix,
                geometry_result=(p["authoring"], p["decoder"]),
            )
            assert not validate_authoring(doc)
            dest = OUT / origin / sample / arm
            dest.mkdir(parents=True)
            write_json(
                dest / "prediction.json",
                {
                    "authoring": doc,
                    "diagnostics": {k: v for k, v in detail.items() if k != "geometry_decoder"},
                    "seconds": time.perf_counter() - start,
                    "geometry_source": str(
                        (PREVIOUS / origin / sample / (geometry + "-geometry.json")).relative_to(
                            ROOT
                        )
                    ),
                },
            )
        saved.append((origin, sample, role, r))
        if i % 20 == 0:
            print("predicted", i, sample, flush=True)

    def score_rows(items):
        rows = []
        for origin, sample, role, r in items:
            ref = (
                synthetic_reference(
                    ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json"
                )
                if origin == "synthetic"
                else reference(int(sample.split("_")[1]), r["preprocessing"])
            )
            for arm in NEW:
                pred = json.loads((OUT / origin / sample / arm / "prediction.json").read_text())
                doc = pred["authoring"]
                rows.append(
                    {
                        "sample_id": sample,
                        "origin": origin,
                        "role": role,
                        "arm": arm,
                        "status": (
                            "needs_attention" if doc["topology"]["regions"] else "manual_required"
                        ),
                        "elapsed_seconds": pred["seconds"],
                        "metrics": score(doc, ref, r["preprocessing"]["working_size_px"]),
                        "has_region_reference": bool(ref["regions"]),
                        "owner_reference_count": sum(
                            (bool(g["entity_ids"]) for g in ref["openings"])
                        ),
                        "area_iou": study.area_iou(doc, ref, r["preprocessing"]["working_size_px"]),
                    }
                )
        return rows

    validation = [
        v
        for v in saved
        if v[0] != "synthetic"
        and v[2] == "validation"
        or (v[0] == "synthetic" and v[1] in old["validation_synthetic_ids"])
    ]
    rows = score_rows(validation)
    summaries = json.loads((PREVIOUS / "selection.json").read_text())["validation_summary"]
    for arm in NEW:
        summaries[arm] = {
            g: study.summarize([r for r in rows if r["arm"] == arm and r["origin"] == g])
            for g in ["human", "new_human", "synthetic"]
        }
    chosen, candidates = study.select(summaries)
    write_json(
        OUT / "selection.json",
        {
            "selected": chosen,
            "candidates": candidates,
            "validation_summary": summaries,
            "test_used": False,
        },
    )
    print("selected", json.dumps(chosen), flush=True)
    rows = previous["rows"] + score_rows(saved)
    arms = list(summaries)
    aggregate = {
        a: {
            g: {
                role: study.summarize(
                    [r for r in rows if r["arm"] == a and r["origin"] == g and (r["role"] == role)]
                )
                for role in (
                    ["synthetic_control"] if g == "synthetic" else ["train", "validation", "test"]
                )
            }
            for g in ["human", "new_human", "synthetic"]
        }
        for a in arms
    }
    write_json(
        OUT / "report.json",
        {
            "case_count": len(saved),
            "summary": aggregate,
            "rows": rows,
            "selection": chosen,
            "model_promoted": False,
            "training_run": False,
            "test_used_for_selection": False,
            "control_predictions_root": str(PREVIOUS.relative_to(ROOT)),
        },
    )
    print("complete", len(saved), chosen["arm"], flush=True)


if __name__ == "__main__":
    main()
