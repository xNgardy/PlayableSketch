import argparse
from copy import deepcopy
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from SketchPipeline.association.topology import load_review, skeleton
from SketchPipeline.review.server import digest
from SketchPipeline.association.associate import propose, hypotheses
from SketchPipeline.solver.linear import solve
from SketchPipeline.validation.validate import load_json, SCHEMAS, REGISTRY


def reconstruct(review_path, observations_path, request):
    schema = SCHEMAS["urn:playablesketch:metric-input:1"]
    Draft202012Validator(schema, registry=REGISTRY).validate(request)
    revision, observations, transform = load_review(
        review_path, observations_path, request["topology_revision_id"]
    )
    doc, pixels = skeleton(
        revision, observations, request["region_kinds"], request.get("settings", {})
    )
    doc["revision_id"] += "-" + digest(request)[:12]
    doc["layout"]["dimensions"] = deepcopy(request["dimensions"])
    all_ids = [item["id"] for group in doc["layout"].values() for item in group]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Metric IDs must be globally unique")
    text_ids = {t["id"] for t in observations["texts"]}
    for d in request["dimensions"]:
        if (d["value_cm"] is None) != (d["state"] == "missing"):
            raise ValueError("Only missing dimensions may have null values")
        if not set(d["provenance"]["evidence_ids"]) <= text_ids:
            raise ValueError("Dimension references unknown numeric evidence")
        if d["state"] == "confirmed" and d["provenance"]["method"] not in (
            "user_correction",
            "manual_annotation",
        ):
            raise ValueError(
                "OCR/derived measurements require explicit user confirmation provenance"
            )
    relation_ids = [r["id"] for r in request.get("relations", [])]
    if len(set(relation_ids)) != len(relation_ids) or set(relation_ids) & set(all_ids):
        raise ValueError("Relation IDs must be unique and distinct from layout IDs")
    evidence_ids = {
        item["id"]
        for group in (
            observations["texts"],
            observations["lines"],
            observations["opening_candidates"],
        )
        for item in group
    }
    for r in request.get("relations", []):
        if not set(r.get("evidence_ids", [])) <= evidence_ids:
            raise ValueError("Relation references unknown observation evidence")
    association = propose(doc, pixels, observations, transform, top_k=request.get("top_k", 3))
    bound = {e for d in request["dimensions"] for e in d["provenance"]["evidence_ids"]}
    ignored = [item["evidence_id"] for item in request.get("ignored_texts", [])]
    if len(set(ignored)) != len(ignored) or not set(ignored) <= text_ids or set(ignored) & bound:
        raise ValueError("Ignored text must be unique, linked, and not also bound to a dimension")
    association["ignored_texts"] = deepcopy(request.get("ignored_texts", []))
    used = set(all_ids)
    for p in association["proposals"]:
        if p["evidence_id"] in bound or p["evidence_id"] in ignored:
            continue
        identifier = "metric-" + p["evidence_id"]
        while identifier in used:
            identifier += "x"
        used.add(identifier)
        doc["layout"]["dimensions"].append(
            {
                "id": identifier,
                "value_cm": p["value_cm"],
                "basis": "wall_centerline",
                "target": {"type": "unassigned"},
                "state": "missing" if p["value_cm"] is None else "inferred",
                "span_label": p["raw_text"],
                "provenance": {
                    "method": "ocr",
                    "evidence_ids": [p["evidence_id"]],
                    "note": "Association alternatives in report; not confirmed.",
                },
            }
        )
    kwargs = {
        "relations": request.get("relations", []),
        "origin_vertex_id": request.get("origin_vertex_id"),
    }
    draft, report = solve(doc, observations=observations, **kwargs)
    report["association"] = association
    report["search"] = hypotheses(
        doc,
        [p for p in association["proposals"] if p["evidence_id"] not in ignored],
        budget=request.get("hypothesis_budget", 16),
        **kwargs,
    )
    report["source"] = {
        "topology_revision_id": revision["revision_id"],
        "topology_revision_sha256": revision["revision_sha256"],
        "state_sha256": revision["state_sha256"],
        "source_fingerprints": revision["source_fingerprints"],
    }
    report["pixel_topology"] = pixels
    source_image = (
        Path(observations_path).resolve().parent / observations["source"]["image_path"]
    ).resolve()
    draft["source"]["image_path"] = str(source_image)
    if draft["source"].get("legacy_draft_path"):
        draft["source"]["legacy_draft_path"] = str(
            (
                Path(observations_path).resolve().parent / draft["source"]["legacy_draft_path"]
            ).resolve()
        )
    return (draft, report)


def main():
    parser = argparse.ArgumentParser(
        description="Step 09 CLI: approved pixel topology + explicit metric bindings -> pending draft."
    )
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New output directory; existing results are never overwritten",
    )
    args = parser.parse_args()
    request = load_json(args.bindings)
    draft, report = reconstruct(args.review, args.observations, request)
    load_review(args.review, args.observations, request["topology_revision_id"])
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("draft.json", draft), ("report.json", report), ("bindings.json", request)):
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "metric_valid": report["validation"]["metric_valid"],
                "rank": report["rank"],
                "variables": report["variable_count"],
                "review": "pending",
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
