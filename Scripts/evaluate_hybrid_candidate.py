import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import torch
from Scripts.train_hybrid_candidate import OUT, BASE, WallUNet, inputs, write, sha
from Scripts.hybrid_candidate_inference import (
    door_predictions,
    regions_from_predictions,
    HybridCandidate,
)
from Scripts.independent_boundary_experiment import counts, bbox_iou, metrics, polygons, polygon_iou


def summarize(rows):
    labelled = [r for r in rows if r["room_evaluable"]]
    return {
        "images": len(rows),
        "doors": metrics([r["doors"] for r in rows]),
        "rooms": metrics([r["rooms"] for r in labelled]),
        "room_labelled_images": len(labelled),
        "exact_room_count": sum(r["exact_count"] for r in labelled),
        "room_count_accuracy": sum(r["exact_count"] for r in labelled) / max(1, len(labelled)),
    }


def score(record, probability, doors, parameters):
    boxes, regions, _, attached = regions_from_predictions(probability, doors, parameters)
    return {
        "id": record["id"],
        "kind": record["kind"],
        "room_evaluable": bool(record["rooms"]),
        "doors": counts(boxes, record["boxes"], bbox_iou, 0.5),
        "rooms": (
            counts(polygons(regions), polygons(record["rooms"]), polygon_iou, 0.5)
            if record["rooms"]
            else None
        ),
        "exact_count": len(regions) == len(record["rooms"]),
        "predicted_room_count": len(regions),
        "expected_room_count": len(record["rooms"]),
        "unattached_door_count": sum(not value for value in attached),
    }


def run():
    from ultralytics import YOLO

    torch.set_num_threads(3)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    p = json.loads((OUT / "protocol.json").read_text())
    validation = [r for r in p["samples"] if r["split"] == "validation" and r["kind"] == "human"]
    wall_paths = [OUT / "wall-best.pt", OUT / "wall-last.pt"]
    door_paths = [
        OUT / "door-training/yolo11n/weights/best.pt",
        OUT / "door-training/yolo11n/weights/last.pt",
    ]
    wall_paths = list({sha(path): path for path in wall_paths}.values())
    door_paths = list({sha(path): path for path in door_paths}.values())
    wall_cache = {}
    door_cache = {}
    grays = {r["id"]: cv2.imread(r["image"], 0) for r in validation}
    for path in wall_paths:
        model = WallUNet()
        model.load_state_dict(torch.load(path, weights_only=True, map_location="cpu")["state_dict"])
        model.to(device).eval()
        with torch.inference_mode():
            wall_cache[str(path)] = {
                key: model(torch.from_numpy(inputs(gray)[None]).to(device))
                .sigmoid()[0, 0]
                .cpu()
                .numpy()
                for key, gray in grays.items()
            }
        print("Cached validation wall", path.name, flush=True)
    for path in door_paths:
        detector = YOLO(str(path))
        door_cache[str(path)] = {
            key: door_predictions(detector, gray, device) for key, gray in grays.items()
        }
        print("Cached validation doors", path.name, flush=True)
    configurations = []
    for wall in wall_paths:
        for door in door_paths:
            for wall_threshold in p["evaluation"]["wall_thresholds"]:
                for door_threshold in p["evaluation"]["door_thresholds"]:
                    for closing_kernel in p["evaluation"]["closing_kernels"]:
                        parameters = {
                            "wall_threshold": wall_threshold,
                            "door_threshold": door_threshold,
                            "closing_kernel": closing_kernel,
                        }
                        summary = summarize(
                            [
                                score(
                                    r,
                                    wall_cache[str(wall)][r["id"]],
                                    door_cache[str(door)][r["id"]],
                                    parameters,
                                )
                                for r in validation
                            ]
                        )
                        objective = (
                            summary["rooms"]["f1"]
                            + 0.25 * summary["room_count_accuracy"]
                            + 0.25 * summary["doors"]["f1"]
                        )
                        configurations.append(
                            {
                                "wall": str(wall),
                                "door": str(door),
                                "parameters": parameters,
                                "validation": summary,
                                "objective": objective,
                            }
                        )
    best = max(
        configurations,
        key=lambda r: (
            r["objective"],
            r["validation"]["doors"]["f1"],
            r["parameters"]["door_threshold"],
            -abs(r["parameters"]["wall_threshold"] - 0.5),
        ),
    )
    write(
        OUT / "validation-selection.json",
        {"selected": best, "configurations": configurations, "test_used_for_selection": False},
    )
    package = OUT / "candidate"
    package.mkdir(exist_ok=True)
    for kind in ["wall", "door"]:
        shutil.copy2(best[kind], package / (kind + ".pt"))
    lock = {
        "version": "hybrid-unet-yolo11/1.0",
        "wall": {"path": "wall.pt", "sha256": sha(package / "wall.pt")},
        "door": {"path": "door.pt", "sha256": sha(package / "door.pt")},
        "parameters": best["parameters"],
        "input_side": 1024,
        "door_full_and_tiled": True,
        "room_definition": p["room_definition"],
        "review_required": True,
        "production_promoted": False,
        "validation_objective": best["objective"],
    }
    write(package / "model-lock.json", lock)
    candidate = HybridCandidate(package / "model-lock.json")
    test = [r for r in p["samples"] if r["split"] == "test"]
    for r in json.loads((BASE / "stress-protocol.json").read_text())["samples"]:
        gray = cv2.resize(cv2.imread(r["image"], 0), (1024, 1024), interpolation=cv2.INTER_CUBIC)
        image = OUT / "stress" / Path(r["image"]).name
        image.parent.mkdir(exist_ok=True)
        cv2.imwrite(str(image), gray)
        test.append(
            {
                **r,
                "image": str(image),
                "boxes": [(np.asarray(b) * 2).tolist() for b in r["boxes"]],
                "rooms": [
                    [(np.asarray(part) * 2).tolist() for part in pieces] for pieces in r["rooms"]
                ],
            }
        )
    results = []
    for record in test:
        gray = cv2.imread(record["image"], 0)
        with torch.inference_mode():
            probability = (
                candidate.wall(torch.from_numpy(inputs(gray)[None]).to(device))
                .sigmoid()[0, 0]
                .cpu()
                .numpy()
            )
        doors = door_predictions(candidate.door, gray, device)
        results.append(score(record, probability, doors, best["parameters"]))
    summaries = {
        kind: summarize([r for r in results if r["kind"] == kind])
        for kind in ["human", "synthetic", "stress"]
    }
    photos = []
    for identifier, filename in [
        ("L", "WhatsApp Image 2026-11-09 at 13.26.15.jpeg"),
        ("U", "WhatsApp Image 2026-11-09 at 13.54.14.jpeg"),
    ]:
        prediction = candidate.predict(
            Path("/Users/pelinsukaleli/Downloads") / filename, OUT / "photos" / identifier
        )
        photos.append(
            {
                "case": identifier,
                "room_count": prediction["room_count"],
                "door_count": prediction["door_count"],
                "unattached_doors": sum(not v for v in prediction["door_attached_to_wall"]),
            }
        )
    report = {
        "version": p["version"],
        "test": summaries,
        "development_photos": photos,
        "parameters": best["parameters"],
        "selected_wall_epoch": torch.load(
            package / "wall.pt", weights_only=True, map_location="cpu"
        )["epoch"],
        "wall_epochs_run": len(json.loads((OUT / "wall-history.json").read_text())),
        "door_epochs_run": len((OUT / "door-training/yolo11n/results.csv").read_text().splitlines())
        - 1,
        "protocol": str(OUT / "protocol.json"),
        "model_lock": str(package / "model-lock.json"),
        "test_scope": p["evaluation"]["test_scope"],
        "production_promoted": False,
        "device": device,
    }
    write(OUT / "report.json", report)
    write(OUT / "test-per-image.json", results)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    run()
