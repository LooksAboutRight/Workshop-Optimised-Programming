import unittest

from wop.core.geometry import LineSegment, Point
from wop.core.tooling.tool import Tool, ToolError, ToolSegment, ToolShape, ToolSegmentRole

CUTTER = ToolSegmentRole.CUTTER
HOLDER = ToolSegmentRole.HOLDER


def square_shape() -> ToolShape:
    corners = [Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4), Point(0, 0)]
    roles = [CUTTER, HOLDER, HOLDER, CUTTER]
    return ToolShape(
        tuple(ToolSegment(LineSegment(a, b), r) for (a, b), r in zip(zip(corners, corners[1:]), roles))
    )


class ToolShapeTests(unittest.TestCase):
    def test_roles_are_separated(self):
        shape = square_shape()
        self.assertEqual(len(shape.segments), 4)
        self.assertEqual(len(shape.cutter_segments), 2)
        self.assertEqual(len(shape.holder_segments), 2)

    def test_tool_keeps_number_and_name(self):
        tool = Tool(3, "rough OD", square_shape())
        self.assertEqual((tool.number, tool.name), (3, "rough OD"))

    def test_empty_shape_is_rejected(self):
        with self.assertRaises(ToolError):
            ToolShape(())

    def test_gap_in_the_outline_is_rejected(self):
        pieces = (
            ToolSegment(LineSegment(Point(0, 0), Point(4, 0)), CUTTER),
            ToolSegment(LineSegment(Point(5, 0), Point(0, 4)), HOLDER),
            ToolSegment(LineSegment(Point(0, 4), Point(0, 0)), HOLDER),
        )
        with self.assertRaises(ToolError) as caught:
            ToolShape(pieces)
        self.assertIn("segment 0", str(caught.exception))

    def test_open_outline_is_rejected(self):
        pieces = (
            ToolSegment(LineSegment(Point(0, 0), Point(4, 0)), CUTTER),
            ToolSegment(LineSegment(Point(4, 0), Point(0, 4)), HOLDER),
        )
        with self.assertRaises(ToolError) as caught:
            ToolShape(pieces)
        self.assertIn("not closed", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
