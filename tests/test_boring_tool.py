import unittest
from dataclasses import replace

from tests.helpers import is_valid_outline
from wop.core.geometry import ArcSegment, LineSegment
from wop.core.tooling.tool import ToolError, ToolSegmentRole
from wop.core.tooling.tool_presets import block_tool
from wop.core.tooling.tool_reference import default_tip
from wop.core.tool_types import TOOL_TYPES, info_of, make_tool


def standard(**values):
    return make_tool("boring", 1, replace(TOOL_TYPES.get("boring").default(), **values))


def corners(tool):
    return [(round(p.segment.end.x, 3), round(p.segment.end.z, 3)) for p in tool.shape.pieces if isinstance(p.segment, LineSegment)]


class StandardBoringBarTests(unittest.TestCase):
    """The default follows the drawing `Boring bar.DXF` of the user (drawing X is Z, drawing Y is the radius), with sharp corners."""

    def test_it_follows_the_drawing(self):
        tool = standard()
        self.assertIsInstance(tool.shape.pieces[0].segment, ArcSegment)
        self.assertAlmostEqual(tool.shape.pieces[0].segment.radius, 0.3)
        self.assertEqual(corners(tool)[0], (-3.5, 20.176))  # the wall edge leans away by 10 degrees and ends where it meets the bar
        self.assertEqual(corners(tool)[1:4], [(-3.5, 100.0), (-19.5, 100.0), (-19.5, 2.016)])  # bar, end of the bar, front width
        self.assertAlmostEqual(default_tip(tool.shape).x, 0, places=6)
        self.assertAlmostEqual(default_tip(tool.shape).z, 0, places=6)

    def test_the_cutting_edges_are_the_nose_and_the_two_edges(self):
        self.assertEqual([p.role.name for p in standard().shape.pieces], ["CUTTER", "CUTTER", "HOLDER", "HOLDER", "HOLDER", "CUTTER"])

    def test_the_bar_lies_towards_the_axis_and_along_z(self):
        tool = standard()
        self.assertTrue(all(p.segment.end.x <= 1e-9 for p in tool.shape.pieces))
        self.assertTrue(all(p.segment.end.z >= -1e-9 for p in tool.shape.pieces))

    def test_a_short_wall_edge_steps_down_to_the_bar_at_a_right_angle(self):
        tool = standard(wall_edge_length_mm=10)
        edge, step = tool.shape.pieces[1].segment, tool.shape.pieces[2]
        self.assertEqual(step.role, ToolSegmentRole.HOLDER)
        self.assertAlmostEqual(step.segment.end.x, -3.5)
        along = (edge.end.x - edge.start.x, edge.end.z - edge.start.z)
        across = (step.segment.end.x - step.segment.start.x, step.segment.end.z - step.segment.start.z)
        self.assertAlmostEqual(along[0] * across[0] + along[1] * across[1], 0, places=6)

    def test_the_info_names_the_tip_angle_and_the_smallest_bore(self):
        text = "\n".join(info_of(standard()))
        self.assertIn("74.0 deg", text)
        self.assertIn("19.5 mm", text)

    def test_values_that_make_no_tool_are_refused(self):
        for values in ({"bar_width_mm": 25}, {"front_width_mm": 0}, {"wall_edge_angle_deg": 30}, {"nose_radius_mm": 30},
                       {"length_mm": 10}, {"end_edge_angle_deg": 135, "wall_edge_angle_deg": 135}):
            with self.subTest(values=values), self.assertRaises(ToolError):
                standard(**values)

    def test_the_stub_values_give_the_old_rectangle(self):
        from wop.ui.model.helpers import STUB_BORING_TOOL

        tool = make_tool("boring", 1, STUB_BORING_TOOL)
        old = block_tool(1, "old", False)
        self.assertEqual(set(corners(tool)), {(round(p.segment.end.x, 3), round(p.segment.end.z, 3)) for p in old.shape.pieces})
        self.assertEqual(sorted(p.role.name for p in tool.shape.pieces), sorted(p.role.name for p in old.shape.pieces))


class NewProjectToolsTests(unittest.TestCase):
    def test_the_example_projects_start_with_the_standard_turning_tool_and_boring_bar(self):
        from wop.ui.model import helpers

        was = helpers.NEW_PROJECT_USES_STUB_TOOLS
        helpers.NEW_PROJECT_USES_STUB_TOOLS = False  # the tests normally start with the stubs
        try:
            self.assertEqual(helpers.new_project().program.tools, ())  # a real new project has no tools (T18)
            tools = helpers.with_starter_tools(helpers.new_project()).program.tools
        finally:
            helpers.NEW_PROJECT_USES_STUB_TOOLS = was
        self.assertEqual([(t.kind, t.name) for t in tools], [("turning", "Turning tool"), ("boring", "Boring bar")])
        self.assertEqual(tools[0], make_tool("turning", 1, TOOL_TYPES.get("turning").default()))
        self.assertEqual(tools[1], make_tool("boring", 2, TOOL_TYPES.get("boring").default()))


class EveryBoringCombinationTests(unittest.TestCase):
    def test_every_combination_that_builds_is_a_valid_outline(self):
        import itertools

        built = 0
        for a, c, r, front, bar, edge in itertools.product((60, 96, 134), (60, 90, 100, 130), (0, 0.3, 2), (8, 19.5, 30), (8, 16), (5, 25)):
            try:
                tool = standard(end_edge_angle_deg=a, wall_edge_angle_deg=c, nose_radius_mm=r, front_width_mm=front, bar_width_mm=bar,
                                wall_edge_length_mm=edge)
            except ToolError:
                continue
            built += 1
            self.assertTrue(is_valid_outline(tool.shape.segments), (a, c, r, front, bar, edge))
        self.assertGreater(built, 100)


if __name__ == "__main__":
    unittest.main()
