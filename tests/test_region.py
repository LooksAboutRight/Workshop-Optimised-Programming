import math
import unittest

from tests import reference_data

from wop.core.constants import COLLISION_PENETRATION_TOLERANCE_MM
from wop.core.geometry import Point
from wop.core.geometry.region import Region
from wop.core.geometry.region_types import RegionError

AREA_TOLERANCE_MM2 = 0.01


class CreationTests(unittest.TestCase):
    def test_rectangle(self):
        region = Region.rectangle(0, -20, 10, 0)
        self.assertAlmostEqual(region.area, 200)
        bounds = region.bounds
        self.assertEqual((bounds.min_x, bounds.min_z, bounds.max_x, bounds.max_z), (0, -20, 10, 0))

    def test_empty(self):
        region = Region.empty()
        self.assertTrue(region.is_empty)
        self.assertEqual(region.area, 0)
        self.assertIsNone(region.bounds)
        self.assertEqual(region.polygons(), ())

    def test_triangle_from_points(self):
        region = Region.from_points([Point(0, 0), Point(4, 0), Point(0, 3)])
        self.assertAlmostEqual(region.area, 6)

    def test_bad_outlines_are_rejected(self):
        with self.assertRaises(RegionError):
            Region.from_points([Point(0, 0), Point(1, 1)])
        bow_tie = [Point(0, 0), Point(2, 2), Point(2, 0), Point(0, 2)]
        with self.assertRaises(RegionError):
            Region.from_points(bow_tie)
        with self.assertRaises(RegionError):
            Region.rectangle(0, 0, 0, 5)

    def test_stepped_shaft_from_segments(self):
        region = Region.from_segments(reference_data.stepped_shaft_profile())
        self.assertAlmostEqual(region.area, reference_data.STEPPED_SHAFT_AREA_MM2)

    def test_rounded_end_from_segments(self):
        region = Region.from_segments(reference_data.rounded_end_profile())
        self.assertAlmostEqual(
            region.area, reference_data.ROUNDED_END_AREA_MM2, delta=AREA_TOLERANCE_MM2
        )


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.left = Region.rectangle(0, 0, 10, 10)
        self.right = Region.rectangle(5, 0, 15, 10)

    def test_union_difference_intersection(self):
        self.assertAlmostEqual(self.left.union(self.right).area, 150)
        self.assertAlmostEqual(self.left.difference(self.right).area, 50)
        self.assertAlmostEqual(self.left.intersection(self.right).area, 50)
        self.assertAlmostEqual(self.left.overlap_area(self.right), 50)

    def test_regions_are_not_changed_by_operations(self):
        self.left.difference(self.right)
        self.assertAlmostEqual(self.left.area, 100)

    def test_touching_regions_have_no_overlap(self):
        other = Region.rectangle(10, 0, 20, 10)
        self.assertEqual(self.left.intersection(other).area, 0)
        self.assertTrue(self.left.intersection(other).is_empty)

    def test_difference_can_split_into_two_polygons(self):
        groove = Region.rectangle(4, -1, 6, 11)
        parts = self.left.difference(groove)
        self.assertEqual(len(parts.polygons()), 2)

    def test_hole_is_reported(self):
        ring = self.left.difference(Region.rectangle(3, 3, 7, 7))
        polygons = ring.polygons()
        self.assertEqual(len(polygons), 1)
        self.assertEqual(len(polygons[0].holes), 1)

    def test_grow_and_shrink(self):
        grown = self.left.offset(1)
        self.assertAlmostEqual(grown.area, 100 + 4 * 10 + math.pi, delta=AREA_TOLERANCE_MM2)
        self.assertAlmostEqual(self.left.offset(-1).area, 64)
        self.assertTrue(self.left.offset(-6).is_empty)

    def test_offset_zero_and_empty(self):
        self.assertAlmostEqual(self.left.offset(0).area, 100)
        self.assertTrue(Region.empty().offset(1).is_empty)

    def test_translated(self):
        moved = self.left.translated(3, -2)
        bounds = moved.bounds
        self.assertEqual((bounds.min_x, bounds.min_z), (3, -2))
        self.assertAlmostEqual(moved.area, 100)

    def test_contains_point(self):
        self.assertTrue(self.left.contains_point(Point(5, 5)))
        self.assertTrue(self.left.contains_point(Point(10, 5)))
        self.assertFalse(self.left.contains_point(Point(11, 5)))

    def test_strictly_contains_point_excludes_the_boundary(self):
        self.assertTrue(self.left.strictly_contains_point(Point(5, 5)))
        self.assertFalse(self.left.strictly_contains_point(Point(10, 5)))
        self.assertFalse(self.left.strictly_contains_point(Point(11, 5)))

    def test_distance(self):
        far = Region.rectangle(13, 0, 20, 10)
        self.assertAlmostEqual(self.left.distance_to(far), 3)
        self.assertEqual(self.left.distance_to(self.right), 0)


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.block = Region.rectangle(0, 0, 10, 10)

    def test_shrunk_and_overlaps_give_the_same_answer_as_penetrates(self):
        for other in (Region.rectangle(10, 0, 20, 10), Region.rectangle(9, 0, 20, 10), Region.rectangle(10 - 0.001, 0, 20, 10)):
            self.assertEqual(
                self.block.penetrates(other), self.block.shrunk_for_collision().overlaps(other.shrunk_for_collision())
            )

    def test_an_offset_is_made_once_and_kept(self):
        self.assertIs(self.block.offset(-1), self.block.offset(-1))
        self.assertIs(self.block.shrunk_for_collision(), self.block.shrunk_for_collision())

    def test_touching_is_not_penetration(self):
        self.assertFalse(self.block.penetrates(Region.rectangle(10, 0, 20, 10)))

    def test_overlap_below_the_tolerance_is_not_penetration(self):
        self.assertFalse(self.block.penetrates(Region.rectangle(9.999, 0, 20, 10)))

    def test_clear_overlap_is_penetration(self):
        self.assertTrue(self.block.penetrates(Region.rectangle(9, 0, 20, 10)))

    def test_empty_never_penetrates(self):
        self.assertFalse(self.block.penetrates(Region.empty()))

    def test_path_through_the_region(self):
        path = [Point(-5, 5), Point(15, 5)]
        # The area is shrunk by the tolerance on both sides, so 10 mm becomes 9.99 mm.
        expected = 10 - 2 * COLLISION_PENETRATION_TOLERANCE_MM
        self.assertAlmostEqual(self.block.length_inside(path), expected, delta=0.001)

    def test_path_along_the_edge_is_outside(self):
        path = [Point(-5, 10), Point(15, 10)]
        self.assertEqual(self.block.length_inside(path), 0)

    def test_path_outside(self):
        self.assertEqual(self.block.length_inside([Point(20, 0), Point(30, 0)]), 0)
        self.assertEqual(self.block.length_inside([Point(5, 5)]), 0)


if __name__ == "__main__":
    unittest.main()
