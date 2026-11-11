"""The way out of a place in the stock (wop/core/analytic/tip_walk.py, way_out): up a wall, along a floor, down a slope, and none where the tool does not fit."""

import unittest

from wop.core.geometry import LineSegment, Point

from wop.core.geometry.chains import oriented, polygon_loop
from wop.core.geometry.penetration import RegionIndex, blocked_by_material, blocked_by_part
from wop.core.analytic.tip_walk import TipCurves, way_out
from wop.core.geometry.tool_edges import ToolEdge
from wop.core.constants import CHAIN_SNAP_MM
from wop.core.geometry.intersect import point_of

TOLERANCE = CHAIN_SNAP_MM


def loop_of(*points):
    return oriented(polygon_loop([Point(x, z) for x, z in points]), True)


def square_tool(size, cutting=True):
    """A square tool, its tip at the lower corner (0, 0)."""
    corners = [Point(0, 0), Point(size, 0), Point(size, size), Point(0, size)]
    return [tuple(ToolEdge(LineSegment(a, b), cutting) for a, b in zip(corners, corners[1:] + corners[:1]))]


class WayOutTests(unittest.TestCase):
    """Radius is the first number, Z the second: the free side is the larger radius and the larger Z."""

    def setUp(self):
        # a pocket: the floor at radius 3 between two walls up to radius 8 (z -20 to -10), the stock fills it
        self.pocket = [loop_of((0, -30), (8, -30), (8, -20), (3, -20), (3, -10), (8, -10), (8, 0), (0, 0))]
        self.pocket_stock = [loop_of((3, -20), (8, -20), (8, -10), (3, -10))]

    def out(self, part, stock, tool, start, heading=None, away=None):
        curves = TipCurves(tool, [segment for loop in part for segment in loop])
        found = way_out(curves, start, tool, RegionIndex(part), RegionIndex(stock), TOLERANCE, heading, away=away)
        if found:  # the way is continuous and the tool stands on every place of it
            for before, after in zip(found, found[1:]):
                self.assertTrue(before.end.is_close(after.start, 1e-6))
            keep, material = RegionIndex(part), RegionIndex(stock)
            for piece in found:
                for i in range(11):
                    place = point_of(piece, i / 10)
                    self.assertFalse(blocked_by_part(tool, keep, place, TOLERANCE))
                    self.assertFalse(blocked_by_material(tool, material, place, TOLERANCE))
        return found

    def test_the_tool_leaves_a_pocket_up_along_the_wall(self):
        way = self.out(self.pocket, self.pocket_stock, square_tool(2), Point(3, -12))
        self.assertTrue(way)
        self.assertAlmostEqual(way[-1].end.x, 8, delta=2 * TOLERANCE)  # clear of the stock when its lowest edge is on the top of it (within the tolerance)
        self.assertAlmostEqual(way[-1].end.z, -12, delta=2 * TOLERANCE)

    def test_a_tool_that_is_clear_has_an_empty_way(self):
        self.assertEqual(self.out(self.pocket, self.pocket_stock, square_tool(2), Point(8, -12)), [])

    def test_a_tool_that_touches_nothing_first_goes_on_to_the_wall(self):
        way = self.out(self.pocket, self.pocket_stock, square_tool(2), Point(5, -12.5), heading=(0.0, 1.0))
        self.assertTrue(way)
        self.assertAlmostEqual(way[0].end.z, -12, delta=2 * TOLERANCE)  # on to the wall
        self.assertAlmostEqual(way[-1].end.x, 8, delta=2 * TOLERANCE)  # and up it

    def test_without_a_heading_a_floating_tool_has_no_way(self):
        self.assertIsNone(self.out(self.pocket, self.pocket_stock, square_tool(2), Point(5, -12.5)))

    def test_under_a_lip_the_way_out_is_along_the_floor(self):
        # a tunnel under a lid: radius 3 to 6, z -30 to -12, open to the front; going up leads nowhere
        part = [loop_of((0, -40), (8, -40), (8, -12), (6, -12), (6, -30), (3, -30), (3, 0), (0, 0))]
        stock = [loop_of((3, -30), (6, -30), (6, -12), (3, -12))]
        way = self.out(part, stock, square_tool(2), Point(3, -20))
        self.assertTrue(way)
        self.assertAlmostEqual(way[-1].end.x, 3, delta=2 * TOLERANCE)
        self.assertAlmostEqual(way[-1].end.z, -12, delta=2 * TOLERANCE)

    def test_the_way_may_lead_down(self):
        # the floor of the tunnel falls from radius 3 at the back to radius 1 at the mouth: the tool has to go down to get out
        part = [loop_of((0, -40), (8, -40), (8, -12), (6, -12), (6, -30), (3, -30), (1, -12), (1, 0), (0, 0))]
        stock = [loop_of((3, -30), (6, -30), (6, -12), (1, -12))]
        start = Point(3 - 2 * 2 / 18, -28)  # the rear corner of the tool on the floor
        way = self.out(part, stock, square_tool(2), start)
        self.assertTrue(way)
        self.assertLess(way[-1].end.x, start.x - 1)
        self.assertAlmostEqual(way[-1].end.z, -12, delta=2 * TOLERANCE)

    def test_a_tool_wider_than_the_mouth_has_no_way_out(self):
        # the tunnel is 3 high, the mouth only 1.5: the tool of 2 stands inside but cannot leave
        part = [loop_of((0, -40), (8, -40), (8, -12), (4.5, -12), (4.5, -14), (6, -14), (6, -30), (3, -30), (3, 0), (0, 0))]
        stock = [loop_of((3, -30), (6, -30), (6, -14), (4.5, -14), (4.5, -12), (3, -12))]
        self.assertIsNone(self.out(part, stock, square_tool(2), Point(3, -20)))

    def test_where_the_contact_ends_the_tool_may_go_straight_on_out_of_the_pocket(self):
        stock = [loop_of((0, -30), (10, -30), (10, 0), (0, 0))]  # the bar stands 2 above the walls (it holds the part too)
        around = self.out(self.pocket, stock, square_tool(2), Point(3, -12))  # up the wall and along its top, wherever the contact leads
        way = self.out(self.pocket, stock, square_tool(2), Point(3, -12), away=(1.0, 0.0))
        self.assertTrue(way)
        self.assertLess(sum(piece.length for piece in way), sum(piece.length for piece in around))  # straight on at the top of the wall is shorter
        self.assertAlmostEqual(way[-1].end.x, 10, delta=2 * TOLERANCE)
        self.assertAlmostEqual(way[-1].end.z, -12, delta=2 * TOLERANCE)

    def test_a_tool_that_cannot_cut_cannot_stand_in_the_stock(self):
        self.assertIsNone(self.out(self.pocket, self.pocket_stock, square_tool(2, cutting=False), Point(3, -12)))


if __name__ == "__main__":
    unittest.main()
