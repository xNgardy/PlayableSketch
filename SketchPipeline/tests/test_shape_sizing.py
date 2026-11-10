import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from SketchPipeline.shape_authoring.decoder import authoring_document, boundary_graph
from SketchPipeline.shape_authoring.sizing import recompute
from SketchPipeline.shape_authoring.contract import validate_authoring, accept_revision
from SketchPipeline.validation.validate import validate_document


def plan(boxes=None, doors=1, passage=False):
    boxes = boxes or [
        {"type": "room", "bounds_px": [0, 0, 200, 160], "model_score": 1},
        {"type": "room", "bounds_px": [200, 0, 320, 160], "model_score": 1},
    ]
    segments, _ = boundary_graph(boxes)
    shared = [(s, o) for s, o in segments.items() if len(o) == 2]
    proposals = []
    if shared and doors:
        s, owners = shared[0]
        axis = 0 if s[0][1] == s[1][1] else 1
        L = s[1][axis] - s[0][axis]
        for i in range(doors):
            a, b = (list(s[0]), list(s[1]))
            a[axis] = s[0][axis] + L * (0.1 + i * 0.45)
            b[axis] = a[axis] + L * 0.1
            proposals.append(
                {
                    "segment": s,
                    "entity_indices": owners,
                    "start": a,
                    "end": b,
                    "type": "open_passage" if passage else "door",
                }
            )
    meta = {
        "working_size_px": [500, 400],
        "original_to_working": np.eye(3).tolist(),
        "working_to_original": np.eye(3).tolist(),
    }
    return authoring_document(
        {
            "image_path": "synthetic.png",
            "image_sha256": "0" * 64,
            "width_px": 500,
            "height_px": 400,
        },
        meta,
        boxes,
        proposals,
    )


def value(result, entity, param):
    return next(
        (
            v
            for v in result["authoring"]["physical_design"]["values"]
            if v["entity_id"] == entity and v["parameter"] == param
        )
    )


class ShapeSizingTests(unittest.TestCase):

    def ready(self, result):
        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(validate_authoring(result["authoring"]), [])
        report = validate_document(result["preview"]["canonical"])
        self.assertTrue(report["metric_valid"], report)
        self.assertFalse(report["exportable"])
        self.assertFalse(result["exportable"])

    def test_proportion_example_and_automatic_defaults(self):
        r = recompute(plan(doors=0))
        self.ready(r)
        self.assertAlmostEqual(value(r, "region_0001", "width_cm")["value"], 500, places=3)
        self.assertAlmostEqual(value(r, "region_0001", "depth_cm")["value"], 400, places=3)
        self.assertAlmostEqual(value(r, "region_0002", "width_cm")["value"], 300, places=3)

    def test_resize_and_crop_translation_invariance(self):
        a = plan()
        b = copy.deepcopy(a)
        for entities in b["topology"].values():
            for e in entities:
                e["geometry"]["points_px"] = [
                    [x * 2 + 10, y * 2 + 8] for x, y in e["geometry"]["points_px"]
                ]
                e["geometry"]["points_normalized"] = [
                    [(x - 10) / 1000, (y - 8) / 800] for x, y in e["geometry"]["points_px"]
                ]
        b["image_evidence"].update(
            working_size_px=[1020, 820], normalization_bounds_px=[10, 8, 1010, 808]
        )
        first = recompute(a)
        second = recompute(b)
        self.ready(first)
        self.ready(second)
        va = [v["value"] for v in first["authoring"]["physical_design"]["values"]]
        vb = [v["value"] for v in second["authoring"]["physical_design"]["values"]]
        np.testing.assert_allclose(va, vb, atol=1e-05)

    def test_numbered_source_does_not_change_sizes(self):
        a = plan()
        b = copy.deepcopy(a)
        b["image_evidence"]["source"]["image_path"] = "999cm.png"
        b["image_evidence"]["source"]["image_sha256"] = "f" * 64
        self.assertEqual(
            recompute(a)["authoring"]["physical_design"]["values"],
            recompute(b)["authoring"]["physical_design"]["values"],
        )

    def test_immutable_inputs_and_pending_acceptance(self):
        a = plan()
        original = copy.deepcopy(a)
        r = recompute(a)
        self.ready(r)
        self.assertEqual(a, original)
        self.assertEqual(r["authoring"]["physical_design"]["acceptance"]["status"], "pending")

    def test_user_override_and_units_survive_recompute_even_unlocked(self):
        d = plan()
        r = recompute(
            d,
            {
                "edits": [
                    {"entity_id": "region_0001", "parameter": "width_cm", "value": 8, "unit": "m"}
                ]
            },
        )
        self.ready(r)
        again = recompute(d, {"design_scale": 1.5}, r)
        self.ready(again)
        self.assertAlmostEqual(value(again, "region_0001", "width_cm")["value"], 800, places=4)
        self.assertEqual(value(again, "region_0001", "width_cm")["origin"], "user_override")
        self.assertFalse(value(again, "region_0001", "width_cm")["locked"])

    def test_lock_and_reset_keep_suggestion_provenance(self):
        d = plan()
        r = recompute(
            d,
            {
                "edits": [
                    {
                        "entity_id": "region_0001",
                        "parameter": "width_cm",
                        "value": 800,
                        "locked": True,
                    }
                ]
            },
        )
        reset = recompute(
            d,
            {"edits": [{"entity_id": "region_0001", "parameter": "width_cm", "action": "reset"}]},
            r,
        )
        self.ready(reset)
        v = value(reset, "region_0001", "width_cm")
        self.assertFalse(v["locked"])
        self.assertEqual(v["origin"], "proportion_suggestion")
        self.assertAlmostEqual(v["value"], 500, places=3)

    def test_shared_wall_conflict_retains_values_and_last_preview(self):
        d = plan()
        r = recompute(d)
        bad = recompute(
            d,
            {
                "edits": [
                    {
                        "entity_id": "region_0001",
                        "parameter": "depth_cm",
                        "value": 400,
                        "locked": True,
                    },
                    {
                        "entity_id": "region_0002",
                        "parameter": "depth_cm",
                        "value": 500,
                        "locked": True,
                    },
                ]
            },
            r,
        )
        self.assertEqual(bad["status"], "needs_attention")
        self.assertTrue(bad["preview_is_stale"])
        self.assertEqual(bad["preview"], r["preview"])
        self.assertEqual(value(bad, "region_0001", "depth_cm")["value"], 400)
        self.assertEqual(value(bad, "region_0002", "depth_cm")["value"], 500)
        repaired = recompute(
            d,
            {"edits": [{"entity_id": "region_0002", "parameter": "depth_cm", "action": "reset"}]},
            bad,
        )
        self.ready(repaired)

    def test_aspect_lock_and_shared_depth_recompute_together(self):
        r = recompute(
            plan(),
            {
                "aspect_locks": ["region_0001"],
                "edits": [{"entity_id": "region_0001", "parameter": "width_cm", "value": 800}],
            },
        )
        self.ready(r)
        self.assertAlmostEqual(value(r, "region_0001", "depth_cm")["value"], 640, places=3)
        self.assertAlmostEqual(value(r, "region_0002", "depth_cm")["value"], 640, places=3)

    def test_two_doors_remain_distinct_and_nonoverlapping(self):
        r = recompute(plan(doors=2))
        self.ready(r)
        openings = r["preview"]["canonical"]["layout"]["openings"]
        self.assertEqual(len(openings), 2)
        a, b = sorted(openings, key=lambda o: o["center_offset_cm"])
        self.assertLessEqual(
            a["center_offset_cm"] + a["clear_width_cm"] / 2,
            b["center_offset_cm"] - b["clear_width_cm"] / 2 + 1e-05,
        )
        self.assertEqual(len(r["preview"]["canonical"]["layout"]["passages"]), 2)

    def test_conflicting_door_offsets_are_not_silently_moved(self):
        d = plan(doors=2)
        r = recompute(d)
        bad = recompute(
            d,
            {
                "edits": [
                    {"entity_id": "opening_0001", "parameter": "near_edge_offset_cm", "value": 10},
                    {"entity_id": "opening_0002", "parameter": "near_edge_offset_cm", "value": 20},
                ]
            },
            r,
        )
        self.assertEqual(bad["status"], "needs_attention")
        self.assertEqual(bad["preview"], r["preview"])

    def test_large_door_expands_unlocked_shared_span(self):
        r = recompute(
            plan(),
            {"edits": [{"entity_id": "opening_0001", "parameter": "clear_width_cm", "value": 600}]},
        )
        self.ready(r)
        self.assertGreaterEqual(value(r, "region_0001", "depth_cm")["value"], 600 - 0.0001)

    def test_reversed_reference_and_orthogonal_rotations(self):
        for rotation in [0, 90, 180, 270]:
            d = plan()
            o = d["topology"]["openings"][0]
            w = next((w for w in d["topology"]["walls"] if w["id"] == o["support_wall_id"]))
            o["placement"].update(
                reference_junction_id=w["end_junction_id"],
                direction="toward_start",
                near_edge_normalized=1 - o["placement"]["interval_normalized"][1],
            )
            d["physical_design"]["orientation_degrees"] = rotation
            d["physical_design"]["anchor"]["position_cm"] = [100, -50]
            r = recompute(d)
            self.ready(r)
            anchor = r["authoring"]["physical_design"]["anchor"]["junction_id"]
            p = next(
                (
                    v["position_cm"]
                    for v in r["preview"]["canonical"]["layout"]["vertices"]
                    if v["id"] == anchor
                )
            )
            self.assertEqual(p, [100, -50])

    def test_corridor_bend_interfaces_are_continuous(self):
        boxes = [
            {"type": "room", "bounds_px": [0, 0, 200, 160], "model_score": 1},
            {"type": "corridor_segment", "bounds_px": [200, 60, 300, 100], "model_score": 1},
            {"type": "corridor_segment", "bounds_px": [260, 100, 300, 200], "model_score": 1},
        ]
        d = plan(boxes, doors=0)
        segments, _ = boundary_graph(boxes)
        props = []
        for s, owners in segments.items():
            if len(owners) == 2:
                props.append(
                    {
                        "segment": s,
                        "entity_indices": owners,
                        "start": list(s[0]),
                        "end": list(s[1]),
                        "type": "open_passage",
                    }
                )
        d = authoring_document(
            d["image_evidence"]["source"],
            {
                "working_size_px": [500, 400],
                "original_to_working": np.eye(3).tolist(),
                "working_to_original": np.eye(3).tolist(),
            },
            boxes,
            props,
        )
        r = recompute(d)
        self.ready(r)
        for o in r["preview"]["canonical"]["layout"]["openings"]:
            w = next(
                (w for w in r["preview"]["canonical"]["layout"]["walls"] if w["id"] == o["wall_id"])
            )
            p = {v["id"]: v["position_cm"] for v in r["preview"]["canonical"]["layout"]["vertices"]}
            axis = "xy".index(w["axis"])
            self.assertAlmostEqual(
                o["clear_width_cm"],
                p[w["end_vertex_id"]][axis] - p[w["start_vertex_id"]][axis] - 20,
                places=4,
            )

    def test_cycle_preserves_all_four_interfaces(self):
        boxes = [
            {"type": "room", "bounds_px": b, "model_score": 1}
            for b in [
                [0, 0, 100, 100],
                [100, 0, 200, 100],
                [0, 100, 100, 200],
                [100, 100, 200, 200],
            ]
        ]
        d = plan(boxes, doors=0)
        segments, _ = boundary_graph(boxes)
        props = []
        for s, owners in segments.items():
            if len(owners) == 2:
                a, b = (np.asarray(s[0]), np.asarray(s[1]))
                props.append(
                    {
                        "segment": s,
                        "entity_indices": owners,
                        "start": (a + (b - a) * 0.3).tolist(),
                        "end": (a + (b - a) * 0.6).tolist(),
                        "type": "door",
                    }
                )
        d = authoring_document(
            d["image_evidence"]["source"],
            {
                "working_size_px": [500, 400],
                "original_to_working": np.eye(3).tolist(),
                "working_to_original": np.eye(3).tolist(),
            },
            boxes,
            props,
        )
        r = recompute(d)
        self.ready(r)
        self.assertEqual(len(r["preview"]["canonical"]["layout"]["passages"]), 4)

    def test_topology_change_stales_bindings_until_explicit_reset(self):
        d = plan()
        r = recompute(
            d, {"edits": [{"entity_id": "region_0001", "parameter": "width_cm", "value": 800}]}
        )
        changed = plan(doors=2)
        changed["revision_id"] = "topology_2"
        stale = recompute(changed, {}, r)
        self.assertEqual(stale["status"], "needs_attention")
        self.assertTrue(
            all((v["state"] == "stale" for v in stale["authoring"]["physical_design"]["values"]))
        )
        reset = recompute(changed, {"reset_bindings": True}, stale)
        self.ready(reset)
        self.assertTrue(reset["discarded_bindings"])

    def test_invalid_values_are_rejected_before_solver(self):
        for bad in [float("nan"), float("inf"), -1, True, 0]:
            with self.assertRaises(ValueError):
                recompute(
                    plan(),
                    {
                        "edits": [
                            {"entity_id": "region_0001", "parameter": "width_cm", "value": bad}
                        ]
                    },
                )

    def test_bulk_choice_does_not_accept_geometry_or_export(self):
        r = recompute(plan(), {"use_suggested_sizes": True})
        self.ready(r)
        self.assertTrue(r["suggestions_chosen"])
        self.assertEqual(r["authoring"]["physical_design"]["acceptance"]["status"], "pending")

    def test_height_conflicts_are_explicit(self):
        r = recompute(
            plan(),
            {"edits": [{"entity_id": "global", "parameter": "door_height_cm", "value": 400}]},
        )
        self.assertEqual(r["status"], "needs_attention")
        self.assertEqual(r["issues"][0]["code"], "height_conflict")

    def test_settings_overrides_and_floor_config(self):
        r = recompute(
            plan(),
            {
                "settings": {"floor_thickness_cm": 30},
                "edits": [{"entity_id": "global", "parameter": "door_height_cm", "value": 250}],
            },
        )
        self.ready(r)
        self.assertEqual(r["preview"]["canonical"]["settings"]["floor_thickness_cm"], 30)
        self.assertEqual(r["preview"]["canonical"]["layout"]["openings"][0]["clear_height_cm"], 250)

    def test_unknown_geometry_does_not_generate_valid_preview(self):
        d = plan()
        d["topology"]["regions"][0]["geometry"]["state"] = "ambiguous"
        r = recompute(d)
        self.assertEqual(r["status"], "needs_attention")
        self.assertIsNone(r["preview"])

    def test_existing_contract_fixture(self):
        path = Path("SketchPipeline/shape_authoring/fixtures/multi_door_bend.authoring.json")
        r = recompute(json.loads(path.read_text()))
        self.ready(r)

    def test_malformed_requests_and_settings_are_rejected(self):
        for request in [
            [],
            {"edits": "bad"},
            {"edits": ["bad"]},
            {"settings": []},
            {"use_suggested_sizes": "yes"},
            {"reset_bindings": 1},
        ]:
            with self.assertRaises(ValueError):
                recompute(plan(), request)

    def test_opening_height_suggestion_follows_global_override(self):
        r = recompute(
            plan(),
            {"edits": [{"entity_id": "global", "parameter": "door_height_cm", "value": 250}]},
        )
        self.ready(r)
        self.assertEqual(value(r, "opening_0001", "height_cm")["previous_suggestion"]["value"], 250)

    def test_aligned_disconnected_rooms_resize_independently(self):
        boxes = [
            {"type": "room", "bounds_px": b, "model_score": 1}
            for b in [[0, 0, 200, 160], [0, 220, 200, 380]]
        ]
        r = recompute(
            plan(boxes, doors=0),
            {
                "edits": [
                    {"entity_id": "region_0001", "parameter": "width_cm", "value": 400},
                    {"entity_id": "region_0002", "parameter": "width_cm", "value": 600},
                ]
            },
        )
        self.ready(r)
        self.assertAlmostEqual(value(r, "region_0001", "width_cm")["value"], 400, places=4)
        self.assertAlmostEqual(value(r, "region_0002", "width_cm")["value"], 600, places=4)


if __name__ == "__main__":
    unittest.main()
