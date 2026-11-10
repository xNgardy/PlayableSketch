from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from SketchPipeline.fixtures.build_tablet_references import SOURCE, artifacts
from SketchPipeline.fixtures.export_ocr_crops import export
from SketchPipeline.preprocessing.dataset import audit
from SketchPipeline.preprocessing.prepare import InputError
from SketchPipeline.validation.validate import load_json, validate_document

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "Data/annotations/v1/manifest_tablet_11_20.json"


def draft(n):
    return load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json")


class TabletReferencesTests(unittest.TestCase):

    def test_all_new_sources_and_combined_dataset_pass_audit(self):
        _, samples = audit(MANIFEST)
        self.assertEqual(len(samples), 10)
        self.assertEqual(sum((len(s[2]["texts"]) for s in samples)), 61)
        self.assertEqual(sum((len(s[2]["opening_candidates"]) for s in samples)), 11)
        self.assertEqual(
            [s[0]["metric_status"] for s in samples][-2:], ["conflicting", "incomplete"]
        )
        self.assertEqual(len(audit(MANIFEST.with_name("manifest_all_20.json"))[1]), 20)

    def test_generated_references_are_reproducible(self):
        for path, document in artifacts().items():
            with self.subTest(path=path.name):
                self.assertEqual(load_json(path), document)

    def test_eight_metric_references_and_two_negative_drafts(self):
        for n in range(11, 19):
            d = load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json")
            obs = load_json(ROOT / f"Data/annotations/v1/Data_{n}.observations.json")
            self.assertTrue(validate_document(d, obs)["exportable"], n)
        for n in (19, 20):
            self.assertFalse(validate_document(draft(n))["metric_valid"])
            self.assertFalse((ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json").exists())

    def test_two_door_wall_separation_is_not_a_corner_offset(self):
        d = draft(15)
        dimension = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_separation")
        )
        self.assertEqual(dimension["value_cm"], 150)
        self.assertEqual(dimension["basis"], "edge_offset")
        self.assertEqual(
            dimension["target"],
            {
                "type": "opening_separation",
                "from_opening_id": "d_lower",
                "to_opening_id": "d_upper",
            },
        )
        for mutation in ("wrong_value", "reverse", "unknown", "same", "wrong_basis"):
            changed = deepcopy(d)
            m = next((m for m in changed["layout"]["dimensions"] if m["id"] == dimension["id"]))
            if mutation == "wrong_value":
                m["value_cm"] = 380
            elif mutation == "reverse":
                m["target"]["from_opening_id"], m["target"]["to_opening_id"] = (
                    "d_upper",
                    "d_lower",
                )
            elif mutation == "unknown":
                m["target"]["from_opening_id"] = "missing"
            elif mutation == "same":
                m["target"]["from_opening_id"] = "d_upper"
            else:
                m["basis"] = "wall_centerline"
            with self.subTest(mutation=mutation):
                self.assertFalse(validate_document(changed)["metric_valid"])

    def test_corridor_wall_spans_end_at_centerline_junctions(self):
        for n, width, wall_span in ((16, 180, 325), (17, 160, 260)):
            d = draft(n)
            self.assertTrue(all((o["clear_width_cm"] == width for o in d["layout"]["openings"])))
            spans = [m for m in d["layout"]["dimensions"] if m["target"]["type"] == "wall_chain"]
            self.assertEqual([m["value_cm"] for m in spans], [wall_span, wall_span])
            self.assertTrue(all((m["basis"] == "wall_centerline" for m in spans)))

    def test_t_junction_and_actual_bottom_label_are_preserved(self):
        d = draft(18)
        obs = load_json(ROOT / "Data/annotations/v1/Data_18.observations.json")
        self.assertEqual(len(obs["texts"]), 10)
        self.assertNotIn(900, [t["parsed_value_cm"] for t in obs["texts"]])
        upper = next(
            (
                m
                for m in d["layout"]["dimensions"]
                if m["target"].get("opening_id") == "d_upper"
                and m["target"]["type"] == "opening_offset"
            )
        )
        self.assertEqual(
            (upper["value_cm"], upper["target"]["region_id"], upper["target"]["side"]),
            (210, "rC", "west"),
        )
        bottom = next(
            (m for m in d["layout"]["dimensions"] if m["provenance"]["evidence_ids"] == ["t010"])
        )
        self.assertEqual(bottom["target"], {"type": "region_span", "region_id": "rB", "axis": "x"})

    def test_missing_and_conflicting_dimensions_are_not_filled_from_pixels(self):
        d = draft(20)
        missing = [m for m in d["layout"]["dimensions"] if m["value_cm"] is None]
        self.assertEqual(len(missing), 1)
        self.assertEqual(
            missing[0]["target"], {"type": "region_span", "region_id": "rB", "axis": "x"}
        )
        right = next((r for r in d["layout"]["rooms"] if r["id"] == "rB"))
        points = {v["id"]: v["position_cm"] for v in d["layout"]["vertices"]}
        self.assertEqual({points[v][1] for v in right["boundary_vertex_ids"]}, {0, 470})
        self.assertTrue(any((points[v][0] is None for v in right["boundary_vertex_ids"])))
        conflict = draft(19)
        widths = [
            m["value_cm"]
            for m in conflict["layout"]["dimensions"]
            if m["target"].get("axis") == "x"
        ]
        self.assertEqual(widths, [720, 690])
        self.assertTrue(
            any(
                (
                    i["code"] == "SKETCH_DIMENSION_CONFLICT"
                    for i in validate_document(conflict)["issues"]
                )
            )
        )

    def test_region_labels_require_coverage_and_valid_pixels(self):
        path = MANIFEST.parent / "Data_11.annotations.json"
        for mutation in ("outside", "duplicate", "missing"):
            side = load_json(path)
            if mutation == "outside":
                side["regions"][0]["polygon_px"][0][0] = 99999
            elif mutation == "duplicate":
                side["regions"].append(deepcopy(side["regions"][0]))
            else:
                side["regions"] = []

            def reader(p):
                return side if Path(p) == path else load_json(p)

            with (
                self.subTest(mutation=mutation),
                patch("SketchPipeline.preprocessing.dataset.load_json", side_effect=reader),
            ):
                with self.assertRaises(InputError):
                    audit(MANIFEST)

    def test_ocr_export_preserves_source_groups_and_excludes_multiline(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "ocr"
            self.assertEqual(export(MANIFEST, output, SOURCE), (61, 53))
            manifest = load_json(output / "manifest.json")
            self.assertFalse(manifest["training_performed"])
            records = {s["image"]: s for s in manifest["samples"]}
            for line in (output / "recognition_single_line.tsv").read_text().splitlines():
                path, transcription = line.split("\t")
                record = records[path]
                self.assertEqual(record["text_layout"], "single_line")
                self.assertEqual(record["transcription"], transcription)
                self.assertEqual(record["split"], "development")
                self.assertTrue((output / path).is_file())
            with self.assertRaises(ValueError):
                export(MANIFEST, output, SOURCE)


if __name__ == "__main__":
    unittest.main()
