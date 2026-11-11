"""DXF import "as drawn" for closed shapes (workholding items, holders, turrets, tools) and named points from CAD (TH1)."""

import unittest

from wop.core.contour import ContourError
from wop.core.contour_solver import build_contour
from wop.core.dxf_contour import (
    DxfArc,
    DxfDrawing,
    DxfLine,
    DxfPoint,
    contour_from_drawing,
    name_markers,
    shape_from_drawing,
)

# A 10 x 20 box in a drawing with the axis horizontal (drawing x = Z, drawing y = radius): z -20..0, radius 5..15,
# with a side lying on... nothing; and one that does lie on the axis (radius 0) below.
BOX = [
    DxfLine((-20, 5), (0, 5)), DxfLine((0, 5), (0, 15)), DxfLine((0, 15), (-20, 15)), DxfLine((-20, 15), (-20, 5)),
]
ON_AXIS_BOX = [
    DxfLine((-20, 0), (0, 0)), DxfLine((0, 0), (0, 10)), DxfLine((0, 10), (-20, 10)), DxfLine((-20, 10), (-20, 0)),
]
BELOW_AXIS_BOX = [
    DxfLine((-20, -5), (0, -5)), DxfLine((0, -5), (0, -15)), DxfLine((0, -15), (-20, -15)), DxfLine((-20, -15), (-20, -5)),
]


def drawing(entities, points=()):
    return DxfDrawing(tuple(entities), (), tuple(points))


class ShapeImportTests(unittest.TestCase):
    def test_a_closed_box_becomes_a_closed_contour_where_it_was_drawn(self):
        result = shape_from_drawing(drawing(BOX))
        contour = build_contour("b", "box", result.definition)
        self.assertTrue(contour.is_valid and contour.is_closed)
        xs = {p.x for s in contour.segments for p in (s.start, s.end)}
        zs = {p.z for s in contour.segments for p in (s.start, s.end)}
        self.assertEqual((min(xs), max(xs), min(zs), max(zs)), (5, 15, -20, 0))
        self.assertEqual(result.messages, ())

    def test_a_line_on_the_axis_stays(self):
        result = shape_from_drawing(drawing(ON_AXIS_BOX))
        self.assertEqual(len(result.definition.steps), 4)
        self.assertFalse(any("axis" in m for m in result.messages))
        # the part import drops it (a part profile is open on the axis), which is why shapes have their own import
        self.assertTrue(any("axis" in m for m in contour_from_drawing(drawing(ON_AXIS_BOX)).messages))

    def test_a_shape_below_the_axis_is_not_mirrored(self):
        result = shape_from_drawing(drawing(BELOW_AXIS_BOX))
        contour = build_contour("b", "box", result.definition)
        self.assertEqual(min(p.x for s in contour.segments for p in (s.start, s.end)), -15)

    def test_an_open_outline_is_refused_in_words(self):
        with self.assertRaises(ContourError) as raised:
            shape_from_drawing(drawing(BOX[:3]))
        self.assertIn("not closed", str(raised.exception))
        with self.assertRaises(ContourError):
            shape_from_drawing(drawing([]))

    def test_the_longest_outline_is_used_and_the_rest_named(self):
        small = [DxfLine((100, 100), (101, 100)), DxfLine((101, 100), (101, 101)), DxfLine((101, 101), (100, 100))]
        result = shape_from_drawing(drawing(BOX + small))
        self.assertTrue(any("separate outlines" in m for m in result.messages))
        self.assertEqual(len(result.definition.steps), 4)

    def test_an_arc_in_a_closed_outline(self):
        # a half disc: the arc from 0 to 180 degrees over a line
        entities = [DxfLine((-10, 0), (10, 0)), DxfArc((0, 0), 10, 0, 180)]
        result = shape_from_drawing(drawing(entities))
        self.assertTrue(build_contour("h", "half", result.definition).is_closed)

    def test_named_points_are_placed_like_the_outline(self):
        # drawing (x, y) = (z, radius)
        result = shape_from_drawing(drawing(BOX, [DxfPoint("shank seat", (-10.0, 8.0))]))
        self.assertEqual(len(result.points), 1)
        self.assertEqual((result.points[0].name, result.points[0].x, result.points[0].z), ("shank seat", 8.0, -10.0))


class MarkerNameTests(unittest.TestCase):
    def test_each_point_takes_the_nearest_text_once(self):
        points = name_markers([(0, 0), (10, 0)], [("b", (11, 1)), ("a", (1, 1))])
        self.assertEqual([p.name for p in points], ["a", "b"])

    def test_text_that_is_too_far_is_not_used_and_unnamed_points_are_numbered(self):
        points = name_markers([(0, 0), (50, 0), (60, 0)], [("far", (500, 500))])
        self.assertEqual([p.name for p in points], ["point 1", "point 2", "point 3"])

    def test_one_text_names_only_one_point(self):
        points = name_markers([(0, 0), (1, 0)], [("seat", (0, 1))])
        self.assertEqual([p.name for p in points], ["seat", "point 1"])


if __name__ == "__main__":
    unittest.main()
