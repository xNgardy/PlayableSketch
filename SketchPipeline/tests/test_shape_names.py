import unittest
from SketchPipeline.shape_authoring.names import region_names


class RegionNameTests(unittest.TestCase):

    def test_rooms_and_corridors_have_independent_sequences(self):
        regions = [
            {"id": "a", "type": "room", "name": "Room 1"},
            {"id": "c", "type": "corridor_segment", "name": "Corridor 2"},
            {"id": "b", "type": "room", "name": "Room 3"},
        ]
        self.assertEqual(region_names(regions), {"a": "Room 1", "c": "Corridor 1", "b": "Room 2"})

    def test_custom_names_are_preserved(self):
        self.assertEqual(
            region_names([{"id": "a", "type": "room", "name": "Studio"}]), {"a": "Studio"}
        )
