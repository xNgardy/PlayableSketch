import cv2
import numpy as np

VERSION = "shape-photo-paper/1.1"


def normalize_ink(gray, content_bounds=None):
    if gray.dtype != np.uint8 or gray.ndim != 2:
        raise ValueError("Expected a uint8 grayscale image")
    sample = gray
    if content_bounds is not None:
        x, y, X, Y = map(int, content_bounds)
        if not 0 <= x < X <= gray.shape[1] or not 0 <= y < Y <= gray.shape[0]:
            raise ValueError("Invalid content bounds")
        sample = gray[y:Y, x:X]
    paper = float(np.percentile(sample, 90))
    dark = float(np.percentile(sample, 1))
    applied = paper < 235 and paper - dark >= 12
    gain = min(4.0, 220.0 / max(paper - dark, 25.0)) if applied else 1.0
    normalized = (
        np.clip((gray.astype(np.float32) - paper) * gain + 255, 0, 255).astype(np.uint8)
        if applied
        else gray.copy()
    )
    return (
        normalized,
        {
            "version": VERSION,
            "applied": applied,
            "paper_level": paper,
            "dark_percentile": dark,
            "statistics_content_bounds_px": (
                list(content_bounds) if content_bounds is not None else None
            ),
            "gain": gain,
            "geometry_transform": "identity",
            "numeric_text_read": False,
        },
    )
