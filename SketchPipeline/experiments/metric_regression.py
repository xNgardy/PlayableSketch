import argparse
from copy import deepcopy
import json
from pathlib import Path
from SketchPipeline.solver.linear import solve
from SketchPipeline.validation.validate import load_json

ROOT = Path(__file__).resolve().parents[2]


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for n in (1, 3, 8, 9, 10, 15, 18, 41, 49, 50):
        doc = load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json")
        notes = [
            "Manual topology + confirmed measurement associations are test inputs, not automatic predictions."
        ]
        if n in (9, 10):
            for r in doc["layout"]["rooms"] + doc["layout"]["corridors"]:
                vertices = r["boundary_vertex_ids"]
                if len(vertices) != 4:
                    raise ValueError("Expected legacy four-corner rectangle")
                for i, wid in enumerate(r["boundary_wall_ids"]):
                    wall = next((w for w in doc["layout"]["walls"] if w["id"] == wid))
                    a, b = (vertices[i], vertices[(i + 1) % 4])
                    if i >= 2:
                        a, b = (b, a)
                    wall.update(start_vertex_id=a, end_vertex_id=b)
            notes.append(
                "Legacy reversed unresolved wall directions explicitly normalized using CCW rectangle order; original JSON untouched."
            )
        for v in doc["layout"]["vertices"]:
            v["position_cm"] = [12345, -98765]
        for o in doc["layout"]["openings"]:
            o.update(center_offset_cm=777, clear_width_cm=333)
        relations = []
        if n == 8:
            relations = [
                {
                    "id": "alignment",
                    "type": "centered_opening",
                    "opening_id": "d0",
                    "state": "confirmed",
                    "note": "Explicit Data8 reference premise: door centered on left corridor interface.",
                },
                {
                    "id": "full-entrance",
                    "type": "full_span_opening",
                    "opening_id": "o-c0-rB",
                    "state": "confirmed",
                    "note": "Explicit Data8 reference premise: full centerline corridor entrance minus configured thickness.",
                },
            ]
            notes.append(
                "Data8 uses two explicit reference premises; without them it is underdetermined."
            )
        draft, report = solve(doc, relations=relations)
        report["test_input_notes"] = notes
        folder = output / f"Data_{n}"
        folder.mkdir()
        for filename, value in (("draft.json", draft), ("report.json", report)):
            (folder / filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        cases.append(
            {
                "case_id": f"Data_{n}",
                "linear_status": report["status"],
                "draft_status": draft["status"],
                "rank": report["rank"],
                "variables": report["variable_count"],
                "nullity": report["nullity"],
                "metric_valid": report["validation"]["metric_valid"],
                "schema_valid": report["validation"]["schema_valid"],
                "exportable": False,
                "test_input_notes": notes,
            }
        )
    summary = {
        "kind": "development_metric_regression",
        "algorithm_version": "metric-solver/1.0",
        "cases": cases,
        "notes": [
            "These are solver regressions on known topology, not end-to-end perception scores or held-out accuracy.",
            "No original image, annotation, accepted layout or model weights modified.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Offline Step 09 development regression, NOT perception accuracy evaluation."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output)
    for row in summary["cases"]:
        print(
            f"{row['case_id']}: {row['linear_status']}, rank={row['rank']}/{row['variables']}, metric_valid={row['metric_valid']}"
        )


if __name__ == "__main__":
    main()
