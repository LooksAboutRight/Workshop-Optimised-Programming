import math
import unittest

from wop.core.geometry import LineSegment, Point
from wop.core.tooling.tool import ToolSegment, ToolSegmentRole, ToolShape, flank_half_angle_deg
from wop.core.tooling.tool_presets import thread_tool

CUTTER, HOLDER = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER


def v_tool(half_left: float, half_right: float, height: float = 2) -> ToolShape:
    left = Point(height, height * math.tan(math.radians(half_left)))
    right = Point(height, -height * math.tan(math.radians(half_right)))
    tip = Point(0, 0)
    return ToolShape((
        ToolSegment(LineSegment(tip, left), CUTTER),
        ToolSegment(LineSegment(left, right), HOLDER),
        ToolSegment(LineSegment(right, tip), CUTTER),
    ))


class FlankAngleTests(unittest.TestCase):
    def test_the_standard_thread_tool_has_30_degrees(self):
        self.assertAlmostEqual(flank_half_angle_deg(thread_tool(1, "t").shape), 30)
        self.assertAlmostEqual(flank_half_angle_deg(thread_tool(1, "t", False).shape), 30)

    def test_a_drawn_v_gives_its_own_angle_and_the_larger_flank_counts(self):
        self.assertAlmostEqual(flank_half_angle_deg(v_tool(27.5, 27.5)), 27.5)
        self.assertAlmostEqual(flank_half_angle_deg(v_tool(20, 35)), 35)

    def test_a_tool_without_a_slanted_cutting_edge_gets_the_standard_value(self):
        shape = ToolShape((
            ToolSegment(LineSegment(Point(0, 0), Point(0, -3)), CUTTER),
            ToolSegment(LineSegment(Point(0, -3), Point(5, -3)), HOLDER),
            ToolSegment(LineSegment(Point(5, -3), Point(5, 0)), HOLDER),
            ToolSegment(LineSegment(Point(5, 0), Point(0, 0)), HOLDER),
        ))
        self.assertAlmostEqual(flank_half_angle_deg(shape), 30)


if __name__ == "__main__":
    unittest.main()
