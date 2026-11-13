"""The reference point of a tool (the touch-off point) and the path of the nose (Python 3.11 and later)."""

import math
import unittest
from dataclasses import replace

from wop.core.constants import TIP_POINT
from wop.core.contour import Contour, ContourDefinition, LineStep, NamedPoint
from wop.core.contour_solver import solve_contour
from wop.core.geometry import LineSegment, Point, segments_to_polyline
from wop.core.nose_compensation import reference_path
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool_presets import block_tool, drill_tool, groove_tool, thread_tool
from wop.core.tooling.tool_reference import default_tip, nose_circle, tip_is_drawn, tip_of, with_tip_at_origin
from wop.core.tool_types import TOOL_TYPES, make_tool

from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.turning_common import TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.program_model.stock import stock_region


def holder():
    return make_tool("holder", 1, TOOL_TYPES.get("holder").default())  # PCLNR, CNMG 120408: 80 degrees, nose 0.8


def bar():
    return make_tool("boring_bar", 1, TOOL_TYPES.get("boring_bar").default())


def distance_to_line(point, line):
    dx, dz = line.end.x - line.start.x, line.end.z - line.start.z
    return abs((point.x - line.start.x) * dz - (point.z - line.start.z) * dx) / math.hypot(dx, dz)


from wop.core.tooling.tool_reference import nose_circle


class ForwardLeaningEdgeTests(unittest.TestCase):
    """A side edge angle below 90 degrees leans over the work: the box corner would be at the far end of the edge, in the air."""

    def tool(self, angle, radius, **values):
        from wop.core.tool_types.turning import TurningToolType

        kind = TurningToolType()
        return make_tool("turning", 1, replace(kind.default(), side_edge_angle_deg=angle, nose_radius_mm=radius, front_edge_angle_deg=110, **values))

    def test_the_reference_point_is_under_the_nose_radius(self):
        for angle, radius in ((80, 2), (80, 0), (60, 0.5)):
            with self.subTest(angle=angle, radius=radius):
                tool = self.tool(angle, radius)
                tip = default_tip(tool.shape)
                cutter = segments_to_polyline(tool.shape.cutter_segments, 0.001)
                lowest_x = min(p.x for p in cutter)
                self.assertAlmostEqual(tip.x, lowest_x, delta=1e-3)
                self.assertLess(min(abs(p.x - tip.x) + abs(p.z - tip.z) for p in cutter), 0.02)  # a point of the tool
                self.assertGreater(tip.z - min(p.z for p in cutter), 0)  # the cutting edge reaches further to the chuck than the tip

    def test_a_square_or_backward_leaning_tool_keeps_the_box_corner(self):
        for angle in (90, 96, 100):
            tool = self.tool(angle, 0.3)
            cutter = segments_to_polyline(tool.shape.cutter_segments, 0.001)
            tip = default_tip(tool.shape)
            self.assertAlmostEqual(tip.z, min(p.z for p in cutter), delta=1e-3)

    def test_the_left_hand_tool_is_the_mirror_image(self):
        from wop.core.tool_types.turning import ToolHand

        right, left = default_tip(self.tool(80, 2).shape), default_tip(self.tool(80, 2, hand=ToolHand.LEFT).shape)
        self.assertAlmostEqual(left.x, right.x, places=6)
        self.assertAlmostEqual(left.z, -right.z, places=6)

    def test_a_wall_edge_that_leans_towards_the_wall_moves_x_under_the_nose(self):
        d = TOOL_TYPES.get("boring").default()
        for angle in (100, 90):  # clears the wall or parallel: the box corner stays
            tool = make_tool("boring", 1, replace(d, wall_edge_angle_deg=angle))
            cutter = segments_to_polyline(tool.shape.cutter_segments, 0.001)
            self.assertAlmostEqual(default_tip(tool.shape).x, max(p.x for p in cutter), delta=1e-3)
        tool = make_tool("boring", 1, replace(d, wall_edge_angle_deg=80))
        cutter = segments_to_polyline(tool.shape.cutter_segments, 0.001)
        tip = default_tip(tool.shape)
        self.assertAlmostEqual(tip.z, min(p.z for p in cutter), delta=1e-3)  # Z stays the lowest Z
        self.assertLess(tip.x, max(p.x for p in cutter) - 1)  # X is not the far end of the wall edge
        self.assertLess(min(abs(p.x - tip.x) + abs(p.z - tip.z) for p in cutter), 0.02)  # a point of the tool

    def test_two_edges_that_lean_forward_give_the_nearest_point_of_the_cutting_edges(self):
        tool = make_tool("turning", 1, replace(TOOL_TYPES.get("turning").default(), side_edge_angle_deg=80, front_edge_angle_deg=80))
        cutter = segments_to_polyline(tool.shape.cutter_segments, 0.001)
        tip = default_tip(tool.shape)
        self.assertLess(min(abs(p.x - tip.x) + abs(p.z - tip.z) for p in cutter), 0.02)

    def test_with_the_tip_at_the_origin_the_nose_circle_is_found(self):
        radius, centre = nose_circle(with_tip_at_origin(self.tool(80, 2)))
        self.assertAlmostEqual(radius, 2)
        self.assertAlmostEqual(centre.x, 2, places=3)  # the nose circle is a radius above the tip


class ReferencePointTests(unittest.TestCase):
    def test_a_90_degree_starter_tool_keeps_its_corner(self):
        for tool in (block_tool(1, "outside"), block_tool(1, "boring", False)):
            self.assertTrue(default_tip(tool.shape).is_close(Point(0, 0)))

    def test_groove_thread_and_drill_presets_keep_their_origin(self):
        for tool in (groove_tool(1, "g"), groove_tool(1, "g", body_towards_larger_x=False),
                     thread_tool(1, "t"), thread_tool(1, "t", False), drill_tool(1, "d")):
            self.assertTrue(default_tip(tool.shape).is_close(Point(0, 0)), tool.name)

    def test_an_insert_holder_is_touched_off_at_the_corner_of_the_box_round_its_cutting_edges(self):
        tool = with_tip_at_origin(holder())
        cutter = segments_to_polyline(tool.shape.cutter_segments)  # the arc counts with all its points
        self.assertAlmostEqual(min(p.x for p in cutter), 0, delta=1e-3)  # nothing reaches further to the axis ...
        self.assertAlmostEqual(min(p.z for p in cutter), 0, delta=1e-3)  # ... or to the chuck than the reference point

    def test_the_nose_centre_is_a_nose_radius_away_from_the_reference_point_in_both_directions(self):
        radius, centre = nose_circle(with_tip_at_origin(holder()))
        self.assertAlmostEqual(radius, 0.8, places=6)
        self.assertAlmostEqual(centre.x, radius, places=3)
        self.assertAlmostEqual(centre.z, radius, places=3)

    def test_a_boring_bar_is_touched_off_at_its_highest_x(self):
        radius, centre = nose_circle(with_tip_at_origin(bar()))
        self.assertAlmostEqual(centre.x, -radius, places=3)  # the nose lies towards the axis of the reference point
        self.assertAlmostEqual(centre.z, radius, places=3)

    def test_a_drawn_named_point_replaces_the_computed_one(self):
        tool = replace(holder(), points=(NamedPoint(TIP_POINT, 1.5, 2.5),))
        self.assertTrue(tip_is_drawn(tool))
        self.assertTrue(tip_of(tool).is_close(Point(1.5, 2.5)))
        moved = with_tip_at_origin(tool)
        self.assertTrue(tip_of(moved).is_close(Point(0, 0)))
        before = tool.shape.pieces[0].segment.start
        self.assertTrue(moved.shape.pieces[0].segment.start.is_close(Point(before.x - 1.5, before.z - 2.5)))

    def test_named_points_move_with_the_tool(self):
        tool = replace(holder(), points=(NamedPoint("mark", 3, 4),))
        tip = default_tip(tool.shape)
        moved = next(p for p in with_tip_at_origin(tool).points if p.name == "mark")
        self.assertAlmostEqual(moved.x, 3 - tip.x, places=9)
        self.assertAlmostEqual(moved.z, 4 - tip.z, places=9)


class ReferencePathTests(unittest.TestCase):
    def path_of(self, *points):
        steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
        return solve_contour(ContourDefinition(Point(*points[0]), steps))

    def test_a_sharp_tool_gets_the_contour_unchanged(self):
        path = self.path_of((10, 0), (10, -20))
        self.assertEqual([s for _i, s in reference_path(path, block_tool(1, "a"), True)], path)

    def test_on_a_cylinder_and_a_face_the_reference_point_follows_the_contour(self):
        path = self.path_of((10, 0), (10, -20), (14, -20))
        found = [s for _i, s in reference_path(path, with_tip_at_origin(holder()), True)]
        self.assertAlmostEqual(found[0].start.x, 10, delta=1e-3)  # on the cylinder the reference point is on the contour
        self.assertTrue(found[0].end.is_close(Point(10, -20), 1e-3))  # in the corner it reaches the corner of the box

    def test_on_a_slope_the_nose_circle_touches_the_contour(self):
        tool = with_tip_at_origin(holder())
        radius, centre = nose_circle(tool)
        path = self.path_of((10, 0), (14, -10))  # a slope
        for _index, piece in reference_path(path, tool, True):
            if isinstance(piece, LineSegment):
                middle = piece.point_at(0.5)
                circle_centre = Point(middle.x + centre.x, middle.z + centre.z)
                self.assertAlmostEqual(distance_to_line(circle_centre, path[0]), radius, places=6)

    def test_inside_the_nose_circle_is_on_the_other_side(self):
        tool = with_tip_at_origin(bar())
        radius, centre = nose_circle(tool)
        path = self.path_of((10, 0), (6, -10))
        piece = next(s for _i, s in reference_path(path, tool, False) if isinstance(s, LineSegment))
        middle = piece.point_at(0.5)
        circle_centre = Point(middle.x + centre.x, middle.z + centre.z)
        self.assertAlmostEqual(distance_to_line(circle_centre, path[0]), radius, places=6)


class NoseBlockTests(unittest.TestCase):
    SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)

    def run_block(self, *points):
        steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
        definition = ContourDefinition(Point(*points[0]), steps)
        shape = Contour("c", "test", tuple(solve_contour(definition)), definition)
        raw = RawPart("steel", 30, 60)
        block = ContourTurningBlock(
            block_id="c1", tool_number=1, spindle=self.SPINDLE, contour_id="c", side=TurningSide.OUTSIDE,
            feed_mm_per_rev=0.25, depth_of_cut_mm=1, finish_allowance_mm=0.2,
        )
        context = BlockContext(raw, with_tip_at_origin(holder()), stock_region(raw),
                               Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1), contours=(shape,))
        return block.generate(context)

    def test_a_plain_cylinder_with_an_insert_leaves_nothing_uncut(self):
        result = self.run_block((12, 0), (12, -30))
        self.assertEqual(result.messages, ())  # the corner the nose cannot reach is too small for a note ...
        radius = nose_circle(with_tip_at_origin(holder()))[0]
        self.assertAlmostEqual(result.removed.area, (15 - 12) * 30 - radius ** 2 * (1 - math.pi / 4), delta=0.01)  # ... but it stands: the shoulder keeps its corner

    def test_a_slope_with_an_insert_leaves_nothing_uncut(self):
        result = self.run_block((8, 0), (8, -10), (14, -16), (14, -30))
        self.assertEqual(result.messages, ())


if __name__ == "__main__":
    unittest.main()
