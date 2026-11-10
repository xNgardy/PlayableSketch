import copy, json, time
from pathlib import Path
import cv2, numpy as np, torch
from .dino_model import ROOT, sha
from .model import LocalSegmenter
from .contrast import normalize_ink
from .evaluate_unified_areas import cases, area_iou
from .decoder_refined import decode as geometry_decode
from .task_ensemble import decode, POLICY, endpoint_tiles
from .contract import validate_authoring
from .synthetic import write_json
from .human_error_review import reference
from .pilot import score, synthetic_reference
from .evaluate_region_recovery import summary
from SketchPipeline.perception.structural import suppress_grid

OUT = ROOT / "Saved/ShapeFirst/task_ensemble/v2"
ARMS = [
    "baseline",
    "dino_specialist",
    "unet_dino",
    "unet_specialist",
    "fused_specialist",
    "supported_dino",
    "supported_dino_specialist",
    "unet256_specialist",
    "unet_multiscale_specialist",
    "dino_roi_specialist",
]


def reference_for(origin, sample, old):
    return (
        synthetic_reference(ROOT / "Saved/ShapeFirst/v1/development" / sample / "reference.json")
        if origin == "synthetic"
        else reference(int(sample.split("_")[1]), old["preprocessing"])
    )


def score_case(origin, sample, role, old):
    ref = reference_for(origin, sample, old)
    rows = []
    for arm in ARMS:
        path = OUT / origin / sample / arm / "prediction.json"
        pred = json.loads(path.read_text())
        doc = pred["authoring"]
        rows.append(
            {
                "sample_id": sample,
                "origin": origin,
                "role": role,
                "arm": arm,
                "status": "needs_attention" if doc["topology"]["regions"] else "manual_required",
                "elapsed_seconds": pred["seconds"],
                "metrics": score(doc, ref, old["preprocessing"]["working_size_px"]),
                "has_region_reference": bool(ref["regions"]),
                "owner_reference_count": sum((bool(g["entity_ids"]) for g in ref["openings"])),
                "area_iou": area_iou(doc, ref, old["preprocessing"]["working_size_px"]),
            }
        )
    return rows


def summarize(rows):
    out = summary(rows)
    values = [r["area_iou"] for r in rows if r["area_iou"] is not None]
    out["area_iou"] = float(np.mean(values)) if values else None
    return out


def validation_summary(rows):
    return {
        arm: {
            group: summarize([r for r in rows if r["arm"] == arm and r["origin"] == group])
            for group in ["human", "new_human", "synthetic"]
        }
        for arm in ARMS
    }


def select(summaries):
    base = summaries["baseline"]
    candidates = []
    for arm, value in summaries.items():
        checks = {}
        for group in ["human", "new_human", "synthetic"]:
            for key in ["regions", "doors", "attached_openings"]:
                checks[group + "_" + key] = (value[group][key]["f1"] or 0) >= (
                    base[group][key]["f1"] or 0
                ) - 0.02
            checks[group + "_connection_precision"] = (
                value[group]["attached_openings"]["precision"] or 0
            ) >= (base[group]["attached_openings"]["precision"] or 0) - 0.02
        checks["synthetic_false_connections"] = (
            value["synthetic"]["false_connections"] <= base["synthetic"]["false_connections"]
        )
        objective = sum(
            (
                weight
                * (
                    (value[group]["doors"]["f1"] or 0)
                    + (value[group]["attached_openings"]["f1"] or 0)
                )
                / 2
                for group, weight in [("human", 0.4), ("new_human", 0.4), ("synthetic", 0.2)]
            )
        )
        candidates.append(
            {
                "arm": arm,
                "eligible": all(checks.values()),
                "guards": checks,
                "objective": objective,
                "correct_doors": sum((value[g]["doors"]["true_positive"] for g in value)),
                "correct_connections": sum((value[g]["attachment_correct"] for g in value)),
            }
        )
    chosen = max(
        [c for c in candidates if c["eligible"]],
        key=lambda c: (c["objective"], c["arm"] == "baseline"),
    )
    return (chosen, candidates)


def main():
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    OUT.mkdir(parents=True, exist_ok=False)
    old_protocol = json.loads((ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json").read_text())
    unet_lock = json.loads((ROOT / "SketchPipeline/shape_authoring/models.lock.json").read_text())
    dino_lock = json.loads(
        (ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json").read_text()
    )
    specialist = ROOT / "Saved/ShapeFirst/dinov2/corridor_addon/v1/checkpoints/epoch_10.pt"
    inputs = list(cases())
    paths = [
        Path(__file__),
        Path(__file__).with_name("task_ensemble.py"),
        Path(__file__).with_name("decoder_refined.py"),
        Path(__file__).with_name("door_geometry.py"),
    ]
    protected = [
        ROOT / dino_lock["checkpoint_path"],
        ROOT / unet_lock["checkpoint_path"],
        specialist,
        ROOT / "SketchPipeline/shape_authoring/propose.py",
        ROOT / "SketchPipeline/shape_authoring/job_context.py",
    ]
    frozen = {
        "version": "task-ensemble-study/1.0",
        "date": "2026-11-05",
        "arms": ARMS,
        "policy": POLICY,
        "models": {
            "dino": dino_lock,
            "unet": unet_lock,
            "door_specialist": {
                "path": str(specialist.relative_to(ROOT)),
                "sha256": sha(specialist),
                "usage": "Only independent endpoint head, never its room geometry. Earlier full-model deployment was rejected.",
            },
        },
        "selection": "Old/new validation + six preassigned synthetic validation images only; balanced door/attachment F1. Region,door,attachment F1/precision drop <=.02; no additional synthetic false connections. Exact objective tie keeps baseline.",
        "scope": "Previously inspected same-writer development corpus; not blind. Different model weights and U-Net architecture, fixed shared DINO backbone for DINO-derived heads.",
        "validation_development": "Second protocol adds training-scale U-Net and image-selected native ROI endpoint views after v1 validation tie/regressions. Same development corpus; not blind.",
        "roi_policy": {
            "side_native": 256,
            "max_tiles": 8,
            "selection": "Shared predicted walls, then highest existing endpoint or wall midpoint; no labels.",
        },
        "training_run": False,
        "production_changed": False,
        "protected": {str(p.relative_to(ROOT)): sha(p) for p in protected},
        "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
    }
    write_json(OUT / "protocol.json", frozen)
    for path in paths:
        dest = OUT / "source_snapshot" / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
    unet = LocalSegmenter(ROOT / unet_lock["checkpoint_path"], unet_lock["checkpoint_sha256"])
    detector = LocalSegmenter(specialist, sha(specialist))
    saved = []
    for i, (origin, sample, role, folder) in enumerate(inputs):
        started = time.perf_counter()
        old = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as z:
            dino = z["native_probabilities"]
        with np.load(folder / "native-auxiliary-masks.npz") as z:
            active_endpoints = z["probabilities"][6]
        matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )
        clean, _, _ = suppress_grid(gray)
        if origin != "synthetic":
            a, _ = normalize_ink(
                gray, old["evidence_preprocessing"].get("diagnostic_content_bounds_px")
            )
            b, _ = normalize_ink(
                clean, old["evidence_preprocessing"].get("diagnostic_content_bounds_px")
            )
        else:
            a, b = (gray, clean)
        cached = ROOT / "Saved/ShapeFirst/task_ensemble/v1" / origin / sample / "ensemble-masks.npz"
        with np.load(cached) as z:
            unet_maps = z["unet"].astype(np.float32)
            endpoints = z["specialist_endpoints"].astype(np.float32)
        tick = time.perf_counter()
        small = unet.predict(
            cv2.resize(a, (256, 256), interpolation=cv2.INTER_AREA),
            cv2.resize(b, (256, 256), interpolation=cv2.INTER_AREA),
        )
        unet256 = np.stack(
            [
                cv2.resize(c, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
                for c in small
            ]
        )
        unet_seconds = time.perf_counter() - tick
        specialist_seconds = 0.0
        multiscale = (unet_maps + unet256) / 2
        dest = OUT / origin / sample
        dest.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            dest / "ensemble-masks.npz",
            unet=unet_maps.astype(np.float16),
            specialist_endpoints=endpoints.astype(np.float16),
        )
        fused = dino.copy()
        fused[:3] = 0.75 * dino[:3] + 0.25 * unet_maps[:3]
        geometries = {}
        for name, maps in [
            ("dino", dino),
            ("unet", unet_maps),
            ("fused", fused),
            ("unet256", unet256),
            ("unet_multiscale", multiscale),
        ]:
            doc, detail = geometry_decode(
                gray,
                maps,
                old["authoring"]["image_evidence"]["source"],
                old["evidence_preprocessing"],
                working_gray=working,
                working_metadata=old["preprocessing"],
                evidence_to_working=matrix,
                region_policy="supported-corridors",
                opening_policy="corridor-passages",
                door_policy="observed-jambs",
            )
            assert not validate_authoring(doc), (sample, name, validate_authoring(doc))
            geometries[name] = (doc, detail)
            write_json(dest / (name + "-geometry.json"), {"authoring": doc, "decoder": detail})
        baseline = geometries["dino"][0]
        tick = time.perf_counter()
        roi_endpoints, tiles = endpoint_tiles(
            geometries["dino"][1]["region_boxes"],
            gray,
            clean,
            detector,
            endpoints,
            np.linalg.inv(matrix),
        )
        specialist_seconds = time.perf_counter() - tick
        np.savez_compressed(
            dest / "roi-endpoints.npz", probability=roi_endpoints.astype(np.float16)
        )
        write_json(dest / "roi-views.json", tiles)
        for arm in ARMS:
            step = time.perf_counter()
            if arm == "baseline":
                doc = baseline
                detail = {}
                g = "dino"
            else:
                g = (
                    "unet256"
                    if arm.startswith("unet256")
                    else (
                        "unet_multiscale"
                        if arm.startswith("unet_multiscale")
                        else (
                            "unet"
                            if arm.startswith("unet_")
                            else "fused" if arm.startswith("fused") else "dino"
                        )
                    )
                )
                endpoint = (
                    roi_endpoints
                    if arm == "dino_roi_specialist"
                    else endpoints if "specialist" in arm else active_endpoints
                )
                support = unet_maps if arm.startswith("supported") else None
                doc, detail = decode(
                    gray,
                    {
                        "dino": dino,
                        "unet": unet_maps,
                        "fused": fused,
                        "unet256": unet256,
                        "unet_multiscale": multiscale,
                    }[g],
                    endpoint,
                    old["authoring"]["image_evidence"]["source"],
                    old["evidence_preprocessing"],
                    working_gray=working,
                    working_metadata=old["preprocessing"],
                    evidence_to_working=matrix,
                    consensus_probabilities=support,
                    geometry_result=geometries[g],
                )
            assert not validate_authoring(doc), (sample, arm, validate_authoring(doc))
            if arm == "dino_specialist":
                assert doc["topology"]["regions"] == baseline["topology"]["regions"]
            record = {
                "authoring": doc,
                "seconds": time.perf_counter() - step,
                "diagnostics": {k: v for k, v in detail.items() if k != "geometry_decoder"},
                "geometry_source": g,
                "endpoint_source": (
                    "full_epoch10_head6" if "specialist" in arm else "active_dino_head6"
                ),
                "shared_input_frame": True,
            }
            directory = dest / arm
            directory.mkdir()
            write_json(directory / "prediction.json", record)
        write_json(
            dest / "inference.json",
            {
                "source_folder": str(folder.relative_to(ROOT)),
                "unet_seconds": unet_seconds,
                "specialist_seconds": specialist_seconds,
                "total_seconds": time.perf_counter() - started,
            },
        )
        saved.append((origin, sample, role, old))
        if i % 5 == 0:
            print("predicted", i, sample, flush=True)
    validation_rows = []
    for origin, sample, role, old in saved:
        if (
            origin != "synthetic"
            and role == "validation"
            or (origin == "synthetic" and sample in old_protocol["validation_synthetic_ids"])
        ):
            validation_rows += score_case(origin, sample, role, old)
    summaries = validation_summary(validation_rows)
    chosen, candidates = select(summaries)
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
    rows = []
    for origin, sample, role, old in saved:
        rows += score_case(origin, sample, role, old)
    aggregate = {
        arm: {
            origin: {
                role: summarize(
                    [
                        r
                        for r in rows
                        if r["arm"] == arm and r["origin"] == origin and (r["role"] == role)
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
        for arm in ARMS
    }
    assert all((sha(ROOT / p) == h for p, h in frozen["protected"].items()))
    write_json(
        OUT / "report.json",
        {
            "case_count": len(saved),
            "summary": aggregate,
            "rows": rows,
            "selection": chosen,
            "model_promoted": False,
            "training_run": False,
            "protected_unchanged": True,
            "test_used_for_selection": False,
        },
    )
    print("complete", len(saved), chosen["arm"], flush=True)


if __name__ == "__main__":
    main()
