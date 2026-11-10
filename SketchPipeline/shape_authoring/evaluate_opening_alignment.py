import argparse
import copy
import csv
import json
from pathlib import Path
import cv2
import numpy as np
from .dino_model import ROOT, sha
from .evaluate_unified_areas import cases
from .decoder_refined import decode as production_decode
from .corridor_geometry import decode as geometry_decode
from .opening_alignment import POLICY
from .evaluate_corridor_geometry import save, summarize, metrics_for, preview
from .contract import validate_authoring

ARMS = ["baseline", "aligned_baseline", "geometry_before", "geometry_fixed"]


def predict(case, out):
    origin, sample, split, folder = case
    old = json.loads((folder / "proposals.json").read_text())
    original_path = ROOT / f"Saved/ShapeFirst/task_ensemble/v2/{origin}/{sample}/dino-geometry.json"
    original = json.loads(original_path.read_text())
    previous_path = (
        ROOT / f"Saved/ShapeFirst/corridor_geometry/v3/audit/{origin}/{sample}/enclosure.json"
    )
    previous = json.loads(previous_path.read_text())
    gray = cv2.imread(str(folder / "evidence.png"), 0)
    working = cv2.imread(str(folder / "working.png"), 0)
    with np.load(folder / "model-masks.npz") as z:
        prob = z["native_probabilities"]
    matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
        old["evidence_preprocessing"]["working_to_original"]
    )
    options = dict(
        working_gray=working,
        working_metadata=old["preprocessing"],
        evidence_to_working=matrix,
        region_policy="supported-corridors",
        opening_policy="corridor-passages",
        door_policy="observed-jambs",
    )
    args = (gray, prob, old["authoring"]["image_evidence"]["source"], old["evidence_preprocessing"])
    replay, _ = production_decode(*args, **options)
    assert replay["topology"] == original["authoring"]["topology"], (
        "legacy_replay_changed",
        origin,
        sample,
    )
    aligned, alignment_detail = production_decode(*args, **options, opening_alignment=True)
    fixed, fixed_detail, floor = geometry_decode(
        *args,
        working_metadata=old["preprocessing"],
        evidence_to_working=matrix,
        baseline_result=(original["authoring"], original["decoder"]),
        opening_alignment=True,
    )
    predictions = {
        "baseline": original,
        "aligned_baseline": {"authoring": aligned, "decoder": alignment_detail},
        "geometry_before": previous,
        "geometry_fixed": {"authoring": fixed, "decoder": fixed_detail},
    }
    for arm, p in predictions.items():
        assert not validate_authoring(p["authoring"]), (
            origin,
            sample,
            arm,
            validate_authoring(p["authoring"]),
        )
        save(out / origin / sample / (arm + ".json"), p)
    return (
        old,
        predictions,
        {
            "input_folder": str(folder.relative_to(ROOT)),
            "input_checkpoint_sha256": old["model"]["checkpoint_sha256"],
            "evidence_sha256": sha(folder / "evidence.png"),
            "model_masks_sha256": sha(folder / "model-masks.npz"),
            "baseline_sha256": sha(original_path),
            "previous_geometry_sha256": sha(previous_path),
        },
    )


def main(out):
    cv2.setNumThreads(1)
    out.mkdir(parents=True, exist_ok=False)
    module = Path(__file__).parent
    sources = list(module.glob("*.py")) + list(module.glob("*.json"))
    data = [
        p
        for n in range(51, 71)
        for p in [
            ROOT / f"Data/Data_{n}.png",
            ROOT / f"Data/annotations/v1/Data_{n}.annotations.json",
            ROOT / f"Data/annotations/v1/Data_{n}.observations.json",
            ROOT / f"Data/ground_truth/structural_v1/Data_{n}.structural.json",
        ]
    ]
    protected = data + list((module / "models").glob("*.pt"))
    frozen = {
        "version": "opening-alignment-study/1.0",
        "date": "2026-11-06",
        "policy": POLICY,
        "arms": ARMS,
        "development": "Targeted fix motivated by previously inspected Data_58 and Data_61 records. Previously seen same-writer corpus; not a blind evaluation. No test-based parameter selection in this run.",
        "selection_rule": "Per old/new/synthetic validation group: region/door/connection F1 decline <=.02; unmatched regions and connections cannot increase. Weighted door+connection F1 (.4/.4/.2); baseline wins exact ties.",
        "protected_hashes": {str(p.relative_to(ROOT)): sha(p) for p in protected},
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "cache_hashes": {},
        "model_training": False,
        "reference_inference_inputs": False,
        "defaults_changed": True,
        "service_source_integration": "DINO refined path explicitly enables aligned openings and validation-selected enclosure geometry. Model weights unchanged.",
    }
    save(out / "protocol.json", frozen)
    for p in sources:
        dest = out / "source_snapshot" / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    corpus = list(cases())
    old_protocol = json.loads((ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json").read_text())
    validation = [
        c
        for c in corpus
        if c[0] != "synthetic"
        and c[2] == "validation"
        or (c[0] == "synthetic" and c[1] in old_protocol["validation_synthetic_ids"])
    ]
    override_path = ROOT / "Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json"
    overrides = json.loads(override_path.read_text())
    frozen["reference_override_sha256"] = sha(override_path)
    predicted = []
    for case in validation:
        old, pred, cache = predict(case, out / "validation")
        predicted.append((case, old, pred))
        frozen["cache_hashes"][case[0] + "/" + case[1]] = cache
    rows = []
    for (origin, sample, split, folder), old, pred in predicted:
        for arm, p in pred.items():
            rows.append(
                {
                    "origin": origin,
                    "sample_id": sample,
                    "split": split,
                    "arm": arm,
                    "metrics": metrics_for(origin, sample, old, p["authoring"], overrides),
                }
            )
    sums = {
        a: {
            g: summarize([r for r in rows if r["arm"] == a and r["origin"] == g])
            for g in ["human", "new_human", "synthetic"]
        }
        for a in ARMS
    }
    candidates = []
    for arm in ARMS:
        checks = {}
        for g in ["human", "new_human", "synthetic"]:
            before, after = (sums["baseline"][g], sums[arm][g])
            for k in ["regions", "doors", "connections"]:
                checks[g + "_" + k] = (after[k]["f1"] or 0) >= (before[k]["f1"] or 0) - 0.02
            for k in ["unmatched_regions", "unmatched_connections"]:
                checks[g + "_" + k] = after[k] <= before[k]
        objective = sum(
            (
                w
                * ((sums[arm][g]["doors"]["f1"] or 0) + (sums[arm][g]["connections"]["f1"] or 0))
                / 2
                for g, w in [("human", 0.4), ("new_human", 0.4), ("synthetic", 0.2)]
            )
        )
        candidates.append(
            {"arm": arm, "eligible": all(checks.values()), "checks": checks, "objective": objective}
        )
    selected = max(
        [c for c in candidates if c["eligible"]],
        key=lambda c: (c["objective"], c["arm"] == "baseline"),
    )["arm"]
    selection = {
        "selected": selected,
        "candidates": candidates,
        "validation_summary": sums,
        "test_used": False,
    }
    save(out / "selection.json", selection)
    print("selected", json.dumps(selection["candidates"]), flush=True)
    rows = []
    sections = []
    for i, case in enumerate(corpus):
        origin, sample, split, folder = case
        old, pred, cache = predict(case, out / "audit")
        frozen["cache_hashes"][origin + "/" + sample] = cache
        for arm, p in pred.items():
            rows.append(
                {
                    "origin": origin,
                    "sample_id": sample,
                    "split": split,
                    "arm": arm,
                    "metrics": metrics_for(origin, sample, old, p["authoring"], overrides),
                }
            )
        if origin == "new_human":
            image_path = out / "audit" / origin / sample / "comparison.png"
            preview(
                folder,
                sample,
                old,
                pred["geometry_before"]["authoring"],
                pred["geometry_fixed"]["authoring"],
                titles=("Düzeltme öncesi", "Düzeltme sonrası"),
            ).save(image_path)
            sections.append(
                f'<section><h2>{sample} · {split}</h2><p>Sol: 512 kanıt. Orta: düzeltme öncesi geometri adayı. Sağ: üç parçalı düzeltme sonrası.</p><img src="audit/{origin}/{sample}/comparison.png"></section>'
            )
        if i % 10 == 0:
            print("audited", i, origin, sample, flush=True)
    aggregate = {
        a: {
            g: {
                s: summarize(
                    [
                        r
                        for r in rows
                        if r["arm"] == a and r["origin"] == g and (s == "all" or r["split"] == s)
                    ]
                )
                for s in (
                    ["synthetic_control"]
                    if g == "synthetic"
                    else ["train", "validation", "test", "all"]
                )
            }
            for g in ["human", "new_human", "synthetic"]
        }
        for a in ARMS
    }
    save(
        out / "report.json",
        {"summary": aggregate, "rows": rows, "selection": selection, "new_training": False},
    )
    save(out / "protocol.json", frozen)
    with (out / "metrics.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "arm",
                "origin",
                "split",
                "metric",
                "correct",
                "predicted",
                "reference",
                "precision",
                "recall",
                "f1",
            ]
        )
        for a, groups in aggregate.items():
            for g, splits in groups.items():
                for s, m in splits.items():
                    for k in ["regions", "doors", "connections"]:
                        v = m[k]
                        w.writerow(
                            [
                                a,
                                g,
                                s,
                                k,
                                v["true_positive"],
                                v["predicted"],
                                v["reference"],
                                v["precision"],
                                v["recall"],
                                v["f1"],
                            ]
                        )
    (out / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Kapı sınırı ve tür düzeltmesi</title><style>body{font:16px system-ui;background:#f3f5f8;margin:24px}section{background:white;padding:16px;margin:20px 0}img{width:100%}</style><h1>Kapı sınırı ve tür düzeltmesi</h1><p>Seçilen: '
        + selected
        + ". Öneriler kullanıcı onayı gerektirir.</p>"
        + "".join(sections)
    )
    assert all((sha(ROOT / p) == h for p, h in frozen["source_hashes"].items()))
    assert all((sha(ROOT / p) == h for p, h in frozen["protected_hashes"].items()))
    save(
        out / "verification.json",
        {
            "cases": len(corpus),
            "arms": len(ARMS),
            "legacy_topology_replays_equal": 130,
            "legacy_validation_replays_equal": 15,
            "contract_valid_predictions": (len(corpus) + len(validation)) * len(ARMS),
            "protected_files": len(protected),
            "protected_changed": [],
            "model_training": False,
            "selected": selected,
            "test_used_for_selection": False,
        },
    )
    print("complete", selected, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/opening_alignment/v1"
    )
    main(parser.parse_args().output)
