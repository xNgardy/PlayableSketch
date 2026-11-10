import copy
import cv2
import numpy as np
from .geometry import line_evidence, length

CONFIG = dict(
    version="structural-evidence/1.0",
    grid_min_lines=8,
    grid_spacing_cv=0.18,
    grid_min_projection=0.32,
    grid_max_local_contrast=46,
    annotation_contrast_ratio=0.62,
    annotation_max_width_ratio=0.72,
)


def periodic_peaks(profile):
    p = np.asarray(profile, float)
    peaks = np.flatnonzero(
        (p >= CONFIG["grid_min_projection"]) & (p >= np.roll(p, 1)) & (p > np.roll(p, -1))
    )
    if len(peaks) < CONFIG["grid_min_lines"]:
        return ([], None)
    intervals = np.diff(peaks)
    candidates = sorted(set((int(x) for x in intervals if 8 <= x <= len(p) / 8)))
    best = None
    candidates = sorted(
        set(
            (
                round(float(x), 3)
                for seed in candidates
                for x in np.arange(max(8, seed - 0.75), seed + 0.751, 0.025)
            )
        )
    )
    for spacing in candidates:
        for anchor in peaks[:12]:
            distance = np.abs((peaks - anchor + spacing / 2) % spacing - spacing / 2)
            selected = peaks[distance <= 1.5]
            if len(selected) < max(CONFIG["grid_min_lines"], 0.8 * len(peaks)):
                continue
            steps = np.diff(selected) / spacing
            if np.mean(np.abs(steps - np.rint(steps))) > CONFIG["grid_spacing_cv"]:
                continue
            score = (len(selected), spacing)
            if best is None or score > best[0]:
                best = (score, selected.tolist(), float(spacing))
    return (best[1], best[2]) if best else ([], None)


def suppress_grid(gray):
    gray = np.asarray(gray, np.uint8)
    background = cv2.medianBlur(gray, 31)
    contrast = cv2.subtract(background, gray)
    faint = (contrast >= 4) & (contrast <= CONFIG["grid_max_local_contrast"])
    xs, sx = periodic_peaks(faint.mean(axis=0))
    ys, sy = periodic_peaks(faint.mean(axis=1))
    mask = np.zeros(gray.shape, np.uint8)
    for x in xs:
        mask[:, max(0, x - 2) : x + 3] = 255
    for y in ys:
        mask[max(0, y - 2) : y + 3, :] = 255
    mask[~faint] = 0
    cleaned = gray.copy()
    cleaned[mask > 0] = background[mask > 0]
    return (
        cleaned,
        mask,
        dict(
            x_lines=xs,
            y_lines=ys,
            x_spacing=sx,
            y_spacing=sy,
            suppressed_pixels=int((mask > 0).sum()),
            limitation="Only confident axis-aligned periodic families; no forced perspective rectification.",
        ),
    )


def stroke_features(gray, lines):
    bg = cv2.medianBlur(gray, 31)
    contrast = cv2.subtract(bg, gray).astype(float)
    meaningful = contrast[contrast > 25]
    reference = float(np.percentile(meaningful, 85)) if len(meaningful) else 255.0
    output = []
    for line in lines:
        a, b = (np.asarray(line["start"]), np.asarray(line["end"]))
        direction = (b - a) / max(np.linalg.norm(b - a), 1e-06)
        normal = np.array([-direction[1], direction[0]])
        ts = np.linspace(0.08, 0.92, max(5, min(100, round(length(line) / 3))))
        pts = a[None, :] + ts[:, None] * (b - a)[None, :]
        ribbon = pts[:, None, :] + np.arange(-5, 6)[None, :, None] * normal[None, None, :]
        q = np.rint(ribbon).astype(int)
        q[:, :, 0] = np.clip(q[:, :, 0], 0, gray.shape[1] - 1)
        q[:, :, 1] = np.clip(q[:, :, 1], 0, gray.shape[0] - 1)
        values = contrast[q[:, :, 1], q[:, :, 0]]
        strongest = values.max(axis=1)
        local_contrast = float(np.median(strongest))
        width = float(np.median((values > max(20, 0.5 * local_contrast)).sum(axis=1)))
        output.append(
            dict(
                contrast=local_contrast,
                contrast_ratio=local_contrast / max(reference, 1),
                width_px=width,
            )
        )
    strong_widths = [f["width_px"] for f in output if f["contrast_ratio"] >= 0.8]
    reference_width = float(np.median(strong_widths)) if strong_widths else 3.0
    for f in output:
        f["width_ratio"] = f["width_px"] / max(reference_width, 1)
    return output


def classify_lines(gray, lines):
    result = copy.deepcopy(lines)
    features = stroke_features(gray, lines)
    for line, f in zip(result, features):
        weak_thin = (
            f["contrast_ratio"] < CONFIG["annotation_contrast_ratio"]
            and f["width_ratio"] <= CONFIG["annotation_max_width_ratio"]
        )
        line["structural_features"] = f
        line["structural_class"] = (
            "dimension_graphic_candidate"
            if weak_thin
            else "wall_candidate" if line["role"] == "wall_candidate" else "unknown"
        )
        if weak_thin:
            line["role"] = "annotation_candidate"
    return result


def structural_evidence(gray, polygons, profile):
    if profile not in ("baseline", "grid", "structural"):
        raise ValueError("Unknown geometry profile")
    cleaned, grid_mask, grid_info = (
        suppress_grid(gray) if profile != "baseline" else (gray.copy(), np.zeros_like(gray), None)
    )
    detectors, geometry, masks = line_evidence(cleaned, polygons)
    if profile == "structural":
        for method in detectors:
            detectors[method] = classify_lines(gray, detectors[method])
            geometry["recovery_lines"][method] = classify_lines(
                gray, geometry["recovery_lines"][method]
            )
    geometry["structural_experiment"] = dict(profile=profile, config=CONFIG, grid=grid_info)
    masks["grid_suppression"] = grid_mask
    masks["geometry_input"] = cleaned
    return (detectors, geometry, masks)


def structural_lines(lines):
    return [line for line in lines if line.get("structural_class") != "dimension_graphic_candidate"]
