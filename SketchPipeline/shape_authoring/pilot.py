import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, Point
from SketchPipeline.evaluation.metrics import pairs, counts, endpoint_error, distribution
from SketchPipeline.preprocessing.prepare import project
from .decoder import iou
from .propose import run
from .synthetic import freeze, write_json

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def human_reference(n, preprocessing):
    folder = ROOT / "Data/annotations/v1"
    a = json.loads((folder / f"Data_{n}.annotations.json").read_text())
    forward = preprocessing["original_to_working"]
    regions = []
    for region in a.get("regions", []):
        points = project(region["polygon_px"], forward)
        regions.append(
            {
                "id": region["region_id"],
                "type": "corridor_segment" if region["kind"] == "corridor" else "room",
                "bounds_px": np.r_[points.min(axis=0), points.max(axis=0)].tolist(),
                "polygon": points.tolist(),
            }
        )
    openings = []
    for gap in a["gaps"]:
        if gap["kind"] not in ("door", "open_passage"):
            continue
        points = project([gap["start_px"], gap["end_px"]], forward)
        adjacent = []
        if regions:
            middle = Point(points.mean(axis=0))
            closest = sorted(
                [(Polygon(r["polygon"]).boundary.distance(middle), r["id"]) for r in regions]
            )
            if len(closest) >= 2 and closest[1][0] < max(preprocessing["working_size_px"]) * 0.04:
                adjacent = [closest[0][1], closest[1][1]]
        openings.append(
            {
                "id": gap["id"],
                "type": gap["kind"],
                "points_px": points.tolist(),
                "entity_ids": adjacent,
            }
        )
    return {
        "id": f"Data_{n}",
        "regions": regions,
        "openings": openings,
        "approximate_human_labels": True,
        "reference_policy_version": "structural-openings/2.0",
        "attachment_reference": "Nearest two approximate traced polygon boundaries; diagnostic only, not an independently verified exact-topology label.",
    }


def synthetic_reference(path):
    spec = json.loads(Path(path).read_text())
    openings = []
    for o in spec["openings"]:
        points = [[t, o["fixed"]] if o["axis"] == 0 else [o["fixed"], t] for t in o["interval"]]
        openings.append({**o, "points_px": points})
    return {**spec, "openings": openings, "approximate_human_labels": False}


def score(document, reference, size):
    top = document["topology"]
    pr = top["regions"]
    rr = reference["regions"]
    po = top["openings"]
    ro = reference["openings"]
    bounds = lambda e: np.r_[
        np.min(e["geometry"]["points_px"], axis=0), np.max(e["geometry"]["points_px"], axis=0)
    ]
    matches = pairs(pr, rr, lambda a, b: 1 - iou(bounds(a), b["bounds_px"]), 0.5) if rr else []
    mapping = {pr[i]["id"]: rr[j]["id"] for i, j, _ in matches}
    location = pairs(
        po,
        ro,
        lambda a, b: (
            endpoint_error(a["geometry"]["points_px"], b["points_px"])
            if a["type"] == b["type"]
            else float("inf")
        ),
        max(size) * 0.04,
    )
    attached = sum(
        (
            set((mapping.get(e, "unmatched") for e in po[i]["entity_ids"]))
            == set(ro[j]["entity_ids"])
            for i, j, _ in location
            if ro[j]["entity_ids"]
        )
    )
    attach_den = sum((bool(ro[j]["entity_ids"]) for _, j, _ in location))
    predicted_relations = Counter(
        (
            (o["type"], tuple(sorted((mapping.get(e, "unmatched:" + e) for e in o["entity_ids"]))))
            for o in po
        )
    )
    true_relations = Counter(((o["type"], tuple(sorted(o["entity_ids"]))) for o in ro))
    region_metric = counts(len(matches), len(pr), len(rr)) if rr else None
    exact = (
        len(matches) == len(pr) == len(rr)
        and len(location) == len(po) == len(ro)
        and (predicted_relations == true_relations)
    )
    if reference["approximate_human_labels"] or not rr:
        exact = None
    doors_p = [o for o in po if o["type"] == "door"]
    doors_r = [o for o in ro if o["type"] == "door"]
    door_matches = pairs(
        doors_p,
        doors_r,
        lambda a, b: endpoint_error(a["geometry"]["points_px"], b["points_px"]),
        max(size) * 0.04,
    )
    return {
        "regions": region_metric,
        "openings": counts(len(location), len(po), len(ro)),
        "doors": counts(len(door_matches), len(doors_p), len(doors_r)),
        "region_bounds_error_px": distribution(
            [float(np.max(np.abs(bounds(pr[i]) - rr[j]["bounds_px"]))) for i, j, _ in matches]
        ),
        "opening_endpoint_error_px": distribution([e for _, _, e in location]),
        "attachment_correct": attached,
        "attachment_scorable": attach_den,
        "exact_topology": exact,
        "false_connections": (
            len(po) - attached if not reference["approximate_human_labels"] else None
        ),
        "duplicate_connections": (
            sum(
                (max(0, n - true_relations.get(pair, 0)) for pair, n in predicted_relations.items())
            )
            if not reference["approximate_human_labels"]
            else None
        ),
        "region_id_mapping": mapping,
        "human_correction_time_seconds": None,
    }


def aggregate(rows):
    out = {}
    for key in ("regions", "openings", "doors"):
        records = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        out[key] = counts(
            sum((r["true_positive"] for r in records)),
            sum((r["predicted"] for r in records)),
            sum((r["reference"] for r in records)),
        )
    exact = [
        r["metrics"]["exact_topology"] for r in rows if r["metrics"]["exact_topology"] is not None
    ]
    out.update(
        exact_topology_successes=sum(exact),
        exact_topology_scorable=len(exact),
        exact_topology_fraction=sum(exact) / len(exact) if exact else None,
        attachment_correct=sum((r["metrics"]["attachment_correct"] for r in rows)),
        attachment_scorable=sum((r["metrics"]["attachment_scorable"] for r in rows)),
        elapsed_seconds=distribution([r["elapsed_seconds"] for r in rows]),
        manual_required=sum((r["status"] == "manual_required" for r in rows)),
        false_connections=sum((r["metrics"]["false_connections"] or 0 for r in rows)),
        duplicate_connections=sum((r["metrics"]["duplicate_connections"] or 0 for r in rows)),
        human_correction_time_seconds=None,
        samples=len(rows),
    )
    return out


def draw_preview(image, document, reference, path):
    panel = (
        Image.open(image)
        .convert("RGB")
        .resize(tuple(document["image_evidence"]["working_size_px"]))
    )
    panel = panel.resize((panel.width * 2, panel.height * 2))
    draw = ImageDraw.Draw(panel)
    for region in reference["regions"]:
        draw.rectangle([v * 2 for v in region["bounds_px"]], outline="#16a34a", width=2)
    for r in document["topology"]["regions"]:
        pts = r["geometry"]["points_px"]
        bounds = np.r_[np.min(pts, axis=0), np.max(pts, axis=0)]
        draw.rectangle((bounds * 2).tolist(), outline="#e87916", width=2)
        draw.text((bounds[0] * 2 + 3, bounds[1] * 2 + 3), r["id"], fill="#b45309")
    for opening in document["topology"]["openings"]:
        draw.line(
            [tuple(np.array(p) * 2) for p in opening["geometry"]["points_px"]],
            fill="#ef4444",
            width=4,
        )
    panel.save(path)


def pilot(output):
    import torch

    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    protocol = freeze(output)
    arms = ["classical", "candidate_12", "candidate_20"]
    sources = sorted(Path(__file__).parent.glob("*.py")) + [
        Path(__file__).with_name("proposals.config.json")
    ]
    protected = [
        p for p in (ROOT / "Data").rglob("*") if p.is_file() and "__pycache__" not in p.parts
    ]
    fingerprints = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    manifest = {
        "protocol_sha256": sha(output / "protocol.json"),
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "model_hashes": {arm: sha(output / arm / "model.pt") for arm in arms if arm != "classical"},
        "protected_files": fingerprints,
        "preflight": "Decoder development used 2000_wavy; this remains a development study, not a fresh holdout.",
    }
    manifest_path = output / "comparison-freeze.json"
    if manifest_path.exists():
        raise ValueError("Comparison already frozen. Preserve it and choose a new run version.")
    write_json(manifest_path, manifest)
    samples = []
    for parent in protocol["development_parent_seeds"]:
        for style in protocol["development_styles"]:
            folder = output / "development" / f"{parent}_{style}"
            samples.append(
                {
                    "id": f"{parent}_{style}",
                    "origin": "synthetic",
                    "style": style,
                    "parent_group": f"plan_{parent}",
                    "image": folder / "source.png",
                    "reference": folder / "reference.json",
                }
            )
    for n in protocol["human_development_ids"]:
        obs = json.loads((ROOT / f"Data/annotations/v1/Data_{n}.observations.json").read_text())
        samples.append(
            {
                "id": f"Data_{n}",
                "origin": "human",
                "style": "human",
                "parent_group": f"writer_unknown_Data_{n}",
                "image": (ROOT / "Data/annotations/v1" / obs["source"]["image_path"]).resolve(),
                "human_id": n,
            }
        )
    rows = []
    gallery = []
    for sample in samples:
        print(sample["id"], flush=True)
        for arm in arms:
            directory = output / "comparison" / sample["id"] / arm
            result = run(
                sample["image"],
                directory,
                backend="classical" if arm == "classical" else "learned",
                checkpoint=None if arm == "classical" else output / arm / "model.pt",
                expected_sha256=None if arm == "classical" else manifest["model_hashes"][arm],
            )
            reference = (
                human_reference(sample["human_id"], result["preprocessing"])
                if sample["origin"] == "human"
                else synthetic_reference(sample["reference"])
            )
            metrics = score(
                result["authoring"], reference, result["preprocessing"]["working_size_px"]
            )
            row = {
                "sample_id": sample["id"],
                "origin": sample["origin"],
                "style": sample["style"],
                "parent_group": sample["parent_group"],
                "arm": arm,
                "status": result["status"],
                "elapsed_seconds": result["elapsed_seconds"],
                "failure": result["failure"],
                "metrics": metrics,
            }
            rows.append(row)
            write_json(directory / "metrics.json", row)
            draw_preview(
                directory / "working.png",
                result["authoring"],
                reference,
                directory / "comparison.png",
            )
            gallery.append(
                f"""<figure><figcaption>{html.escape(sample['id'])} · {arm} · regions {metrics['regions'] and metrics['regions']['true_positive']}/{len(reference['regions'])} · openings {metrics['openings']['true_positive']}/{len(reference['openings'])}</figcaption><img loading="lazy" src="{directory.relative_to(output).as_posix()}/comparison.png"></figure>"""
            )
    summary = {}
    for arm in arms:
        summary[arm] = {
            scope: aggregate(
                [r for r in rows if r["arm"] == arm and (scope == "all" or r["origin"] == scope)]
            )
            for scope in ("all", "synthetic", "human")
        }

    def ranking(arm):
        s = summary[arm]["synthetic"]
        return (
            s["exact_topology_fraction"] or 0,
            s["openings"]["f1"] or 0,
            s["regions"]["f1"] or 0,
            -(s["elapsed_seconds"]["p50"] or 0),
        )

    selected = max(arms[1:], key=ranking)
    s = summary[selected]["synthetic"]
    targets = protocol["targets"]
    gates = {
        key: (
            (s["regions"][key.removeprefix("region_")] or 0) >= target
            if key.startswith("region_")
            else (
                (s["openings"][key.removeprefix("opening_")] or 0) >= target
                if key.startswith("opening_")
                else (s["exact_topology_fraction"] or 0) >= target
            )
        )
        for key, target in targets.items()
    }
    changed = [path for path, expected in fingerprints.items() if sha(ROOT / path) != expected]
    report = {
        "version": "shape-pilot-report/1.0",
        "scope": protocol["scope"],
        "arms": summary,
        "selected_candidate": selected,
        "targets": targets,
        "target_checks": gates,
        "automation_targets_met": all(gates.values()),
        "protected_files_checked": len(fingerprints),
        "protected_files_changed": changed,
        "human_correction_time_seconds": None,
        "unseen_writer_generalization": "unknown",
        "human_attachment_labels": "Approximate polygon proximity only; human exact topology unscored.",
        "rows": rows,
        "comparison_freeze_sha256": sha(manifest_path),
        "selection_ranking": {a: list(ranking(a)) for a in arms},
    }
    write_json(output / "report.json", report)
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Shape proposals comparison</title><style>body{font:15px system-ui;background:#fafafa;margin:24px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0;padding:10px;background:white;border:1px solid #ddd}img{max-width:100%}figcaption{margin-bottom:8px}</style><h1>Shape proposals · development comparison</h1><p>Green: approximate/reference region bounds. Orange: proposed regions. Red: proposed openings. All proposals require review. Human correction time and unseen-writer accuracy are unknown.</p><main>'
        + "".join(gallery)
        + "</main>"
    )
    lock = {
        "version": "shape-model/1.0",
        "architecture": "shape-unet/1.0",
        "checkpoint_path": str((output / selected / "model.pt").relative_to(ROOT)),
        "checkpoint_sha256": manifest["model_hashes"][selected],
        "candidate_width": int(selected.split("_")[1]),
        "config_sha256": sha(Path(__file__).with_name("proposals.config.json")),
        "protocol_sha256": manifest["protocol_sha256"],
        "report_path": str((output / "report.json").relative_to(ROOT)),
        "automation_targets_met": all(gates.values()),
        "scope": "Local development model; every proposal requires user correction/review. Not an unseen-writer result.",
    }
    write_json(Path(__file__).with_name("models.lock.json"), lock)
    print(
        json.dumps({"selected": selected, "target_checks": gates, "protected_changes": changed}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "Saved/ShapeFirst/v1")
    args = parser.parse_args()
    pilot(args.output.resolve())
