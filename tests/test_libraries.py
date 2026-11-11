"""Libraries (LIB1): the Example, forking, switching, new, save as, import, and the move of old settings."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from wop.adapters.library_files import (
    LibraryFileError,
    clean_name,
    library_file,
    library_names,
    read_library,
    unique_library_name,
)
from wop.core.files.app_settings import AppSettings, settings_to_dict
from wop.core.files.libraries import content_to_dict, with_content_from_dict, with_example_content
from wop.core.material import Material, MaterialLibrary
from wop.core.lathe.workholding import JAWS_KIND

from wop.ui.app_model import AppModel, ModelError


class LibraryDataTests(unittest.TestCase):
    def test_the_example_content_round_trips_through_a_file_dict(self):
        for kind in ("materials", "workholding", "tools"):
            with self.subTest(kind):
                settings = with_example_content(AppSettings(), kind)
                again = with_content_from_dict(AppSettings(), kind, content_to_dict(settings, kind))
                self.assertEqual(again, settings)

    def test_a_file_of_another_kind_is_refused(self):
        from wop.core.files.app_settings import SettingsError

        data = content_to_dict(with_example_content(AppSettings(), "workholding"), "workholding")
        with self.assertRaises(SettingsError):
            with_content_from_dict(AppSettings(), "tools", data)

    def test_file_names_are_made_safe(self):
        self.assertEqual(clean_name('a/b:c*"d'), "a_b_c__d")
        with self.assertRaises(LibraryFileError):
            clean_name("  . ")


class LibraryFileTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.settings_path = Path(self._folder.name) / "settings.json"

    def test_names_start_with_the_example(self):
        self.assertEqual(library_names(self.settings_path, "materials"), ("Example",))

    def test_a_free_name_is_numbered(self):
        library_file(self.settings_path, "materials", "Mine").parent.mkdir(parents=True)
        library_file(self.settings_path, "materials", "Mine").write_text("{}", encoding="utf-8")
        self.assertEqual(unique_library_name(self.settings_path, "materials", "Mine"), "Mine 2")

    def test_a_missing_library_is_an_error(self):
        with self.assertRaises(LibraryFileError):
            read_library(self.settings_path, "materials", "Nope")


class LibraryModelTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "settings.json"

    def test_a_new_app_uses_the_example_everywhere(self):
        model = AppModel(settings_path=self.path)
        for kind in ("materials", "workholding", "tools"):
            self.assertEqual(model.active_library_name(kind), "Example")
        self.assertTrue(model.workholding_library)
        self.assertTrue(model.tool_library)

    def test_a_saved_tool_is_in_the_file_and_survives_a_restart_and_the_folder_is_known(self):
        model = AppModel(settings_path=self.path)
        number = model.add_tool_of_type(model.tool_type_choices()[0][0])
        message = model.save_tool_to_library(number)
        file = model.library_file_path("tools")
        self.assertTrue(file.exists())
        self.assertIn(str(file), message)
        self.assertEqual(model.library_folder_path("tools"), file.parent)
        name = model.program.tool(number).name
        self.assertIn(name, [t.name for t in AppModel(settings_path=self.path).tool_library])
        self.assertIsNone(AppModel().library_folder_path("tools"))  # settings only in memory

    def test_the_first_change_forks_the_example_into_my_library(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Titanium", 1500)
        self.assertEqual(model.active_library_name("materials"), "My library")
        self.assertEqual(model.active_library_name("workholding"), "Example")  # other kinds are not touched
        self.assertTrue(library_file(self.path, "materials", "My library").exists())
        self.assertEqual(model.library_names("materials"), ("Example", "My library"))
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.active_library_name("materials"), "My library")
        self.assertIn("Titanium", restarted.form_context().materials)

    def test_switching_back_to_the_example_leaves_the_file_alone(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Titanium", 1500)
        model.switch_library("materials", "Example")
        self.assertIsNone(model.materials.find("Titanium"))
        self.assertIn("Titanium", read_library(self.path, "materials", "My library")["materials"]["materials"][0]["name"])
        model.switch_library("materials", "My library")
        self.assertIsNotNone(model.materials.find("Titanium"))

    def test_a_new_library_is_empty_and_gets_the_changes(self):
        model = AppModel(settings_path=self.path)
        model.new_library("workholding", "Lathe 2")
        self.assertEqual(model.workholding_library, ())
        model.add_workholding_item(JAWS_KIND)
        self.assertEqual(len(read_library(self.path, "workholding", "Lathe 2")["items"]), 1)
        with self.assertRaises(ModelError):
            model.new_library("workholding", "lathe 2")  # the name is taken, also with other capitals
        with self.assertRaises(ModelError):
            model.new_library("workholding", "Example")

    def test_save_as_keeps_the_content_under_a_new_name(self):
        model = AppModel(settings_path=self.path)
        before = model.workholding_library
        model.save_library_as("workholding", "Copy")
        self.assertEqual(model.active_library_name("workholding"), "Copy")
        self.assertEqual(model.workholding_library, before)
        self.assertEqual(model.library_names("workholding"), ("Example", "Copy"))

    def test_a_library_file_can_be_imported_and_gets_a_free_name(self):
        giver = AppModel(settings_path=Path(self._folder.name) / "other" / "settings.json")
        giver.add_material("Titanium", 1500)
        source = library_file(Path(self._folder.name) / "other" / "settings.json", "materials", "My library")
        model = AppModel(settings_path=self.path)
        model.add_material("Copper", 800)  # makes "My library" here too
        model.import_library("materials", source)
        self.assertEqual(model.active_library_name("materials"), "My library 2")
        self.assertIsNotNone(model.materials.find("Titanium"))
        self.assertIsNone(model.materials.find("Copper"))

    def test_a_file_of_the_wrong_kind_is_not_imported(self):
        giver = AppModel(settings_path=Path(self._folder.name) / "other" / "settings.json")
        giver.add_material("Titanium", 1500)
        source = library_file(Path(self._folder.name) / "other" / "settings.json", "materials", "My library")
        with self.assertRaises(ModelError):
            AppModel(settings_path=self.path).import_library("workholding", source)

    def test_a_missing_library_falls_back_to_the_example_with_a_message(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Titanium", 1500)
        library_file(self.path, "materials", "My library").unlink()
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.active_library_name("materials"), "Example")
        self.assertIn("My library", restarted.settings_message)

    def test_a_damaged_library_falls_back_to_the_example_and_the_file_is_kept(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Titanium", 1500)
        library_file(self.path, "materials", "My library").write_text("garbage", encoding="utf-8")
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.active_library_name("materials"), "Example")
        self.assertTrue(library_file(self.path, "materials", "My library").exists())

    def test_old_settings_with_their_own_content_move_into_library_files(self):
        old = replace(AppSettings(), materials=MaterialLibrary((Material("Titanium", 1500),)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings_to_dict(old, include_content=True)), encoding="utf-8")
        model = AppModel(settings_path=self.path)
        self.assertEqual(model.active_library_name("materials"), "My library")
        self.assertIsNotNone(model.materials.find("Titanium"))
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("materials", saved)  # the settings file no longer holds the content
        self.assertEqual(saved["libraries"]["materials"], "My library")
        self.assertEqual(AppModel(settings_path=self.path).materials, model.materials)

    def test_a_project_keeps_its_own_copy_when_the_library_is_switched(self):
        model = AppModel(settings_path=self.path)
        model.add_workholding_item(JAWS_KIND)  # forks into My library
        name = model.workholding_library[-1].name
        model.set_setup_form(replace(model.setup_form(), workholding=name))
        model.new_library("workholding", "Other")
        self.assertIsNotNone(model.program.workholding.jaws)
        self.assertEqual(model.program.workholding.jaws.name, name)

    def test_a_library_can_be_renamed_and_deleted(self):
        model = AppModel(settings_path=self.path)
        model.add_material("Titanium", 1500)  # My library
        model.rename_library("materials", "My library", "Shop")
        self.assertEqual(model.active_library_name("materials"), "Shop")
        self.assertEqual(model.library_names("materials"), ("Example", "Shop"))
        self.assertEqual(AppModel(settings_path=self.path).active_library_name("materials"), "Shop")
        with self.assertRaises(ModelError):
            model.rename_library("materials", "Example", "X")
        with self.assertRaises(ModelError):
            model.delete_library("materials", "Example")
        model.delete_library("materials", "Shop")
        self.assertEqual(model.active_library_name("materials"), "Example")
        self.assertIsNone(model.materials.find("Titanium"))
        self.assertEqual(model.library_names("materials"), ("Example",))

    def test_without_a_settings_folder_libraries_work_in_memory(self):
        model = AppModel()
        model.new_library("materials", "Temp")
        self.assertEqual(model.library_names("materials"), ("Example", "Temp"))
        with self.assertRaises(ModelError):
            model.import_library("materials", Path("x.json"))


class ToolLibraryTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "settings.json"
        self.model = AppModel(settings_path=self.path)

    def test_the_example_library_has_a_tool_of_each_type(self):
        self.assertEqual(len(self.model.tool_library), len(self.model.tool_type_choices()))
        self.assertEqual(len({t.name for t in self.model.tool_library}), len(self.model.tool_library))

    def test_adding_from_the_library_copies_it_and_takes_a_free_number(self):
        first = self.model.tool_library[0]
        number = self.model.add_tool_from_library(first.name)
        self.assertEqual(self.model.program.tool(number).name, first.name)
        again = self.model.add_tool_from_library(first.name)
        self.assertNotEqual(again, number)  # the library number was taken: the next free one
        with self.assertRaises(ModelError):
            self.model.add_tool_from_library("nope")

    def test_the_state_of_a_tool_against_the_library(self):
        number = self.model.add_tool_of_type(self.model.tool_type_choices()[0][0])
        self.assertEqual(self.model.tool_library_state(number), "new")
        self.model.save_tool_to_library(number)
        self.assertEqual(self.model.tool_library_state(number), "same")
        self.assertEqual(self.model.active_library_name("tools"), "My library")  # the Example forked
        form = self.model.tool_form(number)
        self.model.edit_tool(number, replace(form, number=number + 5))  # only the number: still the same tool
        self.assertEqual(self.model.tool_library_state(number + 5), "same")

    def test_a_tool_the_library_does_not_know_is_offered_but_a_factory_tool_is_not(self):
        from wop.core.tooling.tool import ToolMaterial

        self.assertEqual(self.model.tools_new_to_library(), ())  # the tools of a new project are factory tools
        number = self.model.add_tool_of_type(self.model.tool_type_choices()[0][0])
        self.assertEqual(self.model.tools_new_to_library(), ())  # exactly as its type makes it
        self.model.edit_tool(number, replace(self.model.tool_form(number), name="My special tool", material=ToolMaterial.HSS))
        self.assertEqual(self.model.tools_new_to_library(), (number,))
        self.model.save_tool_to_library(number)
        self.assertEqual(self.model.tools_new_to_library(), ())

    def test_a_changed_tool_needs_a_yes_to_replace_the_library_tool(self):
        from wop.core.tooling.tool import ToolMaterial

        number = self.model.add_tool_from_library(self.model.tool_library[0].name)
        self.model.edit_tool(number, replace(self.model.tool_form(number), material=ToolMaterial.HSS))
        self.assertEqual(self.model.tool_library_state(number), "differs")
        self.assertEqual(self.model.tools_differing_from_library(), (number,))
        with self.assertRaises(ModelError):
            self.model.save_tool_to_library(number)
        self.model.save_tool_to_library(number, replace_existing=True)
        self.assertEqual(self.model.tool_library_state(number), "same")
        self.assertEqual(len([t for t in self.model.tool_library if t.name == self.model.program.tool(number).name]), 1)

    def test_saved_tools_are_there_after_a_restart(self):
        number = self.model.add_tool_of_type(self.model.tool_type_choices()[0][0])
        name = self.model.program.tool(number).name
        self.model.save_tool_to_library(number)
        restarted = AppModel(settings_path=self.path)
        self.assertIn(name, [t.name for t in restarted.tool_library])

    def test_a_tool_can_be_removed_from_the_library(self):
        self.model.save_tool_to_library(self.model.add_tool_of_type(self.model.tool_type_choices()[0][0]))
        name = self.model.tool_library[-1].name
        self.model.remove_tool_from_library(name)
        self.assertNotIn(name, [t.name for t in self.model.tool_library])
        with self.assertRaises(ModelError):
            self.model.remove_tool_from_library(name)


class MachineFolderTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.path = Path(self._folder.name) / "settings.json"
        self.machines = Path(self._folder.name) / "machines"

    def _files(self):
        return sorted(p.name for p in self.machines.glob("*.machine.json")) if self.machines.is_dir() else []

    def test_each_machine_is_a_file_that_goes_with_it(self):
        model = AppModel(settings_path=self.path)
        first, second = model.new_machine(), None
        second = model.new_machine()
        self.assertEqual(len(self._files()), 2)
        model.delete_machine(second)
        self.assertEqual(self._files(), [f"{first}.machine.json"])
        self.assertEqual([m.name for m in AppModel(settings_path=self.path).machines], [first])

    def test_a_renamed_machine_is_one_file_under_the_new_name(self):
        model = AppModel(settings_path=self.path)
        name = model.new_machine()
        from dataclasses import replace as _replace

        model.save_machine(_replace(model.find_machine(name), name="Lathe"), old_name=name)
        self.assertEqual(self._files(), ["Lathe.machine.json"])

    def test_the_settings_file_no_longer_holds_the_machines(self):
        model = AppModel(settings_path=self.path)
        model.new_machine()
        self.assertNotIn("machines", json.loads(self.path.read_text(encoding="utf-8")))

    def test_old_settings_with_machines_move_into_files(self):
        probe = AppModel(settings_path=self.path)
        name = probe.new_machine()
        machine = probe.find_machine(name)
        for file in self.machines.glob("*"):
            file.unlink()
        old = replace(AppSettings(), machines=(machine,), default_machine=name)
        self.path.write_text(json.dumps(settings_to_dict(old, include_content=True)), encoding="utf-8")
        model = AppModel(settings_path=self.path)
        self.assertEqual([m.name for m in model.machines], [name])
        self.assertEqual(self._files(), [f"{name}.machine.json"])
        self.assertNotIn("machines", json.loads(self.path.read_text(encoding="utf-8")))

    def test_a_default_machine_that_is_gone_gives_way_to_the_first_one(self):
        model = AppModel(settings_path=self.path)
        a, b = model.new_machine(), model.new_machine()
        model.set_default_machine(b)
        (self.machines / f"{b}.machine.json").unlink()  # moved away by hand
        restarted = AppModel(settings_path=self.path)
        self.assertEqual(restarted.default_machine, a)

    def test_a_damaged_machine_file_is_reported_and_left_alone(self):
        model = AppModel(settings_path=self.path)
        model.new_machine()
        (self.machines / "Broken.machine.json").write_text("garbage", encoding="utf-8")
        restarted = AppModel(settings_path=self.path)
        self.assertIn("Broken.machine.json", restarted.settings_message)
        self.assertTrue((self.machines / "Broken.machine.json").exists())

    def test_a_machine_remembers_its_libraries_and_brings_them_back(self):
        model = AppModel(settings_path=self.path)
        name = model.new_machine()
        model.use_machine(name)
        model.new_library("workholding", "Lathe jaws")
        saved = json.loads((self.machines / f"{name}.machine.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["libraries"]["workholding"], "Lathe jaws")
        other = model.new_machine()
        model.use_machine(other)
        model.switch_library("workholding", "Example")
        model.use_machine(name)  # back to the first machine: its libraries come back
        self.assertEqual(model.active_library_name("workholding"), "Lathe jaws")
        # and at the next start, the default machine brings its libraries
        model.set_default_machine(name)
        self.assertEqual(AppModel(settings_path=self.path).active_library_name("workholding"), "Lathe jaws")

    def test_opening_a_project_brings_the_libraries_of_its_machine(self):
        model = AppModel(settings_path=self.path)
        name = model.new_machine()
        model.use_machine(name)
        model.new_library("workholding", "Lathe jaws")
        project_file = self.path.parent / "part.wop.json"
        model.save(project_file)  # the project carries the machine
        other = model.new_machine()
        model.use_machine(other)
        model.switch_library("workholding", "Example")
        self.assertEqual(model.active_library_name("workholding"), "Example")
        model.open(project_file)
        self.assertEqual(model.active_library_name("workholding"), "Lathe jaws")

    def test_touched_marks_of_a_machine_stay_with_its_file(self):
        model = AppModel(settings_path=self.path)
        name = model.new_machine()
        model.set_machine_field_touched(name, "max_rpm")
        restarted = AppModel(settings_path=self.path)
        self.assertTrue(restarted.is_machine_field_touched(name, "max_rpm"))


if __name__ == "__main__":
    unittest.main()
