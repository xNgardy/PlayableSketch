import argparse
import copy
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

VERSION = "shape-synthetic/1.0"
CHANNELS = ["wall", "room_interior", "corridor_interior", "tick", "junction", "open_interface"]
STYLES = ["clean", "wavy", "grid", "stray", "broken"]


def plan(seed):
    rng = np.random.default_rng(seed)
    x, y = (int(rng.integers(104, 146)), int(rng.integers(102, 150)))
    family = seed % 6
    if family < 2:
        regions = [("room_a", "room", [25, 35, x, 225]), ("room_b", "room", [x, 35, 231, 225])]
    elif family == 2:
        regions = [
            ("room_a", "room", [25, 25, x, 231]),
            ("room_b", "room", [x, 25, 231, y]),
            ("room_c", "room", [x, y, 231, 231]),
        ]
    elif family == 3:
        regions = [
            ("room_a", "room", [25, 25, x, y]),
            ("room_b", "room", [x, 25, 231, y]),
            ("room_c", "room", [25, y, x, 231]),
            ("room_d", "room", [x, y, 231, 231]),
        ]
    elif family == 4:
        regions = [
            ("room_a", "room", [25, 25, x, 125]),
            ("corridor_a", "corridor_segment", [x, 75, 185, 125]),
            ("corridor_b", "corridor_segment", [155, 125, 185, 175]),
            ("room_b", "room", [115, 175, 231, 231]),
        ]
    else:
        regions = [
            ("room_a", "room", [25, 25, x, 165]),
            ("room_b", "room", [x, 75, 231, 215]),
            ("room_c", "room", [35, 165, x, 231]),
        ]
    contacts = []
    for i, (aid, ak, a) in enumerate(regions):
        for bid, bk, b in regions[i + 1 :]:
            if a[2] == b[0] or b[2] == a[0]:
                axis, fixed, lo, hi = (1, max(a[0], b[0]), max(a[1], b[1]), min(a[3], b[3]))
            elif a[3] == b[1] or b[3] == a[1]:
                axis, fixed, lo, hi = (0, max(a[1], b[1]), max(a[0], b[0]), min(a[2], b[2]))
            else:
                continue
            if hi - lo < 20:
                continue
            kind = "open_passage" if "corridor_segment" in (ak, bk) else "door"
            count = 2 if family == 1 else 1
            if kind == "open_passage":
                intervals = [[lo + 5, hi - 5]]
            elif count == 2:
                intervals = [[lo + (hi - lo) * f - 9, lo + (hi - lo) * f + 9] for f in (0.27, 0.72)]
            else:
                center = lo + (hi - lo) * float(rng.uniform(0.35, 0.65))
                width = min(float(rng.uniform(19, 29)), (hi - lo) * 0.42)
                intervals = [[center - width / 2, center + width / 2]]
            for interval in intervals:
                contacts.append(
                    {
                        "id": f"opening_{len(contacts) + 1}",
                        "entity_ids": [aid, bid],
                        "axis": axis,
                        "fixed": fixed,
                        "interval": interval,
                        "type": kind,
                    }
                )
    return {
        "id": f"plan_{seed}",
        "seed": seed,
        "family": family,
        "regions": [{"id": i, "type": k, "bounds_px": b} for i, k, b in regions],
        "openings": contacts,
    }


def render(seed, style, size=256, *, specification=None):
    if style not in STYLES:
        raise ValueError("Unknown synthetic style")
    specification = plan(seed) if specification is None else copy.deepcopy(specification)
    rng = np.random.default_rng(seed * 17 + STYLES.index(style))
    canvas = np.full((size, size), 255, np.uint8)
    masks = np.zeros((len(CHANNELS), size, size), np.uint8)
    scale = size / 256
    thickness = int(rng.integers(2, 4))
    wobble = 1.5 if style != "clean" else 0.15
    if style == "grid":
        for t in range(7, size, 13):
            cv2.line(canvas, (t, 0), (t, size - 1), 210, 1)
            cv2.line(canvas, (0, t), (size - 1, t), 210, 1)

    def stroke(a, b, channel, width=thickness):
        a, b = (np.asarray(a, float) * scale, np.asarray(b, float) * scale)
        length = np.linalg.norm(b - a)
        n = max(3, round(length / 4))
        points = np.linspace(a, b, n)
        normal = np.array([-(b - a)[1], (b - a)[0]]) / max(length, 1)
        phase = float(rng.uniform(0, 6.28))
        displacement = wobble * np.sin(np.linspace(phase, phase + float(rng.uniform(5, 10)), n))
        displacement[[0, -1]] = 0
        points += displacement[:, None] * normal
        points = np.rint(points).astype(np.int32)
        cv2.polylines(canvas, [points], False, int(rng.integers(10, 70)), width, cv2.LINE_AA)
        cv2.polylines(masks[channel], [points], False, 255, width + 1)

    all_corners = []
    boundaries = []
    for r in specification["regions"]:
        x0, y0, x1, y1 = r["bounds_px"]
        pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        all_corners.extend(pts)
        boundaries.extend(zip(pts, pts[1:] + pts[:1]))
        channel = 1 if r["type"] == "room" else 2
        cv2.rectangle(
            masks[channel],
            (round((x0 + 4) * scale), round((y0 + 4) * scale)),
            (round((x1 - 4) * scale), round((y1 - 4) * scale)),
            255,
            -1,
        )
    segments = set()
    for a, b in boundaries:
        axis = 0 if a[1] == b[1] else 1
        fixed = a[1 - axis]
        lo, hi = sorted((a[axis], b[axis]))
        cuts = sorted(
            {lo, hi} | {c[axis] for c in all_corners if c[1 - axis] == fixed and lo < c[axis] < hi}
        )
        segments.update(((axis, fixed, u, v) for u, v in zip(cuts, cuts[1:])))

    def point(axis, fixed, t):
        return [t, fixed] if axis == 0 else [fixed, t]

    for axis, fixed, lo, hi in sorted(segments):
        gaps = [
            o["interval"]
            for o in specification["openings"]
            if o["axis"] == axis
            and o["fixed"] == fixed
            and (o["interval"][0] >= lo)
            and (o["interval"][1] <= hi)
        ]
        if style == "broken" and rng.random() < 0.25 and (hi - lo > 60):
            c = (lo + hi) / 2
            gaps.append([c - 5, c + 5])
        at = lo
        for start, end in sorted(gaps):
            if start > at:
                stroke(point(axis, fixed, at), point(axis, fixed, start), 0)
            at = max(at, end)
        if at < hi:
            stroke(point(axis, fixed, at), point(axis, fixed, hi), 0)
    for o in specification["openings"]:
        axis, fixed = (o["axis"], o["fixed"])
        lo, hi = o["interval"]
        if o["type"] == "door":
            for t in (lo, hi):
                a = point(axis, fixed, t)
                b = a.copy()
                a[1 - axis] -= 6
                b[1 - axis] += 6
                stroke(a, b, 3, width=2)
        else:
            a, b = np.rint(
                np.asarray([point(axis, fixed, lo), point(axis, fixed, hi)]) * scale
            ).astype(int)
            cv2.line(masks[5], tuple(a), tuple(b), 255, 5)
    for corner in set(map(tuple, all_corners)):
        cv2.circle(masks[4], tuple(np.rint(np.array(corner) * scale).astype(int)), 4, 255, -1)
    if style in ("stray", "grid"):
        for _ in range(12):
            a = rng.integers(8, size - 8, 2)
            b = a + rng.integers(-6, 7, 2)
            cv2.line(canvas, tuple(a), tuple(b), int(rng.integers(60, 160)), 1)
        for _ in range(5):
            p = tuple(rng.integers(10, size - 35, 2))
            cv2.putText(
                canvas, str(int(rng.integers(10, 999))), p, cv2.FONT_HERSHEY_SIMPLEX, 0.3, 60, 1
            )
    noise = rng.normal(0, 1.5, canvas.shape)
    canvas = np.clip(canvas.astype(float) + noise, 0, 255).astype(np.uint8)
    return (canvas, masks, specification)


def write_json(path, value):

    def scalar(item):
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, np.ndarray):
            return item.tolist()
        raise TypeError(f"Unsupported JSON value: {type(item).__name__}")

    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False, default=scalar) + "\n")


def freeze(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "version": "shape-pilot/1.0",
        "seed": 220126,
        "generator_version": VERSION,
        "train_parent_seeds": list(range(1000, 1096)),
        "train_styles": ["clean", "wavy", "grid", "stray"],
        "development_parent_seeds": list(range(2000, 2012)),
        "development_styles": STYLES,
        "human_development_ids": [3, 8, 18, 31, 41, 45],
        "candidates": [12, 20],
        "epochs": 20,
        "batch_size": 12,
        "learning_rate": 0.002,
        "size": 256,
        "selection": "Highest development exact topology, then opening F1, then region F1, then lower latency.",
        "targets": {
            "region_precision": 0.8,
            "region_recall": 0.7,
            "opening_precision": 0.8,
            "opening_recall": 0.7,
            "exact_topology_fraction": 0.5,
        },
        "region_iou_threshold": 0.5,
        "opening_endpoint_tolerance_fraction": 0.04,
        "correction_time_seconds": None,
        "correction_time_status": "Requires a human reviewer; not inferred from errors.",
        "scope": "Development only. No unseen-writer/test generalization; synthetic derivatives grouped by parent seed.",
        "data_license": "New code-generated structural masks; no external images, pretrained weights or human mask supervision.",
        "model_license": "Project-authored architecture and newly trained weights; no imported pretrained model.",
        "cloud_transmission": False,
    }
    path = output / "protocol.json"
    if path.exists() and json.loads(path.read_text()) != protocol:
        raise ValueError("Frozen protocol differs; choose new output version")
    if not path.exists():
        write_json(path, protocol)
    return protocol


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("Saved/ShapeFirst/v1"))
    args = parser.parse_args()
    p = freeze(args.output)
    for seed in p["development_parent_seeds"]:
        for style in STYLES:
            image, masks, spec = render(seed, style)
            folder = args.output / "development" / f"{seed}_{style}"
            folder.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(folder / "source.png"), image)
            np.savez_compressed(folder / "masks.npz", masks=masks)
            write_json(folder / "reference.json", spec)
    print(
        json.dumps(
            {
                "protocol_sha256": hashlib.sha256(
                    (args.output / "protocol.json").read_bytes()
                ).hexdigest(),
                "development_images": 60,
            }
        )
    )
