from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import unittest
from SketchPipeline.fixtures.build_tablet_31_40_references import (
    SOURCE,
    artifacts,
    build_actual_case,
)
from SketchPipeline.preprocessing.dataset import audit
from SketchPipeline.validation.validate import validate_document

ROOT = Path(__file__).resolve().parents[2]


def draft(n):
    return json.loads((ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json").read_text())


class Tablet3140ReferencesTests(unittest.TestCase):

    def test_reproducibility_and_older_manifest_prefix(self):
        output = artifacts()
        self.assertEqual(len(output), 48)
        for path, document in output.items():
            with self.subTest(path=path.name):
                self.assertEqual(json.loads(path.read_text()), document)
        old = json.loads(SOURCE.with_name("manifest_all_30.json").read_text())
        new = output[SOURCE.with_name("manifest_all_40.json")]
        self.assertEqual(new["samples"][:30], old["samples"])
        self.assertEqual(len(new["samples"]), 40)

    def test_batch_and_combined_schema_evidence_audit(self):
        _, batch = audit(SOURCE.with_name("manifest_tablet_31_40.json"))
        self.assertEqual(len(batch), 10)
        self.assertEqual(sum((len(s[2]["texts"]) for s in batch)), 151)
        self.assertEqual(sum((len(s[3]["regions"]) for s in batch)), 45)
        _, combined = audit(SOURCE.with_name("manifest_all_40.json"))
        self.assertEqual(len(combined), 40)
        self.assertEqual(sum((len(s[2]["texts"]) for s in combined)), 329)

    def test_six_accepted_four_negative(self):
        for n in range(31, 41):
            p = ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json"
            obs = json.loads(SOURCE.with_name(f"Data_{n}.observations.json").read_text())
            if n in (32, 33, 34, 35, 36, 38):
                self.assertTrue(validate_document(json.loads(p.read_text()), obs)["exportable"], n)
            else:
                self.assertFalse(p.exists(), n)
                self.assertFalse(validate_document(draft(n), obs)["metric_valid"], n)

    def test_31_preserves_unwritten_door_widths_and_positions(self):
        d = draft(31)
        self.assertEqual(len(d["layout"]["openings"]), 2)
        self.assertTrue(
            all(
                (
                    o["clear_width_cm"] is None and o["center_offset_cm"] is None
                    for o in d["layout"]["openings"]
                )
            )
        )
        self.assertEqual(sum((m["value_cm"] is None for m in d["layout"]["dimensions"])), 4)
        self.assertEqual(len(d["layout"]["dimensions"]), 12)

    def test_37_actual_values_and_unknown_placement(self):
        d = draft(37)
        a = next(
            (
                m
                for m in d["layout"]["dimensions"]
                if m["target"] == dict(type="region_span", region_id="rA", axis="y")
            )
        )
        self.assertEqual(a["value_cm"], 600)
        ce = next((o for o in d["layout"]["openings"] if o["id"] == "dCE"))
        self.assertEqual((ce["clear_width_cm"], ce["center_offset_cm"]), (110, None))
        rd = next((r for r in d["layout"]["rooms"] if r["id"] == "rD"))
        positions = {v["id"]: v["position_cm"] for v in d["layout"]["vertices"]}
        self.assertTrue(all((positions[v][1] is None for v in rd["boundary_vertex_ids"])))
        self.assertEqual(sum((m["value_cm"] is None for m in d["layout"]["dimensions"])), 3)
        spec = deepcopy(
            next((s for s in json.loads(SOURCE.read_text())["samples"] if s["id"] == "Data_37"))
        )
        spec["expected_status"] = "reference_validated"
        with self.assertRaises(ValueError):
            build_actual_case(spec)

    def test_40_has_no_fabricated_corridor_length_or_far_x(self):
        d = draft(40)
        missing = [m for m in d["layout"]["dimensions"] if m["value_cm"] is None]
        self.assertEqual([m["span_label"] for m in missing], ["cH.length"])
        self.assertEqual(missing[0]["target"], dict(type="region_span", region_id="cH", axis="x"))
        positions = {v["id"]: v["position_cm"] for v in d["layout"]["vertices"]}
        for r in d["layout"]["rooms"]:
            if r["id"] in ("rB", "rC"):
                self.assertTrue(all((positions[v][0] is None for v in r["boundary_vertex_ids"])))
        self.assertTrue(all((o["center_offset_cm"] is not None for o in d["layout"]["openings"])))

    def test_cycles_parallel_doors_and_actual_conflict(self):
        cycle = draft(35)["layout"]
        self.assertEqual(len(cycle["rooms"]), 4)
        self.assertEqual(len(cycle["passages"]), 4)
        side = json.loads(SOURCE.with_name("Data_35.annotations.json").read_text())
        self.assertIn("cross", [j["kind"] for j in side["junctions"]])
        d = draft(38)
        self.assertEqual(len(d["layout"]["rooms"]), 6)
        self.assertEqual(len(d["layout"]["openings"]), 7)
        ab = [
            o
            for o in d["layout"]["openings"]
            if {e["id"] for e in o["connected_entities"]} == {"rA", "rB"}
        ]
        self.assertEqual(sorted((o["clear_width_cm"] for o in ab)), [90, 110, 130])
        self.assertEqual(len({o["wall_id"] for o in ab}), 1)
        changed = deepcopy(d)
        next(
            (
                m
                for m in changed["layout"]["dimensions"]
                if m["target"]["type"] == "opening_separation"
            )
        )["value_cm"] = 350
        self.assertFalse(validate_document(changed)["metric_valid"])
        conflict = draft(39)
        off = next(
            (
                m
                for m in conflict["layout"]["dimensions"]
                if m["target"].get("opening_id") == "dAB"
                and m["target"]["type"] == "opening_offset"
            )
        )
        self.assertEqual(off["value_cm"], 80)
        self.assertTrue(
            any(
                (
                    i["code"] == "SKETCH_DIMENSION_CONFLICT"
                    for i in validate_document(conflict)["issues"]
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
