import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from SketchPipeline.evaluation.metrics import pairs, endpoint_error
from .human_error_review import reference
from .synthetic import write_json


def audit(output):
    output = Path(output).resolve()
    path = output / "opening-audit.json"
    if path.exists():
        raise ValueError("Opening audit already exists")
    protocol = json.loads((output / "protocol.json").read_text())
    endpoint_rows = {
        r["sample_id"]: r for r in json.loads((output / "keypoint-report.json").read_text())["rows"]
    }
    rows = []
    for role in ["validation", "test"]:
        for n in protocol["human_splits"][role]:
            folder = output / "evaluation/human" / f"Data_{n}" / "dino"
            result = json.loads((folder / "proposals.json").read_text())
            top = result["authoring"]["topology"]
            ref = reference(n, result["preprocessing"])
            mapping = json.loads((folder / "metrics.json").read_text())["metrics"][
                "region_id_mapping"
            ]
            tolerance = max(result["preprocessing"]["working_size_px"]) * 0.04
            opening_matches = pairs(
                top["openings"],
                ref["openings"],
                lambda a, b: (
                    endpoint_error(a["geometry"]["points_px"], b["points_px"])
                    if a["type"] == b["type"]
                    else float("inf")
                ),
                tolerance,
            )
            detected = {j: i for i, j, c in opening_matches}
            doors = [g for g in ref["openings"] if g["type"] == "door"]
            points = [point for g in doors for point in g["points_px"]]
            peaks = endpoint_rows[f"Data_{n}"]["prediction_points_px"]
            point_matches = pairs(
                peaks, points, lambda a, b: float(np.linalg.norm(np.asarray(a) - b)), tolerance
            )
            found_points = {j for i, j, c in point_matches}
            door_number = {g["id"]: i for i, g in enumerate(doors)}
            found_regions = set(mapping.values())
            for index, gap in enumerate(ref["openings"]):
                missing = sorted(set(gap["entity_ids"]) - found_regions)
                walls = [
                    wall["id"]
                    for wall in top["walls"]
                    if len(wall["entity_ids"]) == 2
                    and set((mapping.get(i, "unmatched") for i in wall["entity_ids"]))
                    == set(gap["entity_ids"])
                ]
                endpoints = (
                    all((door_number[gap["id"]] * 2 + i in found_points for i in (0, 1)))
                    if gap["type"] == "door"
                    else None
                )
                if index in detected:
                    reason = "location_detected"
                elif not gap["entity_ids"]:
                    reason = "reference_owners_unknown"
                elif missing:
                    reason = "connected_region_missing"
                elif not walls:
                    reason = "regions_found_but_no_shared_wall"
                elif gap["type"] == "open_passage":
                    reason = "shared_wall_exists_but_passage_not_proposed"
                elif not endpoints:
                    reason = "endpoint_head_incomplete"
                else:
                    reason = "regions_wall_and_endpoints_present_but_not_proposed"
                rows.append(
                    {
                        "sample_id": f"Data_{n}",
                        "role": role,
                        "opening_id": gap["id"],
                        "type": gap["type"],
                        "reason": reason,
                        "reference_region_ids": gap["entity_ids"],
                        "missing_region_ids": missing,
                        "shared_wall_ids": walls,
                        "both_endpoints_head_matched": endpoints,
                        "diagnostic_only": True,
                        "causal_failure_proven": False,
                    }
                )
    summary = {
        role: dict(Counter((r["reason"] for r in rows if r["role"] == role)))
        for role in ["validation", "test"]
    }
    value = {
        "version": "dino-opening-evidence-audit/1.0",
        "scope": "Post-selection inventory, approximate annotations; categories are not proven causes or new evaluation.",
        "summary": summary,
        "rows": rows,
        "thresholds_changed": False,
        "model_reselected": False,
    }
    write_json(path, value)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.output)
