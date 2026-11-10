import argparse
from copy import deepcopy
import json
from .build_tablet_references import ANNOTATIONS, METRIC, ROOT, build_case
from SketchPipeline.validation.validate import as_validated, validate_document

SOURCE = ANNOTATIONS / "tablet_31_40.source.json"


def build_actual_case(spec):
    topology = deepcopy(spec)
    for region in topology["regions"]:
        if "topology_scaffold_cm" in region:
            if spec["expected_status"] != "incomplete":
                raise ValueError("A topology scaffold cannot produce an accepted reference.")
            region["bounds_cm"] = region["topology_scaffold_cm"]
    obs, side, draft = build_case(topology)
    layout = draft["layout"]
    regions = {r["id"]: r for r in layout["rooms"] + layout["corridors"]}
    points = {v["id"]: v for v in layout["vertices"]}
    for region in spec["regions"]:
        masks = region.get("unresolved_coordinates", [])
        if not masks:
            continue
        ids = regions[region["id"]]["boundary_vertex_ids"]
        xmax = region["topology_scaffold_cm"][2]
        for vid in ids:
            v = points[vid]
            for axis in ("x", "y"):
                i = "xy".index(axis)
                if axis in masks or (axis + "_max" in masks and v["position_cm"][i] == xmax):
                    v["position_cm"][i] = None
                    v["state"] = "missing"
                    v["provenance"][
                        "note"
                    ] = "Unresolved coordinate: no measured dimension. Temporary topology scaffold removed; never derived from pixels."
    for opening in layout["openings"]:
        if opening["clear_width_cm"] is None:
            opening["state"] = "missing"
            opening["provenance"][
                "note"
            ] = "Pixel door gap is visible; no written clear width or exact opening location. Both remain null."
    checked = validate_document(draft, obs)
    if not checked["schema_valid"]:
        raise ValueError(f"{spec['id']}: schema failure after removing scaffolds: {checked}")
    if spec["expected_status"] == "reference_validated" and (not checked["metric_valid"]):
        raise ValueError(f"{spec['id']}: unexpected metric failure: {checked}")
    if spec["expected_status"] != "reference_validated" and checked["metric_valid"]:
        raise ValueError(f"{spec['id']}: negative reference became metric-valid")
    if spec["expected_status"] == "incomplete" and (
        not any((i["code"] == "SKETCH_DIMENSION_MISSING" for i in checked["issues"]))
    ):
        raise ValueError("Missing constraints must survive projection.")
    if spec["expected_status"] == "conflicting" and (
        not any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in checked["issues"]))
    ):
        raise ValueError("The actual dimension conflict must survive.")
    draft["issues"] = checked["issues"] if not checked["metric_valid"] else []
    return (obs, side, draft)


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
    old = json.loads((ANNOTATIONS / "manifest_all_30.json").read_text())
    if {s["id"] for s in old["samples"]} & {s["id"] for s in samples}:
        raise ValueError("Duplicate sample ID.")
    output[ANNOTATIONS / "manifest_tablet_31_40.json"] = dict(
        schema_version="playablesketch-dataset/1.0", split_policy=policy, samples=samples
    )
    output[ANNOTATIONS / "manifest_all_40.json"] = dict(
        schema_version="playablesketch-dataset/1.0",
        split_policy=policy,
        samples=old["samples"] + samples,
    )
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce actual-image Data_31–40 manual references; no inference/training."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only generated Data_31–40 artifacts and their separate manifests",
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
        print(f"All {len(output)} Data_31–40 artifacts match the actual-image manual source.")
        return
    if not args.overwrite and any((p.exists() for p in output)):
        raise SystemExit("Existing artifacts preserved; use --check or explicitly --overwrite.")
    for path, document in output.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"Wrote {len(output)} Data_31–40 artifacts; no images or older labels changed.")


if __name__ == "__main__":
    main()
