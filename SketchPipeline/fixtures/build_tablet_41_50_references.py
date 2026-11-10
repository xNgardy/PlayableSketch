import argparse
import json
from .build_tablet_references import ANNOTATIONS, METRIC, ROOT
from .build_tablet_31_40_references import build_actual_case
from SketchPipeline.validation.validate import as_validated, validate_document

SOURCE = ANNOTATIONS / "tablet_41_50.source.json"


def artifacts():
    source = json.loads(SOURCE.read_text())
    output, samples = ({}, [])
    for spec in source["samples"]:
        identifier = spec["id"]
        obs, side, draft = build_actual_case(spec)
        output[ANNOTATIONS / (identifier + ".observations.json")] = obs
        output[ANNOTATIONS / (identifier + ".annotations.json")] = side
        output[METRIC / (identifier + ".observations.json")] = obs
        output[METRIC / (identifier + ".draft.json")] = draft
        if spec["expected_status"] == "reference_validated":
            output[METRIC / (identifier + ".validated.json")] = as_validated(
                draft, "manual-tablet-reference-annotation", obs
            )
        samples.append(
            dict(
                id=identifier,
                image_path=spec["image_path"],
                image_sha256=spec["image_sha256"],
                encoded_size_px=spec["size_px"],
                exif_orientation=1,
                base_plan_id=spec["base_plan_id"],
                writer_id=spec["writer_id"],
                split="development",
                observations_path=identifier + ".observations.json",
                annotations_path=identifier + ".annotations.json",
                annotation_status="complete",
                counts={k: len(obs[k]) for k in ("texts", "lines", "opening_candidates")},
                metric_status=spec["expected_status"],
                page_corners=None,
                page_aspect_ratio=None,
            )
        )
    policy = "development_only; group variants/crops by base_plan_id and writer; no held-out accuracy claim"
    old = json.loads((ANNOTATIONS / "manifest_all_40.json").read_text())
    if {s["id"] for s in old["samples"]} & {s["id"] for s in samples}:
        raise ValueError("Duplicate sample ID.")
    output[ANNOTATIONS / "manifest_tablet_41_50.json"] = dict(
        schema_version="playablesketch-dataset/1.0", split_policy=policy, samples=samples
    )
    output[ANNOTATIONS / "manifest_all_50.json"] = dict(
        schema_version="playablesketch-dataset/1.0",
        split_policy=policy,
        samples=old["samples"] + samples,
    )
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce actual-image Data_41–50 manual references; no inference/training."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only generated Data_41–50 artifacts and their separate manifests",
    )
    args = parser.parse_args()
    output = artifacts()
    if args.check:
        differences = [
            str(p.relative_to(ROOT))
            for p, d in output.items()
            if not p.exists() or json.loads(p.read_text()) != d
        ]
        if differences:
            raise SystemExit("Reference differences: " + ", ".join(differences))
        print(f"All {len(output)} Data_41–50 artifacts match the actual-image manual source.")
        return
    if not args.overwrite and any((p.exists() for p in output)):
        raise SystemExit("Existing artifacts preserved; use --check or explicitly --overwrite.")
    for path, document in output.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"Wrote {len(output)} Data_41–50 artifacts; no images or older labels changed.")


if __name__ == "__main__":
    main()
