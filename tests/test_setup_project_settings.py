import unittest
from dataclasses import replace

from wop.core.lathe.machine import MachineDef
from wop.core.files.machine_io import machine_from_dict, machine_to_dict
from wop.core.program_model.units import XInputMode
from wop.ui.block_forms import FieldKind, form_for
from wop.ui.machine_form import MachineForm, form_from_machine, machine_from_form
from wop.ui.setup_form import SetupForm

from wop.ui.app_model import AppModel


class MachineFieldsTests(unittest.TestCase):
    def test_new_machine_values_survive_the_file_and_the_form(self):
        machine = MachineDef("m", postprocessor="fanuc", change_radius_mm=60, change_z_mm=40)
        self.assertEqual(machine_from_dict(machine_to_dict(machine)), machine)
        self.assertEqual(machine_from_form(form_from_machine(machine), machine), machine)

    def test_the_machine_form_has_the_new_fields_and_the_tool_change_may_stay_empty(self):
        specs = {s.path[0]: s for s in form_for(MachineForm())}
        for name in ("postprocessor", "change_radius_mm", "change_z_mm"):
            self.assertIn(name, specs)
        self.assertIs(specs["change_radius_mm"].kind, FieldKind.OPTIONAL_FLOAT)
        self.assertIsNone(MachineForm().change_radius_mm)


class SetupFormTests(unittest.TestCase):
    def test_the_form_starts_with_the_project_settings_and_has_a_machine_button(self):
        specs = form_for(SetupForm())
        self.assertEqual([s.path[0] for s in specs][:4], ["title", "machine", "machine_settings", "x_mode"])
        button = specs[2]
        self.assertIs(button.kind, FieldKind.BUTTON)
        self.assertEqual(button.button_text, "Machine settings...")
        self.assertEqual(specs[0].heading, "Project settings")

    def test_the_machine_dropdown_lists_none_and_the_machines(self):
        form = SetupForm(machine_choices=(("A", "A"), ("B", "B (copy in project)")))
        machine = next(s for s in form_for(form) if s.path == ("machine",))
        self.assertEqual([c.value for c in machine.choices], ["", "A", "B"])


class SetupProjectSettingsModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.auto_check = False
        self.model.save_machine(MachineDef("Lathe A", change_radius_mm=70, change_z_mm=30, postprocessor="fanuc"))
        self.model.save_machine(MachineDef("Lathe B"))

    def test_title_x_mode_and_machine_are_set_through_the_setup_form(self):
        form = replace(self.model.setup_form(), title="Part 7", x_mode=XInputMode.RADIUS, machine="Lathe A")
        self.model.set_setup_form(form)
        self.assertEqual(self.model.project.settings.title, "Part 7")
        self.assertEqual(self.model.project.settings.x_mode, XInputMode.RADIUS)
        self.assertEqual(self.model.machine.name, "Lathe A")
        self.assertEqual(self.model.postprocessor_id, "fanuc")
        self.assertEqual(self.model.setup_form().machine, "Lathe A")

    def test_the_tool_change_position_follows_the_machine_until_it_is_typed(self):
        self.model.set_setup_form(replace(self.model.setup_form(), machine="Lathe A"))
        safety = self.model.program.safety
        self.assertEqual((safety.change_point_x, safety.change_point_z), (70, 30))
        self.model.set_setup_form(replace(self.model.setup_form(), machine="Lathe B"))  # no position: follows the part
        self.assertNotEqual(self.model.program.safety.change_point_x, 70)
        self.model.set_setup_form(replace(self.model.setup_form(), machine="Lathe A"))
        self.model.set_touched("setup", ("change_radius_mm",))
        self.model.set_setup_form(replace(self.model.setup_form(), change_radius_mm=55))
        self.model.set_setup_form(replace(self.model.setup_form(), machine="Lathe B"))
        self.assertEqual(self.model.program.safety.change_point_x, 55)  # typed: stays

    def test_the_project_copy_of_a_machine_is_in_the_dropdown(self):
        self.model.set_machine(MachineDef("Only here"))
        names = [value for value, _text in self.model.setup_form().machine_choices]
        self.assertIn("Only here", names)


if __name__ == "__main__":
    unittest.main()
