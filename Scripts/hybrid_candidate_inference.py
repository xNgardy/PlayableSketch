import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import torch
from Scripts.train_hybrid_candidate import WallUNet, inputs
from Scripts.independent_boundary_experiment import components, write
from SketchPipeline.preprocessing.prepare import prepare
from SketchPipeline.shape_authoring.diagnostic_preprocessing import letterbox


def prepare_input(image):
    images, metadata = prepare(Path(image), max_side=1024)
    return letterbox(images["gray"], metadata, 1024)


def door_predictions(detector, gray, device):
    windows = [(0, 0, gray.shape[1], gray.shape[0])]
    for y in (0, 384):
        for x in (0, 384):
            windows.append((x, y, x + 640, y + 640))
    boxes = []
    scores = []
    for x, y, X, Y in windows:
        tile = cv2.cvtColor(gray[y:Y, x:X], cv2.COLOR_GRAY2RGB)
        result = detector.predict(tile, imgsz=640, device=device, conf=0.05, verbose=False)[0]
        for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
            if (
                x > 0
                and box[0] < 6
                or y > 0
                and box[1] < 6
                or X < gray.shape[1]
                and box[2] > X - x - 6
                or Y < gray.shape[0]
                and box[3] > Y - y - 6
            ):
                continue
            box = box + np.array([x, y, x, y])
            boxes.append(box)
            scores.append(float(score))
    if not boxes:
        return []
    from torchvision.ops import nms

    kept = nms(
        torch.tensor(np.asarray(boxes), dtype=torch.float32), torch.tensor(scores), 0.4
    ).tolist()
    return [(boxes[i].tolist(), scores[i]) for i in kept]


def seal_door(barrier, bounds):
    x, y, X, Y = bounds
    axis = 0 if X - x >= Y - y else 1
    normal = 1 - axis
    lo, hi = (x, X) if axis == 0 else (y, Y)
    low, high = (y, Y) if axis == 0 else (x, X)
    best = None
    for fixed in range(max(0, round(low) - 6), min(barrier.shape[normal], round(high) + 7)):
        strengths = []
        for start, end in [(lo - 20, lo + 4), (hi - 4, hi + 20)]:
            positions = np.arange(max(0, round(start)), min(barrier.shape[axis], round(end) + 1))
            normals = np.arange(max(0, fixed - 2), min(barrier.shape[normal], fixed + 3))
            patch = (
                barrier[np.ix_(normals, positions)]
                if axis == 0
                else barrier[np.ix_(positions, normals)].T
            )
            strengths.append(float(patch.max(0).mean()) if patch.size else 0.0)
        rank = (min(strengths), sum(strengths), -abs(fixed - (low + high) / 2))
        if best is None or rank > best[0]:
            best = (rank, fixed)
    if best is None or best[0][0] < 0.2:
        return False
    p, q = (
        ([lo - 6, best[1]], [hi + 6, best[1]])
        if axis == 0
        else ([best[1], lo - 6], [best[1], hi + 6])
    )
    cv2.line(barrier, tuple(np.rint(p).astype(int)), tuple(np.rint(q).astype(int)), 1, 6)
    return True


def regions_from_predictions(probability, doors, parameters):
    if probability.ndim != 2 or not np.isfinite(probability).all():
        raise ValueError("Expected a finite two-dimensional wall probability map")
    barrier = np.uint8(probability > parameters["wall_threshold"])
    boxes = [box for box, score in doors if score >= parameters["door_threshold"]]
    attached = [seal_door(barrier, box) for box in boxes]
    kernel = parameters["closing_kernel"]
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    masks, regions = components(barrier)
    return boxes, regions, barrier, attached


class HybridCandidate:
    def __init__(self, configuration):
        from ultralytics import YOLO

        self.path = Path(configuration).resolve()
        self.config = json.loads(self.path.read_text())
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        paths = {}
        for kind in ["wall", "door"]:
            path = Path(self.config[kind]["path"])
            if not path.is_absolute():
                path = self.path.parent / path
            if hashlib.sha256(path.read_bytes()).hexdigest() != self.config[kind]["sha256"]:
                raise ValueError(kind + " checkpoint checksum mismatch")
            paths[kind] = path
        self.wall = WallUNet()
        state = torch.load(paths["wall"], weights_only=True, map_location="cpu")
        if state.get("architecture") != "wall-unet/1.0":
            raise ValueError("Unexpected wall architecture")
        self.wall.load_state_dict(state["state_dict"])
        self.wall.to(self.device).eval()
        self.door = YOLO(str(paths["door"]))

    def predict(self, image, output):
        gray, metadata = prepare_input(image)
        with torch.inference_mode():
            probability = (
                self.wall(torch.from_numpy(inputs(gray)[None]).to(self.device))
                .sigmoid()[0, 0]
                .cpu()
                .numpy()
            )
        proposals = door_predictions(self.door, gray, self.device)
        boxes, regions, barrier, attached = regions_from_predictions(
            probability, proposals, self.config["parameters"]
        )
        inverse = np.asarray(metadata["working_to_original"])

        def original(points):
            p = np.c_[np.asarray(points), np.ones(len(points))] @ inverse.T
            return (p[:, :2] / p[:, 2:]).tolist()

        result = {
            "version": "hybrid-candidate-prediction/1.0",
            "image_sha256": hashlib.sha256(Path(image).read_bytes()).hexdigest(),
            "room_count": len(regions),
            "door_count": len(boxes),
            "door_attached_to_wall": attached,
            "room_type": "room",
            "regions_working_px": regions,
            "regions_original_px": [[original(p) for p in parts] for parts in regions],
            "door_boxes_working_px": boxes,
            "parameters": self.config["parameters"],
            "device": self.device,
            "review_required": True,
            "model_lock": str(self.path),
        }
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        write(output / "prediction.json", result)
        cv2.imwrite(str(output / "input.png"), gray)
        cv2.imwrite(str(output / "wall-mask.png"), np.uint8(probability * 255))
        cv2.imwrite(str(output / "closed-barrier.png"), 255 - barrier * 255)
        canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        for region in regions:
            for polygon in region:
                cv2.polylines(canvas, [np.rint(polygon).astype(np.int32)], True, (30, 150, 30), 3)
        for bounds in boxes:
            x, y, X, Y = np.rint(bounds).astype(int)
            cv2.rectangle(canvas, (x, y), (X, Y), (20, 30, 230), 3)
        cv2.imwrite(str(output / "overlay.png"), canvas)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-lock", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = HybridCandidate(args.model_lock).predict(args.image, args.output)
    print(
        json.dumps(
            {key: result[key] for key in ["room_count", "door_count", "device", "review_required"]}
        )
    )
