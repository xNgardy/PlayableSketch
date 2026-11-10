from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from SketchPipeline.evaluation.metrics import (
    association_metrics,
    compare_layout,
    counts,
    end_to_end,
    endpoint_error,
    pairs,
    release_gate,
    numeric_metrics,
)
from SketchPipeline.evaluation.protocol import audit_split, sha, verify
from SketchPipeline.evaluation.review import correction_metrics, validate_telemetry
from SketchPipeline.evaluation.report import graph_metrics
from SketchPipeline.validation.validate import load_json, as_validated
from SketchPipeline.review.metric_store import MetricReviewStore
from SketchPipeline.review.server import ReviewError
from SketchPipeline.tests.test_metric_pipeline import prepare

ROOT = Path(__file__).resolve().parents[2]


class EvaluationTests(unittest.TestCase):

    def fixture(self, n=3):
        return load_json(ROOT / f"Data/ground_truth/v1/Data_{n}.validated.json")

    def test_maximum_cardinality_handles_competing_matches(self):
        costs = [[0, 1], [0.5, 100]]
        self.assertEqual(len(pairs([0, 1], [0, 1], lambda i, j: costs[i][j], 1)), 2)

    def test_object_matching_no_duplicate_credit(self):
        self.assertEqual(len(pairs([0, 0], [0], lambda a, b: abs(a - b), 1)), 1)
        self.assertIsNone(counts(0, 0, 0)["f1"])

    def test_translation_not_metric_error(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        for v in pred["layout"]["vertices"]:
            v["position_cm"] = [v["position_cm"][0] + 123, v["position_cm"][1] - 789]
        self.assertTrue(compare_layout(pred, ref)["exact"])

    def test_ids_not_used_as_reference_correspondence(self):
        ref = self.fixture()

        def rename(value):
            if isinstance(value, list):
                return [rename(x) for x in value]
            if isinstance(value, dict):
                return {k: rename(v) for k, v in value.items()}
            if isinstance(value, str):
                return "renamed-" + value if value in ids else value
            return value

        ids = {e["id"] for group in ref["layout"].values() for e in group}
        self.assertTrue(compare_layout(rename(ref), ref)["exact"])

    def test_scale_is_not_aligned_away(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        for v in pred["layout"]["vertices"]:
            v["position_cm"] = [x * 1.1 for x in v["position_cm"]]
        self.assertFalse(compare_layout(pred, ref)["exact"])

    def test_rotation_requires_explicit_policy(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        for v in pred["layout"]["vertices"]:
            v["position_cm"] = [-v["position_cm"][1], v["position_cm"][0]]
        self.assertFalse(compare_layout(pred, ref)["exact"])

    def test_mirrored_asymmetric_layout_not_accepted(self):
        ref = self.fixture(8)
        pred = deepcopy(ref)
        for v in pred["layout"]["vertices"]:
            v["position_cm"][0] *= -1
        self.assertFalse(compare_layout(pred, ref)["exact"])

    def test_wrong_opening_width_detected(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        pred["layout"]["openings"][0]["clear_width_cm"] += 10
        result = compare_layout(pred, ref)
        self.assertFalse(result["exact"])
        self.assertEqual(result["opening_width_error_cm"]["maximum"], 10)

    def test_shifted_door_is_not_hidden_by_ids(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        pred["layout"]["openings"][0]["center_offset_cm"] += 5
        result = compare_layout(pred, ref)
        self.assertFalse(result["exact"])
        self.assertEqual(result["opening_center_displacement_cm"]["maximum"], 5)

    def test_missing_geometry_is_null(self):
        self.assertIsNone(compare_layout(None, self.fixture())["exact"])
        pred = self.fixture()
        pred["layout"]["vertices"][0]["position_cm"] = [None, None]
        self.assertEqual(compare_layout(pred, self.fixture())["status"], "not_computed")

    def test_missing_opening_is_not_perfect_zero_error(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        pred["layout"]["openings"][0]["clear_width_cm"] = None
        self.assertEqual(compare_layout(pred, ref)["status"], "not_computed")

    def test_wrong_shared_wall_relation_is_error(self):
        ref = self.fixture()
        pred = deepcopy(ref)
        next((w for w in pred["layout"]["walls"] if len(w["region_ids"]) == 2))["region_ids"] = [
            "wrongA",
            "wrongB",
        ]
        self.assertFalse(compare_layout(pred, ref)["exact"])

    def test_digit_error_counts_missing_and_extra_digits(self):
        metric = dict(
            matched_pairs=[dict(predicted_raw="80 cm", expected_raw="800 cm")],
            unmatched_reference_ids=["r2"],
            unmatched_prediction_ids=["p2"],
            numeric_exact_correct=0,
            reference=2,
        )
        result = numeric_metrics(
            metric, [dict(id="p2", raw_text="17")], [dict(id="r2", raw_text="120")]
        )
        self.assertEqual(result["digit_edits"], 6)
        self.assertEqual(result["reference_digits"], 6)

    def test_association_compares_spans_not_ids(self):
        a = [dict(text_id="truth", span_start_px=[0, 0], span_end_px=[100, 0])]
        p = [
            dict(
                evidence_id="prediction",
                candidates=[dict(start_px_y_up=[100, 0], end_px_y_up=[0, 0])],
            )
        ]
        self.assertEqual(association_metrics(p, a, {"prediction": "truth"})["top1"], 1)
        self.assertIsNone(association_metrics(None, a, {})["top1"])

    def test_failed_and_needs_review_remain_denominator(self):
        report = end_to_end(
            [
                dict(id="a", automatic_state="auto_accepted", correct=False),
                dict(id="b", automatic_state="needs_review"),
                dict(id="c", automatic_state="failed"),
            ]
        )
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["false_auto_accepts"], ["a"])
        self.assertEqual(report["before"]["failed"], 1)

    def test_wrong_auto_accept_blocks_release(self):
        result = release_gate(
            false_auto_accepts=["bad"],
            invalid_exports=[],
            regressions_passed=True,
            human_review_cases=1,
            unseen_writer_cases=1,
            p95_seconds=1,
            correction_seconds=10,
        )
        self.assertEqual(result["local_review_required_workflow"], "failed")
        self.assertIn("critical_false_auto_accept", result["blockers"])

    def test_missing_human_time_and_holdout_block_autonomy(self):
        result = release_gate(
            false_auto_accepts=[],
            invalid_exports=[],
            regressions_passed=True,
            human_review_cases=0,
            unseen_writer_cases=0,
            p95_seconds=1,
        )
        self.assertEqual(result["local_review_required_workflow"], "passed")
        self.assertEqual(result["autonomous_or_general_release"], "blocked")

    def test_group_leakage_detected(self):
        samples = [
            dict(id="a", base_plan_id="g", image_sha256="1", evaluation_split="train"),
            dict(
                id="b", source_id="a", base_plan_id="g", image_sha256="2", evaluation_split="test"
            ),
        ]
        self.assertFalse(audit_split(samples, {"g": "train"})["passed"])

    def test_same_family_and_identical_image_cannot_cross_split(self):
        samples = [
            dict(id="a", base_plan_id="g1", image_sha256="same"),
            dict(id="b", base_plan_id="g2", image_sha256="same"),
        ]
        result = audit_split(samples, {"g1": "train", "g2": "test"}, {"g1": 1, "g2": 1})
        self.assertEqual(len(result["issues"]), 2)

    def test_protocol_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "source"
            file.write_text("original")
            protocol = dict(input_sha256={"source": sha(file)})
            self.assertTrue(verify(protocol, root))
            file.write_text("changed")
            with self.assertRaises(ValueError):
                verify(protocol, root)

    def test_old_review_elapsed_not_human_time(self):
        rows = [
            dict(
                created_at="2026-10-21T10:00:00+00:00",
                command=dict(type="save", affected_entity_ids=["a"]),
            ),
            dict(created_at="2026-10-21T11:00:00+00:00", command=dict(type="accept")),
        ]
        result = correction_metrics(rows)
        self.assertIsNone(result["active_review_seconds"])
        self.assertEqual(result["wall_elapsed_seconds"], 3600)
        self.assertEqual(result["edit_commands"], 1)

    def test_telemetry_strict_and_bounded(self):
        for value in [
            True,
            dict(active_ms=True, interaction_count=1, source="browser-visible-interaction/v1"),
            dict(active_ms=1800001, interaction_count=1, source="browser-visible-interaction/v1"),
            dict(active_ms=1, interaction_count=1, source="other"),
        ]:
            with self.assertRaises(ValueError):
                validate_telemetry(value)

    def test_hallucinated_confirmed_measurement_does_not_auto_export(self):
        doc = load_json(ROOT / "Data/ground_truth/v1/Data_9.draft.json")
        with self.assertRaises(ValueError):
            as_validated(doc, "controlled-test")
        doc = load_json(ROOT / "Data/ground_truth/v1/Data_10.draft.json")
        with self.assertRaises(ValueError):
            as_validated(doc, "controlled-test")

    def test_telemetry_is_immutable_ledger_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            topology, path, obs, bindings = prepare(Path(directory))
            try:
                store = MetricReviewStore(topology)
                state = dict(
                    bindings=bindings,
                    names={},
                    validation_mode="geometry_only",
                    start_room_id=None,
                    goal_room_id=None,
                    semantics_confirmed=True,
                )
                telemetry = dict(
                    active_ms=1234, interaction_count=2, source="browser-visible-interaction/v1"
                )
                first = store.transact("Data_1", None, "save", state, telemetry=telemetry)
                record = store.latest("Data_1")
                self.assertEqual(record["telemetry"], telemetry)
                self.assertNotIn("telemetry", record["draft"])
                with self.assertRaises(ReviewError):
                    store.transact(
                        "Data_1",
                        first["base_revision_id"],
                        "save",
                        state,
                        telemetry={"active_ms": -1},
                    )
                self.assertEqual(store.latest("Data_1")["revision_id"], record["revision_id"])
            finally:
                topology.uploads.close()

    def test_challenge_writer_owns_output_directory(self):
        from unittest.mock import patch
        from SketchPipeline.evaluation.challenges import worker
        from SketchPipeline.evaluation.protocol import write

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "probe.png"
            image.write_bytes(b"controlled-image")
            write(
                root / "manifest.json",
                dict(
                    samples=[
                        dict(
                            id="probe",
                            image_path="probe.png",
                            image_sha256=sha(image),
                            labels_unchanged=False,
                        )
                    ]
                ),
            )

            class Adapter:
                runtime = {"adapter": "controlled-test"}

            def persist(path, *args):
                self.assertFalse(path.exists())
                path.mkdir()

            with (
                patch("SketchPipeline.perception.ocr.RapidOCRAdapter", Adapter),
                patch(
                    "SketchPipeline.perception.run.predict",
                    return_value=({}, dict(duration_seconds=0.5), {}, {}),
                ),
                patch("SketchPipeline.perception.run.write_prediction", persist),
            ):
                worker(root, "probe")
            self.assertEqual(
                json.loads((root / "probe.result.json").read_text())["status"], "inference_complete"
            )

    def test_artifact_tampering_is_detected(self):
        from SketchPipeline.evaluation.integrity import seal, verify_artifacts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "report.json"
            path.write_text("{}")
            seal(root)
            self.assertTrue(verify_artifacts(root))
            path.write_text('{"changed":true}')
            with self.assertRaises(ValueError):
                verify_artifacts(root)

    def test_model_comparison_requires_identical_data_and_policy(self):
        from SketchPipeline.evaluation.metrics import compare_reports

        a = dict(comparability_key="one", samples=[dict(id="a")], cohorts={})
        b = deepcopy(a)
        self.assertTrue(compare_reports(a, b)["comparable"])
        b["comparability_key"] = "different"
        with self.assertRaises(ValueError):
            compare_reports(a, b)

    def test_model_comparison_cannot_drop_failed_samples(self):
        from SketchPipeline.evaluation.metrics import compare_reports

        a = dict(comparability_key="one", samples=[dict(id="a"), dict(id="failed")], cohorts={})
        b = dict(comparability_key="one", samples=[dict(id="a")], cohorts={})
        with self.assertRaises(ValueError):
            compare_reports(a, b)


if __name__ == "__main__":
    unittest.main()
