import hashlib
import unittest
import cv2
import numpy as np
from shapely.geometry import Polygon
from SketchPipeline.shape_authoring.room_geometry import observe, as_rooms, rectangular_parts
from SketchPipeline.shape_authoring.decoder import authoring_document, boundary_graph
from SketchPipeline.shape_authoring.contract import validate_authoring
from SketchPipeline.shape_authoring.sizing import recompute
from SketchPipeline.shape_authoring.delivery import prepare_draft
from SketchPipeline.validation.validate import validate_document


class RoomGeometryTests(unittest.TestCase):
    def plan(self):
        regions = [
            {"type": "room", "bounds_px": [40, 40, 160, 140]},
            {
                "type": "room",
                "bounds_px": [80, 140, 260, 260],
                "points_px": [[80, 140], [130, 140], [130, 210], [260, 210], [260, 260], [80, 260]],
            },
            {"type": "room", "bounds_px": [260, 170, 400, 310]},
            {"type": "room", "bounds_px": [400, 210, 480, 260]},
        ]
        segments, _ = boundary_graph(regions)
        doors = []
        for segment, owners in segments.items():
            if len(owners) != 2:
                continue
            axis = 0 if segment[0][1] == segment[1][1] else 1
            center = (segment[0][axis] + segment[1][axis]) / 2
            p, q = list(segment[0]), list(segment[0])
            p[axis], q[axis] = center - 7, center + 7
            doors.append(
                {"segment": segment, "entity_indices": owners, "start": p, "end": q, "type": "door"}
            )
        metadata = {
            "working_size_px": [512, 512],
            "original_to_working": np.eye(3).tolist(),
            "working_to_original": np.eye(3).tolist(),
        }
        source = {
            "image_path": "test.png",
            "image_sha256": hashlib.sha256(b"rooms").hexdigest(),
            "width_px": 512,
            "height_px": 512,
        }
        return authoring_document(source, metadata, regions, doors)

    def test_nonrectangular_room_survives_sizing_and_runtime_tiling(self):
        doc = self.plan()
        self.assertEqual(validate_authoring(doc), [])
        result = recompute(doc)
        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(len(result["authoring"]["topology"]["regions"]), 4)
        preview = result["preview"]
        self.assertEqual(len(preview["display_regions"]), 4)
        self.assertEqual(len(preview["display_openings"]), 3)
        self.assertEqual(len(preview["canonical"]["layout"]["rooms"]), 5)
        self.assertEqual(preview["canonical"]["layout"]["corridors"], [])
        self.assertTrue(validate_document(preview["canonical"])["metric_valid"])
        display = {r["id"]: Polygon(r["points_cm"]) for r in preview["display_regions"]}
        points = {v["id"]: v["position_cm"] for v in preview["canonical"]["layout"]["vertices"]}
        from shapely.ops import unary_union

        for rid, expected in display.items():
            tiles = [
                Polygon([points[v] for v in r["boundary_vertex_ids"]])
                for r in preview["canonical"]["layout"]["rooms"]
                if preview["region_sources"][r["id"]] == rid
            ]
            self.assertLess(expected.symmetric_difference(unary_union(tiles)).area, 1e-4)
        state = {"names": {"region_0002": "Bent room"}, "start_room_id": None, "goal_room_id": None}
        draft, _ = prepare_draft(preview, result["authoring"], state)
        self.assertEqual(sum(r["name"] == "Bent room" for r in draft["layout"]["rooms"]), 2)

    def test_parts_do_not_fill_missing_l_corner(self):
        points = self.plan()["topology"]["regions"][1]["geometry"]["points_px"]
        from shapely.geometry import box
        from shapely.ops import unary_union

        self.assertEqual(
            Polygon(points)
            .symmetric_difference(unary_union([box(*p) for p in rectangular_parts(points)]))
            .area,
            0,
        )

    def test_all_automatic_area_types_become_rooms(self):
        doc = self.plan()
        doc["topology"]["regions"][-1].update(type="corridor_segment", name="Corridor 9")
        result = as_rooms(doc)
        self.assertTrue(all(r["type"] == "room" for r in result["topology"]["regions"]))
        self.assertEqual(result["topology"]["regions"][-1]["name"], "Room 4")
        self.assertEqual(doc["topology"]["regions"][-1]["type"], "corridor_segment")

    def test_blank_paper_has_no_room(self):
        result, _ = observe(np.full((512, 512), 255, np.uint8))
        self.assertIsNone(result)

    def test_invalid_polygon_is_rejected_before_sizing(self):
        doc = self.plan()
        doc["topology"]["regions"][1]["geometry"]["points_px"][2] = [145, 215]
        p = doc["topology"]["regions"][1]["geometry"]["points_px"]
        doc["topology"]["regions"][1]["geometry"]["points_normalized"] = [
            [x / 512, y / 512] for x, y in p
        ]
        result = recompute(doc)
        self.assertNotEqual(result["status"], "ready")

    def test_observed_l_and_doors_are_recovered_without_model_boxes(self):
        doc = self.plan()
        image = np.full((512, 512), 255, np.uint8)
        for wall in doc["topology"]["walls"]:
            a, b = wall["geometry"]["points_px"]
            cv2.line(image, tuple(map(int, a)), tuple(map(int, b)), 40, 1)
        for opening in doc["topology"]["openings"]:
            p, q = [np.array(v, int) for v in opening["geometry"]["points_px"]]
            cv2.line(image, tuple(p), tuple(q), 255, 3)
            normal = np.array([0, 5]) if p[1] == q[1] else np.array([5, 0])
            for endpoint in (p, q):
                cv2.line(image, tuple(endpoint - normal), tuple(endpoint + normal), 40, 1)
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        regions, openings = result
        self.assertEqual(len(regions), 4)
        self.assertEqual(len(openings), 3)
        self.assertEqual(sorted(len(r["points_px"]) for r in regions), [4, 4, 4, 6])

    def test_rotated_l_room_exports_with_valid_rectangular_floor_parts(self):
        for rotation in (90, 180, 270):
            doc = self.plan()
            doc["physical_design"]["orientation_degrees"] = rotation
            result = recompute(doc)
            self.assertEqual(result["status"], "ready", result["issues"])
            self.assertTrue(validate_document(result["preview"]["canonical"])["metric_valid"])

    def test_edit_save_keeps_l_polygon_and_door_ids(self):
        import tempfile
        from pathlib import Path
        from SketchPipeline.shape_authoring.jobs import ShapeJobs

        with tempfile.TemporaryDirectory() as temporary:
            manager = ShapeJobs(Path(temporary))
            try:
                job = manager.sample()["job_id"]
                base = manager.proposals(job)["authoring"]
                doc = self.plan()
                boxes = []
                for region in doc["topology"]["regions"]:
                    points = [[x * 0.4, y * 0.4] for x, y in region["geometry"]["points_px"]]
                    boxes.append(
                        {
                            "id": region["id"],
                            "type": "room",
                            "points_px": points,
                            "bounds_px": list(Polygon(points).bounds),
                        }
                    )
                openings = [
                    {
                        "id": o["id"],
                        "type": o["type"],
                        "entity_ids": o["entity_ids"],
                        "points_px": [[x * 0.4, y * 0.4] for x, y in o["geometry"]["points_px"]],
                    }
                    for o in doc["topology"]["openings"]
                ]
                result = manager.edit(
                    job,
                    {"base_revision_id": base["revision_id"], "boxes": boxes, "openings": openings},
                )
                saved = result["authoring"]
                self.assertEqual(len(saved["topology"]["regions"][1]["geometry"]["points_px"]), 6)
                self.assertEqual(
                    [o["id"] for o in saved["topology"]["openings"]],
                    [o["id"] for o in doc["topology"]["openings"]],
                )
                self.assertEqual(result["diagnostics"], [])
                self.assertEqual(recompute(saved)["status"], "ready")
            finally:
                manager.close()

    def u_image(self, door=True):
        from shapely.geometry import box
        from shapely.ops import unary_union

        shape = unary_union(
            [
                box(60, 120, 200, 260),
                box(200, 170, 360, 220),
                box(310, 220, 360, 350),
                box(360, 300, 500, 350),
                box(450, 100, 500, 300),
                box(410, 40, 550, 100),
            ]
        )
        image = np.full((600, 600), 255, np.uint8)
        cv2.polylines(image, [np.asarray(shape.exterior.coords, np.int32)], True, 45, 2)
        if door:
            cv2.rectangle(image, (380, 350), (530, 480), 45, 2)
            cv2.line(image, (418, 350), (442, 350), 255, 5)
            for x in (418, 442):
                cv2.line(image, (x, 342), (x, 358), 45, 2)
        return image, shape

    def test_unmarked_u_is_one_room_even_with_wide_ends(self):
        image, shape = self.u_image(door=False)
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        regions, doors = result
        self.assertEqual(len(regions), 1)
        self.assertEqual(doors, [])
        detected = Polygon(regions[0]["points_px"])
        self.assertGreater(detected.intersection(shape).area / detected.union(shape).area, 0.93)

    def test_u_over_sixteen_corners_and_separate_room_keep_one_real_door(self):
        image, shape = self.u_image()
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        regions, doors = result
        self.assertEqual(len(regions), 2)
        self.assertEqual(len(doors), 1)
        self.assertGreater(max(len(r["points_px"]) for r in regions), 16)
        self.assertTrue(all(r["type"] == "room" for r in regions))

    def test_short_collinear_wall_break_is_repaired_without_extra_rooms(self):
        image, _ = self.u_image()
        image[180:184, 58:63] = 255
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(len(result[1]), 1)
        self.assertGreater(detail["ink_recovery"]["repaired_gap_pixels"], 0)

    def test_faint_pencil_under_uneven_lighting_preserves_u_connectivity(self):
        image, _ = self.u_image()
        background = np.tile(np.linspace(175, 235, 600), (600, 1))
        faint = np.uint8(background - (255 - image.astype(float)) * 0.12)
        result, detail = observe(faint)
        self.assertIsNotNone(result, detail)
        self.assertEqual((len(result[0]), len(result[1])), (2, 1))

    def test_narrow_unmarked_neck_stays_open(self):
        from shapely.geometry import box
        from shapely.ops import unary_union

        shape = unary_union(
            [box(40, 80, 150, 210), box(150, 139, 300, 151), box(300, 80, 410, 210)]
        )
        image = np.full((512, 512), 255, np.uint8)
        cv2.polylines(image, [np.asarray(shape.exterior.coords, np.int32)], True, 40, 1)
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        self.assertEqual((len(result[0]), len(result[1])), (1, 0))

    def test_wide_missing_outer_wall_does_not_invent_a_closed_room(self):
        image, _ = self.u_image(door=False)
        image[170:205, 56:65] = 255
        result, detail = observe(image)
        self.assertIsNone(result, detail)

    def test_disconnected_enclosures_are_rooms_without_invented_doors(self):
        image = np.full((512, 512), 255, np.uint8)
        cv2.rectangle(image, (40, 80), (180, 240), 40, 2)
        cv2.rectangle(image, (270, 80), (430, 240), 40, 2)
        result, detail = observe(image)
        self.assertIsNotNone(result, detail)
        self.assertEqual((len(result[0]), len(result[1])), (2, 0))
