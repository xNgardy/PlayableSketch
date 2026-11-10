import hashlib
import json
from pathlib import Path
from .sizing import digest


def analysis_context(record):
    root = Path(__file__).resolve().parents[2]
    directory = Path(__file__).parent
    names = [
        "propose.py",
        "model.py",
        "dino_model.py",
        "decoder.py",
        "decoder_refined.py",
        "region_recovery.py",
        "local_wall_tracking.py",
        "corridor_refinement.py",
        "passage_refinement.py",
        "door_geometry.py",
        "corridor_candidates.py",
        "corridor_junctions.py",
        "contrast.py",
        "decoder_refined.config.json",
        "region_recovery.v1.json",
        "models.lock.json",
        "dinov2-candidate.lock.json",
        "sizing_policy.v2.json",
    ]
    if record.get("profile") == "hybrid":
        names += ["hybrid_model.py", "hybrid_geometry.py", "hybrid_proposals.py"]
    files = {n: hashlib.sha256((directory / n).read_bytes()).hexdigest() for n in names}
    for name in ["opening_alignment.py", "corridor_geometry.py", "room_geometry.py"]:
        files[name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    files["shape_authoring.schema.json"] = hashlib.sha256(
        (root / "SketchPipeline/schemas/shape_authoring.schema.json").read_bytes()
    ).hexdigest()
    context = {
        "schema_version": "shape-analysis-context/1.0",
        "mode": "shape-first/1.0",
        "source_sha256": record["source_sha256"],
        "profile": record.get("profile", "baseline"),
        "model_config": record.get("model_config", {}),
        "code_policy_hashes": files,
        "numeric_ocr": False,
    }
    context["cache_key"] = digest(context)
    return context
