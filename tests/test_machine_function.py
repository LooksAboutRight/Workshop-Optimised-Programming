import unittest
from dataclasses import replace

from tests.helpers import simple_tool
from wop.core.program_model.operations import (
    FunctionCall,
    MachineFunction,
    MachineFunctionKind as Kind,
    SetSpindle,
    SpindleMode,
    SpindleSetting,
    StopSpindle,
    ToolChange,
)
from wop.core.program_model.units import XInputMode
from wop.post.base import Feature, PostSettings

from wop.core.blocks.base import Safety
from wop.core.blocks.facing import FacingBlock
from wop.core.blocks.machine_function import MachineFunctionBlock
from wop.core.program_model.program import Program, plan_program
from wop.core.program_model.raw_part import RawPart
from wop.post.generate import RemedyKind, generate_gcode
from tests.post_helpers import bar_feeder_post, limited_post, shipped_post

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
SETTINGS = PostSettings(x_mode=XInputMode.RADIUS)
FIXED = ["program_stop", "optional_stop", "dwell", "spindle_stop"]


def function(name, block_id="m", title="", dwell_s=2.0, tool=1, **values):
    block = MachineFunctionBlock(block_id=block_id, tool_number=tool, spindle=RPM, function=name, name=title, dwell_s=dwell_s)
    for key, value in values.items():
        block = block.with_variable(key, value)
    return block


def facing(block_id="f", tool=1):
    return FacingBlock(block_id=block_id, tool_number=tool, spindle=RPM, target_z_mm=-1, feed_mm_per_rev=0.2, depth_of_cut_mm=1)


def program(*blocks):
    return Program(
        raw_part=RawPart("steel", 30, 60), tools=(simple_tool(1), simple_tool(2)),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1), blocks=tuple(blocks),
    )


class MachineFunctionBlockTests(unittest.TestCase):
    def test_an_empty_name_takes_the_name_of_the_function(self):
        self.assertEqual(function("optional_stop").title, "optional stop")
        self.assertEqual(function("optional_stop", title="check").title, "check")
        self.assertEqual(function("bar_feed").title, "Bar feed")

    def test_the_block_makes_one_neutral_operation_and_no_tool_change_of_its_own(self):
        plan = plan_program(program(facing("a"), function("dwell", tool=2)))
        operations = plan.blocks[1].operations
        self.assertIn(MachineFunction(Kind.DWELL, 2.0), operations)
        self.assertFalse([op for op in operations if isinstance(op, (ToolChange, SetSpindle))])

    def test_a_block_after_it_needs_no_new_tool_or_spindle(self):
        plan = plan_program(program(facing("a"), function("program_stop"), facing("b")))
        self.assertFalse([op for op in plan.blocks[2].operations if isinstance(op, (ToolChange, SetSpindle))])

    def test_spindle_stop_stops_the_spindle_and_the_next_block_starts_it_again(self):
        plan = plan_program(program(facing("a"), function("spindle_stop"), facing("b")))
        self.assertIn(StopSpindle(), plan.blocks[1].operations)
        self.assertTrue([op for op in plan.blocks[2].operations if isinstance(op, SetSpindle)])

    def test_a_dwell_needs_a_time(self):
        from wop.core.blocks.base import BlockError

        with self.assertRaises(BlockError):
            function("dwell", dwell_s=0)

    def test_a_custom_function_makes_a_call_with_its_values_and_changes_nothing_that_is_tracked(self):
        plan = plan_program(program(facing("a"), function("bar_feed", distance=40.0, pull_back=True), facing("b")))
        operations = plan.blocks[1].operations
        self.assertIn(FunctionCall("bar_feed", (("distance", 40.0), ("pull_back", True))), operations)
        self.assertFalse([op for op in operations if isinstance(op, (ToolChange, SetSpindle, StopSpindle))])
        self.assertFalse([op for op in plan.blocks[2].operations if isinstance(op, (ToolChange, SetSpindle))])

    def test_the_value_of_a_variable_is_set_replaced_and_taken_away(self):
        block = function("bar_feed", distance=40.0)
        self.assertEqual(block.variable_value("distance"), 40.0)
        self.assertEqual(block.with_variable("distance", 12.0).variable_value("distance"), 12.0)
        self.assertEqual(len(block.with_variable("distance", 12.0).values), 1)
        self.assertIsNone(block.with_variable("distance", None).variable_value("distance"))


class MachineFunctionOutputTests(unittest.TestCase):
    def lines(self, block, settings=SETTINGS, post=None):
        plan = plan_program(program(facing("a"), block))
        result = generate_gcode(plan, post or shipped_post(), settings)
        return result, result.text.splitlines()

    def test_stops_dwell_and_spindle_stop(self):
        for name, code in (("program_stop", "M0"), ("optional_stop", "M1"), ("dwell", "G4 P2"), ("spindle_stop", "M5")):
            with self.subTest(name=name):
                result, lines = self.lines(function(name))
                self.assertIn(code, lines)
                self.assertTrue(result.complete)

    def test_a_custom_function_is_written_by_the_post_with_its_values(self):
        result, lines = self.lines(function("bar_feed", distance=40.0, pull_back=True), post=bar_feeder_post())
        self.assertTrue(result.complete)
        self.assertIn("(bar feed 40.0 mm)", lines)
        self.assertIn("M101 D40.0 R1", lines)

    def test_a_function_the_post_lacks_leaves_the_block_out_with_a_reason(self):
        result, lines = self.lines(function("bar_feed"))
        self.assertFalse(result.complete)
        self.assertIn("no function 'bar_feed'", result.issues[0].message)
        self.assertIsNone(result.issues[0].remedy)

    def test_a_value_outside_the_limits_of_the_post_leaves_the_block_out_with_a_reason(self):
        result, lines = self.lines(function("bar_feed", distance=900.0), post=bar_feeder_post())
        self.assertFalse(result.complete)
        self.assertIn("Feed distance", result.issues[0].message)
        self.assertIsNone(result.issues[0].remedy)

    def test_a_spindle_stop_block_for_a_post_without_the_code_has_no_remedy(self):
        result, lines = self.lines(function("spindle_stop"), post=limited_post({Feature.SPINDLE_STOP}))
        self.assertFalse(result.complete)
        self.assertIn("no spindle stop", result.issues[0].message)
        self.assertIsNone(result.issues[0].remedy)

    def test_a_postprocessor_that_cannot_write_it_gives_message_and_remedy(self):
        post = limited_post({Feature.DWELL})
        result, lines = self.lines(function("dwell"), post=post)
        self.assertIs(result.issues[0].remedy, RemedyKind.OMIT_FUNCTION)
        self.assertFalse(result.complete)
        plan = plan_program(program(facing("a"), function("dwell")))
        accepted = generate_gcode(plan, post, SETTINGS, {result.issues[0].key})
        self.assertTrue(accepted.complete)
        self.assertTrue([line for line in accepted.text.splitlines() if "dwell not supported" in line])
        self.assertNotIn("G4 P2", accepted.text.splitlines())


class FunctionListTests(unittest.TestCase):
    def setUp(self):
        from wop.core.lathe.machine import MachineDef
        from wop.ui.app_model import AppModel
        from tests.post_helpers import bar_feeder_definition

        self.model = AppModel()
        self.model.post_library.posts["bar_feeder"] = bar_feeder_definition()
        self.use_bar_feeder = lambda: self.model.set_machine(MachineDef("m", postprocessor="bar_feeder"))

    def keys(self):
        return [choice.key for choice in self.model.available_machine_functions()]

    def test_the_fixed_functions_come_first_and_only_with_a_code_in_the_post(self):
        self.model.set_machine(None)
        self.assertEqual(self.keys(), FIXED)
        self.use_bar_feeder()
        self.assertEqual(self.keys(), FIXED + ["bar_feed"])

    def test_a_fixed_function_without_its_code_is_not_offered(self):
        definition = self.model.post_library.posts["bar_feeder"]
        self.model.post_library.posts["bar_feeder"] = replace(
            definition, codes={name: code for name, code in definition.codes.items() if name not in ("dwell", "spindle_stop")}
        )
        self.use_bar_feeder()
        self.assertEqual(self.keys(), ["program_stop", "optional_stop", "bar_feed"])

    def test_the_custom_function_has_a_readable_label_a_note_and_its_variables(self):
        self.use_bar_feeder()
        choice = self.model.available_machine_functions()[-1]
        self.assertEqual(choice.label, "Bar feed")
        self.assertIn("push the bar", choice.description)
        self.assertEqual([(v.name, v.type, v.minimum, v.maximum) for v in choice.variables],
                         [("distance", "float", 0, 500), ("pull_back", "bool", None, None)])

    def test_the_form_offers_the_same_list_and_the_variables_of_the_chosen_function(self):
        from wop.ui.block_forms import FieldKind, form_for

        self.use_bar_feeder()
        self.model.add_block("machine_function")
        specs = {s.path: s for s in form_for(self.model.selected_block(), self.model.form_context())}
        self.assertEqual([choice.value for choice in specs[("function",)].choices], FIXED + ["bar_feed"])
        self.assertEqual(self.model.selected_block().title, "program stop")
        self.assertNotIn(("variable:distance",), specs)
        self.model.replace_block(self.model.selected, replace(self.model.selected_block(), function="bar_feed"))
        specs = form_for(self.model.selected_block(), self.model.form_context())
        self.assertEqual([s.path[0] for s in specs], ["name", "function", "variable:distance", "variable:pull_back"])
        distance, pull_back = specs[2], specs[3]
        self.assertEqual((distance.kind, distance.minimum, distance.maximum, distance.unit), (FieldKind.FLOAT, 0, 500, "mm"))
        self.assertEqual(pull_back.kind, FieldKind.BOOL)
        self.assertEqual(distance.label, "Feed distance")
        self.assertIn("push the bar", specs[1].note)

    def test_a_new_function_starts_with_the_defaults_of_the_post(self):
        self.use_bar_feeder()
        self.model.add_block("machine_function")
        self.model.replace_block(self.model.selected, replace(self.model.selected_block(), function="bar_feed"))
        block = self.model.selected_block()
        self.assertEqual((block.variable_value("distance"), block.variable_value("pull_back")), (30, False))
        self.model.replace_block(self.model.selected, replace(block, function="dwell"))
        self.assertEqual(self.model.selected_block().values, ())

    def test_a_block_whose_function_the_post_lacks_still_shows_it(self):
        from wop.ui.block_forms import form_for

        self.model.add_block("machine_function")
        self.model.replace_block(self.model.selected, replace(self.model.selected_block(), function="bar_feed"))
        specs = {s.path: s for s in form_for(self.model.selected_block(), self.model.form_context())}
        labels = [choice.label for choice in specs[("function",)].choices]
        self.assertEqual(labels[-1], "Bar feed (not in this post)")

    def test_the_flow_list_says_when_the_post_cannot_write_the_block(self):
        self.model.add_block("machine_function")
        self.assertEqual(self.model.block_note(self.model.selected), "")
        self.model.replace_block(self.model.selected, replace(self.model.selected_block(), function="bar_feed"))
        self.assertIn("no function Bar feed", self.model.block_note(self.model.selected))
        self.use_bar_feeder()
        self.assertEqual(self.model.block_note(self.model.selected), "")
        block = self.model.selected_block().with_variable("distance", 900.0)
        self.model.replace_block(self.model.selected, block)
        self.assertIn("Feed distance", self.model.block_note(self.model.selected))

    def test_values_are_read_and_set_through_the_variable_paths(self):
        from wop.ui.block_forms import FieldKind, FieldSpec, FormError, get_value, parse_text, set_value

        block = function("bar_feed", distance=40.0)
        self.assertEqual(get_value(block, ("variable:distance",)), 40.0)
        self.assertEqual(get_value(set_value(block, ("variable:distance",), 5.0), ("variable:distance",)), 5.0)
        spec = FieldSpec(("variable:distance",), "Feed distance", FieldKind.FLOAT, minimum=0, maximum=500)
        self.assertEqual(parse_text(spec, "12,5"), 12.5)
        with self.assertRaises(FormError):
            parse_text(spec, "900")


class FormFieldsTests(unittest.TestCase):
    def names(self, obj):
        from wop.ui.block_forms import form_for

        return [spec.path[0] for spec in form_for(obj)]

    def test_a_machine_function_shows_name_and_function_and_only_then_what_the_function_needs(self):
        self.assertEqual(self.names(function("program_stop")), ["name", "function"])
        self.assertEqual(self.names(function("dwell")), ["name", "function", "dwell_s"])

    def test_the_setup_form_greys_out_the_length_while_the_stock_is_bar_stock(self):
        from wop.ui.block_forms import form_for
        from wop.ui.setup_form import SetupForm

        for through in (True, False):
            specs = {s.path[0]: s for s in form_for(SetupForm(stock_runs_through=through))}
            self.assertIn("length_mm", specs)  # always there
            self.assertEqual(specs["length_mm"].enabled, not through)

    def test_the_setup_form_has_its_sections(self):
        from wop.ui.block_forms import form_for
        from wop.ui.setup_form import SetupForm

        specs = form_for(SetupForm())
        self.assertEqual([(s.path[0], s.heading) for s in specs if s.heading], [
            ("title", "Project settings"), ("material", "Part"), ("change_radius_mm", "Safe distances"),
            ("length_outside_mm", "Workholding")])
        order = [s.path[0] for s in specs]
        self.assertEqual(order, ["title", "machine", "machine_settings", "x_mode", "work_offset", "material", "draw_raw_part", "outer_diameter_mm", "inner_diameter_mm", "stock_runs_through", "length_mm",
                                 "change_radius_mm", "change_z_mm", "safe_radius_mm", "safe_z_mm", "clearance_mm",
                                 "length_outside_mm", "front_z_mm", "workholding"])

    def test_adding_a_block_leaves_the_tools_view_and_chooses_the_block(self):
        from wop.ui.app_model import AppModel

        model = AppModel()
        model.show_tools()
        model.add_block("custom_path")
        self.assertFalse(model.tools_view)
        self.assertEqual(model.selected_block().type_name, "custom_path")


class PostprocessorOfTheMachineTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel

        self.model = AppModel()

    def test_a_project_without_a_machine_writes_with_the_default_postprocessor(self):
        from wop.core.lathe.machine import MachineDef

        self.model.set_machine(None)
        self.assertEqual(self.model.postprocessor_id, "linuxcnc")
        self.model.set_machine(MachineDef("m", postprocessor="fanuc"))
        self.assertEqual(self.model.postprocessor_id, "fanuc")


if __name__ == "__main__":
    unittest.main()
