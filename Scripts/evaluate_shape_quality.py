import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from SketchPipeline.shape_authoring.evaluate_unified_areas import cases
from SketchPipeline.shape_authoring.evaluate_corridor_geometry import metrics_for
from SketchPipeline.evaluation.metrics import counts
from SketchPipeline.evaluation.metrics import pairs, endpoint_error
from SketchPipeline.shape_authoring.diagnose_new20 import reference as new_reference
from SketchPipeline.shape_authoring.decoder import iou

SOURCE = ROOT / "Saved/ShapeFirst/opening_alignment/v2"
OUT = ROOT / "Saved/ShapeFirst/quality_evaluation/v2"
ARMS = ["baseline", "geometry_before", "geometry_fixed"]
METRICS = ["regions", "doors", "openings", "connections"]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def aggregate(rows, bootstrap=False):
    result = {"samples": len(rows)}
    for key in METRICS:
        values = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        total = counts(
            *(sum((v[k] for v in values)) for k in ["true_positive", "predicted", "reference"])
        )
        total.update(
            unmatched_predictions=total["predicted"] - total["true_positive"],
            missed_references=total["reference"] - total["true_positive"],
            scorable_samples=len(values),
        )
        f1 = [v["f1"] for v in values if v["f1"] is not None]
        total["macro_f1_nonempty_samples"] = float(np.mean(f1)) if f1 else None
        total["macro_denominator"] = len(f1)
        if bootstrap and values:
            array = np.asarray(
                [[v[k] for k in ["true_positive", "predicted", "reference"]] for v in values]
            )
            rng = np.random.default_rng(20261106)
            sums = array[rng.integers(len(array), size=(5000, len(array)))].sum(axis=1)
            den = sums[:, 1] + sums[:, 2]
            scores = 2 * sums[den > 0, 0] / den[den > 0]
            total["f1_drawing_bootstrap_95_interval"] = (
                np.percentile(scores, [2.5, 97.5]).tolist() if len(scores) else None
            )
        result[key] = total
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((SOURCE / "protocol.json").read_text())
    for group in ["source_hashes", "protected_hashes"]:
        assert all(
            (
                hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
                for p, h in protocol[group].items()
            )
        ), group
    overrides = json.loads(
        (ROOT / "Saved/ShapeFirst/new20_diagnosis/label_audit_overrides_v1.json").read_text()
    )
    previous = json.loads((SOURCE / "report.json").read_text())
    indexed = {(r["arm"], r["origin"], r["sample_id"]): r["metrics"] for r in previous["rows"]}
    rows = []
    detailed = []
    for origin, sample, split, folder in cases():
        old = json.loads((folder / "proposals.json").read_text())
        for arm in ARMS:
            path = SOURCE / "audit" / origin / sample / (arm + ".json")
            document = json.loads(path.read_text())["authoring"]
            metric = metrics_for(origin, sample, old, document, overrides)
            assert json.loads(json.dumps(metric)) == indexed[arm, origin, sample], (
                arm,
                origin,
                sample,
            )
            rows.append(
                dict(
                    arm=arm,
                    origin=origin,
                    sample_id=sample,
                    split=split,
                    metrics=metric,
                    prediction_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
            if origin == "new_human" and arm == "geometry_fixed":
                ref, _ = new_reference(int(sample.split("_")[1]), old["preprocessing"], overrides)
                top = document["topology"]
                pr = top["regions"]
                rr = ref["regions"]
                po = top["openings"]
                ro = ref["openings"]
                bounds = lambda x: np.r_[
                    np.min(x["geometry"]["points_px"], axis=0),
                    np.max(x["geometry"]["points_px"], axis=0),
                ]
                detail = {"sample_id": sample, "split": split}
                for kind in ["room", "corridor_segment", "all_typed"]:
                    pp = [v for v in pr if kind == "all_typed" or v["type"] == kind]
                    tt = [v for v in rr if kind == "all_typed" or v["type"] == kind]
                    matches = pairs(
                        pp,
                        tt,
                        lambda a, b: (
                            1 - iou(bounds(a), b["bounds_px"])
                            if a["type"] == b["type"]
                            else float("inf")
                        ),
                        0.5,
                    )
                    detail[kind] = counts(len(matches), len(pp), len(tt))
                mapping = metric["region_id_mapping"]
                side = max(old["preprocessing"]["working_size_px"])
                for fraction in [0.02, 0.04]:
                    cost = lambda a, b: (
                        endpoint_error(a["geometry"]["points_px"], b["points_px"])
                        if a["type"] == b["type"]
                        else float("inf")
                    )
                    connected = lambda a, b: (
                        cost(a, b)
                        if set((mapping.get(v, "unmatched:" + v) for v in a["entity_ids"]))
                        == set(b["entity_ids"])
                        else float("inf")
                    )
                    for name, fun in [
                        ("localized_openings", cost),
                        ("attached_openings", connected),
                    ]:
                        matched = pairs(po, ro, fun, side * fraction)
                        detail[name + "_" + str(fraction)] = counts(len(matched), len(po), len(ro))
                pd = [o for o in po if o["type"] == "door"]
                rd = [o for o in ro if o["type"] == "door"]
                matched = pairs(pd, rd, connected, side * 0.04)
                detail["attached_doors"] = counts(len(matched), len(pd), len(rd))
                detail["matched_endpoint_errors_working_side_fraction"] = [
                    x[2] / side for x in metric["location_matches"]
                ]
                detailed.append(detail)
    scopes = {}
    for origin in ["human", "new_human", "synthetic"]:
        splits = (
            ["synthetic_control"]
            if origin == "synthetic"
            else ["train", "validation", "test", "all"]
        )
        for split in splits:
            scopes[origin + "/" + split] = {
                arm: aggregate(
                    [
                        r
                        for r in rows
                        if r["arm"] == arm
                        and r["origin"] == origin
                        and (split == "all" or r["split"] == split)
                    ],
                    bootstrap=arm == "geometry_fixed",
                )
                for arm in ARMS
            }
    new = [r for r in rows if r["arm"] == "geometry_fixed" and r["origin"] == "new_human"]
    errors = []
    for r in new:
        m = r["metrics"]
        errors.append(
            dict(
                sample_id=r["sample_id"],
                split=r["split"],
                **{
                    k: {
                        "missed": m[k]["reference"] - m[k]["true_positive"],
                        "unmatched": m[k]["predicted"] - m[k]["true_positive"],
                    }
                    for k in METRICS
                },
            )
        )
    complete = [
        r["sample_id"]
        for r in new
        if all(
            (
                r["metrics"][k]["true_positive"]
                == r["metrics"][k]["predicted"]
                == r["metrics"][k]["reference"]
                for k in ["regions", "attached_openings", "connections"]
            )
        )
        and r["metrics"]["region_type_matches"] == r["metrics"]["regions"]["reference"]
    ]
    syn = [
        r["metrics"]["exact_topology"]
        for r in rows
        if r["arm"] == "geometry_fixed" and r["origin"] == "synthetic"
    ]
    detail_summary = {
        k: counts(
            *(sum((d[k][v] for d in detailed)) for v in ["true_positive", "predicted", "reference"])
        )
        for k in detailed[0]
        if isinstance(detailed[0][k], dict)
    }
    endpoint_errors = [
        v for d in detailed for v in d["matched_endpoint_errors_working_side_fraction"]
    ]
    detail_summary["matched_endpoint_error_side_fraction"] = {
        "count": len(endpoint_errors),
        "p50": float(np.percentile(endpoint_errors, 50)),
        "p95": float(np.percentile(endpoint_errors, 95)),
    }
    result = dict(
        version="shape-quality-evaluation/1.1",
        source=str(SOURCE.relative_to(ROOT)),
        scope="Retrospective same-writer development evaluation; not blind or unseen-writer validation.",
        inference_rerun=False,
        independent_prediction_rescoring=True,
        scored_cases=130,
        prediction_documents_rescored=len(rows),
        source_and_protected_hashes_verified=True,
        bootstrap_seed=20261106,
        bootstrap_draws=5000,
        metric_notes={
            "regions": "Bounding box IoU >= 0.5; type agnostic matching.",
            "doors": "Type and endpoint localization, tolerance 4% of maximum working side; does not require correct owners.",
            "connections": "new_human: unique mapped region pairs with a localized correctly typed opening; human/synthetic: opening-level correct attachment. Do not pool these denominators.",
            "confidence": "95% whole-drawing bootstrap intervals describe variability within these drawings, not unseen-writer generalization.",
            "unmatched": "Unmatched to approximate reference; not proof of a physically false element.",
            "accuracy": "TN universe is undefined; accuracy and specificity are not reported.",
        },
        summary=scopes,
        new20_complete_under_matching_criteria=complete,
        synthetic_exact_topology=dict(
            correct=sum(syn), reference=len(syn), fraction=sum(syn) / len(syn)
        ),
        new20_errors=errors,
        new20_detailed_metrics=detail_summary,
        new20_detailed_rows=detailed,
        rows=rows,
    )
    dump(OUT / "report.json", result)
    with (OUT / "metrics.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["scope", "arm", "metric", "TP", "unmatched", "missed", "precision", "recall", "f1"]
        )
        for scope, arms in scopes.items():
            for arm, m in arms.items():
                for k in METRICS:
                    v = m[k]
                    writer.writerow(
                        [
                            scope,
                            arm,
                            k,
                            v["true_positive"],
                            v["unmatched_predictions"],
                            v["missed_references"],
                            v["precision"],
                            v["recall"],
                            v["f1"],
                        ]
                    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["summary", "rows", "new20_errors", "new20_detailed_rows"]
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
