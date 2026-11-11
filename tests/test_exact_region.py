"""`Region` (wop/core/geometry/region.py): the areas as exact chains (the `Region` of the program). Exact values where they are
known, and areas that add up on the residuals of a real project."""

import math
import unittest
from pathlib import Path

import numpy as np

from tests.helpers import planned
from wop.core.constants import ARC_MAX_DEVIATION_MM
from wop.core.geometry.region import Region
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point
from wop.core.geometry.region_types import RegionError

ROOT = Path(__file__).parent.parent
TOLERANCE = 1e-6


def square(size=4.0, x=0.0, z=0.0):
    return Region.rectangle(x, z, x + size, z + size)


def triangle_area(triangles) -> float:
    return sum(abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2 for a, b, c in triangles)


class ExactValueTests(unittest.TestCase):
    def test_a_rectangle_and_its_questions(self):
        region = square()
        self.assertAlmostEqual(region.area, 16)
        self.assertEqual((region.bounds.min_x, region.bounds.max_z), (0, 4))
        self.assertTrue(region.contains_point(Point(4, 2)))  # on the border
        self.assertFalse(region.strictly_contains_point(Point(4, 2)))
        self.assertFalse(region.contains_point(Point(5, 2)))

    def test_an_arc_stays_an_arc(self):
        half = Region.from_segments([ArcSegment(Point(1, 0), Point(-1, 0), Point(0, 0), ArcDirection.CCW), LineSegment(Point(-1, 0), Point(1, 0))])
        self.assertAlmostEqual(half.area, math.pi / 2, delta=TOLERANCE)  # no chords

    def test_union_difference_intersection(self):
        a, b = square(), square(x=2, z=2)
        self.assertAlmostEqual(a.union(b).area, 28)
        self.assertAlmostEqual(a.difference(b).area, 12)
        self.assertAlmostEqual(a.intersection(b).area, 4)
        self.assertAlmostEqual(a.union(square(x=4)).area, 32)  # touching along an edge: one piece
        self.assertEqual(len(a.union(square(x=4)).pieces()), 1)

    def test_a_hole_and_the_pieces(self):
        ring = square(10).difference(square(2, 4, 4))
        self.assertAlmostEqual(ring.area, 96)
        self.assertEqual(len(ring.pieces()), 1)
        self.assertEqual(len(ring.polygons()[0].holes), 1)
        self.assertAlmostEqual(triangle_area(ring.triangles()), 96, delta=TOLERANCE)

    def test_the_offset_rounds_the_outer_corners_exactly(self):
        self.assertAlmostEqual(square().offset(1).area, 16 + 4 * 4 + math.pi, delta=TOLERANCE)
        self.assertAlmostEqual(square().offset(-1).area, 4, delta=TOLERANCE)
        self.assertTrue(square().offset(-2.5).is_empty)

    def test_a_hole_grows_shut_and_a_thin_part_shrinks_away(self):
        with_hole = square(10).difference(Region.rectangle(4, 4, 6, 5))  # a hole 1 mm wide
        self.assertAlmostEqual(with_hole.offset(1).area, 100 + 40 + math.pi, delta=TOLERANCE)
        self.assertTrue(Region.rectangle(0, 0, 10, 0.3).offset(-0.2).is_empty)

    def test_a_notch_keeps_its_inner_corner_sharp_when_the_area_grows(self):
        notched = square(10).difference(Region.rectangle(4, 6, 6, 10))
        grown = notched.offset(0.5)
        self.assertFalse(grown.contains_point(Point(5, 9)))  # the notch is 1 mm narrower but still open
        self.assertTrue(grown.contains_point(Point(4.4, 9)))

    def test_moved_mirrored_and_swept(self):
        region = square()
        self.assertEqual(region.translated(1, 2).bounds.min_x, 1)
        self.assertEqual(region.mirrored().bounds.max_x, 0)
        self.assertEqual(region.mirrored_z().bounds.max_z, 0)
        self.assertAlmostEqual(region.swept(0, -3).area, 16 + 12)
        self.assertAlmostEqual(region.swept(3, 3).area, 16 + 2 * 12)  # a square moved along its diagonal

    def test_distance_penetration_and_length_inside(self):
        self.assertAlmostEqual(square().distance_to(square(x=6)), 2)
        self.assertEqual(square().distance_to(square(x=2)), 0)
        self.assertFalse(square().penetrates(square(x=4)))  # touching
        self.assertTrue(square().penetrates(square(x=3)))
        self.assertAlmostEqual(square().length_inside([Point(-1, 2), Point(5, 2)], 0), 4, delta=TOLERANCE)

    def test_thin_swept_edges(self):
        area = Region.swept_edges(np.array([[0.0, 0.0]]), np.array([[1.0, 0.0]]), 0.0, 2.0, 0.01).area
        self.assertAlmostEqual(area, 2.0 + 2 * 3 * 0.01 + math.pi * 0.01 ** 2, delta=1e-4)

    def test_an_outline_that_crosses_itself_is_refused(self):
        with self.assertRaises(RegionError):
            Region.from_points([Point(0, 0), Point(2, 2), Point(2, 0), Point(0, 2)])


class ReferenceProjectTests(unittest.TestCase):
    def test_the_residuals_of_the_reference_project(self):
        from wop.adapters.project_files import load_project

        program = load_project(ROOT / "examples" / "reference.wop.json").program
        for block_plan in planned(program).blocks:
            exact = block_plan.residual_before
            if exact.is_empty:
                continue
            with self.subTest(block=block_plan.number):
                chords = sum(s.length for loop in exact.loops for s in loop if isinstance(s, ArcSegment)) * ARC_MAX_DEVIATION_MM
                self.assertAlmostEqual(triangle_area(exact.triangles()), exact.area, delta=1e-6 + chords)  # the triangles cut arcs into chords
                self.assertGreater(exact.offset(0.2).area, exact.area)  # grown and shrunk: bigger and smaller
                self.assertLess(exact.offset(-0.05).area, exact.area)
                removed = block_plan.result.removed
                if not removed.is_empty:  # what is left and what is taken away add up to what was there
                    left, taken = exact.difference(removed), exact.intersection(removed)
                    self.assertAlmostEqual(left.area + taken.area, exact.area, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
