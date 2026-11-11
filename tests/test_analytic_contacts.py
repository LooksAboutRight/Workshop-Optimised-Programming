"""The free stretches along a straight move, from the events where tool and part touch (wop/core/geometry/contacts.py).

The reference is a dense scan with the penetration test: the exact stretches must agree with it to the step of the scan.
"""

import random
import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point

from wop.core.geometry.chains import oriented, polygon_loop
from wop.core.geometry.contacts import free_intervals
from wop.core.geometry.penetration import RegionIndex, blocked_by_part
from wop.core.geometry.tool_edges import ToolEdge
from wop.core.constants import CHAIN_SNAP_MM

TOLERANCE = CHAIN_SNAP_MM
STEP = 0.02
MINIMUM = 0.01


def box_loop(x0, z0, x1, z1):
    return oriented(polygon_loop([Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1)]), True)


def disc_loop(cx, cz, radius):
    left, right, centre = Point(cx - radius, cz), Point(cx + radius, cz), Point(cx, cz)
    return oriented((ArcSegment(left, right, centre, ArcDirection.CCW), ArcSegment(right, left, centre, ArcDirection.CCW)), True)


def wedge_tool():
    """A tool like a turning tool: a nose arc and a long edge, the tip at the origin, the body at larger x."""
    nose = ArcSegment(Point(0.3, 0), Point(0, 0.3), Point(0.3, 0.3), ArcDirection.CW)
    corners = [Point(0, 0.3), Point(0, 6), Point(5, 6), Point(5, 1.4), Point(0.3, 0)]
    edges = [ToolEdge(nose, True)] + [ToolEdge(LineSegment(a, b), i % 2 == 0) for i, (a, b) in enumerate(zip(corners, corners[1:]))]
    return [tuple(edges)]


def scanned(tool, region, start, vector, length):
    """The free stretches by a dense scan (the reference)."""
    count = int(length / STEP)
    free = [not blocked_by_part(tool, region, Point(start.x + vector[0] * i * STEP, start.z + vector[1] * i * STEP), TOLERANCE) for i in range(count + 1)]
    found, begin = [], None
    for i, ok in enumerate(free):
        if ok and begin is None:
            begin = i
        if begin is not None and (not ok or i == count):
            found.append((begin * STEP, (i if ok else i - 1) * STEP))
            begin = None
    return [(a, b) for a, b in found if b - a >= MINIMUM]


class FreeIntervalsTests(unittest.TestCase):
    def check(self, tool, loops, start=Point(2, 0), vector=(0.0, -1.0), length=20.0):
        region = RegionIndex(loops)
        exact = free_intervals(tool, region, start, vector, length, TOLERANCE, MINIMUM)
        dense = scanned(tool, region, start, vector, length)
        self.assertEqual(len(exact), len(dense), f"exact {exact} dense {dense}")
        for (a, b), (c, d) in zip(exact, dense):
            self.assertAlmostEqual(a, c, delta=2 * STEP)
            self.assertAlmostEqual(b, d, delta=2 * STEP)
        return exact

    def test_a_wall_ahead_stops_the_tool_where_its_front_touches_it(self):
        found = self.check(wedge_tool(), [box_loop(-5, -30, 6, -10)])  # a wall across the way at z = -10 (the tool tip runs at x = 2, the body is at larger x)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0][1], 10, delta=0.35)  # the nose (radius 0.3) touches a wall straight across

    def test_a_narrow_crest_in_the_middle_is_found(self):
        found = self.check(wedge_tool(), [box_loop(-5, -8.3, 4, -8.0)])  # a crest 0.3 wide that rises above the tip path: a scan with a step of 1 mm would miss it
        self.assertEqual(len(found), 2)

    def test_a_crest_that_misses_the_tool_changes_nothing(self):
        found = self.check(wedge_tool(), [box_loop(-5, -8.3, 0.5, -8.0)])
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0][1], 20, places=6)

    def test_a_tool_edge_of_no_length_is_a_corner_only(self):
        # a tool outline with a line of no length next to its nose (a drawing with a doubled point) met a round boss with a division by zero
        tool = wedge_tool()
        nose_end = tool[0][0].segment.end
        with_point = [tuple([tool[0][0], ToolEdge(LineSegment(nose_end, nose_end), False), *tool[0][1:]])]
        self.assertEqual(self.check(with_point, [disc_loop(2.5, -9, 1.2)]), self.check(tool, [disc_loop(2.5, -9, 1.2)]))

    def test_a_round_boss_is_found_by_the_tangent_of_arcs(self):
        self.check(wedge_tool(), [disc_loop(2.5, -9, 1.2)])  # a boss that the nose runs into
        self.check(wedge_tool(), [disc_loop(4.4, -6, 1.0)])  # one that only the body meets

    def test_random_parts_agree_with_the_dense_scan(self):
        random.seed(7)
        for _ in range(12):
            loops = []
            for _ in range(random.randint(1, 3)):
                x0, z0 = random.uniform(-1, 5), random.uniform(-18, -2)
                if random.random() < 0.5:
                    loops.append(box_loop(x0, z0, x0 + random.uniform(0.4, 3), z0 + random.uniform(0.4, 4)))
                else:
                    loops.append(disc_loop(x0 + 1, z0 + 1, random.uniform(0.4, 1.5)))
            region = RegionIndex(loops)
            if blocked_by_part(wedge_tool(), region, Point(2, 0), TOLERANCE):
                continue  # the start must be free
            self.check(wedge_tool(), loops)

    def test_a_move_in_another_direction(self):
        self.check(wedge_tool(), [box_loop(-5, -12, 6, -6)], start=Point(2, 0), vector=(0.6, -0.8), length=14.0)


if __name__ == "__main__":
    unittest.main()
