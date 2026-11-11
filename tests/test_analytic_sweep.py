"""The exact sweep of a tool edge along an arc (wop/core/geometry/arc_sweep.py), against the swept area worked out with the `Region` of the program.

The reference moves the edge along the path in small steps and takes the union of the parallelograms the pieces of the edge draw
(arcs as fine chords): good to a few thousandths of a square millimetre for the sizes used here.
"""

import math
import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point, segments_to_polyline

from wop.core.geometry.arc_sweep import arc_along_arc, ccw_range, line_along_arc
from wop.core.geometry.chains import region_of_loops
from wop.core.geometry.region import Region

STEPS = 90
REFERENCE_DEVIATION_MM = 0.002
AREA_TOLERANCE_MM2 = 0.02


def arc_from(center, radius, start_deg, end_deg):
    """An arc by its centre, radius and the angles (degrees) it runs between; counter-clockwise when the end angle is larger."""
    a, b = math.radians(start_deg), math.radians(end_deg)
    first = Point(center.x + radius * math.cos(a), center.z + radius * math.sin(a))
    last = Point(center.x + radius * math.cos(b), center.z + radius * math.sin(b))
    return ArcSegment(first, last, center, ArcDirection.CCW if b > a else ArcDirection.CW)


def reference(edge, path):
    """The union of the parallelograms the edge draws while the tip goes along the path (in STEPS steps)."""
    start, end = path.start_angle, path.start_angle + path.direction.value * path.sweep
    region = Region.empty()
    points = segments_to_polyline([edge], REFERENCE_DEVIATION_MM)
    last = None
    for step in range(STEPS + 1):
        angle = start + (end - start) * step / STEPS
        tip = Point(path.center.x + path.radius * math.cos(angle), path.center.z + path.radius * math.sin(angle))
        shift = (tip.x - path.start.x, tip.z - path.start.z)
        if last is not None:
            moved = (shift[0] - last[0], shift[1] - last[1])
            for a, b in zip(points, points[1:]):
                a0, b0 = Point(a.x + last[0], a.z + last[1]), Point(b.x + last[0], b.z + last[1])
                corners = [a0, b0, Point(b0.x + moved[0], b0.z + moved[1]), Point(a0.x + moved[0], a0.z + moved[1])]
                try:
                    region = region.union(Region.from_points(corners))
                except Exception:  # a parallelogram with no area (the edge moves along itself)
                    continue
        last = shift
    return region


def exact(loops):
    region = Region.empty()
    for loop in loops:
        region = region.union(region_of_loops([loop]))
    return region


class SweepTests(unittest.TestCase):
    def check(self, edge, path, expect_loops=None):
        loops = line_along_arc(edge.start, edge.end, path) if isinstance(edge, LineSegment) else arc_along_arc(edge, path)
        if expect_loops is not None:
            self.assertEqual(len(loops), expect_loops)
        mine, wanted = exact(loops), reference(edge, path)
        self.assertGreater(wanted.area, 0.01)
        self.assertLess(mine.difference(wanted).area + wanted.difference(mine).area, AREA_TOLERANCE_MM2, f"area {mine.area} against {wanted.area}")

    def test_a_line_across_the_path_has_no_fold(self):
        path = arc_from(Point(0, 0), 5, 20, 100)
        start = path.start
        self.check(LineSegment(Point(start.x + 1, start.z), Point(start.x + 3, start.z + 0.5)), path)

    def test_a_line_along_the_path_tangent_folds_and_the_path_is_cut(self):
        path = arc_from(Point(0, 0), 5, 0, 120)  # the tangent turns through every direction in a half turn
        start = path.start
        self.check(LineSegment(Point(start.x, start.z), Point(start.x + 2, start.z + 2)), path)

    def test_the_path_in_either_direction_gives_the_same_region(self):
        centre, edge_from = Point(2, -1), Point(0, 0)
        ccw, cw = arc_from(centre, 4, 10, 100), arc_from(centre, 4, 100, 10)
        for path in (ccw, cw):
            start = path.start
            self.check(LineSegment(Point(start.x + 0.2, start.z), Point(start.x + 2.5, start.z - 1)), path)

    def test_an_arc_edge_with_a_larger_path_radius(self):
        path = arc_from(Point(0, 0), 6, 30, 110)
        start = path.start
        edge = arc_from(Point(start.x + 1, start.z + 1), 0.4, -60, 80)  # a nose
        self.check(edge, path)

    def test_an_arc_edge_whose_angles_meet_those_of_the_path(self):
        path = arc_from(Point(0, 0), 3, 0, 90)
        start = path.start
        edge = arc_from(Point(start.x, start.z), 1, 20, 70)  # the same angles: the envelope (radius R + r) is part of the border
        self.check(edge, path)

    def test_an_arc_edge_with_a_smaller_path_radius_than_its_own(self):
        path = arc_from(Point(0, 0), 1, 0, 80)
        start = path.start
        edge = arc_from(Point(start.x - 1, start.z + 0.5), 2.5, 10, 100)
        self.check(edge, path)

    def test_arcs_of_equal_radius(self):
        path = arc_from(Point(0, 0), 2, 20, 100)
        start = path.start
        edge = arc_from(Point(start.x + 0.5, start.z), 2, 30, 110)
        self.check(edge, path)

    def test_the_range_of_an_arc_is_the_same_whatever_its_direction(self):
        a, b = arc_from(Point(0, 0), 1, 10, 100), arc_from(Point(0, 0), 1, 100, 10)
        self.assertAlmostEqual(ccw_range(a)[0], ccw_range(b)[0])
        self.assertAlmostEqual(ccw_range(a)[1], ccw_range(b)[1])


if __name__ == "__main__":
    unittest.main()
