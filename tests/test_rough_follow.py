"""Roughing: the back angle of a tool, the plunge feed and the plunge depth of cut, the fields of the block (the generator `generate` is
used by other test modules)."""

import math
import unittest
from dataclasses import replace
from functools import cache
from pathlib import Path

from wop.core.contour import Contour, ContourDefinition, LineStep
from wop.core.contour_solver import solve_contour
from wop.core.geometry import Point, segments_to_polyline
from wop.core.nose_compensation import reference_path
from wop.core.program_model.operations import ArcMove, LinearMove, SpindleMode, SpindleSetting
from wop.core.files.project_io import project_from_json
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool_back_angle import back_angle_deg, back_direction
from wop.core.tooling.tool_presets import block_tool, groove_tool, thread_tool
from wop.core.tooling.tool_reference import with_tip_at_origin
from wop.core.tool_types import TOOL_TYPES, make_tool

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.turning_common import PassDirection, TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.program_model.stock import stock_region

PROJECTS = Path(__file__).parent / "data" / "projects"
SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
FEED = 0.25
PLUNGE_FEED = 0.1


def path_of(*points):
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    return list(solve_contour(ContourDefinition(Point(*points[0]), steps)))


@cache
def holder_cnmg():
    return with_tip_at_origin(make_tool("holder", 1, TOOL_TYPES.get("holder").default()))  # back angle 5 degrees


@cache
def holder_vnmg():
    program = project_from_json((PROJECTS / "contour_funnel.wop.json").read_text(encoding="utf-8")).program
    return with_tip_at_origin(replace(program.tool(3), number=1))  # VNMG16_95: back angle 50 degrees


class BackAngleTests(unittest.TestCase):
    def test_inserts_from_their_entries(self):
        self.assertAlmostEqual(back_angle_deg(holder_cnmg()), 5, places=6)
        self.assertAlmostEqual(back_angle_deg(holder_vnmg()), 50, places=6)

    def test_a_boring_bar_with_the_same_insert_has_the_same_angle(self):
        bar = with_tip_at_origin(make_tool("boring_bar", 1, TOOL_TYPES.get("boring_bar").default()))
        self.assertAlmostEqual(back_angle_deg(bar, free_up=-1), 5, places=6)

    def test_drawn_and_preset_tools_from_their_cutting_edges(self):
        self.assertAlmostEqual(back_angle_deg(block_tool(1, "plain")), 0, places=6)
        self.assertAlmostEqual(back_angle_deg(groove_tool(1, "groove")), 0, places=6)
        self.assertAlmostEqual(back_angle_deg(thread_tool(1, "thread")), 60, delta=0.1)

    def test_the_body_side_of_the_tool_says_which_way_is_back(self):
        self.assertEqual(back_direction(block_tool(1, "plain")), 1)

    def test_the_side_the_tool_is_not_on_has_no_back_edge(self):
        self.assertIsNone(back_angle_deg(holder_cnmg(), free_up=-1))  # an outside tool is not a boring tool


class ReferencePathAllowanceTests(unittest.TestCase):
    def test_a_sharp_tool_with_an_allowance_moves_the_contour_by_it(self):
        pieces = reference_path(path_of((10, 0), (10, -20)), block_tool(1, "plain"), True, 0.5)
        self.assertAlmostEqual(pieces[0][1].start.x, 10.5, places=6)


def block(**overrides):
    values = dict(
        block_id="c1", tool_number=1, spindle=SPINDLE, contour_id="c", side=TurningSide.OUTSIDE,
        feed_mm_per_rev=FEED, depth_of_cut_mm=2, finish_allowance_mm=0.2, plunge_feed_mm_per_rev=PLUNGE_FEED,
    )
    values.update(overrides)
    return ContourTurningBlock(**values)


def generate(points, tool, raw_part=None, **overrides):
    """The block planned on the contour through the points."""
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    definition = ContourDefinition(Point(*points[0]), steps)
    shape = Contour("c", "test", tuple(solve_contour(definition)), definition)
    raw_part = raw_part or RawPart("steel", 40, 60)
    context = BlockContext(raw_part, tool, stock_region(raw_part), Safety(30, 10, 1), contours=(shape,))
    return block(**overrides).generate(context), shape


def line_moves(operations, feed=FEED):
    """The roughing lines along Z: a feed move that changes only Z."""
    return [
        op for before, op in zip(operations, operations[1:])
        if isinstance(op, LinearMove) and op.feed_mm_per_rev == feed and hasattr(before, "end") and abs(op.end.x - before.end.x) < 1e-9
    ]


class FollowAtTheEndOfALineTests(unittest.TestCase):
    SLOPE = [(8, 0), (8, -10), (14, -16), (14, -30)]

    def test_the_slope_is_touched_along_all_its_height(self):
        # the follow moves of all the lines together cover the contour from the lowest line to the top
        result, _shape = generate(self.SLOPE, holder_cnmg(), finish_pass=False)
        operations = result.operations
        covered = []
        for before, op in zip(operations, operations[1:]):
            if isinstance(op, (LinearMove, ArcMove)) and op.feed_mm_per_rev == FEED and hasattr(before, "end"):
                covered.append((min(before.end.x, op.end.x), max(before.end.x, op.end.x)))
        spans = sorted(span for span in covered if span[1] - span[0] > 1e-6)
        reach = spans[0][0]
        for low, high in spans:
            self.assertLessEqual(low, reach + 1e-6)  # no gap between what one move reaches and the next starts at
            reach = max(reach, high)
        self.assertGreaterEqual(reach, 14.2 - 1e-6)  # up to the top of the slope plus the allowance

    def test_the_same_across_x(self):
        result, _shape = generate(self.SLOPE, holder_cnmg(), finish_pass=False, pass_direction=PassDirection.ALONG_X)
        moves = [op for op in result.operations if isinstance(op, LinearMove) and op.feed_mm_per_rev in (FEED, PLUNGE_FEED)]
        self.assertTrue(any(abs(move.end.x - 8.2) < 1e-6 for move in moves))  # the cylinder before the slope is followed too

    def test_a_cylinder_and_a_wall_still_leave_nothing_to_find(self):
        result, _shape = generate([(8, 0), (8, -10), (12, -10), (12, -30)], holder_cnmg(), finish_pass=False)
        self.assertEqual(result.messages, ())


class PlungeIntoAPocketTests(unittest.TestCase):
    # a groove 6 wide and 4 deep whose back wall is a ramp of 20 degrees (it rises towards the front)
    POCKET = [(14, 0), (14, -10), (10, -10 - 4 / math.tan(math.radians(20))), (10, -27), (14, -27), (14, -40)]
    RAW = RawPart("steel", 40, 60)

    def pocket_lines(self, result):
        return [op for op in line_moves(result.operations) if -27 < op.end.z < -10 and op.end.x < 13.5]

    def test_a_tool_that_leaves_enough_angle_goes_in_with_the_plunge_feed(self):
        result, _shape = generate(self.POCKET, holder_vnmg(), finish_pass=False, depth_of_cut_mm=1.5)
        plunges = [op for op in result.operations if isinstance(op, LinearMove) and op.feed_mm_per_rev == PLUNGE_FEED]
        self.assertTrue(plunges)  # the way into the pocket

    def test_one_plunge_goes_no_deeper_than_the_plunge_depth_of_cut(self):
        result, _shape = generate(self.POCKET, holder_vnmg(), finish_pass=False, depth_of_cut_mm=4, plunge_depth_of_cut_mm=1)
        inside = sorted({round(op.end.x, 3) for op in self.pocket_lines(result)}, reverse=True)
        self.assertGreater(len(inside), 3)  # four millimetres deep in steps of one
        for high, low in zip(inside, inside[1:]):
            self.assertLessEqual(high - low, 1 + 1e-6)

    def test_without_a_plunge_depth_the_depth_of_cut_counts(self):
        result, _shape = generate(self.POCKET, holder_vnmg(), finish_pass=False, depth_of_cut_mm=4)
        inside = sorted({round(op.end.x, 3) for op in self.pocket_lines(result)}, reverse=True)
        for high, low in zip(inside, inside[1:]):
            self.assertLessEqual(high - low, 4 + 1e-6)


class SteepWallTests(unittest.TestCase):
    """A wall steeper than the back of the tool: the lines in the pocket start where the tool body clears the part and its allowance
    (what it cannot reach stays, a note says so)."""

    STEEP = [(14, 0), (14, -10), (10, -10 - 4 / math.tan(math.radians(60))), (10, -27), (14, -27), (14, -40)]
    RAW = RawPart("steel", 40, 60)

    def part_with_allowance(self, allowance):
        from wop.core.geometry.region import Region
        points = segments_to_polyline(path_of(*self.STEEP))
        return Region.from_points(points + [Point(0, points[-1].z), Point(0, points[0].z)]).offset(allowance)

    def plunge_ends(self, result):
        """The positions where the lines in the pocket start: the end of a plunge move (at the plunge feed, straight in)."""
        operations = result.operations
        return [
            op.end for before, op in zip(operations, operations[1:])
            if isinstance(op, LinearMove) and op.feed_mm_per_rev == PLUNGE_FEED and hasattr(before, "end")
            and abs(op.end.z - before.end.z) < 1e-6 and op.end.x < before.end.x and op.end.x < 13.5
        ]

    def test_the_tool_body_never_touches_the_part_and_its_allowance_at_the_start_of_a_line(self):
        from wop.core.reach import placed_shrunk, prepare_tool
        result, _shape = generate(self.STEEP, holder_vnmg(), self.RAW, finish_pass=False, depth_of_cut_mm=1.5)
        ring = self.part_with_allowance(0.2).shrunk_for_collision()
        prepared = prepare_tool(holder_vnmg())
        for end in self.plunge_ends(result):
            self.assertFalse(placed_shrunk(prepared, end).overlaps(ring), f"the tool touches the part at {end}")

class FieldsTests(unittest.TestCase):
    def test_the_finishing_pass_can_be_left_out(self):
        result, _shape = generate([(8, 0), (8, -10), (12, -10), (12, -30)], holder_cnmg(), finish_pass=False, finish_feed_mm_per_rev=0.05)
        self.assertFalse([op for op in result.operations if isinstance(op, LinearMove) and op.feed_mm_per_rev == 0.05])

    def test_bad_values_are_refused(self):
        for overrides in ({"plunge_feed_mm_per_rev": 0}, {"plunge_depth_of_cut_mm": -1}, {"min_free_angle_deg": 90},
                          {"min_free_angle_deg": -1}, {"finish_spindle_value": 0}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(BlockError):
                    block(**overrides)

    def test_a_new_block_has_the_agreed_defaults(self):
        new = ContourTurningBlock.example("c1", 1, SPINDLE)
        self.assertEqual(new.min_free_angle_deg, 5)
        self.assertEqual(new.plunge_feed_mm_per_rev, new.feed_mm_per_rev / 2)
        self.assertEqual(new.plunge_depth_of_cut_mm, new.depth_of_cut_mm / 2)
        self.assertEqual(new.finish_spindle_value, new.spindle.value)
        self.assertTrue(new.finish_pass)


class FollowerFieldsTests(unittest.TestCase):
    """The plunge feed, the plunge depth of cut and the finishing speed follow the feed, the depth of cut and the speed
    until the user types a value of his own."""

    def setUp(self):
        from wop.ui.app_model import AppModel
        self.model = AppModel()
        self.index = self.model.add_block("turning_contour")
        self.owner = self.model.block_owner(self.index)

    def block(self):
        return self.model.blocks[self.index]

    def edit(self, **changes):
        self.model.replace_block(self.index, replace(self.block(), **changes))
        for name in changes:
            self.model.set_touched(self.owner, (name,))  # as the window does, right after the edit

    def test_a_new_block_shows_real_values_not_empty_fields(self):
        block = self.block()
        self.assertEqual(block.plunge_feed_mm_per_rev, block.feed_mm_per_rev / 2)
        self.assertEqual(block.plunge_depth_of_cut_mm, block.depth_of_cut_mm / 2)
        self.assertEqual(block.finish_spindle_value, block.spindle.value)

    def test_they_follow_an_edit_of_the_feed_and_the_depth_of_cut(self):
        self.edit(feed_mm_per_rev=0.3, depth_of_cut_mm=3)
        self.assertAlmostEqual(self.block().plunge_feed_mm_per_rev, 0.15)
        self.assertAlmostEqual(self.block().plunge_depth_of_cut_mm, 1.5)

    def test_a_value_the_user_typed_stays(self):
        self.edit(plunge_feed_mm_per_rev=0.07)
        self.assertEqual(self.block().plunge_feed_mm_per_rev, 0.07)  # the edit itself is not overwritten
        self.edit(feed_mm_per_rev=0.4)
        self.assertEqual(self.block().plunge_feed_mm_per_rev, 0.07)  # and it does not follow the feed any more
        self.assertAlmostEqual(self.block().plunge_depth_of_cut_mm, self.block().depth_of_cut_mm / 2)  # the others still do

    def test_the_finishing_speed_follows_the_spindle_speed(self):
        self.edit(spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 1500))
        self.assertEqual(self.block().finish_spindle_value, 1500)


if __name__ == "__main__":
    unittest.main()
