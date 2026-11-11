"""The trim-and-link boolean of the analytic planner (wop/core/geometry/chains.py), checked against the `Region` of the program.

The areas must agree. Until 2026-10-23 the referee was shapely; now `Region` is built on the same boolean, so
these tests guard against a change more than they check the boolean itself (the exact values are in `tests/test_exact_region.py`).
"""

import math
import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point

from wop.core.geometry.chains import (
    DIFFERENCE,
    INTERSECTION,
    boolean,
    closed_loop,
    loop_area,
    oriented,
    polygon_loop,
    region_of_loops,
    reversed_loop,
)
from wop.core.geometry.tidy import tidied, tidy

AREA_TOLERANCE_MM2 = 0.02  # set when the referee was shapely (arcs as chords of 0.001 mm: a disc of radius 3 was 0.0125 mm2 smaller there)


def rectangle(x0, z0, x1, z1):
    return oriented(polygon_loop([Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1)]), True)


def disc(cx, cz, radius):
    """A full circle as a loop of two half arcs."""
    left, right = Point(cx - radius, cz), Point(cx + radius, cz)
    centre = Point(cx, cz)
    return oriented((ArcSegment(left, right, centre, ArcDirection.CCW), ArcSegment(right, left, centre, ArcDirection.CCW)), True)


def total_area(loops):
    return sum(loop_area(loop) for loop in loops)


class BooleanTests(unittest.TestCase):
    def check(self, a, b, operation):
        loops = boolean(a, b, operation)
        ra, rb = region_of_loops(a), region_of_loops(b)
        oracle = ra.intersection(rb) if operation == INTERSECTION else ra.difference(rb)
        self.assertAlmostEqual(total_area(loops), oracle.area, delta=AREA_TOLERANCE_MM2, msg=operation)
        mine = region_of_loops(loops)
        self.assertLess(mine.difference(oracle).area + oracle.difference(mine).area, 2 * AREA_TOLERANCE_MM2, operation)
        return loops

    def both(self, a, b):
        return self.check(a, b, INTERSECTION), self.check(a, b, DIFFERENCE)

    def test_two_overlapping_rectangles(self):
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(5, 5, 15, 15)])
        self.assertEqual((len(inter), len(diff)), (1, 1))

    def test_one_inside_the_other_makes_a_hole(self):
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(3, 3, 6, 6)])
        self.assertEqual(len(diff), 2)  # the outer loop and the hole
        self.assertEqual(sorted(round(loop_area(loop)) for loop in diff), [-9, 100])

    def test_apart_and_around(self):
        self.both([rectangle(0, 0, 1, 1)], [rectangle(5, 5, 6, 6)])
        self.both([rectangle(3, 3, 6, 6)], [rectangle(0, 0, 10, 10)])

    def test_edges_on_top_of_each_other(self):
        # the second rectangle shares the whole lower edge and half of the right edge with the first
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(5, 0, 10, 4)])
        self.assertEqual(len(diff), 1)
        # the same edge from the other side: nothing in common
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(10, 0, 14, 10)])
        self.assertEqual(inter, [])
        self.assertAlmostEqual(total_area(diff), 100)

    def test_identical_regions(self):
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(0, 0, 10, 10)])
        self.assertEqual(diff, [])

    def test_a_cut_that_splits_a_loop_in_two(self):
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [rectangle(4, -1, 6, 11)])
        self.assertEqual(len(diff), 2)

    def test_arcs_stay_arcs(self):
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [disc(5, 5, 3)])
        self.assertTrue(any(isinstance(piece, ArcSegment) for loop in inter for piece in loop))
        inter, diff = self.both([rectangle(0, 0, 10, 10)], [disc(10, 5, 3)])  # the circle crosses the right edge
        self.assertTrue(any(isinstance(piece, ArcSegment) for loop in diff for piece in loop))
        self.both([disc(0, 0, 4)], [disc(3, 0, 4)])

    def test_a_circle_that_touches_an_edge(self):
        self.both([rectangle(0, 0, 10, 10)], [disc(5, -3, 3)])  # touches the lower edge at one point
        self.both([rectangle(0, 0, 10, 10)], [disc(5, 3, 3)])  # touches from inside

    def test_a_stepped_part_cut_out_of_a_bar(self):
        # a bar (x = radius 0..20, z = -50..0) minus a stepped shaft with a round shoulder: what a turning block removes
        bar = rectangle(0, -50, 20, 0)
        shaft = closed_loop([
            LineSegment(Point(-1, 1), Point(-1, -51)),
            LineSegment(Point(-1, -51), Point(8, -51)),
            LineSegment(Point(8, -51), Point(8, -30)),
            ArcSegment(Point(8, -30), Point(12, -26), Point(12, -30), ArcDirection.CW),
            LineSegment(Point(12, -26), Point(12, 1)),
            LineSegment(Point(12, 1), Point(-1, 1)),
        ])
        shaft = oriented(shaft, True)
        inter, diff = self.both([bar], [shaft])
        self.assertEqual(len(diff), 1)

    def test_the_result_of_one_operation_can_be_used_again(self):
        first = boolean([rectangle(0, 0, 10, 10)], [disc(10, 5, 3)], DIFFERENCE)
        second = boolean(first, [rectangle(0, 4, 5, 6)], DIFFERENCE)
        oracle = region_of_loops([rectangle(0, 0, 10, 10)]).difference(region_of_loops([disc(10, 5, 3)])).difference(region_of_loops([rectangle(0, 4, 5, 6)]))
        self.assertAlmostEqual(total_area(second), oracle.area, delta=AREA_TOLERANCE_MM2)

    def test_the_area_of_a_loop_with_arcs_is_exact(self):
        self.assertAlmostEqual(loop_area(disc(1, 2, 3)), math.pi * 9, places=9)
        self.assertAlmostEqual(loop_area(reversed_loop(disc(1, 2, 3))), -math.pi * 9, places=9)
        half = oriented((ArcSegment(Point(-2, 0), Point(2, 0), Point(0, 0), ArcDirection.CCW), LineSegment(Point(2, 0), Point(-2, 0))), True)
        self.assertAlmostEqual(loop_area(half), math.pi * 4 / 2, places=9)  # a half disc

    def test_reversing_a_loop_changes_the_sign_of_its_area(self):
        loop = rectangle(0, 0, 2, 3)
        self.assertAlmostEqual(loop_area(reversed_loop(loop)), -loop_area(loop))

class TidyTests(unittest.TestCase):
    def test_a_step_of_a_thousandth_is_taken_out_and_collinear_lines_are_joined(self):
        loop = closed_loop([
            LineSegment(Point(0, 0), Point(5, 0)), LineSegment(Point(5, 0), Point(10, 0)),  # one line in two pieces
            LineSegment(Point(10, 0), Point(10, 4)),
            LineSegment(Point(10, 4), Point(10.0015, 4)),  # a step of 0.0015
            LineSegment(Point(10.0015, 4), Point(10.0015, 6)), LineSegment(Point(10.0015, 6), Point(0, 6)), LineSegment(Point(0, 6), Point(0, 0)),
        ])
        tidy_loop = tidy(loop, 0.002)
        self.assertEqual(len(tidy_loop), 5)  # the bottom (joined), the right side in two pieces (the upper one a thousandth off the vertical), the top, the left
        self.assertAlmostEqual(loop_area(tidy_loop), loop_area(loop), delta=0.01)

    def test_a_loop_without_small_features_stays(self):
        loop = rectangle(0, 0, 3, 2)
        self.assertEqual(tidy(loop, 0.002), loop)

    def test_a_needle_and_a_sliver_thinner_than_the_snap_distance_are_no_material(self):
        needle = (LineSegment(Point(1, 1), Point(1.03, 1.01)), LineSegment(Point(1.03, 1.01), Point(1, 1)))  # two pieces on each other, no area
        sliver = rectangle(0, 5, 4, 5.001)  # 0.001 thick
        thin_but_real = rectangle(0, 8, 4, 8.01)  # 0.01 thick: the user's roughing accuracy, kept
        kept = tidied([rectangle(0, 0, 3, 2), needle, sliver, thin_but_real], 0.002)
        self.assertEqual(len(kept), 2)
        self.assertAlmostEqual(sum(loop_area(loop) for loop in kept), 6 + 0.04, places=6)


if __name__ == "__main__":
    unittest.main()
