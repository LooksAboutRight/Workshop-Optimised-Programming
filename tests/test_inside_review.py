"""Inside machining, found with the review projects (`Temp Data/inside_NN_*.wop.json`): every case that went wrong gets a test
with its project copied to `tests/data/projects`. `path_leaves` sweeps the tool along the moves and says how much material the
plan counts as cut that the path does not touch (small slivers at corners are the nose radius)."""

import unittest
from pathlib import Path

from wop.adapters.project_files import load_project
from wop.core.program_model.operations import LinearMove
from wop.core.program_model.program import plan_program
from wop.core.verify import FindingKind, plain_moves, verify_plan
from wop.ui.stepper import Stepper

PROJECTS = Path(__file__).parent / "data" / "projects"
SLIVER_MM2 = 2.0  # what the nose radius leaves in the corners of a small bore


def planned(name: str):
    program = load_project(PROJECTS / name).program
    return program, plan_program(program)


def path_leaves(program, plan, block_index: int) -> float:
    """Area (mm2) the plan says is cut but the tool body never passes over."""
    stepper = Stepper(program, plan)
    current = plan.blocks[block_index].residual_before
    for frame in (f for f in stepper.frames if f.block_index == block_index):
        current = stepper._after_move(current, frame)
    return current.difference(plan.blocks[block_index].residual_after).area


class InsideReviewTests(unittest.TestCase):
    def test_the_way_back_after_a_step_in_the_wall_does_not_cut_into_the_skin_of_the_wall(self):
        # a bore with a chamfered mouth: the line that ends on the chamfer came back along the contour to the line before and
        # then rapided slantwise outward through the 0.2 mm skin of the wall below it
        program, plan = planned("inside_stepped_bore_chamfered_mouth.wop.json")
        self.assertEqual(verify_plan(program, plan), [])

    def test_a_wall_beyond_the_stock_is_cut_all_the_way_to_the_stock(self):
        # the lines were spaced to the radius of the wall (35) and the last one stopped 1 mm short of the tube (30): a ring stayed
        # that the plan counted as cut. The finishing pass follows the wall as drawn, at feed, out to 35 (beyond the tube, in the air)
        program, plan = planned("inside_wall_beyond_the_stock.wop.json")
        reach = max(move.end.x for operation in plan.blocks[0].operations for move in plain_moves(operation) if isinstance(move, LinearMove))
        self.assertAlmostEqual(reach, 35.0, delta=0.01)
        self.assertLess(path_leaves(program, plan, 0), SLIVER_MM2)

    def test_across_x_the_lines_in_a_cavity_stop_where_the_body_of_the_bar_would_touch_the_mouth(self):
        # a cavity (radius 24, Z -8 to -20) behind a mouth of radius 16, a 10 mm boring bar: the 8 lines in the cavity went out to
        # radius 23.8 and the body cut up to 55 mm2 out of the wall of the mouth; now they are cut only as far as the body reaches
        # (the analytic planner: until the shank, 1.92 mm behind the tip, meets the allowance of the mouth)
        program, plan = planned("inside_cavity_behind_narrow_mouth_across_x.wop.json")
        block_plan = plan.blocks[0]
        feed = block_plan.block.feed_mm_per_rev
        operations = list(block_plan.operations)
        roughing = [i for i, op in enumerate(operations) if isinstance(op, LinearMove) and abs(op.feed_mm_per_rev - feed) < 1e-9]
        in_cavity = [operations[i] for i in roughing if -19.9 < operations[i].end.z < -9.2 and operations[i].end.x > 12]
        self.assertTrue(in_cavity)
        self.assertTrue(all(move.end.x <= 16 - 0.2 + 1.92 + 1e-6 for move in in_cavity))  # the mouth, its allowance, the shank behind the tip
        note = next(m for m in plan.messages if "is not cut: the tool cannot reach it" in m)
        self.assertIn("stays for another tool or block", note)
        findings = verify_plan(program, plan)
        self.assertTrue(findings)  # finishing follows the contour: reported
        self.assertTrue(all(f.operation_index > max(roughing) for f in findings))  # the roughing has none

    def test_the_path_leaves_only_slivers_in_a_normal_stepped_bore(self):
        program, plan = planned("inside_stepped_bore_chamfered_mouth.wop.json")
        self.assertLess(path_leaves(program, plan, 0), SLIVER_MM2)
        self.assertEqual([f for f in verify_plan(program, plan) if f.kind is FindingKind.RAPID_IN_MATERIAL], [])


if __name__ == "__main__":
    unittest.main()
