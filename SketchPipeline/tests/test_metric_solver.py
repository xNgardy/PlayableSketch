from copy import deepcopy
from pathlib import Path
import unittest
from SketchPipeline.solver.linear import solve
from SketchPipeline.validation.validate import load_json

ROOT = Path(__file__).resolve().parents[2]


def fixture(n):
    return load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.draft.json")


def dimension(identifier, target, value, basis="wall_centerline"):
    return {
        "id": identifier,
        "value_cm": value,
        "basis": basis,
        "target": target,
        "state": "confirmed",
        "span_label": identifier,
        "provenance": {
            "method": "user_correction",
            "evidence_ids": [],
            "note": "Test confirmed measurement.",
        },
    }


def relation(identifier, opening_id, kind):
    return {
        "id": identifier,
        "opening_id": opening_id,
        "type": kind,
        "state": "confirmed",
        "note": "Explicit test premise; never inferred from proportions.",
    }


def scramble(doc):
    result = deepcopy(doc)
    for v in result["layout"]["vertices"]:
        v["position_cm"] = [91234, -45678]
    for o in result["layout"]["openings"]:
        o.update(center_offset_cm=777, clear_width_cm=333)
    return result


def normalized_legacy_topology(doc):
    result = deepcopy(doc)
    for r in result["layout"]["rooms"] + result["layout"]["corridors"]:
        if len(r["boundary_vertex_ids"]) != 4:
            raise ValueError("Only legacy four-corner fixture")
        vs = r["boundary_vertex_ids"]
        for i, wid in enumerate(r["boundary_wall_ids"]):
            w = next((w for w in result["layout"]["walls"] if w["id"] == wid))
            a, b = (vs[i], vs[(i + 1) % 4])
            if i >= 2:
                a, b = (b, a)
            w.update(start_vertex_id=a, end_vertex_id=b)
    return result


class MetricSolverTests(unittest.TestCase):

    def test_data1_no_pixel_or_existing_coordinate_scale(self):
        source = scramble(fixture(1))
        before = deepcopy(source)
        draft, report = solve(source)
        self.assertEqual(source, before)
        self.assertEqual(report["status"], "determined")
        self.assertTrue(report["validation"]["metric_valid"])
        self.assertEqual(
            [v["position_cm"] for v in draft["layout"]["vertices"]],
            [[0, 0], [600, 0], [600, 400], [0, 400]],
        )
        self.assertEqual(draft["review"]["status"], "pending")
        self.assertFalse(report["exportable"])

    def test_data3_unique_shared_wall_and_lines(self):
        draft, report = solve(scramble(fixture(3)))
        self.assertTrue(report["validation"]["metric_valid"])
        self.assertEqual(
            sorted({v["position_cm"][0] for v in draft["layout"]["vertices"]}), [0, 600, 1100]
        )
        self.assertEqual(len([w for w in draft["layout"]["walls"] if len(w["region_ids"]) == 2]), 1)
        self.assertEqual(draft["layout"]["openings"][0]["center_offset_cm"], 260)

    def test_data8_needs_explicit_alignment_then_rebases_to_local100(self):
        doc = scramble(fixture(8))
        _, missing = solve(doc)
        self.assertEqual(missing["status"], "underdetermined")
        relations = [
            relation("align", "d0", "centered_opening"),
            relation("entrance", "o-c0-rB", "full_span_opening"),
        ]
        draft, report = solve(doc, relations=relations)
        self.assertEqual(report["status"], "determined")
        self.assertTrue(report["validation"]["metric_valid"], report["validation"]["issues"])
        self.assertEqual(
            next((o for o in draft["layout"]["openings"] if o["id"] == "d0"))["center_offset_cm"],
            100,
        )
        self.assertEqual(
            next((o for o in draft["layout"]["openings"] if o["id"] == "o-c0-rB"))[
                "clear_width_cm"
            ],
            180,
        )
        r = next((r for r in draft["layout"]["rooms"] if r["id"] == "rB"))
        vertices = {v["id"]: v["position_cm"] for v in draft["layout"]["vertices"]}
        self.assertEqual(min((vertices[v][1] for v in r["boundary_vertex_ids"])), 70)

    def test_data9_conflict_no_averaged_geometry(self):
        draft, report = solve(scramble(normalized_legacy_topology(fixture(9))))
        self.assertEqual(report["status"], "inconsistent")
        self.assertEqual(draft["status"], "conflicting")
        self.assertTrue(
            all((v["position_cm"] == [None, None] for v in draft["layout"]["vertices"]))
        )
        self.assertTrue(
            any((r["id"] == "m001" and r["evidence_ids"] == ["t001"] for r in report["equations"]))
        )
        self.assertGreater(report["max_residual_cm"], 1)

    def test_data10_missing_does_not_copy_existing_reference_values(self):
        draft, report = solve(scramble(normalized_legacy_topology(fixture(10))))
        self.assertEqual(report["status"], "underdetermined")
        self.assertTrue(report["validation"]["schema_valid"])
        vs = {v["id"]: v["position_cm"] for v in draft["layout"]["vertices"]}
        self.assertIsNone(vs["v006"][0])
        self.assertIsNone(vs["v007"][1])
        self.assertIsNone(vs["v011"][1])

    def test_redundant_equation_count_is_not_rank(self):
        doc = fixture(1)
        width = doc["layout"]["dimensions"][0]
        doc["layout"]["dimensions"] = [dict(deepcopy(width), id=f"dup{i}") for i in range(20)]
        _, report = solve(doc)
        self.assertGreater(report["equation_count"], report["variable_count"])
        self.assertEqual(report["nullity"], 1)
        self.assertEqual(report["status"], "underdetermined")

    def test_t_junction_total_and_parts(self):
        doc = fixture(1)
        layout = doc["layout"]
        p = layout["vertices"][0]["provenance"]
        layout["vertices"].append(
            {
                "id": "split",
                "position_cm": [999, 999],
                "state": "derived",
                "provenance": deepcopy(p),
            }
        )
        wall = layout["walls"][0]
        wall["end_vertex_id"] = "split"
        extra = dict(deepcopy(wall), id="wpart", start_vertex_id="split", end_vertex_id="v002")
        layout["walls"].append(extra)
        layout["rooms"][0]["boundary_vertex_ids"].insert(1, "split")
        layout["rooms"][0]["boundary_wall_ids"].insert(1, "wpart")
        layout["dimensions"] += [
            dimension("part1", {"type": "wall_chain", "wall_ids": [wall["id"]]}, 200),
            dimension("part2", {"type": "wall_chain", "wall_ids": ["wpart"]}, 400),
            dimension("total", {"type": "wall_chain", "wall_ids": [wall["id"], "wpart"]}, 600),
        ]
        draft, good = solve(scramble(doc))
        self.assertTrue(good["validation"]["metric_valid"], good["validation"]["issues"])
        self.assertEqual(
            next((v for v in draft["layout"]["vertices"] if v["id"] == "split"))["position_cm"],
            [200, 0],
        )
        layout["dimensions"][-3]["value_cm"] = 250
        bad_draft, bad = solve(doc)
        self.assertEqual(bad["status"], "inconsistent")
        self.assertEqual(bad_draft["status"], "conflicting")

    def test_separation_same_wall_and_max_corner_offsets(self):
        for n in (15, 18, 41):
            with self.subTest(n=n):
                _, report = solve(scramble(fixture(n)))
                self.assertTrue(
                    report["validation"]["metric_valid"], report["validation"]["issues"]
                )

    def test_invalid_side_chain_relation_are_rejected(self):
        doc = fixture(3)
        doc["layout"]["dimensions"][-1]["target"]["side"] = "west"
        with self.assertRaises(ValueError):
            solve(doc)
        with self.assertRaises(ValueError):
            solve(fixture(3), relations=[relation("bad", "d0", "full_span_opening")])

    def test_wrong_ocr_cannot_override_confirmed_width(self):
        doc = fixture(1)
        wrong = deepcopy(doc["layout"]["dimensions"][0])
        wrong.update(id="ocrwrong", value_cm=450, state="inferred")
        doc["layout"]["dimensions"].append(wrong)
        draft, report = solve(doc)
        self.assertEqual(draft["layout"]["vertices"][1]["position_cm"][0], 600)
        self.assertEqual(report["status"], "determined")
        self.assertFalse(report["validation"]["metric_valid"])
        self.assertEqual(draft["status"], "needs_review")

    def test_explicit_narrow_passage_does_not_imply_full_span(self):
        doc = fixture(3)
        opening = doc["layout"]["openings"][0]
        opening.update(type="open_passage", clear_height_cm=300)
        doc["layout"]["passages"][0]["type"] = "open_passage"
        right = doc["layout"]["rooms"].pop()
        doc["layout"]["corridors"].append(right)
        for record in (opening, doc["layout"]["passages"][0]):
            next((e for e in record["connected_entities"] if e["id"] == right["id"]))[
                "type"
            ] = "corridor"
        draft, report = solve(doc)
        self.assertTrue(report["validation"]["metric_valid"], report["validation"]["issues"])
        self.assertEqual(draft["layout"]["openings"][0]["clear_width_cm"], 120)
        self.assertEqual(draft["layout"]["openings"][0]["center_offset_cm"], 260)

    def test_negative_solution_is_not_accepted_by_linear_success(self):
        doc = fixture(3)
        doc["layout"]["dimensions"][-1]["value_cm"] = 9999
        _, report = solve(doc)
        self.assertEqual(report["status"], "determined")
        self.assertFalse(report["validation"]["metric_valid"])


if __name__ == "__main__":
    unittest.main()
