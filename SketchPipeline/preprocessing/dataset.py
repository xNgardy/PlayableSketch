import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import numpy as np
from jsonschema import Draft202012Validator, ValidationError
from SketchPipeline.validation.validate import load_json, validate_document, SCHEMAS
from .prepare import InputError, decode, prepare, project, write_artifacts

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "Data/annotations/v1/manifest.json"


def require(condition, message):
    if not condition:
        raise InputError(message)


def audit(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    base = manifest_path.parent
    manifest = load_json(manifest_path)
    require(
        manifest["schema_version"] == "playablesketch-dataset/1.0", "Unsupported manifest version."
    )
    require(bool(manifest["samples"]), "Dataset must contain samples.")
    require(
        len({s["id"] for s in manifest["samples"]}) == len(manifest["samples"]),
        "Duplicate sample ID.",
    )
    groups = {}
    samples = []
    for sample in manifest["samples"]:
        id = sample["id"]
        require(
            isinstance(id, str) and re.fullmatch("[A-Za-z][A-Za-z0-9_-]{0,127}", id),
            "Unsafe sample ID.",
        )
        require(sample["split"] == "development", f"{id}: current fixtures are development-only.")
        for group in (("plan", sample["base_plan_id"]), ("writer", sample["writer_id"])):
            if group[1] is not None:
                require(
                    groups.get(group, sample["split"]) == sample["split"], f"{id}: split leakage."
                )
                groups[group] = sample["split"]
        path = (base / sample["image_path"]).resolve()
        obs_path = (base / sample["observations_path"]).resolve()
        side_path = base / sample["annotations_path"]
        obs = load_json(obs_path)
        side = load_json(side_path)
        schema = SCHEMAS["urn:playablesketch:pixel-annotations:1"]
        Draft202012Validator(schema).validate(side)
        result = validate_document(obs)
        require(
            result["schema_valid"] and (not result["issues"]),
            f"{id}: invalid observations: {result['issues']}",
        )
        require(
            obs["region_annotation_status"] == sample["annotation_status"] == "complete",
            f"{id}: incomplete annotations.",
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(
            digest == sample["image_sha256"] == obs["source"]["image_sha256"],
            f"{id}: image hash mismatch.",
        )
        require(
            (obs_path.parent / obs["source"]["image_path"]).resolve() == path,
            f"{id}: observation image path mismatch.",
        )
        require(
            (side_path.parent / side["observations_path"]).resolve() == obs_path,
            f"{id}: sidecar observation mismatch.",
        )
        original, _, _, orientation = decode(path)
        h, w = original.shape[:2]
        require(
            [w, h]
            == sample["encoded_size_px"]
            == [obs["frame"]["width_px"], obs["frame"]["height_px"]],
            f"{id}: size mismatch.",
        )
        require(orientation == sample["exif_orientation"], f"{id}: EXIF mismatch.")
        require(
            obs["frame"]["id"] == "original"
            and np.array_equal(obs["frame"]["original_to_frame"], np.eye(3)),
            f"{id}: annotation frame must be encoded original.",
        )
        require(
            sample["counts"] == {k: len(obs[k]) for k in ["texts", "lines", "opening_candidates"]},
            f"{id}: counts mismatch.",
        )
        draft = load_json(side_path.parent / side["reference_draft_path"])
        require(
            draft["observation_document_id"] == obs["document_id"]
            and draft["source"]["image_sha256"] == digest,
            f"{id}: metric source mismatch.",
        )
        dimensions = {d["id"]: d for d in draft["layout"]["dimensions"]}
        texts = {t["id"]: t for t in obs["texts"]}
        lines = {line["id"]: line for line in obs["lines"]}
        candidate_ids = {o["id"] for o in obs["opening_candidates"]}
        used_lines = [lid for stroke in side["strokes"] for lid in stroke["line_ids"]]
        require(
            Counter(used_lines) == Counter({lid: 1 for lid in lines}),
            f"{id}: each line needs exactly one stroke class.",
        )
        extra_ids = [s["id"] for k in ["strokes", "junctions", "gaps"] for s in side[k]]
        require(len(extra_ids) == len(set(extra_ids)), f"{id}: duplicate sidecar ID.")
        pairs = [(a["text_id"], a["dimension_id"]) for a in side["associations"]]
        expected = [
            (t, d["id"])
            for d in dimensions.values()
            for t in d["provenance"]["evidence_ids"]
            if t in texts
        ]
        require(
            Counter(pairs) == Counter(expected) and set((t for t, d in pairs)) == set(texts),
            f"{id}: association coverage mismatch.",
        )
        for tid, did in pairs:
            require(
                texts[tid]["parsed_value_cm"] == dimensions[did]["value_cm"],
                f"{id}: transcribed value mismatch.",
            )
        gap_ids = []
        for gap in side["gaps"]:
            if gap["kind"] == "incidental":
                require(
                    gap["opening_candidate_id"] is None,
                    f"{id}: incidental stroke gap cannot be an opening.",
                )
            else:
                gap_ids.append(gap["opening_candidate_id"])
        require(
            Counter(gap_ids) == Counter({oid: 1 for oid in candidate_ids}),
            f"{id}: opening/gap mismatch.",
        )
        regions = {
            r["id"]: kind
            for kind, items in (
                ("room", draft["layout"]["rooms"]),
                ("corridor", draft["layout"]["corridors"]),
            )
            for r in items
        }
        seen_regions = set()
        for region in side.get("regions", []):
            require(
                region["region_id"] not in seen_regions
                and regions.get(region["region_id"]) == region["kind"],
                f"{id}: invalid/duplicate region annotation.",
            )
            seen_regions.add(region["region_id"])
            polygon = region["polygon_px"]
            area = (
                abs(
                    sum(
                        (
                            a[0] * b[1] - b[0] * a[1]
                            for a, b in zip(polygon, polygon[1:] + polygon[:1])
                        )
                    )
                )
                / 2
            )
            require(area > 1, f"{id}: degenerate region polygon.")
        require(
            "regions" not in side or seen_regions == set(regions),
            f"{id}: incomplete region annotation coverage.",
        )
        points = [j["point_px"] for j in side["junctions"]]
        points.extend(
            (point for region in side.get("regions", []) for point in region["polygon_px"])
        )
        for key, start, end in [
            ("gaps", "start_px", "end_px"),
            ("associations", "span_start_px", "span_end_px"),
        ]:
            for item in side[key]:
                require(item[start] != item[end], f"{id}: zero length annotation.")
                points.extend([item[start], item[end]])
        points.extend((p for t in obs["texts"] for p in t["polygon_px"]))
        points.extend((p for o in obs["opening_candidates"] for p in o["polygon_px"]))
        points.extend((p for line in lines.values() for p in [line["start_px"], line["end_px"]]))
        require(
            all(
                (
                    np.isfinite([x, y]).all() and 0 <= x <= w - 1 and (0 <= y <= h - 1)
                    for x, y in points
                )
            ),
            f"{id}: pixel-center annotation outside image.",
        )
        for line in lines.values():
            require(line["start_px"] != line["end_px"], f"{id}: zero-length line.")
        metric = validate_document(draft, observations=obs)
        require(metric["schema_valid"], f"{id}: invalid metric draft schema.")
        expected_status = (
            "reference_validated"
            if metric["metric_valid"]
            else (
                "conflicting"
                if any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in metric["issues"]))
                else "incomplete"
            )
        )
        require(expected_status == sample["metric_status"], f"{id}: metric status mismatch.")
        if sample["metric_status"] == "reference_validated":
            validated = load_json(
                (side_path.parent / side["reference_draft_path"]).with_name(f"{id}.validated.json")
            )
            require(
                validate_document(validated, observations=obs)["exportable"],
                f"{id}: accepted reference no longer links to observations.",
            )
        samples.append((sample, path, obs, side, points))
    return (manifest, samples)


def run(manifest_path, output, max_side=1600):
    output = Path(output)
    require(not output.exists(), "Output already exists; choose a new run directory.")
    manifest, samples = audit(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".dataset-", dir=output.parent))
    try:
        report = {
            "schema_version": "playablesketch-preprocessing-dataset/1.0",
            "manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
            "split": "development",
            "samples": [],
            "status": "complete",
        }
        for sample, path, obs, side, points in samples:
            images, metadata = prepare(
                path,
                max_side=max_side,
                page_corners=sample["page_corners"],
                page_aspect_ratio=sample["page_aspect_ratio"],
            )
            mapped = project(points, metadata["original_to_working"])
            restored = project(mapped, metadata["working_to_original"])
            error = float(np.abs(restored - np.asarray(points)).max())
            require(error <= 1e-06, f"{sample['id']}: annotation round-trip failed.")
            metadata["annotation_round_trip_max_error_px"] = error
            metadata["manual_annotation_issues"] = side["issues"]
            metadata["annotation_counts"] = sample["counts"]
            write_artifacts(staging / sample["id"], images, metadata, obs, side)
            report["samples"].append(
                {
                    "id": sample["id"],
                    "counts": sample["counts"],
                    "metric_status": sample["metric_status"],
                    "round_trip_max_error_px": error,
                    "automatic_quality": metadata["quality"],
                    "manual_issues": side["issues"],
                }
            )
        (staging / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        cards = "".join(
            (
                f"<article><h2>{s['id']}</h2><a href='{s['id']}/comparison.png'><img src='{s['id']}/comparison.png'></a><p>{s['metric_status']}</p><a href='{s['id']}/original_details.png'>Measured spans / junctions (original)</a> | <a href='{s['id']}/working_details.png'>Working details</a> | <a href='{s['id']}/preprocessing.json'>Transforms / quality</a></article>"
                for s in report["samples"]
            )
        )
        (staging / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>Step 06 pixel review</title><style>body{font:16px system-ui;margin:24px;background:#eee}article{background:white;padding:16px;margin:20px 0}img{max-width:100%}</style><h1>Manual pixel annotations: development set</h1><p>Pink: text. Cyan: wall/tick stroke traces. Orange: intended openings. Left: original; right: working. No OCR predictions. Metric status is separate from annotation completeness.</p>"
            + cards
        )
        os.rename(staging, output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(
        description="Audit manual pixel references and prepare an atomic development dataset run."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-side", type=int, default=1600)
    args = parser.parse_args()
    try:
        if args.output:
            report = run(args.manifest, args.output, args.max_side)
            print(f"Prepared {len(report['samples'])} samples: {args.output}/index.html")
        else:
            _, samples = audit(args.manifest)
            print(
                f"Audit passed: {len(samples)} samples, {sum((len(s[2]['texts']) for s in samples))} text regions."
            )
    except (ValueError, OSError, KeyError, TypeError, ValidationError) as exc:
        parser.exit(1, f"Dataset preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
