import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from shapely.geometry import LineString, box
from shapely.ops import unary_union
from Scripts.independent_boundary_experiment import OUT, door_box, write


def generate(destination=OUT, seed_start=810000, count=20, split="test"):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "cache").mkdir(exist_ok=True)
    path = destination / "stress-protocol.json"
    if path.exists():
        return json.loads(path.read_text())["samples"]
    records = []
    for index in range(count):
        rng = np.random.default_rng(seed_start + index)
        width = int(rng.integers(16, 25))
        left = int(rng.integers(70, 100))
        middle = int(rng.integers(230, 270))
        right = int(rng.integers(385, 420))
        top = int(rng.integers(135, 170))
        bottom = int(rng.integers(310, 345))
        if index % 3 == 0:
            points = [(left, top), (middle, top), (middle, bottom), (right, bottom), (right, 90)]
        elif index % 3 == 1:
            points = [(left, top), (middle, top), (middle, bottom), (right, bottom)]
        else:
            points = [
                (left, bottom),
                (middle, bottom),
                (middle, top),
                (right, top),
                (right, bottom),
            ]
        body = unary_union(
            [
                LineString(points).buffer(width, join_style=2, cap_style=2),
                box(left - 45, points[0][1] - 50, left + 45, points[0][1] + 50),
                box(right - 45, points[-1][1] - 50, right + 45, points[-1][1] + 50),
            ]
        )
        door = index % 5 != 0
        choices = []
        boundary = list(body.exterior.coords)
        for a, b in zip(boundary, boundary[1:]):
            if a[1] != b[1] or abs(b[0] - a[0]) < 65:
                continue
            cx = (a[0] + b[0]) / 2
            y = a[1]
            span = min(85, abs(b[0] - a[0]) * 0.65)
            for direction in (-1, 1):
                candidate = box(
                    cx - span / 2,
                    min(y, y + direction * 85),
                    cx + span / 2,
                    max(y, y + direction * 85),
                )
                if (
                    candidate.intersection(body).area > 1e-6
                    or min(candidate.bounds) < 8
                    or max(candidate.bounds) > 504
                ):
                    continue
                if candidate.boundary.intersection(body.boundary).length > 40:
                    choices.append((candidate, cx, y))
        if not choices:
            raise RuntimeError("No nonoverlapping attached stress room")
        room, cx, cy = choices[int(rng.integers(len(choices)))]
        assert room.intersection(body).area < 1e-6
        endpoint_a = [cx - 12, cy]
        endpoint_b = [cx + 12, cy]
        gray = np.full((512, 512), 255, np.uint8)
        target = np.zeros((3, 512, 512), np.uint8)
        shapes = [body] + ([room] if door else [])
        for shape in shapes:
            polygon = np.asarray(shape.exterior.coords, np.int32)
            cv2.polylines(gray, [polygon], True, 40, 2)
            cv2.polylines(target[0], [polygon], True, 1, 2)
        doors = []
        if door:
            a, b = tuple(np.rint(endpoint_a).astype(int)), tuple(np.rint(endpoint_b).astype(int))
            cv2.line(gray, a, b, 255, 4)
            cv2.line(target[0], a, b, 0, 4)
            cv2.line(target[2], a, b, 1, 3)
            for x, y in [a, b]:
                cv2.line(gray, (x, y - 6), (x, y + 6), 40, 2)
                cv2.line(target[1], (x, y - 6), (x, y + 6), 1, 2)
            doors = [[endpoint_a, endpoint_b]]
        rotation = index % 4

        def rotate(points):
            points = np.asarray(points, float)
            for _ in range(rotation):
                points = np.c_[points[:, 1], 511 - points[:, 0]]
            return points.tolist()

        gray = np.rot90(gray, rotation).copy()
        target = np.rot90(target, rotation, axes=(1, 2)).copy()
        doors = [rotate(p) for p in doors]
        rooms = [[rotate(shape.exterior.coords)] for shape in shapes]
        contrast = float(rng.uniform(0.2, 1.0))
        background = np.tile(np.linspace(rng.uniform(180, 220), 245, 512), (512, 1))
        gray = np.uint8(
            np.clip(
                background - (255 - gray.astype(float)) * contrast + rng.normal(0, 0.8, gray.shape),
                0,
                255,
            )
        )
        identifier = f"Stress_{seed_start+index}"
        image = destination / "stress" / f"{identifier}.png"
        image.parent.mkdir(exist_ok=True)
        cv2.imwrite(str(image), gray)
        np.savez_compressed(
            destination / "cache" / f"{identifier}.npz",
            gray=gray,
            target=target,
            known=np.ones_like(target, dtype=np.float16),
        )
        records.append(
            {
                "id": identifier,
                "kind": "stress",
                "split": split,
                "image": str(image),
                "doors": doors,
                "boxes": [door_box(p) for p in doors],
                "rooms": rooms,
                "source_sha256": hashlib.sha256(gray.tobytes()).hexdigest(),
            }
        )
    write(
        path,
        {
            "seed_start": seed_start,
            "samples": records,
            "scope": (
                "Separate procedural U/L/S geometry stress test; no sample used in training, checkpoint selection or confidence selection. Not human generalization evidence."
                if split == "test"
                else "Procedural connected shapes assigned to the declared training or validation split; never reused as test samples."
            ),
        },
    )
    print("Frozen generated images", len(records))
    return records


if __name__ == "__main__":
    generate()
