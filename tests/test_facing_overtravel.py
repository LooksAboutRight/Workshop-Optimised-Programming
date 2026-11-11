import unittest
from dataclasses import replace

from tests.helpers import simple_tool
from wop.core.program_model.operation_text import describe_operations
from wop.core.program_model.operations import LinearMove, Rapid
from wop.core.program_model.raw_part import RawPart

from wop.core.tooling.tool import nose_radius_of

from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.facing import FacingBlock
from wop.core.program_model.stock import stock_region
from wop.ui.app_model import AppModel


class NoseRadiusTests(unittest.TestCase):
    def test_a_tool_without_arcs_has_no_nose_radius(self):
        self.assertEqual(nose_radius_of(simple_tool(1).shape), 0)


class OvertravelTests(unittest.TestCase):
    def test_the_cut_runs_past_the_centre_by_the_overtravel(self):
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        raw = RawPart("steel", 30, 60)
        spindle = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
        context = BlockContext(raw, simple_tool(1), stock_region(raw), Safety(25, 10, 1))
        for overtravel in (0, 0.8):
            block = FacingBlock(block_id="f", tool_number=1, spindle=spindle, target_z_mm=-1, feed_mm_per_rev=0.2,
                                depth_of_cut_mm=1, overtravel_mm=overtravel)
            moves = [op for op in block.generate(context).operations if isinstance(op, LinearMove)]
            self.assertEqual([m.end.x for m in moves][1::2], [-overtravel])  # every second feed is the one across
        tube = RawPart("steel", 30, 60, inner_diameter_mm=10)
        context = BlockContext(tube, simple_tool(1), stock_region(tube), Safety(25, 10, 1))
        moves = [op for op in block.generate(context).operations if isinstance(op, LinearMove)]
        self.assertAlmostEqual(moves[1].end.x, 5 - 0.8)  # past the bore edge

    def test_no_overtravel_at_a_bore_stops_at_the_bore_wall(self):
        """The reference project (a tube): with the overtravel 0 the face line ends exactly on the wall of the bore, and the tool must not go
        on through the bore to the far wall (a pass of its own, found by looking into the wall at the end of the line)."""
        from pathlib import Path

        from wop.adapters.project_files import load_project
        from wop.core.program_model.program import plan_program

        program = load_project(Path(__file__).resolve().parent.parent / "examples" / "reference.wop.json").program
        bore = program.raw_part.inner_diameter_mm / 2
        for overtravel in (0, 0.1):
            facing = replace(program.blocks[0], overtravel_mm=overtravel)
            plan = plan_program(replace(program, blocks=(facing, *program.blocks[1:])), only_block=0)
            reach = min(op.end.x for op in plan.operations if getattr(op, "end", None) is not None)
            self.assertAlmostEqual(reach, bore - overtravel, places=3, msg=f"overtravel {overtravel}")

    def test_a_negative_overtravel_is_refused(self):
        from wop.core.blocks.base import BlockError
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        with self.assertRaises(BlockError):
            FacingBlock(block_id="f", tool_number=1, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, 1000),
                        target_z_mm=-1, feed_mm_per_rev=0.2, depth_of_cut_mm=1, overtravel_mm=-1)


class OvertravelInTheModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.tools = {}
        for type_name, _label in self.model.tool_type_choices():
            number = self.model.add_tool_of_type(type_name)
            nose = self.model.program.tool(number).nose_radius_mm
            if nose > 0:
                self.tools[number] = nose
        self.assertGreaterEqual(len(self.tools), 1)
        self.number, self.nose = next(iter(self.tools.items()))

    def _facing(self, tool_number):
        index = self.model.add_block("facing")
        block = self.model.blocks[index]
        if block.tool_number != tool_number:
            self.model.replace_block(index, replace(block, tool_number=tool_number))
        return index

    def test_a_new_facing_block_gets_twice_the_nose_radius_of_its_tool(self):
        index = self.model.add_block("facing")
        block = self.model.blocks[index]
        expected = 2 * self.model.program.tool(block.tool_number).nose_radius_mm
        self.assertAlmostEqual(block.overtravel_mm, expected)

    def test_an_untouched_overtravel_follows_the_tool_a_touched_one_stays(self):
        index = self._facing(self.number)
        self.assertAlmostEqual(self.model.blocks[index].overtravel_mm, 2 * self.nose)
        other = self.model.program.tools[0].number  # a tool with another nose radius
        self.model.replace_block(index, replace(self.model.blocks[index], tool_number=other))
        self.assertAlmostEqual(self.model.blocks[index].overtravel_mm, 2 * self.model.program.tool(other).nose_radius_mm)
        owner = self.model.block_owner(index)
        self.model.replace_block(index, replace(self.model.blocks[index], overtravel_mm=3))
        self.model.set_touched(owner, ("overtravel_mm",))
        self.model.replace_block(index, replace(self.model.blocks[index], tool_number=self.number))
        self.assertEqual(self.model.blocks[index].overtravel_mm, 3)  # the user typed it: it stays

    def test_reset_to_default_gives_the_value_of_the_tool(self):
        index = self._facing(self.number)
        owner = self.model.block_owner(index)
        self.assertAlmostEqual(self.model.default_object(owner).overtravel_mm, 2 * self.nose)

    def test_the_operations_of_a_block_can_be_read_as_text(self):
        index = self._facing(self.number)
        text = self.model.block_operations_text(index)
        self.assertIn("RAPID", text)
        self.assertIn("FEED", text)
        self.assertIn("TOOL", text)  # what the program adds before the first block is part of it


class OperationTextTests(unittest.TestCase):
    def test_a_drill_operation_can_be_written_out_as_single_moves(self):
        from wop.core.program_model.operations import DrillMode, DrillOperation

        operation = DrillOperation(1, -14, 0.1, 5, DrillMode.PECK, dwell_s=2, exit_z=10, entry_z=0)
        short = describe_operations([operation])
        long = describe_operations([operation], single_moves=True)
        self.assertEqual(len(short.splitlines()), 3)  # explanation, empty line, one line for the drill
        lines = long.splitlines()
        self.assertTrue(lines[2].startswith("DRILL"))
        self.assertIn("    FEED     X0 Z-5  feed 0.1", lines)
        self.assertTrue(any("dwell 2 s" in line for line in lines))
        self.assertEqual(lines[-1], "    RAPID    X0 Z10")

    def test_one_line_per_operation(self):
        from wop.core.geometry import Point

        text = describe_operations([Rapid(Point(25, 2)), LinearMove(Point(0, 2), 0.2)])
        self.assertIn("RAPID    X25 Z2", text)
        self.assertIn("FEED     X0 Z2  feed 0.2", text)


class FacingFormTests(unittest.TestCase):
    def test_the_form_has_the_order_the_user_wants_and_the_finish_feed_follows_the_checkbox(self):
        from wop.ui.block_forms import form_for

        model = AppModel()
        index = model.add_block("facing")
        specs = form_for(model.blocks[index], model.form_context())
        order = []
        for spec in specs:
            if spec.path[0] not in order:
                order.append(spec.path[0])
        self.assertEqual(order, ["name", "direction", "tool_number", "spindle", "target_z_mm", "feed_mm_per_rev",
                                 "depth_of_cut_mm", "overtravel_mm", "finish_allowance_mm", "finish_pass",
                                 "finish_feed_mm_per_rev", "finish_spindle_value", "coolant"])
        feed = next(s for s in specs if s.path[0] == "finish_feed_mm_per_rev")
        self.assertTrue(feed.same_line)
        self.assertFalse(feed.enabled)  # the checkbox is not ticked
        ticked = replace(model.blocks[index], finish_pass=True)
        feed = next(s for s in form_for(ticked, model.form_context()) if s.path[0] == "finish_feed_mm_per_rev")
        self.assertTrue(feed.enabled)

    def test_an_old_facing_block_with_an_allowance_keeps_its_finishing_pass(self):
        from wop.core.blocks import BLOCK_TYPES  # noqa: F401
        from wop.core.files.project_io import _block_from_data

        parameters = {"block_id": "f", "tool_number": 1, "spindle": {"mode": "CONSTANT_SURFACE_SPEED", "value": 100, "rpm_limit": None},
                      "target_z_mm": -1, "feed_mm_per_rev": 0.2, "depth_of_cut_mm": 1}
        for allowance, expected in ((0.3, True), (0, False)):
            block = _block_from_data({"type": "facing", "parameters": dict(parameters, finish_allowance_mm=allowance)})
            self.assertEqual(block.finish_pass, expected)


if __name__ == "__main__":
    unittest.main()
