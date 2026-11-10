import argparse
import copy
import html
import inspect
import json
import sys
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from . import decoder_refined as decoder
from .dino_region_audit import ROOT, sha
from .evaluate_region_recovery import signature
from .human_error_review import reference
from .dino_keypoints import endpoint_peaks
from SketchPipeline.evaluation.metrics import pairs, endpoint_error


def save(path, value):
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=lambda x: x.item() if isinstance(x, np.generic) else x.tolist(),
        )
    )


def observe(call):
    function = decoder.opening_candidates
    lines, first = inspect.getsourcelines(function)
    targets = {}
    for token in (
        "for begin,end in runs(~occupied):",
        "if width<minimum",
        "kind='door';ends=",
        "kind='open_passage';ends=",
        "record['status']='needs_attention'",
    ):
        targets[token] = first + next((i for i, line in enumerate(lines) if token in line))
    segments = {}
    gaps = []
    gates = []

    def trace(frame, event, arg):
        if frame.f_code != function.__code__:
            return None
        if event == "line":
            v = frame.f_locals
            line = frame.f_lineno
            if line == targets["for begin,end in runs(~occupied):"]:
                key = v["segment"]
                if key not in segments:
                    segments[key] = {
                        "segment": key,
                        "owners": list(v["owners"]),
                        "axis": v["axis"],
                        "fixed": v["fixed"],
                        "radius": v["radius"],
                        "start": v["start"],
                        "stop": v["stop"],
                        "occupied": v["occupied"].tolist(),
                    }
            elif line == targets["if width<minimum"]:
                gaps.append(
                    {
                        "segment": v["segment"],
                        "native_gap_px": [v["gap_lo"], v["gap_hi"]],
                        "width": v["width"],
                        "minimum": v["minimum"],
                        "maximum": max(v["gray"].shape)
                        * decoder.POLICY["maximum_gap_side_fraction"],
                        "width_pass": bool(
                            v["minimum"]
                            <= v["width"]
                            <= max(v["gray"].shape) * decoder.POLICY["maximum_gap_side_fraction"]
                        ),
                    }
                )
            elif line in [
                targets[t]
                for t in (
                    "kind='door';ends=",
                    "kind='open_passage';ends=",
                    "record['status']='needs_attention'",
                )
            ]:
                tests = {
                    "raw_tick": v["raw"] >= decoder.POLICY["raw_tick_min_support"],
                    "semantic": v["semantic"] >= decoder.POLICY["model_tick_center_min"],
                    "wall": min(v["supports"]) >= decoder.POLICY["wall_support_min"],
                    "clear_gap": v["gap_clear"] >= decoder.POLICY["gap_clear_min"],
                    "clear_span": v["clear_span"]
                    >= v["stroke"] * decoder.POLICY["minimum_clear_span_strokes"],
                    "interface": v["interface"] >= decoder.POLICY["model_interface_min"],
                }
                gates.append(
                    {
                        **copy.deepcopy(v["record"]),
                        "tests": tests,
                        "branch": (
                            "door"
                            if line == targets["kind='door';ends="]
                            else (
                                "open_passage"
                                if line == targets["kind='open_passage';ends="]
                                else "reject"
                            )
                        ),
                        "model_supported": bool(v["model_supported"]),
                        "strong_raw": bool(v["strong_raw"]),
                        "clear_span_px": v["clear_span"],
                    }
                )
        return trace

    previous = sys.gettrace()
    try:
        sys.settrace(trace)
        result = call()
    finally:
        sys.settrace(previous)
    return (
        result,
        {"segments": list(segments.values()), "all_gaps": gaps, "gate_evaluations": gates},
    )


def audit(study, baseline, output):
    output.mkdir(parents=True, exist_ok=False)
    protected = list(json.loads((baseline / "freeze.json").read_text())["source_hashes"])
    protected += [
        "SketchPipeline/shape_authoring/models/shape-dinov2-decoder-v1.pt",
        "SketchPipeline/shape_authoring/models.lock.json",
    ]
    protected_hashes = {p: sha(ROOT / p) for p in protected}
    inputs = {}
    replays = []
    cases = []
    folders = sorted((study / "evaluation/human").glob("Data_*/dino")) + sorted(
        (study / "evaluation/synthetic").glob("*/dino")
    )
    baseline_report = json.loads((baseline / "report.json").read_text())
    metrics = {r["sample_id"]: r for r in baseline_report["rows"] if r["arm"] == "supported"}
    for folder in folders:
        sample = folder.parent.name
        kind = folder.parent.parent.name
        for name in ("proposals.json", "working.png", "evidence.png", "model-masks.npz"):
            inputs[str((folder / name).relative_to(ROOT))] = sha(folder / name)
        old = json.loads((folder / "proposals.json").read_text())
        gray = cv2.imread(str(folder / "evidence.png"), 0)
        working = cv2.imread(str(folder / "working.png"), 0)
        with np.load(folder / "model-masks.npz") as cache:
            native = cache["native_probabilities"]
        matrix = np.asarray(old["preprocessing"]["original_to_working"]) @ np.asarray(
            old["evidence_preprocessing"]["working_to_original"]
        )

        def run():
            return decoder.decode(
                gray,
                native,
                old["authoring"]["image_evidence"]["source"],
                old["evidence_preprocessing"],
                working_gray=working,
                working_metadata=old["preprocessing"],
                evidence_to_working=matrix,
            )

        plain = run()
        traced, detail = observe(run)
        if len(detail["gate_evaluations"]) != sum((g["width_pass"] for g in detail["all_gaps"])):
            raise ValueError("Incomplete gate observation: " + sample)
        saved = json.loads((baseline / kind / sample / "supported/prediction.json").read_text())
        if (
            plain != traced
            or signature(plain[0]) != signature(saved["authoring"])
            or plain[1] != saved["decoder"]
        ):
            raise ValueError("Replay differs: " + sample)
        replays.append(sample)
        if kind == "human" and metrics[sample]["role"] in ("validation", "test"):
            directory = output / sample
            directory.mkdir()
            save(directory / "trace.json", detail)
            cases.append((folder, old, saved, detail, matrix, gray, directory))
    rows = []
    figures = []
    for folder, old, saved, trace, matrix, gray, directory in cases:
        sample = folder.parent.name
        n = int(sample.split("_")[1])
        row = metrics[sample]
        ref = reference(n, old["preprocessing"])
        top = saved["authoring"]["topology"]
        mapping = row["metrics"]["region_id_mapping"]
        found = set(mapping.values())
        tolerance = max(old["preprocessing"]["working_size_px"]) * 0.04
        matched = {
            j
            for i, j, c in pairs(
                top["openings"],
                ref["openings"],
                lambda a, b: (
                    endpoint_error(a["geometry"]["points_px"], b["points_px"])
                    if a["type"] == b["type"]
                    else float("inf")
                ),
                tolerance,
            )
        }
        inv = np.linalg.inv(matrix)

        def native_points(points):
            p = np.c_[np.asarray(points), np.ones(len(points))] @ inv.T
            return p[:, :2] / p[:, 2:]

        with np.load(folder / "native-auxiliary-masks.npz") as cache:
            peaks = endpoint_peaks(cache["probabilities"][6])
        inputs[str((folder / "native-auxiliary-masks.npz").relative_to(ROOT))] = sha(
            folder / "native-auxiliary-masks.npz"
        )
        image = Image.fromarray(gray).convert("RGB")
        draw = ImageDraw.Draw(image)
        for region in top["regions"]:
            points = native_points(region["geometry"]["points_px"])
            draw.line([tuple(p) for p in points] + [tuple(points[0])], fill="orange", width=1)
        for p in peaks:
            x, y = p
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline="magenta", width=2)
        for s in trace["segments"]:
            axis = s["axis"]
            a = [s["start"], s["fixed"]] if axis == 0 else [s["fixed"], s["start"]]
            b = [s["stop"], s["fixed"]] if axis == 0 else [s["fixed"], s["stop"]]
            draw.line([tuple(a), tuple(b)], fill="cyan", width=1)
        for index, opening in enumerate(ref["openings"]):
            if index in matched:
                continue
            points = native_points(opening["points_px"])
            missing = sorted(set(opening["entity_ids"]) - found)
            shared = [
                s
                for s in trace["segments"]
                if set((mapping.get(top["regions"][i]["id"], "?") for i in s["owners"]))
                == set(opening["entity_ids"])
            ]
            detail = {
                "sample_id": sample,
                "role": row["role"],
                "opening_id": opening["id"],
                "type": opening["type"],
                "reference_native_px": points.tolist(),
                "reference_owners": opening["entity_ids"],
                "missing_regions": missing,
                "approximate_reference": True,
                "diagnostic_only": True,
            }
            if not opening["entity_ids"]:
                reason = "unknown_reference_owners"
            elif missing:
                reason = "missing_region"
            elif not shared:
                reason = "no_shared_boundary"
            else:
                reason = "shared_boundary_present"
                s = min(shared, key=lambda s: abs(points[:, 1 - s["axis"]].mean() - s["fixed"]))
                candidates = [g for g in trace["all_gaps"] if g["segment"] == s["segment"]]
                along = sorted(points[:, s["axis"]].tolist())
                detail["search"] = {k: v for k, v in s.items() if k != "occupied"}
                detail["normal_offsets_px"] = (points[:, 1 - s["axis"]] - s["fixed"]).tolist()
                for g in candidates:
                    g = dict(g)
                    g["endpoint_mean_error_px"] = (
                        sum((abs(a - b) for a, b in zip(g["native_gap_px"], along))) / 2
                    )
                    detail.setdefault("gap_candidates", []).append(g)
                detail["gates"] = [
                    g
                    for g in trace["gate_evaluations"]
                    if np.array_equal(g["segment"], s["segment"])
                ]
                for g in detail.get("gap_candidates", []):
                    axis = s["axis"]
                    coords = [
                        (v, s["fixed"]) if axis == 0 else (s["fixed"], v)
                        for v in g["native_gap_px"]
                    ]
                    draw.line(coords, fill="blue", width=3)
            detail["stage"] = reason
            detail["near_endpoint_peaks_px"] = (
                [
                    min((float(np.linalg.norm(np.asarray(p) - q)) for p in peaks), default=None)
                    for q in points
                ]
                if opening["type"] == "door"
                else None
            )
            rows.append(detail)
            draw.line([tuple(p) for p in points], fill="red", width=4)
            draw.text(tuple(points.mean(axis=0) + [8, 0]), opening["id"], fill="red")
        image.save(directory / "audit.png")
        selected = [r for r in rows if r["sample_id"] == sample]
        save(directory / "missed-openings.json", selected)
        if selected:
            figures.append(
                "<section><h2>"
                + sample
                + " / "
                + row["role"]
                + '</h2><img src="'
                + sample
                + '/audit.png"><pre>'
                + html.escape((directory / "missed-openings.json").read_text())
                + "</pre></section>"
            )
    changed = [p for p, h in inputs.items() if sha(ROOT / p) != h]
    if changed:
        raise ValueError("Cached inputs changed")
    if any((sha(ROOT / p) != h for p, h in protected_hashes.items())):
        raise ValueError("Protected source or weights changed")
    report = {
        "version": "connection-stage-audit/1.0",
        "scope": "Existing development data, approximate references; no training, inference, threshold changes or oracle injection.",
        "replay_count": len(replays),
        "traced_plain_and_saved_outputs_identical": True,
        "missing_counts": dict(Counter((r["role"] + ":" + r["stage"] for r in rows))),
        "rows": rows,
    }
    save(output / "report.json", report)
    save(
        output / "verification.json",
        {
            "all_110_replayed": len(replays) == 110,
            "plain_traced_saved_equal": True,
            "cached_inputs_checked": len(inputs),
            "changed": changed,
            "protected_hashes_unchanged": protected_hashes,
            "source_hashes": {
                str(p.relative_to(ROOT)): sha(p)
                for p in [
                    Path(__file__),
                    Path(decoder.__file__),
                    Path(decoder.__file__).with_name("decoder_refined.config.json"),
                ]
            },
            "input_hashes": inputs,
        },
    )
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Connection stage audit</title><style>body{font:15px system-ui;margin:24px}section{border:1px solid #ccc;padding:16px;margin:20px 0}img{width:640px;max-width:100%}pre{white-space:pre-wrap}</style><h1>Connection stage audit</h1><p>Diagnostic only. Red: approximate missed references. Orange: decoded regions. Cyan: actual fixed search axes. Blue: all gap candidates including width-rejected gaps. Magenta: independently extracted endpoint peaks. References never entered replay.</p>'
        + "".join(figures)
    )
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, default=ROOT / "Saved/ShapeFirst/dinov2/v1")
    parser.add_argument(
        "--baseline", type=Path, default=ROOT / "Saved/ShapeFirst/dinov2/decoder_recovery/v2/final"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.study, args.baseline, args.output)
