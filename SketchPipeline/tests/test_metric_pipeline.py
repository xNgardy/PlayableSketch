from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from jsonschema import ValidationError
from SketchPipeline.association.topology import load_review, skeleton
from SketchPipeline.association.associate import propose, hypotheses, transform_points, span_catalog
from SketchPipeline.metric import reconstruct
from SketchPipeline.review.server import ReviewStore, digest
from SketchPipeline.tests.test_topology_review import write_case, two_rooms, state_with
from SketchPipeline.tests.test_topology import perimeter, wall
from SketchPipeline.tests.test_metric_solver import fixture, dimension


def prepare(root):
    store = write_case(root)
    folder = store.run / "Data_1"
    obs = {
        "schema_version": "playablesketch-observations/1.0",
        "kind": "observations",
        "document_id": "test-observations",
        "revision_id": "ocr1",
        "source": json.loads((folder / "observations.json").read_text())["source"],
        "coordinate_system": "u_right_v_down",
        "units": "px",
        "frame": {
            "id": "original",
            "width_px": 220,
            "height_px": 120,
            "original_to_frame": np.eye(3).tolist(),
        },
        "region_annotation_status": "complete",
        "texts": [],
        "lines": [],
        "opening_candidates": [],
        "issues": [],
        "notes": [],
    }
    obs["source"]["legacy_draft_path"] = None
    for i, value in enumerate([600, 400, 500, 400, 120, 200], 1):
        obs["texts"].append(
            {
                "id": f"t{i}",
                "raw_text": f"{value} cm",
                "polygon_px": [[20 + i, 2], [40 + i, 2], [40 + i, 8], [20 + i, 8]],
                "parsed_value_cm": value,
                "score": 0.8,
                "method": "ocr",
            }
        )
    (folder / "observations.json").write_text(json.dumps(obs))
    store = ReviewStore(store.run, store.output)
    rev = store.save("Data_1", two_rooms(), None, "accept")
    path = store.output / "Data_1" / "revisions" / (rev["revision_id"] + ".json")
    regions = sorted(rev["topology"]["regions"], key=lambda r: r["bounds_px_rotated"][0])
    left, right = [r["id"] for r in regions]
    dims = [
        dimension("dim1", {"type": "region_span", "region_id": left, "axis": "x"}, 600),
        dimension("dim2", {"type": "region_span", "region_id": left, "axis": "y"}, 400),
        dimension("dim3", {"type": "region_span", "region_id": right, "axis": "x"}, 500),
        dimension("dim4", {"type": "region_span", "region_id": right, "axis": "y"}, 400),
        dimension("dim5", {"type": "opening_width", "opening_id": "door"}, 120, "clear_opening"),
        dimension(
            "dim6",
            {
                "type": "opening_offset",
                "opening_id": "door",
                "region_id": left,
                "side": "east",
                "reference": "min_corner",
            },
            200,
            "edge_offset",
        ),
    ]
    for i, d in enumerate(dims, 1):
        d["provenance"]["evidence_ids"] = [f"t{i}"]
    request = {
        "schema_version": "playablesketch-metric-input/1.0",
        "topology_revision_id": rev["revision_id"],
        "region_kinds": {left: "room", right: "room"},
        "dimensions": dims,
        "hypothesis_budget": 4,
    }
    return (store, path, folder / "observations.json", request)


class MetricPipelineTests(unittest.TestCase):

    def test_review_to_draft_exact_and_shared_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path, obs, request = prepare(Path(tmp))
            before = path.read_bytes()
            draft, report = reconstruct(path, obs, request)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(report["validation"]["metric_valid"], report["validation"]["issues"])
            self.assertEqual(draft["review"]["status"], "pending")
            self.assertEqual(
                sorted({v["position_cm"][0] for v in draft["layout"]["vertices"]}), [0, 600, 1100]
            )
            self.assertEqual(draft["layout"]["openings"][0]["center_offset_cm"], 260)
            self.assertTrue(all((not p["accepted"] for p in report["association"]["proposals"])))
            self.assertFalse(report["exportable"])
            self.assertEqual(len(report["source"]["topology_revision_sha256"]), 64)

    def test_ocr_only_never_generates_metric_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path, obs, request = prepare(Path(tmp))
            request["dimensions"] = []
            draft, report = reconstruct(path, obs, request)
            self.assertEqual(report["status"], "underdetermined")
            self.assertTrue(report["validation"]["schema_valid"])
            self.assertFalse(report["validation"]["metric_valid"])
            self.assertTrue(
                all((d["target"] == {"type": "unassigned"} for d in draft["layout"]["dimensions"]))
            )
            self.assertLessEqual(report["search"]["evaluated"], 4)
            self.assertTrue(report["search"]["budget_exhausted"])
            self.assertTrue(report["search"]["requires_review"])

    def test_stale_draft_tampered_and_changed_sources_fail_closed(self):
        for mutation in ("draft", "digest", "source", "stale", "analysis"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                store, path, obs, request = prepare(Path(tmp))
                if mutation == "source":
                    obs.write_text(obs.read_text() + " ")
                elif mutation == "stale":
                    store.save("Data_1", two_rooms(), request["topology_revision_id"], "accept")
                else:
                    rev = json.loads(path.read_text())
                    if mutation == "draft":
                        rev["status"] = "draft"
                    elif mutation == "digest":
                        rev["state_sha256"] = "bad"
                    else:
                        rev["topology"]["regions"] = []
                    rev["revision_sha256"] = digest(
                        {k: v for k, v in rev.items() if k != "revision_sha256"}
                    )
                    path.write_text(json.dumps(rev))
                with self.assertRaises(ValueError):
                    reconstruct(path, obs, request)

    def test_unknown_kind_evidence_or_topology_revision_rejected(self):
        for mutation in (
            "kind",
            "evidence",
            "revision",
            "ocr-confirmed",
            "unknown-field",
            "null-confirmed",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                _, path, obs, request = prepare(Path(tmp))
                if mutation == "kind":
                    request["region_kinds"] = {}
                elif mutation == "evidence":
                    request["dimensions"][0]["provenance"]["evidence_ids"] = ["absent"]
                elif mutation == "revision":
                    request["topology_revision_id"] = "wrong"
                elif mutation == "ocr-confirmed":
                    request["dimensions"][0]["provenance"]["method"] = "ocr"
                elif mutation == "null-confirmed":
                    request["dimensions"][0]["value_cm"] = None
                else:
                    request["wat"] = True
                with self.assertRaises((ValueError, ValidationError)):
                    reconstruct(path, obs, request)

    def test_distinct_frames_and_y_inversion(self):
        result = transform_points([[4, 6], [8, 10]], np.array([[2, 0, 3], [0, 2, 4], [0, 0, 1]]))
        np.testing.assert_allclose(result, [[11, -16], [19, -24]])

    def test_association_uses_observation_frame_inverse(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, path, obs, request = prepare(Path(tmp))
            _, baseline = reconstruct(path, obs, request)
            data = json.loads(obs.read_text())
            data["frame"].update(
                width_px=440, height_px=240, original_to_frame=[[2, 0, 0], [0, 2, 0], [0, 0, 1]]
            )
            for text in data["texts"]:
                text["polygon_px"] = [[2 * x, 2 * y] for x, y in text["polygon_px"]]
            obs.write_text(json.dumps(data))
            new_store = ReviewStore(store.run, Path(tmp) / "other_reviews")
            rev = new_store.save("Data_1", two_rooms(), None, "accept")
            request["topology_revision_id"] = rev["revision_id"]
            path = new_store.output / "Data_1" / "revisions" / (rev["revision_id"] + ".json")
            _, scaled = reconstruct(path, obs, request)
            self.assertEqual(baseline["association"], scaled["association"])

    def test_empty_polygon_does_not_invent_association(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path, obs, request = prepare(Path(tmp))
            rev, observations, transform = load_review(path, obs, request["topology_revision_id"])
            doc, pixels = skeleton(rev, observations, request["region_kinds"], {})
            observations["texts"][0]["polygon_px"] = None
            result = propose(doc, pixels, observations, transform)
            self.assertEqual(result["proposals"][0]["candidates"], [])
            self.assertTrue(result["proposals"][1]["candidates"])
            self.assertIn(
                "normalized_perpendicular_distance",
                result["proposals"][1]["candidates"][0]["features"],
            )
            _, truncated = span_catalog(doc, pixels, chain_budget=1)
            self.assertTrue(truncated)

    def test_real_t_junction_has_one_shared_vertex_and_two_support_walls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, path, obs, request = prepare(Path(tmp))
            lines = perimeter(10, 10, 110, 110) + [
                wall("v1", (60, 10), (60, 20), "vertical"),
                wall("v2", (60, 30), (60, 80), "vertical"),
                wall("v3", (60, 90), (60, 110), "vertical"),
                wall("branch", (60, 60), (110, 60), "horizontal"),
            ]
            openings = [
                {
                    "id": key,
                    "start": [60, a],
                    "end": [60, b],
                    "axis": "vertical",
                    "kind": "door",
                    "decision": "approved",
                }
                for key, a, b in (("upper", 20, 30), ("lower", 80, 90))
            ]
            rev = store.save(
                "Data_1", state_with(lines, openings), request["topology_revision_id"], "accept"
            )
            path = path.parent / (rev["revision_id"] + ".json")
            request.update(
                topology_revision_id=rev["revision_id"],
                dimensions=[],
                region_kinds={r["id"]: "room" for r in rev["topology"]["regions"]},
            )
            draft, report = reconstruct(path, obs, request)
            self.assertEqual(len(draft["layout"]["rooms"]), 3)
            self.assertEqual(
                len(
                    [
                        p
                        for p in report["pixel_topology"]["vertices"].values()
                        if tuple(p) == (60, -60)
                    ]
                ),
                1,
            )
            self.assertEqual(len({o["wall_id"] for o in draft["layout"]["openings"]}), 2)
            self.assertTrue(report["validation"]["schema_valid"])

    def test_bounded_global_search_rejects_bad_ocr_branch(self):
        doc = fixture(1)
        proposals = [
            {
                "evidence_id": "wrongocr",
                "value_cm": 450,
                "candidates": [
                    {
                        "target": {"type": "region_span", "region_id": "rA", "axis": "x"},
                        "basis": "wall_centerline",
                        "cost": 0,
                    },
                    {
                        "target": {"type": "region_span", "region_id": "rA", "axis": "y"},
                        "basis": "wall_centerline",
                        "cost": 1,
                    },
                ],
            }
        ]
        result = hypotheses(doc, proposals, budget=8)
        self.assertEqual(
            result["hypotheses"][0]["assignments"][0]["target"], {"type": "unassigned"}
        )
        self.assertTrue(
            any((r.get("linear_status") == "inconsistent" for r in result["hypotheses"]))
        )
        self.assertFalse(result["auto_confirmed"])
        self.assertEqual(doc["layout"]["dimensions"][0]["value_cm"], 600)


if __name__ == "__main__":
    unittest.main()
