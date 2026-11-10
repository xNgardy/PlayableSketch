from collections import defaultdict
import unittest
from SketchPipeline.experiments.evaluate_v1 import MANIFEST, f1, freeze
from SketchPipeline.experiments.compare_ocr_v1 import evaluation_samples
from SketchPipeline.experiments.train_ocr_v1 import numeric, edit_distance
from SketchPipeline.perception.geometry import gap_evidence
from SketchPipeline.synthetic.augment import read


class ExperimentTests(unittest.TestCase):

    def test_trained_comparison_covers_whole_test_cohort_and_original_diagnostics(self):
        split = freeze()
        all_samples = read(MANIFEST)["samples"]
        chosen = evaluation_samples(all_samples, split)
        self.assertEqual(len(chosen), 240)
        self.assertEqual(
            sum((split["group_split"][s["base_plan_id"]] == "test" for s in chosen)), 144
        )
        self.assertEqual(sum((s["origin"] != "augmented" for s in chosen)), 120)
        self.assertTrue(
            all(
                (
                    s["origin"] != "augmented" or split["group_split"][s["base_plan_id"]] == "test"
                    for s in chosen
                )
            )
        )

    def test_group_split_covers_all_variants_without_family_leakage(self):
        split = freeze()
        samples = read(MANIFEST)["samples"]
        groups = defaultdict(set)
        for s in samples:
            groups[s["base_plan_id"]].add(split["group_split"][s["base_plan_id"]])
        self.assertEqual(len(groups), 80)
        self.assertTrue(all((len(v) == 1 for v in groups.values())))
        families = defaultdict(set)
        for plan, family in split["synthetic_geometry_families"].items():
            families[family].add(split["group_split"][plan])
        self.assertTrue(all((len(v) == 1 for v in families.values())))
        self.assertEqual(split["images"], dict(train=462, validation=114, test=144))

    def test_empty_metrics_are_unknown_and_f1_is_count_consistent(self):
        self.assertIsNone(f1(None, 1.0))
        self.assertEqual(f1(0.0, 0.0), 0.0)
        self.assertAlmostEqual(f1(11 / 16, 1.0), 22 / 27)

    def test_numeric_requires_observed_unit_and_cer_keeps_unit_errors(self):
        self.assertEqual(numeric(" 120cm "), 120.0)
        self.assertIsNone(numeric("120"))
        self.assertEqual(edit_distance("120", "120 cm"), 3)

    def test_compact_gap_evaluation_preserves_all_promoted_proposals(self):

        def line(id, a, b, axis="vertical", role="wall_candidate"):
            return dict(id=id, start=a, end=b, axis=axis, role=role)

        lines = [
            line("a", [100, 10], [100, 100]),
            line("b", [100, 160], [100, 300]),
            line("t1", [80, 100], [120, 100], "horizontal", "unknown"),
            line("t2", [80, 160], [120, 160], "horizontal", "unknown"),
            line("noise", [220, 10], [220, 99]),
            line("noise2", [220, 103], [220, 300]),
        ]
        full = gap_evidence(lines, [], (400, 400))
        compact = gap_evidence(lines, [], (400, 400), diagnostics=False)
        expected = [g for g in full if g["role"] == "opening_candidate"]
        self.assertTrue(expected)
        self.assertEqual(compact, expected)
        self.assertTrue(any((g["role"] == "unresolved_gap" for g in full)))


if __name__ == "__main__":
    unittest.main()
