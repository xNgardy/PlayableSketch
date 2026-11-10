import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from .corridor_candidates import recover, POLICY
from .corridor_zoom import inspect_crops
from .decoder import boundary_graph, authoring_document
from .passage_refinement import opening_candidates
from .contract import validate_authoring
from .synthetic import write_json

ROOT = Path(__file__).resolve().parents[2]
ARMS = ("baseline", "parallel", "parallel_bends", "zoom_verified", "combined")


def project_boxes(boxes, matrix):
    result = []
    for box in boxes:
        p = np.c_[np.asarray(box["bounds_px"]).reshape(2, 2), np.ones(2)] @ matrix.T
        result.append(
            {k: copy.deepcopy(v) for k, v in box.items() if k != "evidence"}
            | {"bounds_px": np.round(p[:, :2].ravel(), 6).tolist()}
        )
    return result


def run_case(folder, output, adapter=None):
    folder = Path(folder)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads((folder / "proposals.json").read_text())
    gray = cv2.imread(str(folder / "evidence.png"), 0)
    working = cv2.imread(str(folder / "working.png"), 0)
    with np.load(folder / "model-masks.npz") as z:
        native = z["native_probabilities"]
    base_path = ROOT / "Saved/ShapeFirst/dinov2/corridor_passage/v2/full"
    if old.get("diagnostics") and old["diagnostics"][0].get("version") == "shape-decoder/2.6":
        base_boxes = old["diagnostics"][0]["region_boxes"]
        base_doc = old["authoring"]
    else:
        from .decoder_refined import decode

        source = old["authoring"]["image_evidence"]["source"]
        matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )
        base_doc, detail = decode(
            gray,
            native,
            source,
            old["evidence_preprocessing"],
            working_gray=working,
            working_metadata=old["preprocessing"],
            evidence_to_working=matrix,
            opening_policy="corridor-passages",
            region_policy="supported-corridors",
        )
        base_boxes = detail["region_boxes"]
    matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
        old["evidence_preprocessing"]["working_to_original"]
    )
    inverse = np.linalg.inv(matrix)
    base_native = project_boxes(base_boxes, inverse)
    parallel, p_detail = recover(gray, base_native, bends=False)
    bent, b_detail = recover(gray, base_native, bends=True)
    fused = np.zeros_like(native)
    zoom = []
    if adapter is not None and b_detail["kept"]:
        image = Path(old["authoring"]["image_evidence"]["source"]["image_path"])
        if not image.is_absolute():
            image = ROOT / image
        fused, zoom = inspect_crops(
            image,
            np.linalg.inv(np.asarray(old["evidence_preprocessing"]["working_to_original"])),
            gray.shape,
            b_detail["kept"],
            adapter,
            output / "crops",
        )
    verified = [
        c for c, z in zip(b_detail["kept"], zoom) if z["corridor_fraction_above_0_5"] >= 0.2
    ]
    variants = {
        "parallel": parallel,
        "parallel_bends": bent,
        "zoom_verified": base_native + verified,
        "combined": bent,
    }
    rows = []
    for arm in ARMS:
        start = time.perf_counter()
        if arm == "baseline":
            doc = base_doc
            detail = {}
            boxes = base_boxes
        else:
            boxes = project_boxes(variants[arm], matrix)
            probability = (
                np.maximum(native, fused) if arm in ("zoom_verified", "combined") else native
            )
            openings, detail = opening_candidates(
                boundary_graph(boxes)[0],
                gray,
                probability,
                inverse,
                region_types=[b["type"] for b in boxes],
            )
            doc = authoring_document(
                old["authoring"]["image_evidence"]["source"],
                old["preprocessing"],
                boxes,
                openings,
                evidence_origin="classical",
            )
        errors = validate_authoring(doc)
        if errors:
            raise ValueError(errors)
        row = {
            "arm": arm,
            "rooms": sum((r["type"] == "room" for r in doc["topology"]["regions"])),
            "corridors": sum((r["type"] == "corridor_segment" for r in doc["topology"]["regions"])),
            "doors": sum((o["type"] == "door" for o in doc["topology"]["openings"])),
            "passages": sum((o["type"] == "open_passage" for o in doc["topology"]["openings"])),
            "elapsed_decode_seconds": time.perf_counter() - start,
        }
        write_json(
            output / (arm + ".json"),
            {
                "authoring": doc,
                "boxes": boxes,
                "opening_evidence": detail,
                "summary": row,
                "review_required": True,
            },
        )
        rows.append(row)
    write_json(
        output / "diagnostics.json",
        {
            "policy": POLICY,
            "parallel": p_detail,
            "bends": b_detail,
            "zoom": zoom,
            "production_changed": False,
            "training_run": False,
        },
    )
    write_json(output / "summary.json", rows)
    return (rows, old)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--zoom", action="store_true")
    args = p.parse_args()
    adapter = None
    if args.zoom:
        from .model import LocalSegmenter

        lock = json.loads(
            (ROOT / "SketchPipeline/shape_authoring/dinov2-candidate.lock.json").read_text()
        )
        adapter = LocalSegmenter(ROOT / lock["checkpoint_path"], lock["checkpoint_sha256"])
    rows, _ = run_case(args.input, args.output, adapter)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
