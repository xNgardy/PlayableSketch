import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
import time
from SketchPipeline.review.server import atomic_json, file_hash
from SketchPipeline.validation.validate import load_json, validate_document

VERSION = "playablesketch-pipeline/1.0"
ROOT = Path(__file__).resolve().parent
PREDICTION_FILES = ("observations.json", "working.json", "topology.json", "unmasked_line_input.png")


def configuration(config=None):
    config = deepcopy({} if config is None else config)
    defaults = {
        "mode": "inference",
        "geometry_profile": "baseline",
        "max_side": 1600,
        "detector": "lsd",
        "settings": {},
        "timeout_seconds": 300,
        "cache_policy": "fresh",
        "drawing_convention": "drawing-convention/v1",
    }
    if not isinstance(config, dict) or set(config) - set(defaults):
        raise ValueError("Unknown job configuration field")
    defaults.update(config)
    if defaults["mode"] not in ("inference", "manual"):
        raise ValueError("mode must be inference or manual")
    if defaults["geometry_profile"] not in ("baseline", "grid", "structural"):
        raise ValueError("Invalid geometry profile")
    if defaults["detector"] not in ("lsd", "hough"):
        raise ValueError("Invalid detector")
    if type(defaults["max_side"]) is not int or not 256 <= defaults["max_side"] <= 2400:
        raise ValueError("max_side must be 256..2400")
    if type(defaults["timeout_seconds"]) is not int or not 1 <= defaults["timeout_seconds"] <= 900:
        raise ValueError("timeout_seconds must be 1..900")
    if defaults["cache_policy"] not in ("fresh", "reuse_job"):
        raise ValueError("cache_policy must be fresh or reuse_job")
    if defaults["drawing_convention"] != "drawing-convention/v1":
        raise ValueError("Unsupported drawing convention")
    settings = defaults["settings"]
    if not isinstance(settings, dict) or set(settings) - {
        "wall_thickness_cm",
        "wall_height_cm",
        "floor_thickness_cm",
        "door_height_cm",
    }:
        raise ValueError("Invalid settings")
    if any((type(v) not in (int, float) or not 0 < v <= 1000000.0 for v in settings.values())):
        raise ValueError("Settings must be finite positive cm values")
    if settings.get("door_height_cm", 220) > settings.get("wall_height_cm", 300):
        raise ValueError("Door height exceeds wall height")
    return defaults


def runtime_identity():
    packages = {}
    for name in ("numpy", "opencv-python-headless", "shapely", "rapidocr", "onnxruntime"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    paths = sorted(
        (
            p
            for folder in (
                "perception",
                "preprocessing",
                "association",
                "solver",
                "validation",
                "schemas",
            )
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and p.suffix in (".py", ".json")
        )
    )
    paths += [Path(__file__)]
    code = hashlib.sha256(
        "\n".join((str(p.relative_to(ROOT)) + ":" + file_hash(p) for p in paths)).encode()
    ).hexdigest()
    return {
        "pipeline_version": VERSION,
        "code_sha256": code,
        "models_lock_sha256": file_hash(ROOT / "perception/models.lock.json"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "determinism": "Pinned configuration/runtime recorded; inference byte equality across hardware is not guaranteed.",
    }


def artifact(path, base, role, source_revision=None, config_sha256=None):
    schema = None
    if path.suffix == ".json":
        schema = load_json(path).get("schema_version")
    return {
        "path": str(path.relative_to(base)),
        "sha256": file_hash(path),
        "size_bytes": path.stat().st_size,
        "schema_version": schema,
        "role": role,
        "source_revision": source_revision,
        "config_sha256": config_sha256,
    }


def verify_manifest(folder):
    folder = Path(folder).resolve()
    manifest = load_json(folder / "manifest.json")
    if manifest.get("schema_version") != VERSION or not manifest.get("prediction_complete"):
        raise ValueError("Incomplete pipeline manifest")
    if manifest["source"]["path"] not in ("source.png", "source.jpg", "source.jpeg") or set(
        manifest["artifacts"]
    ) != set(PREDICTION_FILES):
        raise ValueError("Invalid manifest source/artifact inventory")
    canonical_config = configuration(manifest["config"])
    expected = hashlib.sha256(
        json.dumps(canonical_config, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if expected != manifest["config_sha256"]:
        raise ValueError("Changed pipeline configuration")
    for name, entry in manifest["artifacts"].items():
        if entry["path"] != "prediction/" + name:
            raise ValueError("Invalid prediction artifact path")
    source = (folder / manifest["source"]["path"]).resolve()
    if folder not in source.parents or file_hash(source) != manifest["source"]["sha256"]:
        raise ValueError("Changed source image")
    for entry in manifest["artifacts"].values():
        path = (folder / entry["path"]).resolve()
        if folder not in path.parents or file_hash(path) != entry["sha256"]:
            raise ValueError("Changed/missing pipeline artifact")
    return manifest


def analyze(image, folder, config=None, *, replay=None):
    from SketchPipeline.preprocessing.prepare import decode
    from SketchPipeline.review.uploads import manual_prediction

    folder = Path(folder).resolve()
    image = Path(image).resolve()
    config = configuration(config)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "manifest.json").exists() or (folder / "prediction").exists():
        raise ValueError("Run already published; choose a new output")
    if folder not in image.parents:
        raise ValueError("Stage a copy of the source image inside the run directory")
    decode(image)
    identity = runtime_identity()
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    stages = []
    start = time.monotonic()

    def progress(name):
        now = time.monotonic()
        if stages:
            stages[-1]["duration_seconds"] = now - stages[-1].pop("_started", now)
        stages.append({"stage": name, "_started": now})
        atomic_json(folder / "progress.json", {"stage": name, "elapsed_seconds": now - start})

    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=folder))
    candidate = staging / "prediction"
    mode = "inference"
    failure = None
    replay_from = None
    try:
        if replay is not None:
            mode = "replay"
            progress("replay")
            replay = Path(replay).resolve()
            original = load_json(replay / "observations.json")
            if original["source"]["image_sha256"] != file_hash(image):
                raise ValueError("Replay image hash mismatch")
            candidate.mkdir()
            replay_from = {}
            for filename in PREDICTION_FILES:
                path = replay / filename
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Replay must contain complete ordinary prediction files")
                replay_from[filename] = file_hash(path)
                shutil.copyfile(path, candidate / filename)
        elif config["mode"] == "manual":
            mode = "manual"
            progress("manual_preparation")
            manual_prediction(image, candidate, "Explicit manual mode; no inference attempted.")
        else:
            try:
                from SketchPipeline.perception.ocr import RapidOCRAdapter
                from SketchPipeline.perception.run import run_single

                progress("model_loading")
                adapter = RapidOCRAdapter()
                run_single(
                    image,
                    candidate,
                    adapter,
                    max_side=config["max_side"],
                    detector=config["detector"],
                    geometry_profile=config["geometry_profile"],
                    progress=progress,
                )
            except Exception as error:
                failure = str(error)
                mode = "manual_fallback"
                shutil.rmtree(candidate, ignore_errors=True)
                progress("manual_fallback")
                manual_prediction(image, candidate, error)
        progress("artifact_validation")
        observations = load_json(candidate / "observations.json")
        if mode == "manual":
            observations["issues"] = [
                {
                    "code": "SKETCH_MANUAL_REVIEW_REQUIRED",
                    "severity": "warning",
                    "element_ids": [],
                    "message": "Manual mode selected; automatic inference was not run.",
                }
            ]
        observations["source"]["image_path"] = str(image)
        atomic_json(candidate / "observations.json", observations)
        checked = validate_document(observations)
        if not checked["schema_valid"] or checked["issues"]:
            raise ValueError("Invalid observation contract")
        if observations["source"]["image_sha256"] != file_hash(image):
            raise ValueError("Source identity mismatch")
        for filename in PREDICTION_FILES:
            if not (candidate / filename).is_file():
                raise ValueError("Prediction incomplete: " + filename)
        from SketchPipeline.review.server import ReviewStore

        probe = object.__new__(ReviewStore)
        probe._load_case(candidate, "PipelineProbe")
        observations["source"]["image_path"] = os.path.relpath(image, folder / "prediction")
        atomic_json(candidate / "observations.json", observations)
        candidate.rename(folder / "prediction")
        progress("topology_review")
        stages[-1]["duration_seconds"] = time.monotonic() - stages[-1].pop("_started")
        manifest = {
            "schema_version": VERSION,
            "prediction_complete": True,
            "state": "needs_review",
            "review_stage": "topology",
            "source": {"path": str(image.relative_to(folder)), "sha256": file_hash(image)},
            "config": config,
            "config_sha256": config_hash,
            "runtime": identity,
            "execution_mode": mode,
            "replay_source_hashes": replay_from,
            "inference_failure": failure,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stages": stages,
            "replay_note": (
                "Replay preserves the source prediction configuration; requested perception settings are not rerun."
                if replay_from
                else None
            ),
            "deferred_stages": {
                "association": "requires approved topology",
                "solve": "requires confirmed metric bindings",
                "semantics": "requires user review",
                "validation": "metric review gate",
                "acceptance": "requires named explicit user acceptance",
            },
            "artifacts": {
                name: artifact(
                    folder / "prediction" / name,
                    folder,
                    "unreviewed_prediction",
                    observations["revision_id"],
                    config_hash,
                )
                for name in PREDICTION_FILES
            },
        }
        atomic_json(folder / "manifest.json", manifest)
        verify_manifest(folder)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Step 11 repeatable image job runner. No metric acceptance is inferred."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--image", type=Path, required=True)
    analyze_parser.add_argument("--output", type=Path, required=True)
    analyze_parser.add_argument("--config", type=Path)
    analyze_parser.add_argument("--replay", type=Path)
    worker = sub.add_parser("worker")
    worker.add_argument("--job-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "worker":
        job = load_json(args.job_dir / "job.json")
        analyze(args.job_dir / job["source_path"], args.job_dir, job["config"])
    else:
        config = configuration(load_json(args.config) if args.config else None)
        args.output.mkdir(parents=True, exist_ok=False)
        image = args.output / ("source" + args.image.suffix.lower())
        shutil.copyfile(args.image, image)
        result = analyze(image, args.output, config, replay=args.replay)
        print(
            json.dumps(
                {
                    "state": result["state"],
                    "execution_mode": result["execution_mode"],
                    "output": str(args.output),
                }
            )
        )


if __name__ == "__main__":
    main()
