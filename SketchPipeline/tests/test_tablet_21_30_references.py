from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from SketchPipeline.fixtures.build_tablet_21_30_references import SOURCE, artifacts
from SketchPipeline.fixtures.build_tablet_references import build_case
from SketchPipeline.fixtures.export_ocr_crops import export
from SketchPipeline.preprocessing.dataset import audit
from SketchPipeline.validation.validate import load_json, validate_document

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = SOURCE.with_name("manifest_tablet_21_30.json")


def draft(n):
    return load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json")


class Tablet2130ReferencesTests(unittest.TestCase):

    def test_source_reproduces_all_generated_files(self):
        generated = artifacts()
        self.assertEqual(len(generated), 50)
        for path, document in generated.items():
            with self.subTest(path=path.name):
                self.assertEqual(load_json(path), document)
                self.assertNotIn("GRID_BACKGROUND_IS_NOT_WALL", document.get("issues", []))

    def test_batch_and_combined_audit(self):
        _, batch = audit(MANIFEST)
        self.assertEqual(len(batch), 10)
        self.assertEqual(sum((len(s[2]["texts"]) for s in batch)), 61)
        self.assertEqual(sum((len(s[2]["opening_candidates"]) for s in batch)), 11)
        self.assertEqual(sum((len(s[3]["regions"]) for s in batch)), 21)
        _, combined = audit(MANIFEST.with_name("manifest_all_30.json"))
        self.assertEqual(len(combined), 30)
        self.assertEqual(sum((len(s[2]["texts"]) for s in combined)), 178)
        older = load_json(MANIFEST.with_name("manifest_all_20.json"))["samples"]
        self.assertEqual(
            load_json(MANIFEST.with_name("manifest_all_30.json"))["samples"][:20], older
        )

    def test_eight_complete_references_and_two_negative_cases(self):
        for n in range(21, 29):
            doc = load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json")
            obs = load_json(SOURCE.with_name(f"Data_{n}.observations.json"))
            self.assertTrue(validate_document(doc, obs)["exportable"], n)
        for n in (29, 30):
            self.assertFalse(validate_document(draft(n))["metric_valid"])
            self.assertFalse((ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json").exists())

    def test_opposite_corner_offsets_preserve_fractional_centers(self):
        for n, center, value in ((23, 307.5, 65), (24, 557.5, 85), (26, 360, 70)):
            d = draft(n)
            m = next(
                (
                    m
                    for m in d["layout"]["dimensions"]
                    if m["target"].get("reference") == "max_corner"
                )
            )
            o = next((o for o in d["layout"]["openings"] if o["id"] == m["target"]["opening_id"]))
            self.assertEqual((o["center_offset_cm"], m["value_cm"]), (center, value))
            changed = deepcopy(d)
            next(
                (o for o in changed["layout"]["openings"] if o["id"] == m["target"]["opening_id"])
            )["center_offset_cm"] += (o["clear_width_cm"] / 2)
            self.assertFalse(validate_document(changed)["metric_valid"])

    def test_actual_two_door_sequence_overrides_brief(self):
        d = draft(25)
        openings = {o["id"]: o for o in d["layout"]["openings"]}
        self.assertEqual(
            (openings["d_lower"]["clear_width_cm"], openings["d_lower"]["center_offset_cm"]),
            (85, 182.5),
        )
        self.assertEqual(
            (openings["d_upper"]["clear_width_cm"], openings["d_upper"]["center_offset_cm"]),
            (105, 452.5),
        )
        separation = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_separation")
        )
        self.assertEqual(separation["value_cm"], 175)
        self.assertEqual(separation["target"]["from_opening_id"], "d_lower")

    def test_corridor_local_spans_determine_room_alignment(self):
        for n, spans, right_min, clear in ((27, [240, 210], 30, 160), (28, [140, 260], -120, 200)):
            d = draft(n)
            measured = [
                m["value_cm"]
                for m in d["layout"]["dimensions"]
                if m["target"]["type"] == "wall_chain"
            ]
            self.assertEqual(measured, spans)
            r = next((r for r in d["layout"]["rooms"] if r["id"] == "rB"))
            positions = {v["id"]: v["position_cm"] for v in d["layout"]["vertices"]}
            self.assertEqual(min((positions[v][1] for v in r["boundary_vertex_ids"])), right_min)
            self.assertTrue(
                all(
                    (
                        o["type"] == "open_passage" and o["clear_width_cm"] == clear
                        for o in d["layout"]["openings"]
                    )
                )
            )

    def test_conflicting_total_does_not_invent_a_door(self):
        d = draft(29)
        self.assertEqual(d["layout"]["openings"], [])
        self.assertEqual(d["layout"]["passages"], [])
        obs = load_json(SOURCE.with_name("Data_29.observations.json"))
        self.assertEqual([t["parsed_value_cm"] for t in obs["texts"]], [300, 500, 600, 850])
        self.assertEqual(obs["opening_candidates"], [])
        self.assertTrue(
            any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in validate_document(d)["issues"]))
        )

    def test_missing_opening_location_retains_known_width_and_pixel_gap(self):
        d = draft(30)
        o = d["layout"]["openings"][0]
        self.assertEqual(
            (o["center_offset_cm"], o["clear_width_cm"], o["state"]), (None, 120, "missing")
        )
        self.assertTrue(all((None not in v["position_cm"] for v in d["layout"]["vertices"])))
        self.assertEqual(
            [m["span_label"] for m in d["layout"]["dimensions"] if m["value_cm"] is None],
            ["d0.lower_edge_offset"],
        )
        self.assertEqual(
            len(load_json(SOURCE.with_name("Data_30.observations.json"))["opening_candidates"]), 1
        )
        spec = deepcopy(load_json(SOURCE)["samples"][-1])
        spec["openings"][0]["center_cm"] = [0, None]
        with self.assertRaises(ValueError):
            build_case(spec)

    def test_ocr_export_groups_and_single_line_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "ocr"
            self.assertEqual(export(MANIFEST, out, SOURCE), (61, 49))
            manifest = load_json(out / "manifest.json")
            self.assertFalse(manifest["training_performed"])
            records = manifest["samples"]
            self.assertEqual(sum((r["text_layout"] == "multiline" for r in records)), 12)
            self.assertTrue(
                all(
                    (
                        r["writer_id"] == "tablet_author_01" and r["split"] == "development"
                        for r in records
                    )
                )
            )
            self.assertTrue(all((np.isfinite(r["original_to_crop"]).all() for r in records)))
            self.assertTrue(all(((out / r["image"]).is_file() for r in records)))
            self.assertEqual(
                len((out / "recognition_single_line.tsv").read_text().splitlines()), 49
            )


if __name__ == "__main__":
    unittest.main()
