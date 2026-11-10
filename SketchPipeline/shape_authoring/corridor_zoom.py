from pathlib import Path
import time
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import decode
from SketchPipeline.perception.structural import suppress_grid
from .contrast import normalize_ink


def inspect_crops(image, original_to_native, shape, candidates, adapter, output):
    original = cv2.cvtColor(decode(Path(image))[0], cv2.COLOR_RGB2GRAY)
    matrix = np.asarray(original_to_native, float)
    fused = np.zeros((6, *shape), np.float32)
    records = []
    for index, candidate in enumerate(candidates[:8]):
        x, y, X, Y = candidate["bounds_px"]
        margin = max(min(X - x, Y - y) * 2, max(shape) * 0.08)
        x, y, X, Y = (
            max(0, x - margin),
            max(0, y - margin),
            min(shape[1], X + margin),
            min(shape[0], Y + margin),
        )
        scale = 512 / max(X - x, Y - y)
        dx, dy = ((512 - (X - x) * scale) / 2, (512 - (Y - y) * scale) / 2)
        native_to_crop = np.array(
            [[scale, 0, dx - x * scale], [0, scale, dy - y * scale], [0, 0, 1.0]]
        )
        original_to_crop = native_to_crop @ matrix
        crop = cv2.warpPerspective(
            original, original_to_crop, (512, 512), flags=cv2.INTER_LINEAR, borderValue=255
        )
        cleaned, _, _ = suppress_grid(crop)
        content = [round(dx), round(dy), round(512 - dx), round(512 - dy)]
        raw, _ = normalize_ink(crop, content)
        clean, _ = normalize_ink(cleaned, content)
        started = time.perf_counter()
        probability = adapter.predict(raw, clean)
        projected = np.stack(
            [
                cv2.warpPerspective(
                    c, np.linalg.inv(native_to_crop), (shape[1], shape[0]), flags=cv2.INTER_LINEAR
                )
                for c in probability
            ]
        )
        fused = np.maximum(fused, projected)
        a, b, A, B = map(round, candidate["bounds_px"])
        region = projected[2, b:B, a:A]
        record = {
            "candidate_bounds_native": candidate["bounds_px"],
            "crop_bounds_native": [x, y, X, Y],
            "original_to_crop": original_to_crop.tolist(),
            "crop_to_native": np.linalg.inv(native_to_crop).tolist(),
            "corridor_mean": float(region.mean()),
            "corridor_fraction_above_0_5": float((region > 0.5).mean()),
            "inference_seconds": time.perf_counter() - started,
            "new_real_model_inference": True,
        }
        records.append(record)
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output / f"crop-{index}.png"), crop)
        np.savez_compressed(output / f"crop-{index}-masks.npz", probabilities=probability)
    return (fused, records)
