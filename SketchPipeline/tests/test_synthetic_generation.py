from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np
from PIL import Image
from SketchPipeline.synthetic.generate import (
    DEFAULT_OUTPUT,
    ROOT,
    STYLES,
    audit,
    digest,
    make_plan,
    metric_rank,
    render,
)
from SketchPipeline.validation.validate import validate_document


class SyntheticGenerationTests(unittest.TestCase):

    def test_plan_generation_deterministic_and_topology_diverse(self):
        plans = [
            make_plan(i, extra)
            for extra, count in [(False, 20), (True, 10)]
            for i in range(1, count + 1)
        ]
        self.assertEqual(len({p["id"] for p in plans}), 30)
        self.assertEqual(len({p["family"] for p in plans}), 10)
        fingerprints = {json.dumps([r["bounds_cm"] for r in p["regions"]]) for p in plans}
        self.assertEqual(len(fingerprints), 30)
        for p in plans:
            self.assertEqual(p, make_plan(int(p["id"][2:]), p["id"].startswith("SX")))
            self.assertTrue(3 <= sum((r["kind"] == "room" for r in p["regions"])) <= 6)
            for i, a in enumerate(p["regions"]):
                x, y, x1, y1 = a["bounds_cm"]
                self.assertGreater(x1, x)
                self.assertGreater(y1, y)
                for b in p["regions"][i + 1 :]:
                    X, Y, X1, Y1 = b["bounds_cm"]
                    self.assertTrue(min(x1, X1) <= max(x, X) or min(y1, Y1) <= max(y, Y))

    def test_complete_corpora_grouping_and_pending_metric_outputs(self):
        for name, images, plans in [("handdrawn_pilot", 60, 20), ("extra_plans", 10, 10)]:
            report = audit(DEFAULT_OUTPUT / name)
            self.assertEqual((report["images"], report["base_plans"]), (images, plans))
            manifest = json.loads((DEFAULT_OUTPUT / name / "manifest.json").read_text())
            counts = Counter((s["base_plan_id"] for s in manifest["samples"]))
            self.assertEqual(set(counts.values()), {3 if images == 60 else 1})
            self.assertTrue(
                all(
                    (
                        s["origin"] == "synthetic" and s["writer_id"] is None
                        for s in manifest["samples"]
                    )
                )
            )
            self.assertFalse(list((DEFAULT_OUTPUT / name / "metric").glob("*.validated.json")))

    def test_real_50_manifest_is_not_reclassified_or_extended(self):
        m = json.loads((ROOT / "Data/annotations/v1/manifest_all_50.json").read_text())
        self.assertEqual(len(m["samples"]), 50)
        self.assertEqual([s["id"] for s in m["samples"]], [f"Data_{i}" for i in range(1, 51)])
        self.assertEqual(sum((s["counts"]["texts"] for s in m["samples"])), 512)

    def test_reproducible_pixels_and_annotation_pair(self):
        sample_id = "SP001_ink"
        base = DEFAULT_OUTPUT / "handdrawn_pilot"
        with tempfile.TemporaryDirectory() as temp:
            regenerated = render(make_plan(1), "ink", Path(temp))
            self.assertEqual(
                regenerated["image_sha256"], digest(base / "images" / f"{sample_id}.png")
            )
            for folder, suffix in [
                ("annotations", "observations"),
                ("annotations", "annotations"),
                ("metric", "draft"),
            ]:
                file = f"{sample_id}.{suffix}.json"
                self.assertEqual(
                    json.loads((Path(temp) / folder / file).read_text()),
                    json.loads((base / folder / file).read_text()),
                )

    def test_label_polygons_are_disjoint_and_layer_masks_do_not_overlap(self):
        for batch in ["handdrawn_pilot", "extra_plans"]:
            base = DEFAULT_OUTPUT / batch
            manifest = json.loads((base / "manifest.json").read_text())
            for s in manifest["samples"]:
                with self.subTest(sample=s["id"]):
                    obs = json.loads((base / s["observations_path"]).read_text())
                    for i, a in enumerate(obs["texts"]):
                        pa = cv2.convexHull(np.asarray(a["polygon_px"], np.float32))
                        for b in obs["texts"][i + 1 :]:
                            area, _ = cv2.intersectConvexConvex(
                                pa, cv2.convexHull(np.asarray(b["polygon_px"], np.float32))
                            )
                            self.assertLess(area, 0.01)
                    meta = json.loads((base / s["rendering_path"]).read_text())
                    walls = np.asarray(Image.open(base / meta["masks"]["walls"]))
                    text = np.asarray(Image.open(base / meta["masks"]["text"]))
                    self.assertFalse(np.logical_and(walls > 30, text > 30).any())

    def test_missing_dimension_is_detected_by_rank_audit(self):
        d = json.loads((DEFAULT_OUTPUT / "handdrawn_pilot/metric/SP001_ink.draft.json").read_text())
        d["layout"]["dimensions"] = [
            m
            for m in d["layout"]["dimensions"]
            if m["target"] != {"type": "region_span", "region_id": "rA", "axis": "x"}
        ]
        with self.assertRaises(ValueError):
            metric_rank(d)

    def test_wrong_door_edge_offset_is_not_accepted(self):
        d = json.loads((DEFAULT_OUTPUT / "extra_plans/metric/SX001_ink.draft.json").read_text())
        offset = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_offset")
        )
        offset["value_cm"] += 50
        self.assertFalse(validate_document(d)["metric_valid"])

    def test_generated_evidence_never_claims_manual_transcription(self):
        for style in STYLES:
            p = DEFAULT_OUTPUT / f"handdrawn_pilot/annotations/SP001_{style}.observations.json"
            d = json.loads(p.read_text())
            self.assertTrue(all((t["method"] == "synthetic_render" for t in d["texts"])))
            self.assertTrue(all((t["score"] is None for t in d["texts"])))
            metric = json.loads(
                (DEFAULT_OUTPUT / f"handdrawn_pilot/metric/SP001_{style}.draft.json").read_text()
            )
            self.assertEqual(metric["review"]["status"], "pending")
            self.assertTrue(
                all(
                    (
                        o["provenance"]["method"] == "derived"
                        for values in metric["layout"].values()
                        for o in values
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
