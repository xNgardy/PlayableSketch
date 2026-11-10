from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = dict(
    version="step13-evaluation/1.0",
    scope="retrospective development; no unseen-writer holdout claim",
    metric_tolerance_cm=0.1,
    canonical_alignment="translation only; fixed yaw; no scale/reflection",
    text_iou=0.3,
    region_iou=0.5,
    wall_endpoint_fraction=0.02,
    junction_distance_fraction=0.02,
    opening_endpoint_fraction=0.02,
    latency_budget_seconds=30,
    missing_stage="not_computed/null; retain sample in denominators",
    grouping="all derivatives inherit parent split; synthetic geometry families stay together",
    annotations="manual approximate traces, not segmentation masks",
    automatic_acceptance="prohibited; named user review remains mandatory",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def audit_split(samples, assignments, families=None):
    errors = []
    groups = defaultdict(set)
    identities = defaultdict(set)
    family_splits = defaultdict(set)
    by_id = {s["id"]: s for s in samples}
    if len(by_id) != len(samples):
        errors.append("duplicate_sample_id")
    for s in samples:
        group = s["base_plan_id"]
        split = s.get("evaluation_split", assignments.get(group))
        if split not in {"train", "validation", "test"}:
            errors.append("missing_split:" + s["id"])
        groups[group].add(split)
        identities[s["image_sha256"]].add(split)
        if s.get("source_id"):
            parent = by_id.get(s["source_id"])
            if not parent or parent["base_plan_id"] != group:
                errors.append("parent_group_mismatch:" + s["id"])
        if families and group in families:
            family_splits[families[group]].add(split)
    for name, table in [
        ("parent", groups),
        ("identical_image", identities),
        ("synthetic_family", family_splits),
    ]:
        errors.extend((name + "_leakage:" + str(k) for k, v in table.items() if len(v) > 1))
    return dict(
        passed=not errors,
        issues=errors,
        parent_groups=len(groups),
        writer_holdout_verified=False,
        note="Writer IDs are incomplete; grouping does not establish writer independence.",
    )


def freeze(output, root=ROOT):
    output = Path(output)
    root = Path(root).resolve()
    target = output / "protocol.json"
    if target.exists():
        protocol = read(target)
        verify(protocol, root)
        return protocol
    manifest = root / "Data/augmented/v1/manifest_with_originals.json"
    split_path = root / "Saved/Evaluation/v1/split.json"
    samples = read(manifest)["samples"]
    split = read(split_path)
    if sha(manifest) != split["manifest_sha256"]:
        raise ValueError("Split is stale for dataset manifest")
    audit = audit_split(samples, split["group_split"], split["synthetic_geometry_families"])
    if not audit["passed"]:
        raise ValueError("Leakage: " + str(audit["issues"]))
    files = {}
    missing = []

    def pin(path, expected=None):
        path = Path(path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Input outside project: " + str(path))
        key = path.relative_to(root).as_posix()
        if not path.exists():
            missing.append(key)
            return
        value = sha(path)
        if expected and expected != value:
            raise ValueError("Source hash mismatch: " + key)
        files[key] = value

    pin(manifest)
    pin(split_path)
    for sample in samples:
        pin(manifest.parent / sample["image_path"], sample["image_sha256"])
        for key in ("observations_path", "annotations_path", "metric_path", "transform_path"):
            if sample.get(key):
                pin(manifest.parent / sample[key])
        annotation = read(manifest.parent / sample["annotations_path"])
        pin(
            (manifest.parent / sample["annotations_path"]).parent
            / annotation["reference_draft_path"]
        )
        for filename in ("metrics.json", "observations.json", "working.json"):
            pin(root / "Saved/Evaluation/v1/baseline" / sample["id"] / filename)
        if sample["origin"] != "augmented":
            pin(root / "Saved/Evaluation/v1/topology" / f"{sample['id']}.json")
    pin(root / "Saved/Step09/v1/final_regression/summary.json")
    for name in ("runtime.json", "topology_report.json"):
        pin(root / "Saved/Evaluation/v1" / name)
    for path in (root / "SketchPipeline").rglob("*.py"):
        pin(path)
    for path in (root / "SketchPipeline").rglob("*.json"):
        if "schemas" in path.parts:
            pin(path)
    for folder in (
        "Saved/Step12",
        "Saved/Step10/v1/controlled_fixture/reviews",
        "Saved/Step08/topology-review/metric",
    ):
        base = root / folder
        if base.exists():
            for path in base.rglob("*.json"):
                if folder == "Saved/Step12" and (
                    not path.name
                    in {
                        "physical-fixtures.json",
                        "verification.json",
                        "restarted-pawn.json",
                        "index.json",
                    }
                ):
                    continue
                pin(path)
    for path in (root / "SketchPipeline/review/web").glob("*.js"):
        pin(path)
    protocol = dict(
        policy=POLICY,
        dataset_manifest=manifest.relative_to(root).as_posix(),
        samples=samples,
        split=split,
        leakage_audit=audit,
        input_sha256=files,
        missing_inputs=sorted(set(missing)),
        code_execution="cached historical inference replay + fresh current solver/evaluator; separate fresh challenge predictions",
        original_samples=sum((s["origin"] == "human" for s in samples)),
    )
    write(target, protocol)
    return protocol


def verify(protocol, root=ROOT):
    failures = [
        name
        for name, value in protocol["input_sha256"].items()
        if not (Path(root) / name).is_file() or sha(Path(root) / name) != value
    ]
    if failures:
        raise ValueError(
            "Frozen inputs changed; create a new evaluation directory: " + str(failures[:8])
        )
    return True
