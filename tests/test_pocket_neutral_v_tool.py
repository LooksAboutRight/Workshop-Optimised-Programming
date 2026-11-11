"""A pocket roughed with a symmetric 35 degree V tool (the user's project 'turning contur_2'): the tool has no hand, the lines reach
the bottom of the pocket (the wedge beside the steep wall stays), and the checker does not call the wedge the finished part."""

import unittest
from pathlib import Path

from tests.helpers import planned
from wop.adapters.project_files import load_project
from wop.core.tooling.tool_back_angle import back_direction
from wop.core.verify import plain_moves, verify_plan

PROJECT = Path(__file__).parent / "data" / "projects" / "turning_pocket_neutral_v_tool.wop.json"
POCKET_BOTTOM_RADIUS_MM = 17.334535  # the contour at the bottom of the pocket
ALLOWANCE_STEPS_MM = 1.0  # the lowest line may stop about one depth of cut above the bottom


class PocketWithANeutralVToolTests(unittest.TestCase):
    def setUp(self):
        self.program = load_project(PROJECT).program
        self.plan = planned(self.program)
        self.block_plan = self.plan.blocks[1]

    def test_the_symmetric_tool_counts_as_right_hand(self):
        tool = self.program.equipped_tool(self.block_plan.block.tool_number)
        self.assertEqual(back_direction(tool), 1)

    def test_the_lowest_line_comes_close_to_the_bottom_of_the_pocket(self):
        moves = [move for operation in self.block_plan.operations for move in plain_moves(operation) if hasattr(move, "end")]
        deepest = min(move.end.x for move in moves if move.end.z < -20)
        self.assertLess(deepest, POCKET_BOTTOM_RADIUS_MM + self.block_plan.block.finish_allowance_mm + ALLOWANCE_STEPS_MM)

    def test_the_wedge_that_stays_is_not_a_gouge(self):
        kinds = {finding.kind.name for finding in verify_plan(self.program, self.plan) if finding.block_index == 1}
        self.assertNotIn("GOUGE", kinds)


if __name__ == "__main__":
    unittest.main()
