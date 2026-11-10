import argparse
import copy
import csv
import json
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .dino_model import ROOT, sha
from .corridor_geometry import decode, POLICY
from .evaluate_unified_areas import cases
from .diagnose_new20 import reference as new_reference, evaluate, FONT
from .human_error_review import reference as old_reference
from .pilot import score, synthetic_reference
from .contract import validate_authoring
from SketchPipeline.evaluation.metrics import counts

ARMS = ["baseline", "enclosure", "hybrid"]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
            default=lambda x: x.item() if isinstance(x, np.generic) else x,
        )
    )


def summarize(rows):
    result = {"samples": len(rows)}
    for key in ["regions", "doors", "connections"]:
        metrics = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        result[key] = counts(
            sum((m["true_positive"] for m in metrics)),
            sum((m["predicted"] for m in metrics)),
            sum((m["reference"] for m in metrics)),
        )
        result[key]["scorable_samples"] = len(metrics)
    result["unmatched_connections"] = (
        result["connections"]["predicted"] - result["connections"]["true_positive"]
    )
    result["unmatched_regions"] = (
        result["regions"]["predicted"] - result["regions"]["true_positive"]
    )
    return result


def metrics_for(origin, sample, old, document, overrides):
    if origin == "new_human":
        ref, _ = new_reference(int(sample.split("_")[1]), old["preprocessing"], overrides)
        return evaluate(document, ref, old["preprocessing"]["working_size_px"])
    ref = (
        old_reference(int(sample.split("_")[1]), old["preprocessing"])
        if origin == "human"
        else synthetic_reference(ROOT / f"Saved/ShapeFirst/v1/development/{sample}/reference.json")
    )
    result = score(document, ref, old["preprocessing"]["working_size_px"])
    result["connections"] = counts(
        result["attachment_correct"],
        len(document["topology"]["openings"]),
        sum((bool(g["entity_ids"]) for g in ref["openings"])),
    )
    result["connection_unit"] = (
        "Opening-level attached connection; old approximate owners / synthetic explicit owners. New human metric uses unique region pairs."
    )
    return result


def preview(
    folder, sample, old, baseline, candidate, titles=("Mevcut yöntem", "Deneysel geometri adayı")
):
    gray = cv2.imread(str(folder / "evidence.png"), 0)
    to_work = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
        old["evidence_preprocessing"]["working_to_original"]
    )
    inverse = np.linalg.inv(to_work)
    font = ImageFont.truetype(FONT, 17)
    canvas = Image.new("RGB", (1536, 560), "#f4f6f8")
    for k, (doc, title) in enumerate(
        [(None, "512 kanıt"), (baseline, titles[0]), (candidate, titles[1])]
    ):
        image = Image.fromarray(gray).convert("RGB")
        d = ImageDraw.Draw(image)

        def project(points):
            p = np.c_[np.asarray(points), np.ones(len(points))] @ inverse.T
            return [tuple(v) for v in p[:, :2] / p[:, 2:]]

        if doc:
            for r in doc["topology"]["regions"]:
                p = project(r["geometry"]["points_px"])
                color = "#2563eb" if r["type"] == "room" else "#c2410c"
                d.line(p + [p[0]], fill=color, width=2)
            for o in doc["topology"]["openings"]:
                d.line(
                    project(o["geometry"]["points_px"]),
                    fill="#16a34a" if o["type"] == "door" else "#7c3aed",
                    width=3,
                )
        image = image.resize((512, 512))
        canvas.paste(image, (k * 512, 40))
        ImageDraw.Draw(canvas).text((k * 512 + 10, 10), title, font=font, fill="#111827")
    return canvas


def predict_case(case, output, arms):
    origin, sample, split, folder = case
    old = json.loads((folder / "proposals.json").read_text())
    base_path = ROOT / f"Saved/ShapeFirst/task_ensemble/v2/{origin}/{sample}/dino-geometry.json"
    base = json.loads(base_path.read_text())
    baseline = base["authoring"]
    gray = cv2.imread(str(folder / "evidence.png"), 0)
    with np.load(folder / "model-masks.npz") as z:
        prob = z["native_probabilities"]
    matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
        old["evidence_preprocessing"]["working_to_original"]
    )
    records = {}
    for arm in arms:
        start = time.perf_counter()
        if arm == "baseline":
            document, detail = (copy.deepcopy(baseline), {"cached": True})
        else:
            document, detail, floor = decode(
                gray,
                prob,
                old["authoring"]["image_evidence"]["source"],
                old["evidence_preprocessing"],
                working_metadata=old["preprocessing"],
                evidence_to_working=matrix,
                baseline_result=(baseline, base["decoder"]),
                hybrid=arm == "hybrid",
            )
            (
                cv2.imwrite(str(output / origin / sample / (arm + "_floor.png")), floor * 255)
                if (output / origin / sample).exists()
                else None
            )
        errors = validate_authoring(document)
        assert not errors, (origin, sample, arm, errors)
        record = {
            "authoring": document,
            "decoder": detail,
            "post_cache_seconds": time.perf_counter() - start,
        }
        save(output / origin / sample / (arm + ".json"), record)
        records[arm] = record
    return (
        old,
        records,
        {
            "input_folder": str(folder.relative_to(ROOT)),
            "baseline_sha256": sha(base_path),
            "model_masks_sha256": sha(folder / "model-masks.npz"),
            "evidence_sha256": sha(folder / "evidence.png"),
            "input_checkpoint_sha256": old.get("model", {}).get("checkpoint_sha256"),
        },
    )


def main(output):
    cv2.setNumThreads(1)
    output.mkdir(parents=True, exist_ok=False)
    study = json.loads((ROOT / "Saved/ShapeFirst/dinov2/v1/protocol.json").read_text())
    override_path = ROOT / "Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json"
    overrides = json.loads(override_path.read_text())
    inputs = list(cases())
    validation = [
        c
        for c in inputs
        if c[0] != "synthetic"
        and c[2] == "validation"
        or (c[0] == "synthetic" and c[1] in study["validation_synthetic_ids"])
    ]
    module = Path(__file__).parent
    protected = (
        [
            p
            for p in module.glob("*.py")
            if p.name not in ["corridor_geometry.py", "evaluate_corridor_geometry.py"]
        ]
        + list(module.glob("*.json"))
        + list((module / "models").glob("*.pt"))
    )
    protected += [
        p
        for n in range(51, 71)
        for p in [
            ROOT / f"Data/Data_{n}.png",
            ROOT / f"Data/annotations/v1/Data_{n}.annotations.json",
            ROOT / f"Data/annotations/v1/Data_{n}.observations.json",
            ROOT / f"Data/ground_truth/structural_v1/Data_{n}.structural.json",
        ]
    ]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    sources = {str(p.relative_to(ROOT)): sha(p) for p in module.glob("*.py")}
    frozen = {
        "version": "corridor-geometry-study/1.0",
        "date": "2026-11-06",
        "policy": POLICY,
        "arms": ARMS,
        "development": "Initial geometry developed using 12 new-human training images. v2 added incumbent opening/room protection and cross-section fitting after v1 validation review. Validation was reused for development; this is not blind confirmation. No policy changes after v2 audit/test scores; final rerun corrects preview captions only.",
        "selection": "Old/new human validation and six assigned synthetic validation examples only; no test-driven selection. Region, door, connection F1 decline <=.02 per group; unmatched connections/regions cannot increase. Maximize weighted door/connection F1 (.4 old, .4 new, .2 synthetic); exact tie baseline.",
        "validation_samples": [(c[0], c[1]) for c in validation],
        "source_hashes": sources,
        "protected_hashes": hashes,
        "label_override_sha256": sha(override_path),
        "reference_inputs_used_in_inference": False,
        "door_stage_changed": False,
        "new_training": False,
        "production_changed": False,
        "cache_inputs": {},
    }
    save(output / "protocol.json", frozen)
    for p in list(module.glob("*.py")) + list(module.glob("*.json")):
        dest = output / "source_snapshot" / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    predicted = []
    for case in validation:
        old, records, cache = predict_case(case, output / "validation", ARMS)
        frozen["cache_inputs"][case[0] + "/" + case[1]] = cache
        predicted.append((case, old, records))
    validation_rows = []
    for (origin, sample, split, folder), old, records in predicted:
        for arm, p in records.items():
            validation_rows.append(
                {
                    "origin": origin,
                    "sample_id": sample,
                    "split": split,
                    "arm": arm,
                    "metrics": metrics_for(origin, sample, old, p["authoring"], overrides),
                }
            )
    validation_summary = {
        a: {
            g: summarize([r for r in validation_rows if r["arm"] == a and r["origin"] == g])
            for g in ["human", "new_human", "synthetic"]
        }
        for a in ARMS
    }
    candidates = []
    for arm in ARMS:
        checks = {}
        for group in ["human", "new_human", "synthetic"]:
            before, after = (validation_summary["baseline"][group], validation_summary[arm][group])
            for key in ["regions", "doors", "connections"]:
                checks[group + "_" + key + "_f1"] = (after[key]["f1"] or 0) >= (
                    before[key]["f1"] or 0
                ) - 0.02
            checks[group + "_unmatched_connections"] = (
                after["unmatched_connections"] <= before["unmatched_connections"]
            )
            checks[group + "_unmatched_regions"] = (
                after["unmatched_regions"] <= before["unmatched_regions"]
            )
        objective = sum(
            (
                weight
                * (
                    (validation_summary[arm][g]["doors"]["f1"] or 0)
                    + (validation_summary[arm][g]["connections"]["f1"] or 0)
                )
                / 2
                for g, weight in [("human", 0.4), ("new_human", 0.4), ("synthetic", 0.2)]
            )
        )
        candidates.append(
            {"arm": arm, "checks": checks, "eligible": all(checks.values()), "objective": objective}
        )
    selected = max(
        [c for c in candidates if c["eligible"]],
        key=lambda c: (c["objective"], c["arm"] == "baseline"),
    )["arm"]
    selection = {
        "selected": selected,
        "candidates": candidates,
        "validation_summary": validation_summary,
        "test_used": False,
    }
    save(output / "selection.json", selection)
    print("selected", selected, json.dumps(candidates), flush=True)
    rows = []
    sections = []
    for index, case in enumerate(inputs):
        origin, sample, split, folder = case
        old, records, cache = predict_case(case, output / "audit", ARMS)
        frozen["cache_inputs"][origin + "/" + sample] = cache
        for arm, p in records.items():
            rows.append(
                {
                    "origin": origin,
                    "sample_id": sample,
                    "split": split,
                    "arm": arm,
                    "metrics": metrics_for(origin, sample, old, p["authoring"], overrides),
                    "status": p["decoder"].get("status"),
                }
            )
        if origin == "new_human":
            for arm in ARMS[1:]:
                path = output / "audit" / origin / sample / (arm + "_comparison.png")
                preview(
                    folder, sample, old, records["baseline"]["authoring"], records[arm]["authoring"]
                ).save(path)
            chosen = selected if selected != "baseline" else "enclosure"
            sections.append(
                f'<section><h2>{sample} · {split}</h2><p>Solda kanıt; ortada mevcut yöntem; sağda {chosen}. Deney görselidir; otomatik kabul yok.</p><a href="audit/{origin}/{sample}/{chosen}_comparison.png"><img loading="lazy" src="audit/{origin}/{sample}/{chosen}_comparison.png"></a></section>'
            )
        if index % 10 == 0:
            print("audited", index, origin, sample, flush=True)
    aggregate = {
        arm: {
            origin: {
                split: summarize(
                    [
                        r
                        for r in rows
                        if r["arm"] == arm
                        and r["origin"] == origin
                        and (split == "all" or r["split"] == split)
                    ]
                )
                for split in (
                    ["synthetic_control"]
                    if origin == "synthetic"
                    else ["train", "validation", "test", "all"]
                )
            }
            for origin in ["human", "new_human", "synthetic"]
        }
        for arm in ARMS
    }
    save(
        output / "report.json",
        {
            "summary": aggregate,
            "rows": rows,
            "selection": selection,
            "diagnostic_reference_used_only_for_scoring": True,
            "production_changed": False,
        },
    )
    save(output / "protocol.json", frozen)
    with (output / "metrics.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
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
        for arm, origins in aggregate.items():
            for origin, splits in origins.items():
                for split, s in splits.items():
                    for key in ["regions", "doors", "connections"]:
                        m = s[key]
                        writer.writerow(
                            [
                                arm,
                                origin,
                                split,
                                key,
                                m["true_positive"],
                                m["predicted"],
                                m["reference"],
                                m["precision"],
                                m["recall"],
                                m["f1"],
                            ]
                        )
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Koridor geometri deneyi</title><style>body{font:16px system-ui;background:#f3f5f8;margin:24px}section{background:white;padding:16px;margin:20px 0}img{width:100%}</style><h1>Koridor geometri deneyi</h1><p>Referans geometri tahmine verilmedi. Mavi oda; kahve koridor; yeşil kapı; mor açık geçiş. Seçilen: '
        + selected
        + ".</p>"
        + "".join(sections)
    )
    changed = [p for p, h in hashes.items() if sha(ROOT / p) != h]
    assert not changed, changed
    assert sources[str((module / "corridor_geometry.py").relative_to(ROOT))] == sha(
        module / "corridor_geometry.py"
    )
    save(
        output / "verification.json",
        {
            "cases": len(inputs),
            "arms": len(ARMS),
            "contract_valid_predictions": len(inputs) * len(ARMS) + len(validation) * len(ARMS),
            "protected_files": len(hashes),
            "changed": changed,
            "selected": selected,
            "test_used_for_selection": False,
            "new_training": False,
            "production_changed": False,
        },
    )
    print("complete", selected, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "Saved/ShapeFirst/corridor_geometry/v1"
    )
    main(parser.parse_args().output)
