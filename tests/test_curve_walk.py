"""Where a point lies on a curve of lines and arcs."""

import unittest

from wop.core.contour import ArcRadiusStep, ContourDefinition, LineStep
from wop.core.contour_solver import solve_contour
from wop.core.curve_walk import locate
from wop.core.geometry import ArcDirection, Point


def curve(start, *steps):
    return list(solve_contour(ContourDefinition(Point(*start), tuple(steps))))


def line(x, z):
    return LineStep(Point(x, z))


class LocateTests(unittest.TestCase):
    def test_a_point_on_the_curve_is_found_on_its_piece(self):
        pieces = curve((8, 0), line(8, -10), line(12, -10))
        found = locate(pieces, Point(8, -4))
        self.assertEqual(found.index, 0)
        self.assertAlmostEqual(found.fraction, 0.4, places=6)

    def test_a_point_off_the_curve_is_not_found(self):
        self.assertIsNone(locate(curve((8, 0), line(8, -10)), Point(9, -4)))

    def test_a_point_on_an_arc_is_found_on_the_arc(self):
        pieces = curve((8, 0), line(8, -10), ArcRadiusStep(Point(14, -16), 6, ArcDirection.CCW))
        arc = pieces[1]
        middle = arc.point_at(0.5)
        found = locate(pieces, middle)
        self.assertEqual(found.index, 1)
        self.assertAlmostEqual(found.fraction, 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
