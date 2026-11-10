import copy
import json
import unittest
from pathlib import Path
from SketchPipeline.shape_authoring.contract import (
    POLICY,
    accept_revision,
    invalidate_bindings,
    near_edge_to_center,
    validate_authoring,
)

FIXTURES = Path(__file__).resolve().parents[1] / "shape_authoring" / "fixtures"


def fixture(name="multi_door_bend"):
    return json.loads((FIXTURES / f"{name}.authoring.json").read_text())


class ShapeAuthoringTests(unittest.TestCase):

    def test_empty_document_needs_no_ocr(self):
        document = fixture("empty")
        self.assertEqual(validate_authoring(document), [])
        self.assertNotIn("observation_document_id", document)
        self.assertNotIn("texts", document["image_evidence"])

    def test_two_doors_and_corridor_bend_keep_separate_ids(self):
        document = fixture()
        self.assertEqual(validate_authoring(document), [])
        topology = document["topology"]
        self.assertEqual(len(topology["connections"][0]["opening_ids"]), 2)
        self.assertEqual(sum((r["type"] == "corridor_segment" for r in topology["regions"])), 2)
        bend = topology["connections"][2]
        self.assertEqual(set(bend["entity_ids"]), {"corridor_a", "corridor_b"})
        self.assertEqual(topology["openings"][3]["type"], "open_passage")

    def test_acceptance_preserves_origin_and_input(self):
        document = fixture()
        before = copy.deepcopy(document)
        accepted = accept_revision(document, "designer")
        self.assertEqual(document, before)
        self.assertEqual(accepted["physical_design"]["acceptance"]["revision_id"], "revision_1")
        self.assertEqual(
            accepted["physical_design"]["values"], document["physical_design"]["values"]
        )
        self.assertNotIn("validated", accepted)

    def test_stale_acceptance_and_ambiguous_topology_rejected(self):
        for mode in ("revision", "ambiguous", "reviewer"):
            with self.subTest(mode=mode):
                d = accept_revision(fixture(), "designer")
                if mode == "revision":
                    d["revision_id"] = "revision_2"
                if mode == "ambiguous":
                    d["topology"]["openings"][0]["geometry"]["state"] = "ambiguous"
                if mode == "reviewer":
                    d["physical_design"]["acceptance"]["reviewer"] = " "
                self.assertTrue(validate_authoring(d))

    def test_topology_edit_retains_locks_and_previous_suggestions(self):
        document = accept_revision(fixture(), "designer")
        value = document["physical_design"]["values"][0]
        value.update(value=650, origin="user_override", locked=True)
        changed = invalidate_bindings(document, "revision_2", ["room_a"])
        updated = changed["physical_design"]["values"][0]
        self.assertEqual(
            (updated["value"], updated["origin"], updated["locked"]), (650, "user_override", True)
        )
        self.assertEqual(updated["previous_suggestion"], value["previous_suggestion"])
        self.assertEqual(updated["binding_revision_id"], "revision_1")
        self.assertEqual(updated["state"], "stale")
        self.assertEqual(changed["physical_design"]["acceptance"]["status"], "pending")
        self.assertEqual(validate_authoring(changed), [])
        with self.assertRaises(ValueError):
            accept_revision(changed, "designer")
        self.assertEqual(document["revision_id"], "revision_1")

    def test_near_edge_reference_direction_and_local_t(self):
        self.assertEqual(near_edge_to_center(400, 0, 1, 50, 120), 110)
        self.assertEqual(near_edge_to_center(400, 400, -1, 50, 120), 290)
        self.assertEqual(near_edge_to_center(400, 200, -1, 50, 120), 90)
        for values in [
            (200, 0, 1, 100, 120),
            (400, 0, 1, float("nan"), 120),
            (400, 0, 1, 0, 0),
            (400, 500, -1, 0, 120),
        ]:
            with self.assertRaises(ValueError):
                near_edge_to_center(*values)

    def test_unknown_fields_nonfinite_and_broken_references_rejected(self):
        mutations = [
            lambda d: d.update(texts=[]),
            lambda d: d["physical_design"]["values"][0].update(value=float("inf")),
            lambda d: d["topology"]["openings"][0].update(support_wall_id="absent"),
            lambda d: d["topology"]["walls"][0].update(entity_ids=["absent"]),
            lambda d: d["image_evidence"]["original_to_working"][0].__setitem__(0, 0),
            lambda d: d["topology"]["junctions"][0]["geometry"]["points_px"][0].__setitem__(0, 10),
            lambda d: d["topology"]["openings"][0]["placement"].update(direction="toward_start"),
            lambda d: d["topology"]["connections"][0]["opening_ids"].pop(),
        ]
        for mutate in mutations:
            document = fixture()
            mutate(document)
            self.assertTrue(validate_authoring(document))

    def test_numbered_and_unnumbered_sources_have_identical_policy(self):
        a, b = (fixture(), fixture())
        a["image_evidence"]["source"]["image_path"] = "numbered.png"
        b["image_evidence"]["source"]["image_path"] = "unnumbered.png"
        b["image_evidence"]["source"]["image_sha256"] = "1" * 64
        self.assertEqual(validate_authoring(a), validate_authoring(b))
        self.assertEqual(a["physical_design"], b["physical_design"])
        self.assertEqual(POLICY["numeric_text"], "ignored")

    def test_uniform_resampling_preserves_normalized_geometry_and_sizes(self):
        d = fixture()
        scaled = copy.deepcopy(d)
        evidence = scaled["image_evidence"]
        evidence["working_size_px"] = [800, 800]
        evidence["normalization_bounds_px"] = [0, 0, 800, 800]
        evidence["original_to_working"] = [[2, 0, 0], [0, 2, 0], [0, 0, 1]]
        evidence["working_to_original"] = [[0.5, 0, 0], [0, 0.5, 0], [0, 0, 1]]
        for values in scaled["topology"].values():
            for e in values:
                e["geometry"]["points_px"] = [[x * 2, y * 2] for x, y in e["geometry"]["points_px"]]
        self.assertEqual(validate_authoring(scaled), [])
        self.assertEqual(d["physical_design"], scaled["physical_design"])
        self.assertEqual(
            [e["geometry"]["points_normalized"] for e in d["topology"]["regions"]],
            [e["geometry"]["points_normalized"] for e in scaled["topology"]["regions"]],
        )


if __name__ == "__main__":
    unittest.main()
