import copy
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import decode, prepare, project
from SketchPipeline.perception.structural import suppress_grid

VERSION = "shape-diagnostic-preprocessing/1.0"


def suggest_crop(image):
    _, upright, _, _ = decode(image)
    height, width = upright.shape[:2]
    scale = min(1.0, 1024 / max(width, height))
    view = cv2.resize(
        cv2.cvtColor(upright, cv2.COLOR_RGB2GRAY),
        (max(1, round(width * scale)), max(1, round(height * scale))),
    )
    cleaned, _, _ = suppress_grid(view)
    lines = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(cleaned)[0]
    selected = []
    if lines is not None:
        for x, y, X, Y in lines.reshape(-1, 4):
            dx, dy = (abs(X - x), abs(Y - y))
            if np.hypot(dx, dy) >= max(view.shape) * 0.08 and min(dx, dy) <= max(dx, dy) * 0.2:
                selected.extend([[x, y], [X, Y]])
    if len(selected) < 8:
        return (None, {"status": "abstained", "reason": "fewer_than_four_long_strokes"})
    points = np.asarray(selected) / scale
    margin = max(width, height) * 0.04
    lo = np.maximum(0, np.floor(points.min(axis=0) - margin)).astype(int)
    hi = np.minimum([width, height], np.ceil(points.max(axis=0) + margin)).astype(int)
    crop = [int(lo[0]), int(lo[1]), int(hi[0]), int(hi[1])]
    retained_area = (hi - lo).prod() / (width * height)
    if retained_area < 0.12 or retained_area > 0.95 or min(hi - lo) < 32:
        return (
            None,
            {
                "status": "abstained",
                "reason": "crop_area_or_extent_guard",
                "retained_area_fraction": float(retained_area),
            },
        )
    return (
        crop,
        {
            "status": "candidate",
            "upright_crop": crop,
            "retained_area_fraction": float(retained_area),
            "warning": "Image-only candidate; content coverage is audited after prediction.",
        },
    )


def letterbox(gray, metadata, side):
    height, width = gray.shape
    if max(height, width) > side:
        raise ValueError("Letterbox side is smaller than the prepared image")
    left, top = ((side - width) // 2, (side - height) // 2)
    padded = cv2.copyMakeBorder(
        gray, top, side - height - top, left, side - width - left, cv2.BORDER_CONSTANT, value=255
    )
    result = copy.deepcopy(metadata)
    transform = np.array([[1.0, 0, left], [0, 1.0, top], [0, 0, 1.0]])
    forward = transform @ np.asarray(metadata["original_to_working"])
    result.update(
        original_to_working=forward.tolist(),
        working_to_original=np.linalg.inv(forward).tolist(),
        working_size_px=[side, side],
        diagnostic_content_bounds_px=[left, top, left + width, top + height],
    )
    result.setdefault("transform_chain", []).append(
        {"operation": "diagnostic_letterbox", "matrix": transform.tolist(), "size_px": [side, side]}
    )
    return (padded, result)


def prepare_variant(image, arm, baseline_gray, baseline_metadata, crop=None):
    if arm["name"] == "baseline_256":
        return (baseline_gray.copy(), copy.deepcopy(baseline_metadata))
    images, metadata = prepare(
        image,
        max_side=arm["max_side"],
        crop=crop if arm["crop"] else None,
        deskew_degrees=baseline_metadata.get("automatic_deskew_degrees", 0),
    )
    gray = images["gray"]
    if arm["square"]:
        gray, metadata = letterbox(gray, metadata, arm["max_side"])
    metadata["diagnostic_version"] = VERSION
    metadata["diagnostic_arm"] = arm["name"]
    return (gray, metadata)


def map_probabilities(probabilities, source_metadata, target_metadata):
    matrix = np.asarray(target_metadata["original_to_working"]) @ np.asarray(
        source_metadata["working_to_original"]
    )
    size = tuple(target_metadata["working_size_px"])
    mapped = np.stack(
        [
            cv2.warpPerspective(
                channel,
                matrix,
                size,
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            for channel in probabilities
        ]
    )
    support = np.ones(probabilities.shape[1:], np.uint8)
    if "diagnostic_content_bounds_px" in source_metadata:
        support[:] = 0
        x, y, X, Y = source_metadata["diagnostic_content_bounds_px"]
        support[y:Y, x:X] = 1
    coverage = cv2.warpPerspective(
        support,
        matrix,
        size,
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    mapped[:, coverage == 0] = 0
    return (mapped, coverage)
