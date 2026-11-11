"""WH3: the jaw front face against the Setup clamping plane, and cuts behind the clamping plane."""

import unittest
from dataclasses import dataclass, replace

from tests.helpers import simple_tool
from wop.core.geometry import Point
from wop.core.program_model.operations import BlockBegin, BlockEnd, LinearMove, Rapid, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.lathe.workholding import JAWS_KIND, Workholding, workholding_notes
from wop.core.workholding_types import example_item

from wop.core.blocks import BLOCK_TYPES  # noqa: F401
from wop.core.blocks.base import Block, BlockContext, BlockRegistry, BlockResult, Safety
from wop.core.program_model.program import Program, plan_program
from wop.core.geometry.region import Region
from wop.core.verify import FindingKind, verify_plan

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
BAR = RawPart("Mild steel", 50, 40)  # runs through, clamping plane at z = -40
SHORT = RawPart("Mild steel", 50, 40, length_mm=52)
DEEP = RawPart("Mild steel", 50, 40, length_mm=70)


def holding(anchor="step 1") -> Workholding:
    return Workholding(example_item(JAWS_KIND, "J"), None, anchor)


class NoteTests(unittest.TestCase):
    def test_no_note_without_jaws_or_when_the_front_face_is_at_the_plane(self):
        self.assertEqual(workholding_notes(BAR, None), ())
        self.assertEqual(workholding_notes(SHORT, holding()), ())  # step shoulder at the stock end: front at the plane

    def test_jaws_in_front_of_the_plane(self):
        notes = workholding_notes(BAR, holding())  # the shoulder sits at the plane, so the front is 12 mm further out
        self.assertEqual(len(notes), 1)
        self.assertIn("12 mm in front of the clamping plane", notes[0])

    def test_jaws_behind_the_plane(self):
        notes = workholding_notes(DEEP, holding())
        self.assertIn("18 mm behind the clamping plane", notes[0])

    def test_nothing_to_say_when_the_jaws_cannot_be_placed(self):
        self.assertEqual(workholding_notes(BAR, holding("nowhere")), ())


TUBE = RawPart("Mild steel", 50, 40, inner_diameter_mm=20)  # bore radius 10


def inside_jaws() -> Workholding:
    """Jaws made for an inside grip: the example jaws mirrored, so that they lie on the axis side of their point."""
    from wop.core.contour_solver import build_contour
    from wop.core.contour_transform import mirrored_x
    from wop.core.lathe.workholding import GripMode

    item = example_item(JAWS_KIND, "J")
    outline = build_contour("c", "c", mirrored_x(item.outline.definition))
    return Workholding(replace(item, outline=outline), None, "step 2", GripMode.INSIDE)  # step 2 is the point nearest the axis


class InsideGripNoteTests(unittest.TestCase):
    def test_jaws_made_for_the_outside_reach_into_the_wall_of_the_tube(self):
        from wop.core.lathe.workholding import GripMode

        outside_jaws = replace(holding(), grip=GripMode.INSIDE)
        notes = [n for n in workholding_notes(TUBE, outside_jaws) if "wall of the tube" in n]
        self.assertEqual(len(notes), 1)
        self.assertIn("bore radius 10", notes[0])

    def test_jaws_inside_the_bore_give_no_wall_note(self):
        self.assertEqual([n for n in workholding_notes(TUBE, inside_jaws()) if "wall of the tube" in n], [])

    def test_an_outside_grip_never_gives_the_wall_note(self):
        self.assertEqual([n for n in workholding_notes(BAR, holding()) if "wall of the tube" in n], [])


class PlanAndCheckTests(unittest.TestCase):
    def test_the_note_is_in_the_plan_messages(self):
        program = Program(
            raw_part=BAR, tools=(simple_tool(1, side=1),), safety=Safety(25, 10, 1), blocks=(),
            workholding=holding(),
        )
        plan = plan_program(program)
        self.assertEqual(plan.workholding_notes, workholding_notes(BAR, holding()))
        self.assertIn(plan.workholding_notes[0], plan.messages)

    def _program(self, workholding):
        registry = BlockRegistry()

        @registry.register
        @dataclass(frozen=True, kw_only=True)
        class DeepCut(Block):
            type_name = "deepcut"

            def generate(self, context: "BlockContext") -> "BlockResult":
                operations = (
                    BlockBegin(0, self.block_id, self.type_name, ""),
                    Rapid(Point(5, -30)),
                    LinearMove(Point(5, -45), 0.2),  # 5 mm behind the clamping plane (z -40), inside the stock
                    BlockEnd(self.block_id),
                )
                return BlockResult(operations, Region.empty())

        block = DeepCut(block_id="d", tool_number=1, spindle=RPM)
        return Program(
            raw_part=BAR, tools=(simple_tool(1, side=1),), safety=Safety(25, 10, 1),
            blocks=(block,), workholding=workholding,
        )

    def test_a_cut_behind_the_plane_is_found(self):
        program = self._program(holding())
        kinds = [f.kind for f in verify_plan(program, plan_program(program))]
        self.assertIn(FindingKind.CLAMP_PLANE, kinds)

    def test_the_jaws_finding_is_not_doubled_by_the_plane_finding(self):
        program = self._program(None)  # the flat plane is also the jaws: one finding says it
        kinds = [f.kind for f in verify_plan(program, plan_program(program))]
        self.assertNotIn(FindingKind.CLAMP_PLANE, kinds)
        self.assertIn(FindingKind.JAWS, kinds)


if __name__ == "__main__":
    unittest.main()
