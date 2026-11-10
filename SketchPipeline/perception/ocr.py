import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import cv2
import numpy as np
from SketchPipeline.preprocessing.prepare import InputError
from .numeric import parse_numeric, BARE
from SketchPipeline.preprocessing.prepare import project

LOCK_PATH = Path(__file__).with_name("models.lock.json")


def deduplicate_polygons(polygons):
    kept = []
    for polygon in sorted(
        polygons, key=lambda p: cv2.contourArea(np.asarray(p, np.float32)), reverse=True
    ):
        contour = cv2.convexHull(np.asarray(polygon, np.float32))
        area = cv2.contourArea(contour)
        if area <= 0:
            continue
        duplicate = False
        for existing in kept:
            overlap, _ = cv2.intersectConvexConvex(
                contour, cv2.convexHull(np.asarray(existing, np.float32))
            )
            if overlap / area >= 0.8:
                duplicate = True
                break
        if not duplicate:
            kept.append(polygon)
    return sorted(kept, key=lambda p: (min((x[1] for x in p)), min((x[0] for x in p))))


def rectify_crop(rgb, polygon):
    points = np.asarray(polygon, dtype=np.float32)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise InputError("OCR crop requires four finite ordered corners.")
    width = max(
        2, round(max(np.linalg.norm(points[1] - points[0]), np.linalg.norm(points[2] - points[3])))
    )
    height = max(
        2, round(max(np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[2] - points[1])))
    )
    if width * height > 8000000:
        raise InputError("OCR crop exceeds 8 MP.")
    target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    forward = cv2.getPerspectiveTransform(points, target)
    if abs(np.linalg.det(forward)) < 1e-12:
        raise InputError("Degenerate OCR polygon.")
    crop = cv2.warpPerspective(rgb, forward, (width, height), borderValue=(255, 255, 255))
    return (crop, forward)


def rotation_matrix(k, width, height):
    return np.asarray(
        [
            [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            [[0, 1, 0], [-1, 0, width - 1], [0, 0, 1]],
            [[-1, 0, width - 1], [0, -1, height - 1], [0, 0, 1]],
            [[0, -1, height - 1], [1, 0, 0], [0, 0, 1]],
        ][k],
        dtype=float,
    )


def choose_reading(readings):
    if not readings:
        return {
            "raw_text": "[unreadable]",
            "score": 0.0,
            "rotation_degrees": 0,
            "parsed": parse_numeric("[unreadable]"),
        }

    def rank(item):
        valid = item["parsed"]["value_cm"] is not None and item["score"] >= 0.45
        return (valid, item["score"])

    chosen = dict(max(readings, key=rank))
    chosen["parsed"] = dict(chosen["parsed"])
    if not chosen["raw_text"].strip():
        chosen["raw_text"] = "[unreadable]"
        chosen["parsed"]["issue"] = "SKETCH_NUMBER_UNREADABLE"
    if chosen["score"] < 0.45:
        chosen["parsed"]["value_cm"] = None
        chosen["parsed"]["issue"] = "SKETCH_OCR_LOW_CONFIDENCE"
    credible = [
        r
        for r in readings
        if r["parsed"]["value_cm"] is not None and r["score"] >= max(0.45, chosen["score"] - 0.12)
    ]
    values = sorted({r["parsed"]["value_cm"] for r in credible})
    if len(values) > 1:
        chosen["parsed"]["value_cm"] = None
        chosen["parsed"]["alternatives_cm"] = values
        chosen["parsed"]["issue"] = "SKETCH_NUMBER_AMBIGUOUS"
    return chosen


class RapidOCRAdapter:

    def __init__(self):
        import rapidocr
        from rapidocr import RapidOCR
        from rapidocr.ch_ppocr_det import TextDetector
        from rapidocr.ch_ppocr_rec import TextRecognizer
        import onnxruntime as ort
        from omegaconf import OmegaConf

        lock = json.loads(LOCK_PATH.read_text())
        if version("rapidocr") != lock["package_version"]:
            raise InputError("RapidOCR version mismatch; install requirements-perception.txt.")
        model_root = Path(rapidocr.__file__).parent / "models"
        for info in lock["models"].values():
            path = model_root / info["filename"]
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]
            ):
                raise InputError(
                    f"OCR model missing/hash mismatch: {path}. No automatic model replacement."
                )
        params = {
            "Global.use_cls": False,
            "Global.log_level": "error",
            "Det.model_path": str(model_root / lock["models"]["det"]["filename"]),
            "Rec.model_path": str(model_root / lock["models"]["rec"]["filename"]),
            "Det.limit_side_len": 1600,
            "Det.limit_type": "max",
            "Det.thresh": 0.3,
            "Det.box_thresh": 0.5,
            "Det.unclip_ratio": 1.6,
            "Det.use_dilation": True,
            "Det.max_candidates": 128,
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "EngineConfig.onnxruntime.use_cuda": False,
            "EngineConfig.onnxruntime.use_coreml": False,
        }
        cfg = RapidOCR(params=params).cfg
        cfg.Global.model_root_dir = str(model_root)
        for stage in (cfg.Det, cfg.Rec):
            stage.engine_cfg = cfg.EngineConfig["onnxruntime"]
            stage.model_root_dir = str(model_root)
        cfg.Rec.font_path = cfg.Global.font_path
        self.detector = TextDetector(cfg.Det)
        self.recognizer = TextRecognizer(cfg.Rec)
        self.runtime = {
            "adapter": "rapidocr-separate-stages/1.0",
            "models": lock,
            "rapidocr_version": version("rapidocr"),
            "onnxruntime_version": ort.__version__,
            "providers": self.detector.session.session.get_providers(),
            "recognizer_providers": self.recognizer.session.session.get_providers(),
            "available_providers": ort.get_available_providers(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "detection_orientation_policy": "0 degrees; additional 90-degree pass when a substantial tall polygon suggests rotated text; contained-proposal suppression",
            "configuration": OmegaConf.to_container(cfg, resolve=True, enum_to_str=True),
        }

    def detect(self, rgb):
        result = self.detector(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if result.boxes is None:
            self.detection_debug = {"passes": [], "proposals_working": []}
            return []
        polygons = [np.asarray(box, dtype=float).tolist() for box in result.boxes]
        self.detection_debug = {
            "passes": [{"rotation_degrees": 0, "working_to_detector": np.eye(3).tolist()}],
            "proposals_working": list(polygons),
        }
        tall = False
        for polygon in polygons:
            extent = np.ptp(np.asarray(polygon), axis=0)
            if extent[1] > 1.5 * extent[0] and extent[1] >= 40 and (extent.prod() >= 500):
                tall = True
                break
        if tall:
            matrix = rotation_matrix(1, rgb.shape[1], rgb.shape[0])
            second = self.detector(
                cv2.cvtColor(np.ascontiguousarray(np.rot90(rgb)), cv2.COLOR_RGB2BGR)
            )
            self.detection_debug["passes"].append(
                {"rotation_degrees": 90, "working_to_detector": matrix.tolist()}
            )
            if second.boxes is not None:
                for box in second.boxes:
                    mapped = project(box, np.linalg.inv(matrix))
                    angles = np.arctan2(*(mapped - mapped.mean(axis=0))[:, ::-1].T)
                    mapped = mapped[np.argsort(angles)]
                    mapped = np.roll(mapped, -int(np.argmin(mapped.sum(axis=1))), axis=0)
                    polygons.append(mapped.tolist())
            self.detection_debug["proposals_working"] = list(polygons)
            polygons = deduplicate_polygons(polygons)
        return polygons

    def recognize(self, crops):
        from rapidocr.ch_ppocr_rec import TextRecInput

        if not crops:
            return []
        result = self.recognizer(
            TextRecInput(img=[cv2.cvtColor(c, cv2.COLOR_RGB2BGR) for c in crops])
        )
        return [
            (str(text), float(score))
            for text, score in zip(result.txts, result.scores, strict=True)
        ]

    def read_polygons(self, rgb, polygons):
        crops = []
        records = []
        for polygon in polygons:
            crop, forward = rectify_crop(rgb, polygon)
            readings = []
            for k in range(4):
                local = rotation_matrix(k, crop.shape[1], crop.shape[0]) @ forward
                crops.append(np.ascontiguousarray(np.rot90(crop, k)))
                readings.append(
                    {
                        "rotation_degrees": k * 90,
                        "working_to_crop": local.tolist(),
                        "crop_to_working": np.linalg.inv(local).tolist(),
                    }
                )
            records.append(readings)
        recognized = self.recognize(crops)
        for readings in records:
            for item in readings:
                raw, score = recognized.pop(0)
                item.update(raw_text=raw, score=score, parsed=parse_numeric(raw))
        return records


def union_box(polygons):
    points = np.concatenate([np.asarray(p) for p in polygons])
    low = points.min(axis=0)
    high = points.max(axis=0)
    return [[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]]]


def group_units(fragments):
    remaining = set(range(len(fragments)))
    groups = []
    for i, f in enumerate(fragments):
        if i not in remaining or not BARE.fullmatch(f["chosen"]["raw_text"]):
            continue
        box = np.asarray(f["polygon_working"])
        lo = box.min(axis=0)
        hi = box.max(axis=0)
        center = (lo + hi) / 2
        choices = []
        for j in remaining - {i}:
            other = fragments[j]
            if other["chosen"]["raw_text"].strip().lower() != "cm":
                continue
            ob = np.asarray(other["polygon_working"])
            ol = ob.min(axis=0)
            oh = ob.max(axis=0)
            oc = (ol + oh) / 2
            height = hi[1] - lo[1]
            width = hi[0] - lo[0]
            right = 0 <= ol[0] - hi[0] <= max(12, height) and abs(oc[1] - center[1]) <= height * 0.7
            below = (
                0 <= ol[1] - hi[1] <= max(12, height * 0.9)
                and abs(oc[0] - center[0]) <= width * 0.65
            )
            if right or below:
                choices.append((float(np.linalg.norm(oc - center)), j))
        if choices:
            _, j = min(choices)
            remaining.remove(i)
            remaining.remove(j)
            raw = f["chosen"]["raw_text"] + " " + fragments[j]["chosen"]["raw_text"]
            groups.append(
                {
                    "fragment_ids": [f["id"], fragments[j]["id"]],
                    "polygon_working": union_box(
                        [f["polygon_working"], fragments[j]["polygon_working"]]
                    ),
                    "chosen": {
                        "raw_text": raw,
                        "score": min(f["chosen"]["score"], fragments[j]["chosen"]["score"]),
                        "parsed": parse_numeric(raw),
                        "rotation_degrees": None,
                    },
                }
            )
    groups.extend(
        (
            {
                "fragment_ids": [fragments[i]["id"]],
                "polygon_working": fragments[i]["polygon_working"],
                "chosen": fragments[i]["chosen"],
            }
            for i in sorted(remaining)
        )
    )
    return sorted(
        groups,
        key=lambda g: (
            min((p[1] for p in g["polygon_working"])),
            min((p[0] for p in g["polygon_working"])),
        ),
    )


def ocr_evidence(rgb, adapter):
    polygons = adapter.detect(rgb)
    readings = adapter.read_polygons(rgb, polygons)
    fragments = [
        {
            "id": f"f{i:03d}",
            "polygon_working": polygon,
            "readings": options,
            "chosen": choose_reading(options),
        }
        for i, (polygon, options) in enumerate(zip(polygons, readings, strict=True), 1)
    ]
    return (fragments, group_units(fragments))
