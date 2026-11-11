"""Step E, the replay of a cut list (wop/core/analytic/replay.py): collisions with the part, of the holder with the material, of rapids, and the material left."""

import unittest
from pathlib import Path

from tests.helpers import planned
from wop.core.geometry import LineSegment, Point

from wop.adapters.project_files import load_project
from wop.core.geometry.chains import loop_area, oriented, polygon_loop
from wop.core.analytic.cut_list import Cut, CutKind, RoughingCuts
from wop.core.analytic.replay import ReplayKind, replay
from wop.core.analytic.tool_outline import tool_loops
from wop.core.geometry.tool_edges import ToolEdge
from wop.core.analytic.wanted_lines import WantedLine
from wop.core.blocks.base import BlockContext
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.constants import CHAIN_SNAP_MM

ROOT = Path(__file__).resolve().parent.parent
TOLERANCE = CHAIN_SNAP_MM


def box(x0, z0, x1, z1):
    return oriented(polygon_loop([Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1)]), True)


def block_tool():
    """A block 2 high (radius) and 4 long (Z), its tip at (0, 0): the front face (z 0) and the bottom (radius 0) cut, the top and the back face
    (z 4) do not."""
    a, b, c, d = Point(0, 0), Point(2, 0), Point(2, 4), Point(0, 4)
    return [(ToolEdge(LineSegment(a, b), True), ToolEdge(LineSegment(b, c), False), ToolEdge(LineSegment(c, d), False), ToolEdge(LineSegment(d, a), True))]


def cut_list(moves, rapid=False, material=None, keep=None, clearance=0.0):
    """A cut list of one cut along the given moves (feed moves, or one rapid), on a layer of material 1.5 thick (radius 0 to 1.5, z -20 to 0)
    above a part far below."""
    source = WantedLine(0, Point(0.5, 0), Point(0.5, -20))
    start = moves[0].start
    listed = Cut(start, start, () if rapid else tuple(moves), source, CutKind.DIP, rapid=tuple(moves) if rapid else ())
    return RoughingCuts((listed,), (), (), (), material=tuple(material or [box(0, -20, 1.5, 0)]), keep=tuple(keep or [box(-10, -30, -5, 10)]), clearance=clearance)


class ReplayTests(unittest.TestCase):
    def test_a_trailing_back_face_in_material_the_same_move_has_cut_is_no_collision(self):
        result = replay(cut_list([LineSegment(Point(0.5, 1), Point(0.5, -22))]), block_tool(), TOLERANCE)
        self.assertEqual(result.findings, ())
        self.assertAlmostEqual(sum(loop_area(loop) for loop in result.residual), 0.5 * 20, places=3)  # the layer under the cut is left

    def test_a_back_face_that_leads_into_the_material_is_a_holder_collision(self):
        result = replay(cut_list([LineSegment(Point(0.5, -26), Point(0.5, -10))]), block_tool(), TOLERANCE)
        kinds = {finding.kind for finding in result.findings}
        self.assertEqual(kinds, {ReplayKind.HOLDER})
        self.assertAlmostEqual(result.findings[0].place.z, -24, delta=0.01)  # where the back face (4 behind the tip) meets the material at z -20

    def test_a_rapid_through_the_material_is_found(self):
        result = replay(cut_list([LineSegment(Point(0.5, 5), Point(0.5, -25))], rapid=True), block_tool(), TOLERANCE)
        self.assertEqual([finding.kind for finding in result.findings], [ReplayKind.RAPID])
        self.assertAlmostEqual(result.findings[0].place.z, 0, delta=0.01)  # the front face meets the material at z 0

    def test_a_move_into_the_part_is_found(self):
        part = [box(-5, -30, 0.3, 10)]  # the part reaches up to radius 0.3: the tip at 0.2 goes 0.1 into it
        result = replay(cut_list([LineSegment(Point(0.2, 1), Point(0.2, -10))], keep=part), block_tool(), TOLERANCE)
        self.assertIn(ReplayKind.PART, {finding.kind for finding in result.findings})

    def test_a_rapid_closer_to_the_material_than_the_clearance_is_found(self):
        # X12: the material reaches radius 1.5, the clearance is 1; the tool bottom 0.7 above it is too close, 0.96 is within the 0.05 of the tests
        close = replay(cut_list([LineSegment(Point(2.2, 5), Point(2.2, -25))], rapid=True, clearance=1.0), block_tool(), TOLERANCE)
        self.assertEqual([finding.kind for finding in close.findings], [ReplayKind.CLOSE])
        kept = replay(cut_list([LineSegment(Point(2.46, 5), Point(2.46, -25))], rapid=True, clearance=1.0), block_tool(), TOLERANCE)
        self.assertEqual(kept.findings, ())

    def test_a_rapid_far_from_everything_is_proven_by_the_boxes_alone(self):
        result = replay(cut_list([LineSegment(Point(10, 5), Point(10, -25))], rapid=True), block_tool(), TOLERANCE)
        self.assertEqual(result.findings, ())
        self.assertEqual((result.moves, result.proven_by_box, result.exact_tests), (1, 2, 0))  # the part and the material: two box tests


class ProjectReplayTests(unittest.TestCase):
    def test_the_cut_lists_of_the_projects_replay_with_no_finding_and_leave_the_same_material(self):
        for name, number in (("tests/data/projects/compensation_test.wop.json", 2), ("examples/reference.wop.json", 5), ("tests/data/projects/contour_bump_pocket.wop.json", 2)):
            with self.subTest(project=name):
                program = load_project(ROOT / name).program
                block_plan = planned(program).blocks[number - 1]
                block = block_plan.block
                self.assertIsInstance(block, ContourTurningBlock)
                context = BlockContext(program.raw_part, program.equipped_tool(block.tool_number), block_plan.residual_before, program.safety, program.contours)
                first = block.roughing_cuts(context)
                result = replay(first, tool_loops(context.tool), TOLERANCE)
                self.assertEqual(result.findings, ())
                self.assertEqual(result.not_worked_out, 0)
                self.assertAlmostEqual(
                    sum(loop_area(loop) for loop in result.residual), sum(loop_area(loop) for loop in first.residual), delta=0.1,
                )  # the moves leave the material the planner left (the retreats and the order of the passes make a few hundredths)


class FinishingClearanceTests(unittest.TestCase):
    def test_the_rapids_to_and_from_the_finishing_pass_keep_the_clearance(self):
        # X12: after the analytic roughing the old planner made the finishing pass with a rapid along the face, through the allowance;
        # the rapids to and from it are planned as the rapids between the cuts: a clearance from the material standing at that moment
        from dataclasses import replace

        from wop.core.analytic.cut_operations import path_of
        from wop.core.analytic.rapids import leg_free as _leg_free
        from wop.core.geometry.penetration import RegionIndex
        from wop.core.geometry.removal import cut
        from wop.core.geometry.tool_edges import grown_loops
        from wop.core.constants import RAPID_CLEARANCE_TOLERANCE_MM
        from wop.core.program_model.operations import ArcMove, LinearMove, Rapid

        program = load_project(ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").program
        block_plan = planned(program).blocks[1]
        block = replace(block_plan.block, finish_pass=True)
        context = BlockContext(program.raw_part, program.equipped_tool(block.tool_number), block_plan.residual_before, program.safety, program.contours)
        rough, _notes, first = block._analytic_roughing(context)
        operations = block.generate(context).operations
        begins = next(i for i in range(len(operations)) if tuple(operations[i:i + len(rough)]) == tuple(rough))
        finishing = list(operations[begins + len(rough):-1])
        moving = [i for i, op in enumerate(finishing) if isinstance(op, (LinearMove, ArcMove))]
        tool = tool_loops(context.tool)
        grown = grown_loops(tool, program.safety.clearance_mm - RAPID_CLEARANCE_TOLERANCE_MM)
        before = RegionIndex(list(first.residual))
        here = rough[-1].end
        for op in finishing[:moving[0]]:
            if isinstance(op, Rapid):
                self.assertTrue(_leg_free(here, op.end, grown, before, TOLERANCE), f"approach {here} -> {op.end}")
            here = op.end
        body = finishing[moving[0]:moving[-1] + 1]
        after = RegionIndex(cut(list(first.residual), tool, path_of(body, here), TOLERANCE)[0])
        here = body[-1].end
        for op in finishing[moving[-1] + 1:]:
            if isinstance(op, Rapid):
                self.assertTrue(_leg_free(here, op.end, grown, after, TOLERANCE), f"way out {here} -> {op.end}")
            here = op.end

if __name__ == "__main__":
    unittest.main()
