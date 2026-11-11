import math
import unittest
from dataclasses import dataclass
from enum import Enum

from wop.core.program_model.units import XInputMode
from wop.ui.block_forms import (
    FieldKind,
    FieldSpec,
    FormContext,
    FormError,
    form_for,
    from_display,
    get_value,
    parse_text,
    set_value,
    to_display,
)


class Mode(Enum):
    A = "first way"
    B = "second way"


@dataclass(frozen=True)
class Corner:
    size_mm: float = 0
    limit: float | None = None


@dataclass(frozen=True)
class Sample:
    block_id: str
    name: str
    tool_number: int
    mode: Mode
    target_radius_mm: float
    feed_mm_per_rev: float
    corner: Corner
    text: str = ""
    flag: bool = False
    comment: str = ""


SAMPLE = Sample("b1", "x", 1, Mode.A, 10, 0.2, Corner(1))
CONTEXT = FormContext(tools=((1, "outside"), (2, "bore")))


class FormTests(unittest.TestCase):
    def specs(self):
        return {spec.path: spec for spec in form_for(SAMPLE, CONTEXT)}

    def test_hidden_fields_are_left_out(self):
        paths = [spec.path for spec in form_for(SAMPLE, CONTEXT)]
        self.assertNotIn(("block_id",), paths)
        self.assertNotIn(("comment",), paths)

    def test_kinds_units_and_labels_come_from_the_fields(self):
        specs = self.specs()
        self.assertEqual(specs[("feed_mm_per_rev",)].unit, "mm/rev")
        self.assertEqual(specs[("feed_mm_per_rev",)].label, "Feed")
        self.assertEqual(specs[("mode",)].kind, FieldKind.CHOICE)
        self.assertEqual([c.label for c in specs[("mode",)].choices], ["first way", "second way"])
        self.assertEqual(specs[("text",)].kind, FieldKind.MULTILINE)
        self.assertEqual(specs[("flag",)].kind, FieldKind.BOOL)

    def test_tool_choices_come_from_the_context(self):
        choices = self.specs()[("tool_number",)].choices
        self.assertEqual([(c.value, c.label) for c in choices], [(0, "No tool chosen"), (1, "T1 outside"), (2, "T2 bore")])

    def test_nested_dataclasses_are_flattened_and_optional_numbers_may_be_empty(self):
        specs = self.specs()
        self.assertIn(("corner", "size_mm"), specs)
        self.assertEqual(specs[("corner", "limit")].kind, FieldKind.OPTIONAL_FLOAT)
        self.assertEqual(specs[("corner", "size_mm")].label, "Corner: Size")
        self.assertIsNone(parse_text(specs[("corner", "limit")], "  "))

    def test_values_are_read_and_changed_without_touching_the_original(self):
        changed = set_value(SAMPLE, ("corner", "size_mm"), 2.5)
        self.assertEqual(get_value(changed, ("corner", "size_mm")), 2.5)
        self.assertEqual(SAMPLE.corner.size_mm, 1)
        self.assertEqual(set_value(SAMPLE, ("mode",), Mode.B).mode, Mode.B)

    def test_radius_fields_show_a_diameter_in_diameter_mode(self):
        spec = self.specs()[("target_radius_mm",)]
        self.assertTrue(spec.is_radius)
        self.assertEqual(spec.display_label(XInputMode.DIAMETER), "Target diameter")
        self.assertEqual(spec.display_label(XInputMode.RADIUS), "Target radius")
        self.assertEqual(to_display(spec, 10, XInputMode.DIAMETER), 20)
        self.assertEqual(to_display(spec, 10, XInputMode.RADIUS), 10)
        self.assertEqual(from_display(spec, 20, XInputMode.DIAMETER), 10)

    def test_typed_text_is_checked(self):
        specs = self.specs()
        self.assertEqual(parse_text(specs[("feed_mm_per_rev",)], "0,25"), 0.25)
        whole = FieldSpec(("n",), "Count", FieldKind.INT)
        self.assertEqual(parse_text(whole, "3"), 3)
        for spec, text in ((specs[("feed_mm_per_rev",)], "fast"), (whole, "1.5")):
            with self.assertRaises(FormError):
                parse_text(spec, text)


class ContourStepFormTests(unittest.TestCase):
    def test_a_line_step_has_end_point_and_corner_fields(self):
        from wop.core.contour import LineStep
        from wop.core.geometry import Point

        specs = {s.path: s for s in form_for(LineStep(Point(10, -5)))}
        self.assertEqual(
            sorted(specs), [("corner", "kind"), ("corner", "size_mm"), ("end", "x"), ("end", "z")]
        )
        x = specs[("end", "x")]
        self.assertTrue(x.is_radius)
        self.assertEqual(x.display_label(XInputMode.DIAMETER), "End: X diameter")
        self.assertEqual(specs[("end", "z")].label, "End: Z")
        self.assertFalse(specs[("end", "z")].is_radius)

    def test_arc_steps_show_direction_and_radius(self):
        from wop.core.contour import ArcCenterStep, ArcRadiusStep
        from wop.core.geometry import ArcDirection, Point

        by_radius = {s.path for s in form_for(ArcRadiusStep(Point(1, 1), 5, ArcDirection.CCW))}
        self.assertIn(("radius_mm",), by_radius)
        self.assertIn(("large_arc",), by_radius)
        by_centre = {s.path for s in form_for(ArcCenterStep(Point(1, 1), Point(0, 0), ArcDirection.CW))}
        self.assertIn(("center", "x"), by_centre)
        self.assertIn(("direction",), by_centre)


class RealBlockFormTests(unittest.TestCase):
    def test_every_block_type_gets_a_form_with_tool_and_spindle(self):
        from wop.core.blocks import BLOCK_TYPES
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        spindle = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
        for name in BLOCK_TYPES.names():
            with self.subTest(name):
                block = BLOCK_TYPES.get(name).example("b1", 1, spindle)
                paths = [spec.path for spec in form_for(block, CONTEXT)]
                if not block.needs_tool:  # a machine function needs no tool, spindle or coolant
                    self.assertNotIn(("tool_number",), paths)
                    continue
                self.assertIn(("tool_number",), paths)
                self.assertIn(("spindle", "value"), paths)
                self.assertIn(("coolant",), paths)

    def test_the_form_changes_a_real_block(self):
        from wop.core.blocks.facing import FacingBlock
        from wop.core.program_model.operations import SpindleMode, SpindleSetting

        block = FacingBlock.example("b1", 1, SpindleSetting(SpindleMode.CONSTANT_RPM, 1000))
        changed = set_value(block, ("spindle", "value"), 800.0)
        self.assertEqual(changed.spindle.value, 800.0)


class TaperDisplayTests(unittest.TestCase):
    def test_the_rise_per_100_mm_and_the_angle_convert_both_ways(self):
        from wop.ui.block_forms import taper_from_display, taper_to_display

        self.assertAlmostEqual(taper_to_display(0, True), 0)
        self.assertAlmostEqual(taper_to_display(10, False), 10)
        rise = taper_to_display(10, True)
        self.assertAlmostEqual(rise, 200 * math.tan(math.radians(5)))  # the diameter grows by twice the radius
        self.assertAlmostEqual(taper_from_display(rise, True), 10)
        self.assertAlmostEqual(taper_from_display(-rise, True), -10)

    def test_the_label_says_what_is_shown(self):
        from wop.ui.block_forms import taper_label

        self.assertIn("angle", taper_label(False)[0])
        self.assertIn("100 mm", taper_label(True)[0])


if __name__ == "__main__":
    unittest.main()
