"""A tool on the far side of the axis (back boring): the left-hand boring bar works on the far wall of a bore. The block is planned with the tool
turned over the axis and the moves are turned back, so the far side gives exactly the mirror image of the near side: the same material is
removed, the same findings are made, the machine moves at negative X."""

import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from wop.adapters.project_files import load_project
from wop.core.analytic.far_side import body_side, works_on_far_side
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid
from wop.core.program_model.program import plan_program
from wop.core.tool_types import TOOL_TYPES, make_tool
from wop.core.tool_types.hand import ToolHand
from wop.core.tooling.tool_reference import with_tip_at_origin
from wop.core.verify import verify_plan
from wop.ui.stepper import Stepper

PROJECT = Path(__file__).resolve().parent / "data" / "projects" / "tube_turning.wop.json"  # blocks 1 to 3 bore with tool 4
BAR_NUMBER = 4


def boring_bar(hand: ToolHand, bar_width_mm: float | None = None):
    definition = replace(TOOL_TYPES.get("boring").default(), hand=hand, number=BAR_NUMBER, name="bar")
    if bar_width_mm is not None:
        definition = replace(definition, bar_width_mm=bar_width_mm, front_width_mm=bar_width_mm + 2)
    return make_tool("boring", BAR_NUMBER, definition)


def program_with(hand: ToolHand, bar_width_mm: float | None = None):
    program = load_project(PROJECT).program
    tool = boring_bar(hand, bar_width_mm)
    return replace(program, tools=tuple(tool if t.number == BAR_NUMBER else t for t in program.tools))


def moves_of(plan, tool_number=BAR_NUMBER):
    return [op for block in plan.blocks if block.block.tool_number == tool_number for op in block.operations if isinstance(op, (Rapid, LinearMove, ArcMove))]


class BoringBarHandTests(unittest.TestCase):
    def test_the_left_hand_bar_is_the_mirror_image_in_x(self):
        right, left = boring_bar(ToolHand.RIGHT), boring_bar(ToolHand.LEFT)
        for first, second in zip(right.shape.pieces, left.shape.pieces):
            self.assertAlmostEqual(first.segment.end.x, -second.segment.end.x, places=6)
            self.assertAlmostEqual(first.segment.end.z, second.segment.end.z, places=6)
            self.assertEqual(first.role, second.role)

    def test_the_body_side_tells_the_side_a_tool_works_on(self):
        right, left = with_tip_at_origin(boring_bar(ToolHand.RIGHT)), with_tip_at_origin(boring_bar(ToolHand.LEFT))
        self.assertEqual((body_side(right), body_side(left)), (-1, 1))
        self.assertFalse(works_on_far_side(right, inside=True))
        self.assertTrue(works_on_far_side(left, inside=True))
        self.assertTrue(works_on_far_side(right, inside=False))  # a bar towards the axis on an outside cut: below the axis, upside down


class FarSidePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):  # planning takes a few seconds: once for the tests of the class
        cls.right_program, cls.left_program = program_with(ToolHand.RIGHT), program_with(ToolHand.LEFT)
        cls.right, cls.left = plan_program(cls.right_program), plan_program(cls.left_program)

    def test_the_same_material_is_removed(self):
        for first, second in zip(self.right.blocks, self.left.blocks):
            self.assertAlmostEqual(first.result.removed.area, second.result.removed.area, places=6)
            self.assertAlmostEqual(first.residual_after.area, second.residual_after.area, places=6)
        self.assertEqual(self.left.left_out, ())

    def test_the_moves_are_the_mirror_image_below_the_axis(self):
        right_ends = [op.end for op in moves_of(self.right)]
        left_ends = [op.end for op in moves_of(self.left)]
        self.assertLess(min(p.x for p in left_ends), 0)
        self.assertGreaterEqual(min(p.x for p in right_ends), 0)
        # the cuts of the three bores are the same moves with the sign of X turned (the connecting rapids between the blocks differ)
        cutting_right = [(round(p.x, 6), round(p.z, 6)) for op in moves_of(self.right) if isinstance(op, LinearMove) for p in [op.end]]
        cutting_left = [(round(-p.x, 6), round(p.z, 6)) for op in moves_of(self.left) if isinstance(op, LinearMove) for p in [op.end]]
        self.assertEqual(cutting_right, cutting_left)

    def test_the_tool_never_crosses_the_axis_inside_the_part(self):
        # between the blocks the tool changes sides at the safe Z in front of the material, never behind it
        for plan in (self.left,):
            position = None
            for op in plan.operations:
                if isinstance(op, (Rapid, LinearMove, ArcMove)):
                    if position is not None and position.x * op.end.x < 0:
                        where = position.z + (op.end.z - position.z) * (-position.x) / (op.end.x - position.x)  # Z where the move crosses the axis
                        self.assertGreaterEqual(where, 0, "a move across the axis behind the front face")
                    position = op.end

    def test_the_block_begins_and_ends_at_the_real_safe_point(self):
        safe = self.left_program.safety
        block = next(b for b in self.left.blocks if b.block.tool_number == BAR_NUMBER)
        moves = [op for op in block.operations if isinstance(op, (Rapid, LinearMove, ArcMove))]
        self.assertAlmostEqual(moves[-1].end.x, safe.safe_radius_mm)  # not the safe point below the axis
        self.assertAlmostEqual(moves[-1].end.z, safe.safe_z_mm)

    def test_no_findings_where_the_right_hand_bar_has_none(self):
        self.assertEqual(verify_plan(self.right_program, self.right), [])
        self.assertEqual(verify_plan(self.left_program, self.left), [])

    def test_the_findings_are_the_same_as_for_the_right_hand_bar(self):
        thick_right, thick_left = program_with(ToolHand.RIGHT, 30), program_with(ToolHand.LEFT, 30)
        right = Counter(f.kind for f in verify_plan(thick_right, plan_program(thick_right)))
        left = Counter(f.kind for f in verify_plan(thick_left, plan_program(thick_left)))
        self.assertTrue(right)  # a bar that is too thick for the bore is found
        self.assertEqual(right, left)


class FarSideStepperTests(unittest.TestCase):
    def test_the_material_at_every_step_is_the_same_as_for_the_right_hand_bar(self):
        right_program, left_program = program_with(ToolHand.RIGHT), program_with(ToolHand.LEFT)
        right_plan, left_plan = plan_program(right_program), plan_program(left_program)
        right, left = Stepper(right_program, right_plan), Stepper(left_program, left_plan)
        first = lambda stepper, plan: stepper.first_step_of_block(next(i for i, b in enumerate(plan.blocks) if b.block.tool_number == BAR_NUMBER))  # noqa: E731
        first_right, first_left = first(right, right_plan), first(left, left_plan)
        cutting_right = [i for i in range(first_right, first_right + 60) if right.frame(i).is_cutting]
        cutting_left = [i for i in range(first_left, first_left + 62) if left.frame(i).is_cutting]
        self.assertTrue(cutting_right)
        for a, b in zip(cutting_right, cutting_left):
            self.assertAlmostEqual(right.material(a).area, left.material(b).area, places=6)


if __name__ == "__main__":
    unittest.main()
