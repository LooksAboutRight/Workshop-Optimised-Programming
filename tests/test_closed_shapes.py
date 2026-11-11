import unittest
from dataclasses import replace

from tests.helpers import assert_chain_is_continuous
from wop.core.contour import (
    ArcRadiusStep,
    ContourDefinition,
    ContourError,
    LineStep,
    NamedPoint,
)
from wop.core.files.contour_io import contour_from_dict, contour_to_dict
from wop.core.contour_solver import build_contour
from wop.core.geometry import ArcDirection, Point
from wop.core.files.tool_io import tool_from_dict, tool_to_dict
from wop.core.tooling.tool_shape import shape_to_definition, tool_from_contour
from wop.core.tool_types import TOOL_TYPES, make_tool


def triangle(closed: bool = True, **kwargs) -> ContourDefinition:
    steps = (LineStep(Point(0, 4)), LineStep(Point(4, 4)))
    return ContourDefinition(Point(0, 0), steps, closed, **kwargs)


class ClosedShapeTests(unittest.TestCase):
    def test_an_open_chain_stays_open(self):
        contour = build_contour("c", "open", triangle(closed=False))
        self.assertEqual(len(contour.segments), 2)
        self.assertFalse(contour.is_closed)

    def test_a_closed_shape_gets_a_closing_line(self):
        contour = build_contour("c", "closed", triangle())
        self.assertEqual(len(contour.segments), 3)
        self.assertTrue(contour.is_closed)
        self.assertEqual(contour.cutting, ())
        self.assertTrue(contour.segments[-1].end.is_close(Point(0, 0)))
        assert_chain_is_continuous(self, contour.segments)

    def test_no_closing_line_when_the_last_step_ends_at_the_start(self):
        definition = ContourDefinition(Point(0, 0), (LineStep(Point(0, 4)), LineStep(Point(4, 4)), LineStep(Point(0, 0))), True)
        self.assertEqual(len(build_contour("c", "c", definition).segments), 3)

    def test_a_closed_shape_without_area_is_refused(self):
        definition = ContourDefinition(Point(0, 0), (LineStep(Point(0, 4)),), True)
        with self.assertRaises(ContourError):
            build_contour("c", "flat", definition)

    def test_a_full_circle_is_a_closed_shape(self):
        from wop.core.contour import ArcCenterStep
        circle = ContourDefinition(Point(0, 0), (ArcCenterStep(Point(0, 0), Point(0, 2), ArcDirection.CCW),), True)
        contour = build_contour("c", "circle", circle)
        self.assertTrue(contour.is_closed)
        self.assertEqual(len(contour.segments), 1)


class CuttingAndPointsTests(unittest.TestCase):
    def test_cutting_flags_follow_the_segments(self):
        steps = (LineStep(Point(0, 4), cutting=True), LineStep(Point(4, 4)))
        contour = build_contour("c", "c", ContourDefinition(Point(0, 0), steps, True))
        self.assertEqual(contour.cutting, (True, False, False))  # the closing line is never cutting

    def test_a_corner_connector_has_the_flag_of_its_step(self):
        from wop.core.contour import fillet
        steps = (LineStep(Point(0, 10), corner=fillet(2), cutting=True), LineStep(Point(10, 10)), LineStep(Point(10, 0)))
        contour = build_contour("c", "c", ContourDefinition(Point(0, 0), steps, True))
        self.assertEqual(len(contour.cutting), len(contour.segments))
        self.assertTrue(contour.cutting[0] and contour.cutting[1])  # line and the connector that follows it

    def test_named_points_are_kept_and_checked(self):
        points = (NamedPoint("tip", 1, 2), NamedPoint("ref", 0, 0))
        contour = build_contour("c", "c", triangle(points=points))
        self.assertEqual(contour.points, points)
        with self.assertRaises(ContourError):
            build_contour("c", "c", triangle(points=(NamedPoint("a"), NamedPoint("a"))))
        with self.assertRaises(ContourError):
            build_contour("c", "c", triangle(points=(NamedPoint(" "),)))

    def test_everything_survives_a_save_and_load(self):
        steps = (
            LineStep(Point(0, 4), cutting=True),
            ArcRadiusStep(Point(4, 4), 5, ArcDirection.CCW, cutting=True),
        )
        definition = ContourDefinition(Point(0, 0), steps, True, (NamedPoint("tip", 0, 0),))
        contour = build_contour("c", "c", definition)
        loaded = contour_from_dict(contour_to_dict(contour))
        self.assertEqual(loaded.definition, definition)
        self.assertEqual(loaded.cutting, contour.cutting)
        self.assertEqual(loaded.points, contour.points)

    def test_a_contour_of_a_part_is_saved_as_before(self):
        data = contour_to_dict(build_contour("c", "c", triangle(closed=False)))
        self.assertNotIn("cutting", data)
        self.assertNotIn("points", data)
        self.assertNotIn("closed", data["definition"])


class ToolShapeTests(unittest.TestCase):
    def insert(self):
        return make_tool("turning", 5, TOOL_TYPES.get("turning").default())

    def test_the_shape_of_a_turning_tool_opens_as_a_closed_contour_and_comes_back_the_same(self):
        tool = self.insert()
        definition = shape_to_definition(tool.shape)
        self.assertTrue(definition.closed)
        contour = build_contour("t", "tool", definition)
        self.assertTrue(contour.is_closed)
        again = tool_from_contour(tool, contour)
        self.assertEqual(len(again.shape.pieces), len(tool.shape.pieces))
        for old, new in zip(tool.shape.pieces, again.shape.pieces):
            self.assertIs(old.role, new.role)
            self.assertTrue(old.segment.start.is_close(new.segment.start, 1e-6))
            self.assertTrue(old.segment.end.is_close(new.segment.end, 1e-6))


    def test_an_edited_tool_is_a_free_shape_with_points(self):
        tool = self.insert()
        definition = replace(shape_to_definition(tool.shape), points=(NamedPoint("reference"),))
        edited = tool_from_contour(tool, build_contour("t", "tool", definition))
        self.assertEqual((edited.kind, edited.definition), ("", None))
        self.assertEqual(edited.points, (NamedPoint("reference"),))
        self.assertEqual((edited.number, edited.name, edited.material), (tool.number, tool.name, tool.material))


    def test_points_of_a_tool_are_saved(self):
        tool = replace(self.insert(), points=(NamedPoint("tip", 0, 0), NamedPoint("centre", 1, 1)))
        loaded = tool_from_dict(tool_to_dict(tool))
        self.assertEqual(loaded.points, tool.points)
        self.assertNotIn("points", tool_to_dict(replace(self.insert(), points=())))  # a tool without points writes none


if __name__ == "__main__":
    unittest.main()
