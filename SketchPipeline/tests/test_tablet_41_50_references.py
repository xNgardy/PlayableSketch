from copy import deepcopy
import json
from pathlib import Path
import unittest
from SketchPipeline.fixtures.build_tablet_41_50_references import SOURCE, artifacts
from SketchPipeline.preprocessing.dataset import audit
from SketchPipeline.validation.validate import validate_document

ROOT = Path(__file__).resolve().parents[2]


def draft(n):
    return json.loads((ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json").read_text())


class Tablet4150ReferencesTests(unittest.TestCase):

    def test_reproducible_outputs_and_unchanged_prefix(self):
        output = artifacts()
        self.assertEqual(len(output), 50)
        for path, doc in output.items():
            with self.subTest(path=path.name):
                self.assertEqual(json.loads(path.read_text()), doc)
        old = json.loads(SOURCE.with_name("manifest_all_40.json").read_text())["samples"]
        self.assertEqual(output[SOURCE.with_name("manifest_all_50.json")]["samples"][:40], old)

    def test_batch_and_combined_evidence_audit(self):
        _, batch = audit(SOURCE.with_name("manifest_tablet_41_50.json"))
        self.assertEqual(len(batch), 10)
        self.assertEqual(sum((len(s[2]["texts"]) for s in batch)), 183)
        self.assertEqual(sum((len(s[2]["opening_candidates"]) for s in batch)), 48)
        self.assertEqual(sum((len(s[3]["regions"]) for s in batch)), 53)
        _, combined = audit(SOURCE.with_name("manifest_all_50.json"))
        self.assertEqual(len(combined), 50)
        self.assertEqual(sum((len(s[2]["texts"]) for s in combined)), 512)

    def test_eight_complete_references_two_negative(self):
        for n in range(41, 51):
            p = ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json"
            if n <= 48:
                obs = json.loads(SOURCE.with_name(f"Data_{n}.observations.json").read_text())
                self.assertTrue(validate_document(json.loads(p.read_text()), obs)["exportable"], n)
            else:
                self.assertFalse(p.exists(), n)
                self.assertFalse(validate_document(draft(n))["metric_valid"], n)

    def test_two_door_edge_to_edge_chain(self):
        d = draft(41)
        ab = [o for o in d["layout"]["openings"] if o["id"] in ("dLower", "dUpper")]
        self.assertEqual([o["clear_width_cm"] for o in ab], [100, 110])
        self.assertEqual([o["center_offset_cm"] for o in ab], [130, 335])
        gap = next(
            (m for m in d["layout"]["dimensions"] if m["target"]["type"] == "opening_separation")
        )
        self.assertEqual(gap["value_cm"], 100)
        changed = deepcopy(d)
        next((m for m in changed["layout"]["dimensions"] if m["id"] == gap["id"]))["value_cm"] = 280
        self.assertFalse(validate_document(changed)["metric_valid"])

    def test_rectangular_corridor_bend(self):
        d = draft(43)
        self.assertEqual(len(d["layout"]["corridors"]), 2)
        bend = next((o for o in d["layout"]["openings"] if o["id"] == "pHV"))
        self.assertEqual({e["type"] for e in bend["connected_entities"]}, {"corridor"})
        self.assertEqual(bend["clear_width_cm"], 180)
        self.assertTrue(validate_document(d)["metric_valid"])

    def test_three_corridor_cycle(self):
        d = draft(46)["layout"]
        self.assertEqual(len(d["corridors"]), 3)
        self.assertEqual(len(d["rooms"]), 4)
        self.assertEqual(len(d["passages"]), 7)
        self.assertIn(
            640, [m["value_cm"] for m in d["dimensions"] if m["target"]["type"] == "wall_chain"]
        )

    def test_side_branch_uses_shared_interface_not_entire_corridor(self):
        d = draft(47)
        widths = {o["id"]: o["clear_width_cm"] for o in d["layout"]["openings"]}
        self.assertEqual(widths, dict(dBE=120, pAH=180, pBH=180, pCH=380, pDH=380))
        for wrong in (180, 880):
            changed = deepcopy(d)
            next((o for o in changed["layout"]["openings"] if o["id"] == "pCH"))[
                "clear_width_cm"
            ] = wrong
            codes = {i["code"] for i in validate_document(changed)["issues"]}
            self.assertIn("SKETCH_SETTINGS_CONFLICT", codes)
        changed = deepcopy(d)
        changed["settings"]["wall_thickness_cm"] = 40
        for w in changed["layout"]["walls"]:
            w["thickness_cm"] = 40
        for o in changed["layout"]["openings"]:
            if o["type"] == "open_passage":
                o["clear_width_cm"] -= 20
        self.assertTrue(validate_document(changed)["metric_valid"])

    def test_actual_30_cm_conflict_preserved(self):
        d = draft(49)
        self.assertTrue(
            any((i["code"] == "SKETCH_DIMENSION_CONFLICT" for i in validate_document(d)["issues"]))
        )
        changed = deepcopy(d)
        m = next(
            (
                m
                for m in changed["layout"]["dimensions"]
                if m["target"]["type"] == "wall_chain" and m["value_cm"] == 450
            )
        )
        m["value_cm"] = 420
        changed["issues"] = []
        changed["status"] = "draft"
        self.assertTrue(validate_document(changed)["metric_valid"])
        self.assertEqual(len(d["layout"]["openings"]), 3)

    def test_only_B_east_x_missing_not_door_positions(self):
        d = draft(50)
        self.assertEqual(
            [m["span_label"] for m in d["layout"]["dimensions"] if m["value_cm"] is None],
            ["rB.width"],
        )
        unknown = [v for v in d["layout"]["vertices"] if v["position_cm"][0] is None]
        self.assertEqual(len(unknown), 2)
        self.assertTrue(all((v["position_cm"][1] is not None for v in d["layout"]["vertices"])))
        self.assertTrue(all((o["center_offset_cm"] is not None for o in d["layout"]["openings"])))
        self.assertEqual([o["clear_width_cm"] for o in d["layout"]["openings"]], [120, 110, 100])


if __name__ == "__main__":
    unittest.main()
