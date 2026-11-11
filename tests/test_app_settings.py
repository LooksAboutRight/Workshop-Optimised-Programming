import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from wop.adapters.app_settings_files import (
    DAMAGED_SUFFIX,
    default_settings_path,
    load_app_settings,
    save_app_settings,
)
from wop.core.files.app_settings import AppSettings, SettingsError, settings_from_dict, settings_to_dict
from wop.core.lathe.machine import MachineDef
from wop.core.material import Material, MaterialLibrary

from wop.ui.app_model import AppModel, ModelError
from wop.ui.block_forms import NEW_MATERIAL, FieldKind, FormContext, form_for


def sample() -> AppSettings:
    return AppSettings(
        MaterialLibrary((Material("Titanium", 1500), Material("Wax", None))),
        legend_visible=False,
        machines=(MachineDef("a", min_rpm=10, max_rpm=20), MachineDef("b")),
        default_machine="b",
        machine_touched=("machine:a/spindle_min_rpm",),
    )


class SettingsDataTests(unittest.TestCase):
    def test_the_window_memory_round_trips_and_a_wrong_entry_is_forgotten(self):
        memory = replace(AppSettings(), last_folder="C:/parts", window_geometry="abc=", panel_sizes=(200, 800, 300))
        self.assertEqual(settings_from_dict(settings_to_dict(memory)), memory)
        data = settings_to_dict(AppSettings())
        data.update(last_folder=5, window_geometry=[1], panel_sizes=[1, "x"])
        self.assertEqual(settings_from_dict(data), AppSettings())

    def test_the_dialog_memory_round_trips_and_a_wrong_entry_is_forgotten(self):
        memory = replace(AppSettings(), dialog_geometry=(("MachinesDialog", "abc="), ("PostEditorDialog", "def=")))
        self.assertEqual(settings_from_dict(settings_to_dict(memory)), memory)
        data = settings_to_dict(AppSettings())
        data["dialog_geometry"] = {"MachinesDialog": "abc=", "Bad": 5, 7: "x"}
        self.assertEqual(settings_from_dict(data).dialog_geometry, (("MachinesDialog", "abc="),))
        data["dialog_geometry"] = ["not", "a", "dict"]
        self.assertEqual(settings_from_dict(data), AppSettings())

    def test_an_empty_memory_is_not_written(self):
        data = settings_to_dict(AppSettings())
        self.assertFalse({"last_folder", "window_geometry", "panel_sizes", "dialog_geometry"} & set(data))

    def test_round_trip(self):
        self.assertEqual(settings_from_dict(settings_to_dict(sample(), include_content=True)), sample())

    def test_missing_entries_get_defaults(self):
        data = {"format": settings_to_dict(AppSettings())["format"]}
        self.assertEqual(settings_from_dict(data), AppSettings())

    def test_a_default_that_is_not_in_the_list_is_dropped(self):
        data = settings_to_dict(sample(), include_content=True)
        data["default_machine"] = "gone"
        self.assertIsNone(settings_from_dict(data).default_machine)

    def test_machines_with_the_same_name_are_refused(self):
        data = settings_to_dict(sample(), include_content=True)
        data["machines"] = [data["machines"][0], {**data["machines"][0], "name": "A"}]
        with self.assertRaises(SettingsError):
            settings_from_dict(data)

    def test_wrong_data_is_refused(self):
        good = settings_to_dict(sample(), include_content=True)
        for label, data in {
            "format": {**good, "format": 99},
            "no format": {"materials": good["materials"]},
            "legend": {**good, "legend_visible": "yes"},
            "material": {**good, "materials": {"format": good["materials"]["format"],
                                               "materials": [{"name": "", "specific_cutting_force_n_mm2": 1}]}},
        }.items():
            with self.subTest(label):
                with self.assertRaises(SettingsError):
                    settings_from_dict(data)


class SettingsFileTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "WOP" / "settings.json"

    def test_saving_creates_the_folder_and_loading_gives_the_same_settings(self):
        save_app_settings(self.path, sample())
        without_content = replace(sample(), machines=(), machine_touched=(), materials=MaterialLibrary(), workholding=())
        self.assertEqual(load_app_settings(self.path), (without_content, ""))  # the libraries are in their own files
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        self.assertNotIn(b"\r", self.path.read_bytes())

    def test_no_file_gives_defaults_without_a_message(self):
        self.assertEqual(load_app_settings(self.path), (AppSettings(), ""))

    def test_a_damaged_file_gives_defaults_a_message_and_is_kept_aside(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{nope", encoding="utf-8")
        settings, message = load_app_settings(self.path)
        self.assertEqual(settings, AppSettings())
        self.assertIn("could not be used", message)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.path.with_name(self.path.name + DAMAGED_SUFFIX).read_text(encoding="utf-8"), "{nope")

    def test_a_file_that_is_not_an_object_counts_as_damaged(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps([1, 2]), encoding="utf-8")
        self.assertEqual(load_app_settings(self.path)[0], AppSettings())

    def test_the_default_path_is_in_a_folder_of_the_app(self):
        self.assertEqual(default_settings_path().name, "settings.json")
        self.assertEqual(default_settings_path().parent.name, "WOP")


class SettingsInTheModelTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "settings.json"

    def test_the_last_folder_and_the_window_layout_come_back_after_a_restart(self):
        model = AppModel(settings_path=self.path)
        model.set_last_folder(Path(self._folder.name) / "parts" / "shaft.json")
        model.set_window_layout("geo=", (200, 700, 300))
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.app_settings.last_folder, str(Path(self._folder.name) / "parts"))
        self.assertEqual((restarted.app_settings.window_geometry, restarted.app_settings.panel_sizes), ("geo=", (200, 700, 300)))

    def test_the_size_of_a_dialog_comes_back_after_a_restart(self):
        model = AppModel(settings_path=self.path)
        model.set_dialog_geometry("MachinesDialog", "abc=")
        model.set_dialog_geometry("PostEditorDialog", "def=")
        model.set_dialog_geometry("MachinesDialog", "ghi=")
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.dialog_geometry("MachinesDialog"), "ghi=")
        self.assertEqual(restarted.dialog_geometry("PostEditorDialog"), "def=")
        self.assertEqual(restarted.dialog_geometry("ToolboxesDialog"), "")

    def test_a_new_material_is_listed_saved_and_there_after_a_restart(self):
        model = AppModel(settings_path=self.path)
        self.assertEqual(model.add_material("  Titanium ", 1500), "Titanium")
        self.assertIn("Titanium", model.form_context().materials)
        self.assertFalse(model.dirty)
        restarted = AppModel(settings_path=self.path)
        self.assertIn("Titanium", restarted.form_context().materials)
        self.assertEqual(restarted.materials.find("titanium").specific_cutting_force_n_mm2, 1500)

    def test_a_material_without_cutting_data_is_allowed_and_a_bad_one_is_refused(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Wax", None)
        self.assertFalse(model.materials.find("Wax").has_cutting_data)
        for name, force in (("", 1), ("Bad", 0), ("Bad", -5)):
            with self.subTest(name=name, force=force):
                with self.assertRaises(ModelError):
                    model.add_material(name, force)

    def test_the_check_is_on_and_not_a_setting_and_verify_now_checks_when_it_is_off(self):
        model = AppModel(settings_path=self.path)
        self.assertTrue(model.auto_check)
        self.assertTrue(model.analysis.checked)
        model.auto_check = False  # only tests and tools do this: there is no menu entry and no setting
        model.add_tool_of_type("turning")  # a change: not checked again by itself
        self.assertFalse(model.analysis.checked)
        model.verify_now()
        self.assertTrue(model.analysis.checked)

    def test_the_legend_state_is_remembered(self):
        model = AppModel(settings_path=self.path)
        self.assertTrue(model.app_settings.legend_visible)
        model.set_legend_visible(False)
        self.assertFalse(AppModel(settings_path=self.path).app_settings.legend_visible)

    def test_without_a_settings_path_nothing_is_written(self):
        model = AppModel()
        model.add_material("Titanium", 1500)
        model.set_legend_visible(False)
        self.assertFalse(self.path.exists())
        self.assertIn("Titanium", model.form_context().materials)

    def test_a_damaged_file_is_reported_and_the_app_still_works(self):
        self.path.write_text("garbage", encoding="utf-8")
        model = AppModel(settings_path=self.path)
        self.assertTrue(model.settings_message)
        self.assertEqual(model.app_settings.machines, ())
        self.assertEqual(model.active_library_name("workholding"), "Example")

    def test_a_file_that_cannot_be_written_is_reported_not_fatal(self):
        blocked = Path(self._folder.name) / "file"
        blocked.write_text("x", encoding="utf-8")
        model = AppModel(settings_path=blocked / "settings.json")  # the "folder" is a file
        model.add_material("Titanium", 1500)
        self.assertIn("could not be saved", model.settings_message)
        self.assertIn("Titanium", model.form_context().materials)

    def test_the_posts_are_listed_with_their_names(self):
        choices = dict(AppModel().post_choices())
        self.assertEqual(choices["linuxcnc"], "LinuxCNC")
        self.assertEqual(list(choices), ["linuxcnc"])  # the default post is part of the program and not offered


class MaterialFormTests(unittest.TestCase):
    def test_the_material_is_a_list_ending_with_new_when_the_context_has_materials(self):
        model = AppModel()
        spec = next(s for s in form_for(model.program.raw_part, model.form_context()) if s.path == ("material",))
        self.assertEqual(spec.kind, FieldKind.CHOICE)
        self.assertEqual(spec.choices[-1].value, NEW_MATERIAL)
        self.assertIn("Mild steel", [c.value for c in spec.choices])

    def test_without_materials_in_the_context_it_stays_a_text_field(self):
        model = AppModel()
        spec = next(s for s in form_for(model.program.raw_part, FormContext()) if s.path == ("material",))
        self.assertEqual(spec.kind, FieldKind.TEXT)

    def test_the_postprocessor_of_the_machine_is_a_list(self):
        from wop.ui.machine_form import MachineForm

        model = AppModel()
        spec = next(s for s in form_for(MachineForm(), model.form_context()) if s.path == ("postprocessor",))
        self.assertEqual(spec.kind, FieldKind.CHOICE)
        self.assertEqual([c.value for c in spec.choices], [i for i, _text in model.post_choices()])


class MaterialEditingTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "settings.json"
        self.model = AppModel(settings_path=self.path)

    def force(self, name):
        return self.model.materials.find(name).specific_cutting_force_n_mm2

    def test_a_built_in_material_can_be_changed_and_brought_back(self):
        self.assertEqual(self.model.material_marks("Brass"), "built-in")
        self.model.save_material("Brass", "Brass", 900)
        self.assertEqual(self.force("Brass"), 900)
        self.assertEqual(self.model.material_marks("Brass"), "built-in, changed")
        self.assertEqual(AppModel(settings_path=self.path).materials.find("Brass").specific_cutting_force_n_mm2, 900)
        self.assertEqual(self.model.delete_material("Brass"), "back to the built-in values")
        self.assertEqual(self.force("Brass"), 800)

    def test_a_built_in_material_cannot_be_deleted(self):
        with self.assertRaises(ModelError):
            self.model.delete_material("Brass")

    def test_a_material_of_the_user_can_be_added_changed_and_deleted(self):
        self.model.save_material(None, "Titanium", 1500)
        self.model.save_material("Titanium", "Titanium", 1600)
        self.assertEqual(self.force("Titanium"), 1600)
        self.assertEqual(self.model.delete_material("Titanium"), "deleted")
        self.assertIsNone(self.model.materials.find("Titanium"))
        self.assertEqual(AppModel(settings_path=self.path).materials.find("Titanium"), None)

    def test_renaming_moves_the_raw_part_with_it(self):
        self.model.save_material(None, "Titanium", 1500)
        raw = self.model.program.raw_part
        self.model.set_raw_part(replace(raw, material="Titanium"))
        self.assertTrue(self.model.material_in_use("titanium"))
        self.model.save_material("Titanium", "Ti 6Al4V", 1500)
        self.assertEqual(self.model.program.raw_part.material, "Ti 6Al4V")
        self.assertIsNone(self.model.materials.find("Titanium"))

    def test_a_name_that_exists_or_is_empty_is_refused(self):
        for old, name in ((None, "Brass"), ("Brass", "Aluminium"), (None, " "), ("Brass", "")):
            with self.subTest(old=old, name=name):
                with self.assertRaises(ModelError):
                    self.model.save_material(old, name, 100)
        self.assertEqual(self.force("Brass"), 800)

    def test_a_free_name_is_found_for_a_new_material(self):
        self.model.save_material(None, "New material", None)
        self.assertEqual(self.model.unique_material_name("New material"), "New material 2")
