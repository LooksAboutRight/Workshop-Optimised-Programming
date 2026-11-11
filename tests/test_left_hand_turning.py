"""A left-hand tool (its body towards smaller Z) works from the chuck side towards the front: the block is planned as the mirror
image and turned back (`wop/core/analytic/frame.py`). Project: the user's pocket project with a right-hand tool in block 2
and a left-hand tool in block 3 (`turning_pocket_neutral_v_tool`)."""

import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import planned
from wop.adapters.project_files import load_project
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid
from wop.core.tooling.tool_back_angle import back_direction
from wop.core.verify import verify_plan

PROJECT = Path(__file__).parent / "data" / "projects" / "turning_pocket_neutral_v_tool.wop.json"
LEFT_HAND_BLOCK = 2  # index in the project


def feed_moves(block_plan):
    moves, previous = [], None
    for operation in block_plan.operations:
        if isinstance(operation, LinearMove) and previous is not None:
            moves.append((previous, operation.end))
        end = getattr(operation, "end", None)
        if end is not None:
            previous = end
    return moves


class LeftHandToolTests(unittest.TestCase):
    def setUp(self):
        self.program = load_project(PROJECT).program
        blocks = list(self.program.blocks)
        blocks[1], blocks[2] = blocks[2], blocks[1]  # the left-hand tool first: it meets all the stock
        self.swapped = replace(self.program, blocks=tuple(blocks))

    def test_the_tool_of_the_block_is_left_hand(self):
        tool = self.program.equipped_tool(self.program.blocks[LEFT_HAND_BLOCK].tool_number)
        self.assertEqual(back_direction(tool), -1)

    def test_the_long_lines_run_from_the_chuck_side_towards_the_front(self):
        plan = planned(self.swapped)
        long_lines = [(a, b) for a, b in feed_moves(plan.blocks[1]) if abs(a.z - b.z) > 10 and abs(a.x - b.x) < 0.01]
        self.assertTrue(long_lines)
        self.assertTrue(all(b.z > a.z for a, b in long_lines))

    def test_with_all_the_stock_in_front_of_it_the_tool_does_not_collide(self):
        # the user's decision (2026-10-22): the replay of the analytic planner is trusted over the old checker. The old checker calls every
        # plunge of this tool (a flat side face that does not cut, flush with the wall of the groove the plunge cuts) holder in material;
        # the replay finds the face only touching
        from wop.core.analytic.replay import replay
        from wop.core.analytic.tool_outline import tool_loops
        from wop.core.blocks.base import BlockContext
        from wop.core.constants import CHAIN_SNAP_MM

        plan = planned(self.swapped)
        kinds = {finding.kind.name for finding in verify_plan(self.swapped, plan) if finding.block_index == 1}
        self.assertFalse(kinds & {"GOUGE", "RAPID_IN_MATERIAL"}, kinds)
        block_plan = plan.blocks[1]
        program = self.swapped
        context = BlockContext(program.raw_part, program.equipped_tool(block_plan.block.tool_number), block_plan.residual_before, program.safety, program.contours)
        first = block_plan.block.roughing_cuts(context)
        self.assertEqual(replay(first, tool_loops(context.tool), CHAIN_SNAP_MM).findings, ())

    def test_the_part_stays_whole(self):
        plan = planned(self.swapped)
        block_plan = plan.blocks[1]
        from tests.test_roughing_keeps_off_the_part import keep_of

        keep = keep_of(self.swapped, block_plan.block, block_plan.residual_before)
        self.assertLess(block_plan.residual_after.intersection(keep).area, keep.area + 0.01)
        self.assertGreater(keep.difference(block_plan.residual_after).area, -0.01)
        self.assertLess(keep.difference(block_plan.residual_after).area, 0.01)

    def test_the_block_ends_at_the_safe_z_in_front_not_at_the_chuck(self):
        plan = planned(self.swapped)
        last = [o for o in plan.blocks[1].operations if getattr(o, "end", None) is not None][-1]
        self.assertGreater(last.end.z, self.program.raw_part.front_z_mm - 0.01)

    def test_the_bottom_line_of_the_pocket_follows_the_contour_up_to_the_line_before(self):
        plan = planned(self.program)
        moves = feed_moves(plan.blocks[LEFT_HAND_BLOCK])
        bottom = [(a, b) for a, b in moves if abs(a.x - b.x) < 0.01 and abs(a.x - 17.4845) < 0.01 and abs(a.z - b.z) > 1]
        self.assertTrue(bottom)
        operations = list(plan.blocks[LEFT_HAND_BLOCK].operations)
        index = max(i for i, o in enumerate(operations) if isinstance(o, LinearMove) and abs(o.end.x - 17.4845) < 0.01)
        follow = operations[index + 1]
        self.assertIsInstance(follow, ArcMove)  # up the corner radius, not a rapid straight back
        self.assertGreater(follow.end.x, 18.4)  # to the radius of the line before (18.46)

    def test_after_the_last_cut_of_the_finishing_pass_the_tool_leaves_straight_out(self):
        block = replace(self.program.blocks[LEFT_HAND_BLOCK], finish_pass=True)
        program = replace(self.program, blocks=(*self.program.blocks[:LEFT_HAND_BLOCK], block))
        operations = planned(program).blocks[LEFT_HAND_BLOCK].operations
        last_cut = max(index for index, operation in enumerate(operations) if isinstance(operation, (LinearMove, ArcMove)))
        # X12: the last move of the finishing pass is followed by a feed move straight away from the material (one clearance), then the rapid
        away = operations[last_cut]
        before = next(o for o in reversed(operations[:last_cut]) if getattr(o, "end", None) is not None)
        self.assertTrue(abs(away.end.z - before.end.z) < 0.001 or abs(away.end.x - before.end.x) < 0.001)  # straight along X or along Z
        after = [operation for operation in operations[last_cut + 1:] if isinstance(operation, Rapid)]
        self.assertEqual(len(after), 1)  # then to the safe point


class AcrossXTests(unittest.TestCase):
    """A left-hand tool across X goes through the frame like every case (inside, then the hand, then the swap): its planes run from the chuck
    side towards the front, with the body over what is cut already; the lane over the material lies on the free side (the front and the
    outside), never towards the chuck. In the left-hand rest block of the example the air is in front, so little can be reached: the rules
    leave it with a note (the user looked at it, 2026-10-25: fine, perhaps one small line more could be taken: open issues)."""

    def test_the_rest_block_across_x_runs_from_the_chuck_side_and_stays_clear_of_the_chuck(self):
        from wop.core.blocks.turning_common import PassDirection

        program = load_project(Path(__file__).parent.parent / "examples" / "left_hand_rest_machining.wop.json").program
        blocks = list(program.blocks)
        blocks[2] = replace(blocks[2], pass_direction=PassDirection.ALONG_X)  # block 3: the rest with the left-hand tool
        program = replace(program, blocks=tuple(blocks))
        plan = planned(program)
        result = plan.blocks[2].result
        self.assertIn("is not cut: the tool cannot reach it", " ".join(result.messages))
        self.assertEqual(verify_plan(program, plan), [])
        ends = [operation.end for operation in result.operations if hasattr(operation, "end")]
        self.assertGreater(min(end.z for end in ends), program.raw_part.clamp_z_mm)  # nothing goes past the chuck end of the bar
        planes, here = [], None
        for operation in result.operations:  # the planes: feed moves across X
            end = getattr(operation, "end", None)
            if isinstance(operation, LinearMove) and here is not None and abs(end.z - here.z) < 1e-6 and abs(end.x - here.x) > 1:
                planes.append(end.z)
            if end is not None:
                here = end
        self.assertTrue(planes)
        self.assertLess(planes[0], planes[-1])  # from the chuck side towards the front


class ExampleProjectTests(unittest.TestCase):
    """`examples/left_hand_rest_machining.wop.json`: a right-hand and a left-hand tool on one pocket, each with its own finishing contour."""

    def setUp(self):
        self.program = load_project(Path(__file__).parent.parent / "examples" / "left_hand_rest_machining.wop.json").program
        self.plan = planned(self.program)

    def test_every_block_is_planned_and_the_checker_finds_nothing(self):
        self.assertEqual(self.plan.left_out, ())
        self.assertEqual(verify_plan(self.program, self.plan), [])

    def test_the_finishing_blocks_only_finish(self):
        for number in (3, 4):  # blocks 4 and 5
            feed = {operation.feed_mm_per_rev for operation in self.plan.blocks[number].operations if isinstance(operation, (LinearMove, ArcMove))}
            self.assertEqual(feed, {self.program.blocks[number].finish_feed_mm_per_rev}, f"block {number + 1} roughs")


if __name__ == "__main__":
    unittest.main()
