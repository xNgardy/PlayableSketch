import unittest
import numpy as np
from SketchPipeline.perception.topology import build_topology


def wall(identifier, start, end, axis):
    return {
        "id": identifier,
        "start": list(start),
        "end": list(end),
        "axis": axis,
        "role": "wall_candidate",
    }


def perimeter(x0, y0, x1, y1, prefix="p"):
    return [
        wall(prefix + "-top", (x0, y0), (x1, y0), "horizontal"),
        wall(prefix + "-right", (x1, y0), (x1, y1), "vertical"),
        wall(prefix + "-bottom", (x0, y1), (x1, y1), "horizontal"),
        wall(prefix + "-left", (x0, y0), (x0, y1), "vertical"),
    ]


def opening(identifier, start, end, support_ids):
    return {
        "id": identifier,
        "start": list(start),
        "end": list(end),
        "supporting_line_ids": support_ids,
        "role": "opening_candidate",
        "interpretation": "unknown",
    }


def analyze(lines, gaps=(), **options):
    return build_topology(lines, list(gaps), (120, 220, 3), **options)


class TopologyFixtureTests(unittest.TestCase):

    def test_single_rectangle_is_one_rectangular_region(self):
        result = analyze(perimeter(10, 10, 110, 110))
        self.assertEqual(len(result["regions"]), 1)
        self.assertTrue(result["regions"][0]["rectangle_candidate"])
        self.assertEqual(result["region_connectivity_graph"]["edges"], [])

    def test_shared_wall_without_opening_does_not_connect_regions(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [wall("shared-wall", (60, 10), (60, 110), "vertical")]
        result = analyze(lines)
        self.assertEqual(len(result["regions"]), 2)
        self.assertEqual(result["region_connectivity_graph"]["edges"], [])

    def test_shared_wall_opening_connects_only_its_two_regions(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [
            wall("shared-upper", (60, 10), (60, 50), "vertical"),
            wall("shared-lower", (60, 70), (60, 110), "vertical"),
        ]
        gap = opening("door-1", (60, 50), (60, 70), ["shared-upper", "shared-lower"])
        result = analyze(lines, [gap])
        self.assertEqual(len(result["regions"]), 2)
        edges = result["region_connectivity_graph"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(set(edges[0]["adjacent_region_ids"]), {"r001", "r002"})
        self.assertEqual(
            sum((edge["kind"] == "virtual_boundary" for edge in result["wall_graph"]["edges"])), 1
        )

    def test_t_junction_nodes_and_splits_three_regions(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [
            wall("divider", (60, 10), (60, 110), "vertical"),
            wall("branch", (60, 60), (110, 60), "horizontal"),
        ]
        result = analyze(lines)
        self.assertEqual(len(result["regions"]), 3)
        junction = [
            node
            for node in result["wall_graph"]["nodes"]
            if node["point_px_rotated"] == [60.0, 60.0]
        ]
        self.assertEqual(len(junction), 1)

    def test_two_rooms_and_corridor_form_three_regions_and_two_passages(self):
        lines = perimeter(10, 10, 160, 110)
        lines += [
            wall("left-upper", (60, 10), (60, 50), "vertical"),
            wall("left-lower", (60, 70), (60, 110), "vertical"),
            wall("right-upper", (110, 10), (110, 50), "vertical"),
            wall("right-lower", (110, 70), (110, 110), "vertical"),
        ]
        gaps = [
            opening("left-entrance", (60, 50), (60, 70), ["left-upper", "left-lower"]),
            opening("right-entrance", (110, 50), (110, 70), ["right-upper", "right-lower"]),
        ]
        result = analyze(lines, gaps)
        self.assertEqual(len(result["regions"]), 3)
        self.assertEqual(len(result["region_connectivity_graph"]["edges"]), 2)
        self.assertEqual(len(result["corridor_hypotheses"]), 1)

    def test_near_corners_extend_both_walls_without_tilting_or_order_dependence(self):
        lines = [
            wall("top", (14, 10), (106, 10), "horizontal"),
            wall("right", (110, 14), (110, 106), "vertical"),
            wall("bottom", (14, 110), (106, 110), "horizontal"),
            wall("left", (10, 14), (10, 106), "vertical"),
        ]
        result = analyze(lines)
        reversed_result = analyze(list(reversed(lines)))
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["wall_graph"], reversed_result["wall_graph"])
        for edge in result["wall_graph"]["edges"]:
            self.assertTrue(edge["a"][0] == edge["b"][0] or edge["a"][1] == edge["b"][1])

    def test_rejected_gap_proposal_does_not_block_duplicate_fusion(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [wall("top-copy", (10, 11), (110, 11), "horizontal")]
        gap = opening("rejected", (10, 10), (110, 11), ["p-top", "top-copy"])
        gap["role"] = "unresolved_gap"
        result = analyze(lines, [gap])
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["opening_boundaries"], [])

    def test_blank_small_break_is_not_filled_as_physical_wall(self):
        lines = [line for line in perimeter(10, 10, 110, 110) if line["id"] != "p-top"]
        lines += [
            wall("top-left", (10, 10), (55, 10), "horizontal"),
            wall("top-right", (57, 10), (110, 10), "horizontal"),
        ]
        result = analyze(lines, ink=np.zeros((120, 220), np.uint8))
        self.assertEqual(result["regions"], [])
        self.assertEqual(result["stroke_repairs"], [])

    def test_observed_stroke_repairs_detector_fragmentation(self):
        lines = [line for line in perimeter(10, 10, 110, 110) if line["id"] != "p-top"]
        lines += [
            wall("top-left", (10, 10), (50, 10), "horizontal"),
            wall("top-right", (58, 10), (110, 10), "horizontal"),
        ]
        ink = np.zeros((120, 220), np.uint8)
        ink[10, 10:111] = 255
        result = analyze(lines, ink=ink)
        self.assertEqual(len(result["regions"]), 1)
        self.assertTrue(result["stroke_repairs"])

    def test_tiny_explicit_opening_remains_virtual_even_with_noisy_ink(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [
            wall("upper", (60, 10), (60, 55), "vertical"),
            wall("lower", (60, 57), (60, 110), "vertical"),
        ]
        gap = opening("small-door", (60, 55), (60, 57), ["upper", "lower"])
        result = analyze(lines, [gap], ink=np.ones((120, 220), np.uint8))
        virtual = [
            edge for edge in result["wall_graph"]["edges"] if edge["kind"] == "virtual_boundary"
        ]
        self.assertEqual(len(virtual), 1)
        self.assertEqual(virtual[0]["physical_line_ids"], [])
        self.assertEqual(len(result["region_connectivity_graph"]["edges"]), 1)

    def test_unattached_opening_cannot_link_existing_regions(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [wall("divider", (60, 10), (60, 110), "vertical")]
        gap = opening("unsupported", (60, 50), (60, 70), ["missing-upper", "missing-lower"])
        result = analyze(lines, [gap])
        self.assertEqual(len(result["regions"]), 2)
        self.assertEqual(result["region_connectivity_graph"]["edges"], [])
        self.assertEqual(result["opening_boundaries"][0]["status"], "unresolved_boundary")

    def test_junction_extension_does_not_consume_an_opening(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [
            wall("upper", (60, 10), (60, 50), "vertical"),
            wall("lower", (60, 58), (60, 110), "vertical"),
            wall("tick", (56, 54), (64, 54), "horizontal"),
        ]
        gap = opening("door", (60, 50), (60, 58), ["upper", "lower"])
        result = analyze(lines, [gap])
        boundary = result["opening_boundaries"][0]
        self.assertEqual(boundary["endpoints_px_rotated"], [[60.0, 50.0], [60.0, 58.0]])
        self.assertEqual(len(result["region_connectivity_graph"]["edges"]), 1)

    def test_multiple_openings_align_shared_supports_independent_of_order(self):
        lines = perimeter(10, 10, 110, 110)
        lines += [
            wall("upper", (60, 10), (60, 35), "vertical"),
            wall("middle", (62, 45), (62, 65), "vertical"),
            wall("lower", (61, 75), (61, 110), "vertical"),
        ]
        gaps = [
            opening("first", (60, 35), (62, 45), ["upper", "middle"]),
            opening("second", (62, 65), (61, 75), ["middle", "lower"]),
        ]
        result = analyze(lines, gaps)
        other = analyze(list(reversed(lines)), list(reversed(gaps)))
        self.assertEqual(result["wall_graph"], other["wall_graph"])
        self.assertEqual(len(result["regions"]), 2)
        self.assertTrue(all((region["rectangle_candidate"] for region in result["regions"])))
        self.assertEqual(len(result["region_connectivity_graph"]["edges"]), 2)

    def test_corridor_opening_span_attaches_to_nearby_boundary_junctions(self):
        lines = [line for line in perimeter(10, 10, 60, 110, "left") if line["id"] != "left-right"]
        lines += [
            line for line in perimeter(110, 10, 160, 110, "right") if line["id"] != "right-left"
        ]
        lines += [
            wall("corridor-top", (60, 40), (110, 40), "horizontal"),
            wall("corridor-bottom", (60, 80), (110, 80), "horizontal"),
            wall("left-upper", (60, 10), (60, 38), "vertical"),
            wall("left-lower", (60, 82), (60, 110), "vertical"),
            wall("right-upper", (110, 10), (110, 38), "vertical"),
            wall("right-lower", (110, 82), (110, 110), "vertical"),
        ]
        gaps = [
            opening("left-entrance", (60, 38), (60, 82), ["left-upper", "left-lower"]),
            opening("right-entrance", (110, 38), (110, 82), ["right-upper", "right-lower"]),
        ]
        result = analyze(lines, gaps)
        self.assertEqual(len(result["regions"]), 3)
        self.assertEqual(len(result["region_connectivity_graph"]["edges"]), 2)
        self.assertEqual(len(result["corridor_hypotheses"]), 1)
        self.assertEqual(len(result["opening_endpoint_adjustments"]), 4)


if __name__ == "__main__":
    unittest.main()
