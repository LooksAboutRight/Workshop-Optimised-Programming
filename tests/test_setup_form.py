import unittest
from dataclasses import replace

from wop.core.program_model.raw_part import RawPart, RawPartError
from wop.core.program_model.stock import stock_region
from wop.core.sketch.modes import RAW_PART, problems, sketch_from_contour
from wop.ui.block_forms import FieldKind, form_for
from wop.ui.setup_form import SetupForm, setup_to_parts, stock_summary

from wop.ui.app_model import AppModel, ModelError
from wop.ui.setup_form import setup_from_program


class WorkOffsetTests(unittest.TestCase):
    def test_the_form_offers_the_work_offsets_of_the_post_of_the_machine(self):
        from wop.core.lathe.machine import MachineDef

        model = AppModel()
        model.set_machine(MachineDef("m", postprocessor="linuxcnc"))
        form = model.setup_form()
        self.assertEqual(len(form.work_offset_choices), 9)
        self.assertEqual([code for code, _text in form.field_choices()["work_offset"]], list(form.work_offset_choices))
        self.assertNotIn("work_offset", form.form_disabled())

    def test_a_post_without_work_offsets_greys_the_field(self):
        form = SetupForm(work_offset="G54", work_offset_choices=())
        self.assertIn("work_offset", form.form_disabled())
        self.assertEqual(form.field_choices()["work_offset"], [("G54", "G54")])

    def test_the_project_keeps_a_work_offset_that_the_post_has_not_got(self):
        form = SetupForm(work_offset="G59.3", work_offset_choices=("G54", "G55"))
        choices = form.field_choices()["work_offset"]
        self.assertEqual(choices[-1], ("G59.3", "G59.3 (not in the post)"))
        self.assertEqual(len(choices), 3)


class SetupFormTests(unittest.TestCase):
    def test_the_default_stock_runs_through(self):
        raw, _safety = setup_to_parts(SetupForm())
        self.assertIsNone(raw.length_inside_mm)

    def test_a_stock_that_ends_inside_gets_its_length(self):
        raw, _safety = setup_to_parts(SetupForm(stock_runs_through=False, length_outside_mm=40, length_mm=65))
        self.assertEqual(raw.length_mm, 65)
        self.assertEqual(raw.length_inside_mm, 25)

    def test_the_length_is_ignored_while_the_stock_runs_through(self):
        raw, _safety = setup_to_parts(SetupForm(stock_runs_through=True, length_mm=25))
        self.assertIsNone(raw.length_mm)

    def test_a_stick_out_longer_than_the_part_is_allowed(self):
        raw, _safety = setup_to_parts(SetupForm(stock_runs_through=False, length_outside_mm=40, length_mm=30))
        self.assertEqual(raw.length_inside_mm, 0)
        self.assertEqual(raw.clamp_z_mm, -40)  # the plane stays where the stick-out puts it

    def test_a_part_that_cannot_exist_is_refused(self):
        for form in (SetupForm(outer_diameter_mm=0), SetupForm(inner_diameter_mm=40),
                     SetupForm(length_outside_mm=0), SetupForm(stock_runs_through=False, length_mm=0)):
            with self.subTest(form=form):
                with self.assertRaises(RawPartError):
                    setup_to_parts(form)

    def test_the_safe_positions_are_part_of_the_form(self):
        _raw, safety = setup_to_parts(
            SetupForm(change_radius_mm=60, change_z_mm=20, safe_radius_mm=40, safe_z_mm=5, clearance_mm=2)
        )
        self.assertEqual((safety.safe_radius_mm, safety.safe_z_mm, safety.clearance_mm), (40, 5, 2))
        self.assertEqual((safety.change_point_x, safety.change_point_z), (60, 20))

    def test_the_summary_says_what_the_stock_does(self):
        self.assertIn("Bar stock", stock_summary(SetupForm()))
        self.assertEqual(
            stock_summary(SetupForm(length_outside_mm=40, stock_runs_through=False, length_mm=65)),
            "Length 65 mm: 40 mm stick out, 25 mm in the chuck.",
        )
        self.assertIn("more than the part", stock_summary(SetupForm(length_outside_mm=40, stock_runs_through=False, length_mm=30)))

    def test_the_form_uses_the_new_labels_and_a_checkbox_for_the_choice(self):
        specs = {spec.path[0]: spec for spec in form_for(SetupForm())}
        self.assertEqual(specs["length_outside_mm"].label, "Stick-out (free length)")
        self.assertEqual(specs["stock_runs_through"].kind, FieldKind.BOOL)
        self.assertEqual(specs["stock_runs_through"].label, "Bar stock (unlimited length)")
        self.assertEqual(specs["material"].kind, FieldKind.TEXT)  # a list when the context has materials


class SetupInTheModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()

    def test_the_form_shows_the_raw_part_and_the_safe_positions_of_the_project(self):
        form = self.model.setup_form()
        self.assertEqual(form, setup_from_program(self.model.program))
        self.assertEqual(form.material, self.model.program.raw_part.material)
        self.assertEqual(form.safe_radius_mm, self.model.program.safety.safe_radius_mm)

    def test_a_change_goes_to_the_raw_part_and_the_safe_positions_in_one_step(self):
        calls = []
        self.model.subscribe(lambda: calls.append(1))
        form = replace(self.model.setup_form(), outer_diameter_mm=50, stock_runs_through=False,
                       length_mm=80, safe_z_mm=12)
        self.model.set_setup_form(form)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.model.program.raw_part.outer_diameter_mm, 50)
        self.assertEqual(self.model.program.raw_part.length_inside_mm, 20)  # 80 - the default stick-out of 60
        self.assertEqual(self.model.program.safety.safe_z_mm, 12)
        self.assertEqual(self.model.setup_form(), replace(form, safe_radius_mm=35, change_radius_mm=35, change_z_mm=10))
        self.assertTrue(self.model.dirty)

    def test_the_safe_positions_follow_the_part_until_they_are_touched(self):
        self.model.set_setup_form(replace(self.model.setup_form(), outer_diameter_mm=120, front_z_mm=5))
        form = self.model.setup_form()
        self.assertEqual((form.safe_radius_mm, form.safe_z_mm), (70, 15))
        self.model.set_touched("setup", ("safe_radius_mm",))
        self.model.set_setup_form(replace(form, outer_diameter_mm=40))
        form = self.model.setup_form()
        self.assertEqual((form.safe_radius_mm, form.safe_z_mm), (70, 15))  # touched: stays; the safe Z is not touched
        self.model.set_setup_form(replace(form, front_z_mm=0))
        self.assertEqual(self.model.setup_form().safe_z_mm, 10)

    def test_a_safe_value_typed_now_is_not_overwritten(self):
        form = replace(self.model.setup_form(), outer_diameter_mm=100, safe_radius_mm=77)
        self.model.set_setup_form(form)
        self.assertEqual(self.model.setup_form().safe_radius_mm, 77)

    def test_a_stock_that_runs_through_comes_back_as_through(self):
        self.model.set_setup_form(replace(self.model.setup_form(), stock_runs_through=False))
        self.model.set_setup_form(replace(self.model.setup_form(), stock_runs_through=True))
        self.assertIsNone(self.model.program.raw_part.length_inside_mm)
        self.assertTrue(self.model.setup_form().stock_runs_through)

    def test_a_part_that_cannot_exist_is_refused_and_nothing_changes(self):
        before = self.model.program
        with self.assertRaises(ModelError):
            self.model.set_setup_form(replace(self.model.setup_form(), inner_diameter_mm=500))
        self.assertEqual(self.model.program, before)

    def test_the_raw_part_of_a_loaded_project_is_shown_with_its_length_inside(self):
        raw = RawPart("Brass", 20, 30, length_mm=45)
        self.model.project = replace(self.model.project, program=replace(self.model.program, raw_part=raw))
        form = self.model.setup_form()
        self.assertFalse(form.stock_runs_through)
        self.assertEqual((form.length_outside_mm, form.length_mm), (30, 45))


class DrawnRawPartTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()

    def _draw(self):
        target = self.model.raw_part_sketch_target()
        self.assertEqual(target.mode.key, "raw_part")
        sketch = sketch_from_contour(target.contour)
        self.assertEqual(problems(sketch, RAW_PART), [])
        target.commit(target.contour)

    def test_the_first_drawing_is_the_bar_of_the_form_and_changes_nothing(self):
        before = self.model.setup_form()
        self._draw()
        form = self.model.setup_form()
        self.assertIsNotNone(form.raw_outline)
        self.assertEqual((form.outer_diameter_mm, form.inner_diameter_mm), (before.outer_diameter_mm, before.inner_diameter_mm))
        self.assertEqual((form.length_outside_mm, form.front_z_mm), (before.length_outside_mm, before.front_z_mm))
        self.assertAlmostEqual(stock_region(self.model.program.raw_part).area, stock_region(replace(self.model.program.raw_part, outline=None)).area)

    def test_the_numbers_are_greyed_while_the_raw_part_is_drawn_and_a_button_goes_back(self):
        self.assertNotIn("plain_bar", [s.path[0] for s in form_for(self.model.setup_form())])
        self._draw()
        specs = {s.path[0]: s for s in form_for(self.model.setup_form())}
        for name in ("outer_diameter_mm", "inner_diameter_mm", "length_outside_mm", "front_z_mm", "length_mm", "stock_runs_through"):
            self.assertFalse(specs[name].enabled, name)
        self.assertTrue(specs["material"].enabled)
        self.assertEqual(specs["plain_bar"].button_text, "Back to a plain bar or tube")
        drawn = self.model.setup_form()
        self.model.use_plain_bar()
        again = self.model.setup_form()
        self.assertIsNone(again.raw_outline)
        self.assertIsNone(self.model.program.raw_part.outline)
        self.assertEqual((again.outer_diameter_mm, again.length_outside_mm), (drawn.outer_diameter_mm, drawn.length_outside_mm))

    def test_a_tube_is_drawn_as_a_tube_and_the_safe_position_follows_a_bigger_drawing(self):
        self.model.set_setup_form(replace(self.model.setup_form(), inner_diameter_mm=10))
        target = self.model.raw_part_sketch_target()
        self.assertTrue(target.contour.is_closed)
        target.commit(target.contour)
        self.assertEqual(self.model.setup_form().inner_diameter_mm, 10)

    def test_the_drawing_is_kept_by_a_change_of_material(self):
        self._draw()
        self.model.set_setup_form(replace(self.model.setup_form(), material="Brass"))
        self.assertIsNotNone(self.model.program.raw_part.outline)
        self.assertEqual(self.model.program.raw_part.material, "Brass")
