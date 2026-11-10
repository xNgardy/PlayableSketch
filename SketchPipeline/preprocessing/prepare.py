import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import warnings
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

VERSION = "playablesketch-preprocessing/1.0"
MAX_PIXELS = 40000000
MAX_BYTES = 20000000


class InputError(ValueError):
    pass


def project(points, matrix):
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or (not np.isfinite(points).all()):
        raise InputError("Points must be finite Nx2 coordinates.")
    h = np.asarray(matrix, dtype=np.float64)
    if h.shape != (3, 3) or not np.isfinite(h).all():
        raise InputError("Transform must be a finite 3x3 matrix.")
    mapped = np.column_stack((points, np.ones(len(points)))) @ h.T
    if np.any(np.abs(mapped[:, 2]) < 1e-12):
        raise InputError("Transform projects a point to infinity.")
    return mapped[:, :2] / mapped[:, 2:]


def exif_matrix(orientation, width, height):
    w, h = (width - 1, height - 1)
    matrices = {
        1: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        2: [[-1, 0, w], [0, 1, 0], [0, 0, 1]],
        3: [[-1, 0, w], [0, -1, h], [0, 0, 1]],
        4: [[1, 0, 0], [0, -1, h], [0, 0, 1]],
        5: [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
        6: [[0, -1, h], [1, 0, 0], [0, 0, 1]],
        7: [[0, -1, h], [-1, 0, w], [0, 0, 1]],
        8: [[0, 1, 0], [-1, 0, w], [0, 0, 1]],
    }
    if orientation not in matrices:
        raise InputError(f"Unsupported EXIF orientation: {orientation}")
    return np.asarray(matrices[orientation], dtype=np.float64)


def decode(path):
    path = Path(path)
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise InputError("Only JPG/JPEG/PNG inputs are supported.")
    try:
        if path.stat().st_size > MAX_BYTES:
            raise InputError("Image exceeds the 20 MB input limit.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                if im.format not in ("JPEG", "PNG"):
                    raise InputError("File contents must be JPEG or PNG.")
                if im.width * im.height > MAX_PIXELS or min(im.size) < 16:
                    raise InputError("Image must be at least 16x16 and at most 40 MP.")
                orientation = im.getexif().get(274, 1)
                transform = exif_matrix(orientation, *im.size)
                rgba = im.convert("RGBA")
                original = Image.alpha_composite(Image.new("RGBA", im.size, "white"), rgba).convert(
                    "RGB"
                )
                upright = ImageOps.exif_transpose(im).convert("RGBA")
                upright = Image.alpha_composite(
                    Image.new("RGBA", upright.size, "white"), upright
                ).convert("RGB")
                return (np.asarray(original), np.asarray(upright), transform, orientation)
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InputError(f"Cannot decode image: {exc}") from exc


def quality(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    scale = min(1.0, 1024 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    std = float(small.std())
    if std < 1.0:
        raise InputError("IMAGE_BLANK: insufficient image contrast.")
    lap = float(cv2.Laplacian(small, cv2.CV_64F).var())
    tiles = [
        float(x.mean()) for row in np.array_split(small, 4) for x in np.array_split(row, 4, axis=1)
    ]
    illumination = max(tiles) - min(tiles)
    issues = []
    if lap < 22:
        issues.append("IMAGE_SOFT_OR_FAINT")
    if illumination > 45:
        issues.append("IMAGE_UNEVEN_ILLUMINATION")
    if min(rgb.shape[:2]) < 400:
        issues.append("IMAGE_LOW_RESOLUTION")
    return {
        "gray_std": std,
        "laplacian_variance_1024": lap,
        "tile_mean_range": illumination,
        "issues": issues,
        "policy": "Heuristic warnings only; retain all image variants and strokes.",
    }


def prepare(
    path, *, max_side=1600, crop=None, deskew_degrees=0, page_corners=None, page_aspect_ratio=None
):
    if not isinstance(max_side, int) or not 64 <= max_side <= 8192:
        raise InputError("max_side must be an integer between 64 and 8192.")
    if not math.isfinite(deskew_degrees) or abs(deskew_degrees) > 45:
        raise InputError("Manual deskew must be within +/-45 degrees.")
    if (page_corners is None) != (page_aspect_ratio is None):
        raise InputError("Page corners and known width/height aspect ratio are required together.")
    if page_corners is not None and (crop is not None or deskew_degrees):
        raise InputError("Use either page rectification or crop/manual deskew.")
    original, rgb, matrix, orientation = decode(path)
    report = quality(rgb)
    chain = [{"operation": "exif", "matrix": matrix.tolist(), "orientation": orientation}]

    def apply(name, local, size):
        nonlocal matrix, rgb
        rgb = cv2.warpPerspective(
            rgb,
            local,
            size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        matrix = local @ matrix
        chain.append(
            {"operation": name, "matrix": local.tolist(), "size_px": [int(value) for value in size]}
        )

    h, w = rgb.shape[:2]
    if page_corners is not None:
        points = np.asarray(page_corners, dtype=np.float64)
        ratio = page_aspect_ratio
        if (
            points.shape != (4, 2)
            or not np.isfinite(points).all()
            or (not isinstance(ratio, (int, float)))
            or (not math.isfinite(ratio))
            or (not 0.1 <= ratio <= 10)
        ):
            raise InputError(
                "Provide four finite upright TL/TR/BR/BL corners and aspect ratio in [0.1,10]."
            )
        if np.any(points < 0) or np.any(points[:, 0] > w - 1) or np.any(points[:, 1] > h - 1):
            raise InputError("Page corners must lie inside the upright image.")
        contour = points.astype(np.float32)
        signed_area = cv2.contourArea(contour, oriented=True)
        if not cv2.isContourConvex(contour) or signed_area < 16:
            raise InputError(
                "Page corners must form a nondegenerate clockwise TL/TR/BR/BL polygon."
            )
        if ratio >= 1:
            dw, dh = (max_side, round((max_side - 1) / ratio) + 1)
        else:
            dh, dw = (max_side, round((max_side - 1) * ratio) + 1)
        dst = np.float32([[0, 0], [dw - 1, 0], [dw - 1, dh - 1], [0, dh - 1]])
        local = cv2.getPerspectiveTransform(contour, dst)
        apply("manual_page_homography", local, (dw, dh))
    else:
        report["issues"].append("PAGE_RECTIFICATION_NOT_REQUESTED")
        if crop is not None:
            if len(crop) != 4 or any((type(v) is not int for v in crop)):
                raise InputError("Crop must be integer [left,top,right,bottom] in upright pixels.")
            left, top, right, bottom = crop
            if (
                not (0 <= left < right <= w and 0 <= top < bottom <= h)
                or min(right - left, bottom - top) < 16
            ):
                raise InputError("Crop must be inside the upright frame and at least 16x16.")
            rgb = rgb[top:bottom, left:right].copy()
            local = np.array([[1.0, 0, -left], [0, 1.0, -top], [0, 0, 1.0]])
            matrix = local @ matrix
            chain.append({"operation": "manual_crop", "matrix": local.tolist(), "crop": crop})
        if deskew_degrees:
            h, w = rgb.shape[:2]
            affine = cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), deskew_degrees, 1)
            local = np.vstack((affine, [0, 0, 1]))
            corners = project([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], local)
            lo, hi = (np.floor(corners.min(axis=0)), np.ceil(corners.max(axis=0)))
            local[:2, 2] -= lo
            apply("manual_deskew", local, tuple((hi - lo + 1).astype(int)))
    h, w = rgb.shape[:2]
    scale = min(1.0, max_side / max(w, h))
    dw, dh = (max(1, round(w * scale)), max(1, round(h * scale)))
    if (dw, dh) != (w, h):
        sx, sy = (dw / w, dh / h)
        local = np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1.0]])
        rgb = cv2.resize(rgb, (dw, dh), interpolation=cv2.INTER_AREA)
        matrix = local @ matrix
        chain.append({"operation": "resize", "matrix": local.tolist(), "size_px": [dw, dh]})
    inverse = np.linalg.inv(matrix)
    oh, ow = original.shape[:2]
    probes = np.array(
        [[0, 0], [ow - 1, 0], [ow - 1, oh - 1], [0, oh - 1], [(ow - 1) / 2, (oh - 1) / 2]]
    )
    error = float(np.abs(project(project(probes, matrix), inverse) - probes).max())
    if not math.isfinite(error) or error > 1e-06:
        raise InputError("Transform round-trip exceeds 1e-6 px.")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0.6)
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    metadata = {
        "schema_version": VERSION,
        "source_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "source_name": Path(path).name,
        "original_size_px": [ow, oh],
        "working_size_px": [dw, dh],
        "coordinate_system": "u_right_v_down",
        "coordinate_basis": "pixel_centers_zero_based",
        "original_to_working": matrix.tolist(),
        "working_to_original": inverse.tolist(),
        "transform_chain": chain,
        "round_trip_max_error_px": error,
        "quality": report,
        "parameters": {
            "max_side": max_side,
            "crop": crop,
            "deskew_degrees": deskew_degrees,
            "page_corners": page_corners,
            "page_aspect_ratio": page_aspect_ratio,
        },
        "runtime": {"opencv": cv2.__version__, "numpy": np.__version__},
        "units": "px",
        "metric_scale": None,
    }
    return (
        {
            "original": original,
            "color": rgb,
            "gray": gray,
            "denoised": denoised,
            "adaptive": binary,
        },
        metadata,
    )


def overlay(rgb, observations, matrix):
    canvas = Image.fromarray(rgb).convert("RGB")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)

    def points(values):
        return [tuple(p) for p in project(values, matrix)]

    for item in observations["texts"]:
        if item["polygon_px"] is None:
            continue
        polygon = points(item["polygon_px"])
        draw.line(polygon + polygon[:1], fill="#e02060", width=2)
        draw.text(polygon[0], item["id"], fill="#b00040", stroke_width=1, stroke_fill="white")
    for item in observations["lines"]:
        line = points([item["start_px"], item["end_px"]])
        draw.line(line, fill="#008ca0", width=2)
    for item in observations["opening_candidates"]:
        polygon = points(item["polygon_px"])
        draw.line(polygon + polygon[:1], fill="#d08000", width=3)
        draw.text(polygon[0], item["id"], fill="#804000", stroke_width=1, stroke_fill="white")
    return canvas


def annotation_details(rgb, observations, sidecar, matrix):
    from PIL import ImageDraw

    canvas = overlay(rgb, observations, matrix)
    draw = ImageDraw.Draw(canvas)
    for item in sidecar["associations"]:
        endpoints = project([item["span_start_px"], item["span_end_px"]], matrix)
        a, b = [tuple(p) for p in endpoints]
        for start in np.arange(0, 1, 0.04):
            u = endpoints[0] + start * (endpoints[1] - endpoints[0])
            v = endpoints[0] + min(start + 0.02, 1) * (endpoints[1] - endpoints[0])
            draw.line([tuple(u), tuple(v)], fill="#7b32b0", width=2)
        for x, y in [a, b]:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline="#7b32b0", width=2)
        mid = tuple(endpoints.mean(axis=0))
        draw.text(
            mid,
            f"{item['text_id']}->{item['dimension_id']}",
            fill="#7b32b0",
            stroke_width=1,
            stroke_fill="white",
        )
    for item in sidecar["junctions"]:
        x, y = project([item["point_px"]], matrix)[0]
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), outline="#128020", width=2)
        draw.text((x + 6, y + 6), item["id"], fill="#128020", stroke_width=1, stroke_fill="white")
    for item in sidecar["gaps"]:
        if item["kind"] == "incidental":
            points = [tuple(p) for p in project([item["start_px"], item["end_px"]], matrix)]
            draw.line(points, fill="#b04020", width=3)
    return canvas


def write_artifacts(directory, images, metadata, observations=None, sidecar=None):
    directory = Path(directory)
    directory.mkdir()
    for name, rgb in images.items():
        Image.fromarray(rgb).save(directory / f"{name}.png")
    if observations is not None:
        if observations["source"]["image_sha256"] != metadata["source_sha256"]:
            raise InputError("Annotation source hash does not match the image.")
        original = overlay(images["original"], observations, np.eye(3))
        working = overlay(images["color"], observations, metadata["original_to_working"])
        original.save(directory / "original_overlay.png")
        working.save(directory / "working_overlay.png")

        def preview(im):
            im = im.copy()
            im.thumbnail((1000, 800))
            return im

        a, b = (preview(original), preview(working))
        pair = Image.new("RGB", (a.width + b.width, max(a.height, b.height)), "white")
        pair.paste(a, (0, 0))
        pair.paste(b, (a.width, 0))
        pair.save(directory / "comparison.png")
        if sidecar is not None:
            annotation_details(images["original"], observations, sidecar, np.eye(3)).save(
                directory / "original_details.png"
            )
            annotation_details(
                images["color"], observations, sidecar, metadata["original_to_working"]
            ).save(directory / "working_details.png")
    (directory / "preprocessing.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Conservative JPG/PNG preparation with reversible original pixel coordinates."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "output", type=Path, help="New run directory; existing outputs are never overwritten."
    )
    parser.add_argument(
        "--config", type=Path, help="Optional JSON with prepare() keyword arguments."
    )
    args = parser.parse_args()
    staging = None
    try:
        if args.output.exists():
            raise InputError("Output already exists; choose a new run directory.")
        config = json.loads(args.config.read_text()) if args.config else {}
        images, metadata = prepare(args.image, **config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".preprocessing-", dir=args.output.parent))
        write_artifacts(staging / "image", images, metadata)
        os.rename(staging / "image", args.output)
        print(f"Prepared {args.image.name}: {args.output}")
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(1, f"Preprocessing failed: {exc}\n")
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
