"""The contact curves and the walk of the tool tip along the part (wop/core/analytic/tip_curves.py, tip_walk.py)."""

import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point

from wop.core.geometry.chains import oriented, polygon_loop
from wop.core.analytic.dips import follow_dip, uncovered
from wop.core.geometry.penetration import RegionIndex, blocked_by_part
from wop.core.analytic.tip_curves import contact_curves
from wop.core.analytic.reach import ride_over
from wop.core.analytic.tip_walk import TipCurves, tip_walk
from wop.core.geometry.tool_edges import ToolEdge
from wop.core.geometry.intersect import point_of
from wop.core.constants import CHAIN_SNAP_MM

TOLERANCE = CHAIN_SNAP_MM


def box_loop(x0, z0, x1, z1):
    return oriented(polygon_loop([Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1)]), True)


def square_tool(size):
    """A square tool, its tip at the lower corner (0, 0)."""
    corners = [Point(0, 0), Point(size, 0), Point(size, size), Point(0, size)]
    return [tuple(ToolEdge(LineSegment(a, b), True) for a, b in zip(corners, corners[1:] + corners[:1]))]


def round_tool(radius):
    """A disc around the tip."""
    left, right, centre = Point(-radius, 0), Point(radius, 0), Point(0, 0)
    return [(ToolEdge(ArcSegment(left, right, centre, ArcDirection.CCW), True), ToolEdge(ArcSegment(right, left, centre, ArcDirection.CCW), True))]


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.part = [box_loop(0, -20, 5, -10)]  # a block of the part: radius 0 to 5, z -20 to -10; the free side is z > -10 and radius > 5
        self.keep = RegionIndex(self.part)

    def walk(self, tool, start, goal, heading=None):
        curves = TipCurves(tool, [segment for loop in self.part for segment in loop])
        return tip_walk(curves, start, goal, 1, tool, self.keep, TOLERANCE, heading)

    def test_a_disc_has_the_tangent_lines_on_both_sides_of_a_wall(self):
        curves = contact_curves(round_tool(1), [LineSegment(Point(0, -10), Point(5, -10))])
        levels = {round(c.start.z, 6) for c in curves if isinstance(c, LineSegment) and abs(c.start.z - c.end.z) < 1e-9}
        self.assertTrue({-9.0, -11.0} <= levels)

    def test_an_arc_that_touches_at_a_point_the_line_does_not_reach_gives_no_curve(self):
        half = [(ToolEdge(ArcSegment(Point(-1, 0), Point(1, 0), Point(0, 0), ArcDirection.CCW), True),)]  # only the lower half circle side (angles 0 to 180)
        curves = contact_curves(half, [LineSegment(Point(0, -10), Point(5, -10))])
        tangent_levels = {round(c.start.z, 6) for c in curves if isinstance(c, LineSegment) and abs(c.start.z - c.end.z) < 1e-9}
        self.assertNotIn(-11.0, tangent_levels)  # the half circle (z >= 0) cannot touch a wall from the other side

    def test_the_square_tool_rides_up_a_wall_with_its_edge(self):
        tool = square_tool(2)
        way = self.walk(tool, Point(1, -10), 4)
        self.assertTrue(way)
        self.assertAlmostEqual(way[-1].end.x, 4, places=6)
        self.assertAlmostEqual(way[-1].end.z, -10, places=6)

    def test_the_walk_ends_at_the_top_of_the_wall(self):
        way = self.walk(square_tool(2), Point(1, -10), 8)
        self.assertAlmostEqual(way[-1].end.x, 5, places=6)  # above the block the tool is free: there is nothing to follow

    def test_a_disc_rides_up_along_the_wall_and_goes_on_to_the_wall_first(self):
        tool = round_tool(1)
        way = self.walk(tool, Point(3, -8), 4, heading=(0.0, -1.0))
        self.assertIsInstance(way[0], LineSegment)  # the tip was not touching: it goes on to the wall
        self.assertAlmostEqual(way[0].end.z, -9, places=6)
        self.assertAlmostEqual(way[-1].end.x, 4, places=6)
        self.assertAlmostEqual(way[-1].end.z, -9, places=6)

    def test_the_walk_goes_over_a_low_bump_and_down_on_the_other_side(self):
        tool = square_tool(2)
        curves = TipCurves(tool, [segment for loop in self.part for segment in loop])
        up = tip_walk(curves, Point(1, -10), 8, 1, tool, self.keep, TOLERANCE)  # up the front of the block: it stops on the top (radius 5)
        self.assertAlmostEqual(up[-1].end.x, 5, places=6)
        over = ride_over(curves, up, 1, 8, tool, self.keep, TOLERANCE)  # the line above is at 8: the block is lower, so on over it
        self.assertTrue(over)
        self.assertAlmostEqual(over[-1].end.x, 1, places=6)
        self.assertAlmostEqual(over[-1].end.z, -22, places=6)  # the tool reaches back by its size: its edge touches the back of the block

    def test_no_walk_over_when_the_ride_up_reached_the_goal(self):
        tool = square_tool(2)
        curves = TipCurves(tool, [segment for loop in self.part for segment in loop])
        up = tip_walk(curves, Point(1, -10), 4, 1, tool, self.keep, TOLERANCE)
        self.assertEqual(ride_over(curves, up, 1, 4, tool, self.keep, TOLERANCE), [])  # a wall: the goal is reached

    def test_a_walk_with_no_way_up_is_empty(self):
        self.assertEqual(self.walk(square_tool(2), Point(1, -10), 1), [])  # already at the height

    def test_the_walk_goes_round_a_spike_narrower_than_any_scan_step(self):
        # a spike 0.1 wide that stands 0.05 out of the wall: the disc touches it only while its tip is between radius 1.78 and 2.32, so a scan
        # every millimetre (the old walk: places at 1.75 and 2.5) does not see it and walks through it; the walk along the contact curves goes round it
        spiked = [oriented(polygon_loop([
            Point(0, -20), Point(5, -20), Point(5, -10), Point(2.1, -10), Point(2.1, -9.95), Point(2, -9.95), Point(2, -10), Point(0, -10),
        ]), True)]
        keep = RegionIndex(spiked)
        tool = round_tool(0.5)
        curves = TipCurves(tool, [segment for loop in spiked for segment in loop])
        way = tip_walk(curves, Point(1, -9.5), 4, 1, tool, keep, TOLERANCE)
        self.assertAlmostEqual(way[-1].end.x, 4, places=6)
        self.assertAlmostEqual(way[-1].end.z, -9.5, places=6)
        self.assertGreater(max(max(p.start.z, p.end.z) for p in way), -9.5 + 0.04)  # it left the wall to go over the spike
        for piece in way:  # the referee: the tool may stand on every place of the way, tested every hundredth of a millimetre
            count = max(1, int(piece.length / 0.01))
            for i in range(count + 1):
                self.assertFalse(blocked_by_part(tool, keep, point_of(piece, i / count), TOLERANCE), piece)


class DipTests(unittest.TestCase):
    def test_a_stretch_is_uncovered_where_no_line_of_a_smaller_radius_lies_under_it(self):
        lines = [(10.0, -50.0, 0.0), (8.0, -40.0, -10.0), (6.0, -30.0, -20.0), (6.0, -45.0, -44.0)]  # (radius, low z, high z)
        found = uncovered(lines, 1e-6)
        self.assertEqual(found[2], [(-30.0, -20.0)])  # the lowest line: nothing under it
        self.assertEqual(found[3], [(-45.0, -44.0)])
        self.assertEqual(found[1], [(-40.0, -30.0), (-20.0, -10.0)])  # the line at 8 has the line at 6 under its middle only
        self.assertEqual(found[0], [(-50.0, -45.0), (-44.0, -40.0), (-10.0, 0.0)])

    def test_the_pass_goes_down_into_a_dip_and_up_again(self):
        # a groove in the part: the free side is z > -10 and radius > 5 as in the walk tests, the block has a notch in its top
        notch = [oriented(polygon_loop([Point(0, -30), Point(5, -30), Point(5, -24), Point(3, -24), Point(3, -16), Point(5, -16), Point(5, -10), Point(0, -10)]), True)]
        keep = RegionIndex(notch)
        tool = square_tool(2)
        curves = TipCurves(tool, [segment for loop in notch for segment in loop])
        moves = follow_dip(curves, Point(5, -18), 5.0, 7.5, tool, keep, TOLERANCE)  # from above the notch: first down to its floor
        self.assertTrue(moves)
        self.assertLessEqual(min(min(m.start.x, m.end.x) for m in moves), 3.0 + 1e-6)  # down to the floor of the notch
        self.assertAlmostEqual(moves[-1].end.x, 5.0, places=6)  # along the floor and up the other side to the top of the wall (the tool is free above it)
        self.assertAlmostEqual(moves[-1].end.z, -24.0, places=6)


if __name__ == "__main__":
    unittest.main()
