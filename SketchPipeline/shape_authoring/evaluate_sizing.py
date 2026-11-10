import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
from .sizing import recompute
from .sizing_preview import render
from .dino_region_audit import ROOT, sha


def evaluate(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "Saved/ShapeFirst/dinov2/corridor_passage/v2/full"
    frozen = {}
    rows = []
    figures = []
    for category in ["human", "synthetic"]:
        for case in sorted((source / category).iterdir()):
            path = case / "combined/prediction.json"
            frozen[str(path.relative_to(ROOT))] = sha(path)
            doc = json.loads(path.read_text())["authoring"]
            result = recompute(doc)
            folder = output / category / case.name
            folder.mkdir(parents=True)
            (folder / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
            (folder / "plan.svg").write_text(render(result))
            if result["preview"]:
                (folder / "canonical-preview.json").write_text(
                    json.dumps(result["preview"]["canonical"], indent=2, allow_nan=False)
                )
            row = {
                "case": case.name,
                "category": category,
                "status": result["status"],
                "issues": result["issues"],
                "solver": result.get("solver"),
                "exportable": result["exportable"],
                "metric_valid": (
                    result["preview"]["validation"]["metric_valid"] if result["preview"] else False
                ),
            }
            rows.append(row)
            figures.append(
                "<figure><figcaption>"
                + case.name
                + " · "
                + row["status"]
                + '</figcaption><img loading="lazy" src="'
                + str((folder / "plan.svg").relative_to(output))
                + '"></figure>'
            )
            print(json.dumps({"case": case.name, "status": result["status"]}), flush=True)
    assert all((sha(ROOT / p) == h for p, h in frozen.items()))
    report = {
        "scope": "Sizing of existing AI proposals, not new topology/perception accuracy. Incorrect source interpretations can still be sized.",
        "cases": len(rows),
        "status_counts": dict(Counter((r["status"] for r in rows))),
        "rows": rows,
        "cached_input_hashes": frozen,
        "inputs_changed": False,
        "model_inference_run": False,
        "all_exports_pending": all((not r["exportable"] for r in rows)),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    snapshots = output / "source_snapshot"
    snapshots.mkdir()
    sources = [
        Path(__file__),
        Path(__file__).with_name("sizing.py"),
        Path(__file__).with_name("sizing_qp.py"),
        Path(__file__).with_name("sizing_adapter.py"),
        Path(__file__).with_name("sizing_policy.v2.json"),
        Path(__file__).with_name("sizing_preview.py"),
    ]
    for p in sources:
        shutil.copyfile(p, snapshots / p.name)
    (output / "source-hashes.json").write_text(
        json.dumps({str(p.relative_to(ROOT)): sha(p) for p in sources}, indent=2)
    )
    (output / "gallery.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Sizing previews</title><style>body{font:15px system-ui;margin:24px;background:#f3f4f1}main{display:grid;grid-template-columns:repeat(2,1fr)}figure{border:1px solid #ddd;margin:10px;background:white;padding:12px}img{width:100%}</style><h1>Suggested plan sizes</h1><p>Design starting points, not measurements. These drafts require plan review. Sizing validity is separate from correct sketch interpretation.</p><main>'
        + "".join(figures)
        + "</main>"
    )
    print(json.dumps({"cases": len(rows), "status_counts": report["status_counts"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    evaluate(args.output)
