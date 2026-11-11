"""The program writes what the user drew, the checker reports, the export asks (Python 3.11 and later).

The rule (design notes, section 6): the geometry to cut comes from the form values only; the tool never shortens or skips
it; a block stops only when there is nothing meaningful to make, never because of what the tool can reach; the
roughing comes from the stock, the contour, the allowance and the depth of cut, never deeper than the depth of cut;
every collision is reported by the checker; one block that cannot be planned does not stop the others.
"""

import re
import unittest
from pathlib import Path

from tests.helpers import planned
from wop.core.program_model.operations import BlockBegin, BlockEnd, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.files.project_io import project_from_json

ROOT = Path(__file__).parent.parent
PROJECTS = Path(__file__).parent / "data" / "projects"
EXAMPLES = sorted((ROOT / "examples").glob("*.wop.json")) + sorted((ROOT / "examples" / "blocks").glob("*.wop.json"))
TOOL_PHYSICS_WORDS = ("cannot reach", "cannot get to", "needs a hole", "not finished")  # reasons a block must not stop for


def load(path):
    return project_from_json(Path(path).read_text(encoding="utf-8"))


class ExportQuestionTests(unittest.TestCase):
    def test_a_clean_program_has_nothing_to_ask(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.open(ROOT / "examples" / "reference.wop.json")
        self.assertEqual(model.export_problems(), [])

    def test_a_collision_is_a_reason_to_ask(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.open(ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json")
        problems = model.export_problems()
        self.assertTrue(problems)
        self.assertTrue(any("jaws" in problem for problem in problems))
        self.assertTrue(all("remedy" in problem for problem in problems))

    def test_the_selected_blocks_are_asked_about_on_their_own(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.open(ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json")
        self.assertTrue(model.export_problems((0,)))


class AsDrawnTests(unittest.TestCase):
    def test_the_funnel_project_is_finished_as_drawn_down_to_the_neck(self):
        program = load(PROJECTS / "contour_funnel.wop.json").program
        plan = planned(program)
        self.assertEqual(plan.left_out, ())
        ends = [op.end for op in plan.blocks[-1].operations if hasattr(op, "end")]
        # the neck, as far as material stands: below Z -44.4 the neck lies in the drilled hole (radius 15), the X12 way out leaves there
        self.assertTrue(any(abs(end.x - 2) < 1e-2 and end.z < -44 for end in ends))

    def test_a_thread_the_tool_collides_with_is_written_anyway_and_noted(self):
        from tests.test_blocks_threading import block, program
        from wop.core.blocks.turning_common import TurningSide
        from wop.core.program_model.operations import ThreadOperation
        from wop.core.program_model.raw_part import RawPart
        from wop.core.tooling.tool_presets import thread_tool
        raw = RawPart("steel", 30, 60, inner_diameter_mm=16)  # the 28 mm long tool body does not fit in this bore
        tool = thread_tool(1, "inside", body_towards_larger_x=False)
        plan = planned(program(block(side=TurningSide.INSIDE, crest_radius_mm=8, end_z_mm=-12), tool, raw))
        self.assertTrue([op for op in plan.blocks[0].operations if isinstance(op, ThreadOperation)])
        self.assertTrue(any("collides" in message and "as asked" in message for message in plan.messages))

    def test_no_example_stops_a_block_because_of_the_tool(self):
        for path in EXAMPLES:
            with self.subTest(project=path.name):
                plan = planned(load(path).program)
                for block_plan in plan.blocks:
                    moves = [op for op in block_plan.operations if not isinstance(op, (BlockBegin, BlockEnd))]
                    if not moves:  # a block that writes nothing: its reason must not be the tool
                        for message in block_plan.result.messages:
                            for word in TOOL_PHYSICS_WORDS:
                                self.assertNotIn(word, message, f"block {block_plan.number} stopped because of the tool")

    def test_a_smaller_drill_in_a_larger_hole_rapids_through_the_air(self):
        # the material that is already gone decides where the feed starts: the second drill rapids down the first hole
        from wop.core.blocks.base import Safety
        from wop.core.blocks.drilling import DrillingBlock
        from wop.core.program_model.operations import DrillOperation
        from wop.core.program_model.program import Program
        from wop.core.tooling.tool_presets import block_tool, drill_tool
        spindle = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)

        def drill(number, tool, depth):
            return DrillingBlock(block_id=f"d{number}", name=f"Drill {number}", tool_number=tool, spindle=spindle,
                                 depth_z_mm=depth, feed_mm_per_rev=0.1)

        program = Program(
            raw_part=RawPart("steel", 40, 80), safety=Safety(30, 10, 1),
            tools=(block_tool(1, "t"), drill_tool(2, "big", diameter_mm=16), drill_tool(3, "small", diameter_mm=6)),
            blocks=(drill(1, 2, -20), drill(2, 3, -40)),
        )
        plan = planned(program)
        operations = [op for block_plan in plan.blocks for op in block_plan.operations if isinstance(op, DrillOperation)]
        self.assertIsNone(operations[0].air_z)  # the first drill starts in the material
        self.assertIsNotNone(operations[1].air_z)  # the second goes through the hole that is there
        self.assertLess(operations[1].air_z, -20 + 1)  # ... down to where the first hole ends, not to the front face

    def test_one_failing_block_does_not_blank_the_program(self):
        from dataclasses import replace
        program = load(PROJECTS / "contour_funnel.wop.json").program
        broken = replace(program.blocks[0], block_id="x", tool_number=99)  # a tool that does not exist
        plan = planned(replace(program, blocks=(broken, *program.blocks[1:])))
        self.assertEqual(len(plan.left_out), 1)
        self.assertEqual(len(plan.blocks), len(program.blocks) - 1)


class ToolAwarenessInventoryTests(unittest.TestCase):
    """Every place that asks the tool body something is listed here. A new one fails this test until it is decided,
    following the rule at the top of this file, and added with its reason."""

    ASKS = re.compile(r"check_prepared\(|\.cut_line\(|\bSweeper\(|\.follow_line\(|\.air_line\(|\bcollides\(")
    ALLOWED = {
        "sweep.py": "the Sweeper itself: the one place that moves the tool body along a line",
        "grooving.py": "makes the Sweeper and reports the collisions in the notes; the plunges go to the depth asked",
        "groove_path.py": "the way in and out (air, free lines) of the grooving block; the plunges go to the depth asked",
        "drilling.py": "the air above an earlier hole and the note; the drill goes to the depth asked",
        "threading.py": "the free way in and out and the note; the thread is written as asked",
    }

    def test_only_the_listed_blocks_ask_the_tool_body(self):
        found = {}
        for path in sorted((ROOT / "wop" / "core" / "blocks").glob("*.py")):
            if self.ASKS.search(path.read_text(encoding="utf-8")):
                found[path.name] = True
        self.assertEqual(sorted(found), sorted(self.ALLOWED), "a block asks the tool body that is not in the list (or one on the list no longer does)")


if __name__ == "__main__":
    unittest.main()
