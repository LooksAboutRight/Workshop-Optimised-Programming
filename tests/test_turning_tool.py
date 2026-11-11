import unittest
from dataclasses import replace

from tests.helpers import is_valid_outline
from wop.core.geometry import ArcSegment, LineSegment
from wop.core.tooling.tool import ToolError, ToolSegmentRole
from wop.core.tooling.tool_reference import default_tip
from wop.core.tool_types import TOOL_TYPES, make_tool
from wop.core.tool_types.turning import ToolHand


def standard(**values):
    return make_tool("turning", 1, replace(TOOL_TYPES.get("turning").default(), **values))


def corners(tool):
    return [(round(p.segment.end.x, 3), round(p.segment.end.z, 3)) for p in tool.shape.pieces if isinstance(p.segment, LineSegment)]


class StandardShapeTests(unittest.TestCase):
    """The default is the drawing `right rand cutter.DXF` of the user (drawing X is Z, drawing Y is the radius), without its 0.5 mm rounding."""

    def test_it_follows_the_drawing(self):
        tool = standard()
        pieces = tool.shape.pieces
        self.assertIsInstance(pieces[0].segment, ArcSegment)
        self.assertAlmostEqual(pieces[0].segment.radius, 0.3)
        self.assertEqual(corners(tool)[:1], [(20.0, 2.069)])  # the side edge ends at radius 20, 2.069 further back
        self.assertEqual(corners(tool)[-1], (0.002, 0.331))  # the front edge ends at the nose
        self.assertIn((100.0, 20.0), corners(tool))  # the far corner: length 100, width 20
        self.assertAlmostEqual(default_tip(tool.shape).x, 0, places=6)
        self.assertAlmostEqual(default_tip(tool.shape).z, 0, places=6)

    def test_the_step_returns_to_the_near_side_at_a_right_angle_to_the_side_edge(self):
        tool = standard()
        step = tool.shape.pieces[2]
        self.assertEqual(step.role, ToolSegmentRole.HOLDER)
        self.assertAlmostEqual(step.segment.end.z, 0)
        side = tool.shape.pieces[1].segment
        along = (side.end.x - side.start.x, side.end.z - side.start.z)
        across = (step.segment.end.x - step.segment.start.x, step.segment.end.z - step.segment.start.z)
        self.assertAlmostEqual(along[0] * across[0] + along[1] * across[1], 0, places=6)

    def test_the_cutting_edges_are_the_nose_and_the_two_edges(self):
        roles = [p.role.name for p in standard().shape.pieces]
        self.assertEqual(roles, ["CUTTER", "CUTTER", "HOLDER", "HOLDER", "HOLDER", "HOLDER", "CUTTER"])

    def test_no_step_for_an_edge_angle_of_90_or_less(self):
        for angle in (90, 80, 60):
            with self.subTest(angle=angle):
                tool = standard(side_edge_angle_deg=angle)
                holders = [p for p in tool.shape.pieces if p.role is ToolSegmentRole.HOLDER]
                self.assertEqual(len(holders), 3)  # near side, top and far side only

    def test_a_left_hand_tool_is_the_mirror_image_in_z(self):
        right, left = standard(), standard(hand=ToolHand.LEFT)
        self.assertEqual([(x, -z + 0.0) for x, z in corners(right)], [(x, z + 0.0) for x, z in corners(left)])
        self.assertAlmostEqual(default_tip(left.shape).z, 0, places=6)

    def test_values_that_make_no_tool_are_refused(self):
        for values in ({"width_mm": 0}, {"side_edge_angle_deg": 30}, {"front_edge_angle_deg": 140}, {"nose_radius_mm": 30},
                       {"side_edge_angle_deg": 135, "front_edge_angle_deg": 135}, {"length_mm": 10}, {"width_mm": 1, "side_edge_angle_deg": 130}):
            with self.subTest(values=values), self.assertRaises(ToolError):
                standard(**values)

    def test_the_plain_starter_values_give_the_old_rectangle(self):
        from wop.ui.model.helpers import STUB_TURNING_TOOL

        tool = make_tool("turning", 1, STUB_TURNING_TOOL)
        self.assertEqual(corners(tool), [(8, 0), (8, 12), (0, 12), (0, 0)])
        self.assertEqual([p.role.name for p in tool.shape.pieces], ["CUTTER", "HOLDER", "HOLDER", "CUTTER"])


class EveryCombinationTests(unittest.TestCase):
    def test_every_combination_that_builds_is_a_valid_outline(self):
        import itertools

        built = 0
        for a, b, r, w, hand in itertools.product((50, 90, 96, 130), (50, 90, 96, 130), (0, 0.3, 3), (8, 20), (ToolHand.RIGHT, ToolHand.LEFT)):
            try:
                tool = standard(side_edge_angle_deg=a, front_edge_angle_deg=b, nose_radius_mm=r, width_mm=w, hand=hand)
            except ToolError:
                continue
            built += 1
            self.assertTrue(is_valid_outline(tool.shape.segments), (a, b, r, w, hand))
        self.assertGreater(built, 100)


if __name__ == "__main__":
    unittest.main()
