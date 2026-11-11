import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.test_linuxcnc_ini import SAMPLE_INI
from wop.core.lathe.machine import AxisLimits, Capability, MachineDef

from tests.test_project import full_project
from wop.core.files.project_io import project_from_json, project_to_json
from wop.ui.app_model import AppModel, ModelError


def lathe(name="lathe") -> "MachineDef":
    return MachineDef(name, axes=(AxisLimits("X", -5, 100), AxisLimits("Z", -300, 10)), min_rpm=50,
                      max_rpm=3000, spindle_power_kw=5.5)


class MachineListTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.settings = self.folder / "settings.json"
        self.model = AppModel(settings_path=self.settings)

    def restarted(self):
        return AppModel(settings_path=self.settings)

    def test_a_machine_file_changed_outside_is_read_again_and_own_writes_are_not(self):
        from wop.adapters.machine_folder import delete_machine_file, write_machine_file

        self.model.save_machine(lathe("a"))
        self.assertEqual(self.model.reload_changed_files(), "")  # our own write is not a change
        write_machine_file(self.settings, lathe("b"), (), ())  # another program or PC adds a machine
        note = self.model.reload_changed_files()
        self.assertIn("changed outside", note)
        self.assertEqual([m.name for m in self.model.machines], ["a", "b"])
        self.assertEqual(self.model.reload_changed_files(), "")
        delete_machine_file(self.settings, "a")
        self.assertIn("changed outside", self.model.reload_changed_files())
        self.assertEqual([m.name for m in self.model.machines], ["b"])

    def test_a_library_file_changed_outside_is_read_again(self):
        self.model.add_material("Titanium", 1500)  # forks the Example into My library
        name = self.model.active_library_name("materials")
        self.assertEqual(self.model.reload_changed_files(), "")
        other = AppModel(settings_path=self.settings)
        other.add_material("Brass 2", 900)  # the same files, changed by another running copy
        self.assertIn("changed outside", self.model.reload_changed_files())
        self.assertIn("Brass 2", [m.name for m in self.model.materials.all()])
        self.assertEqual(self.model.active_library_name("materials"), name)

    def test_machines_are_kept_in_the_list_and_survive_a_restart(self):
        self.model.save_machine(lathe("a"))
        self.model.save_machine(lathe("b"))
        self.assertEqual([m.name for m in self.restarted().machines], ["a", "b"])

    def test_a_name_can_only_be_used_once(self):
        self.model.save_machine(lathe("a"))
        self.model.save_machine(lathe("b"))
        with self.assertRaises(ModelError):
            self.model.save_machine(lathe("a"), old_name="b")  # renaming b to a
        self.assertEqual([m.name for m in self.model.machines], ["a", "b"])

    def test_renaming_keeps_default_marks_and_the_project_copy(self):
        self.model.save_machine(lathe("a"))
        self.model.set_default_machine("a")
        self.model.use_machine("a")
        self.model.set_machine_field_touched("a", "spindle_min_rpm")
        self.model.save_machine(replace(lathe("a"), name="z"), old_name="a")
        self.assertEqual([m.name for m in self.model.machines], ["z"])
        self.assertEqual(self.model.default_machine, "z")
        self.assertEqual(self.model.machine.name, "z")
        self.assertTrue(self.model.is_machine_field_touched("z", "spindle_min_rpm"))
        self.assertFalse(self.model.is_machine_field_touched("a", "spindle_min_rpm"))

    def test_the_default_machine_is_in_a_new_project_and_after_a_restart(self):
        self.model.save_machine(lathe("a"))
        self.assertIsNone(self.model.machine)
        self.model.set_default_machine("a")
        self.model.new()
        self.assertEqual(self.model.machine, lathe("a"))
        self.assertFalse(self.model.dirty)
        self.assertEqual(self.restarted().machine, lathe("a"))

    def test_a_project_file_without_a_machine_gets_the_default_machine_when_it_is_opened(self):
        path = self.folder / "plain.wop.json"
        self.model.add_block("facing")
        self.model.save(path)
        self.model.save_machine(lathe("a"))
        self.assertIsNone(self.model.machine)
        self.model.open(path)
        self.assertIsNone(self.model.machine)  # no default machine yet
        self.model.set_default_machine("a")
        self.model.open(path)
        self.assertEqual(self.model.machine, lathe("a"))
        self.assertTrue(self.model.dirty)  # the file is older than what is shown
        self.assertIn("default machine", self.model.take_notice())

    def test_a_project_file_with_a_machine_keeps_it_when_there_is_a_default_machine(self):
        path = self.folder / "own.wop.json"
        self.model.save_machine(lathe("a"))
        self.model.save_machine(lathe("b"))
        self.model.use_machine("b")
        self.model.save(path)
        self.model.set_default_machine("a")
        self.model.open(path)
        self.assertEqual(self.model.machine.name, "b")

    def test_switching_the_machine_changes_what_is_checked(self):
        self.model.save_machine(lathe("small"))
        self.model.save_machine(replace(lathe("slow"), max_rpm=100))
        self.model.add_block("facing")  # constant RPM above 100 for the example block, see the messages
        self.model.use_machine("small")
        before = list(self.model.analysis.messages)
        self.model.use_machine("slow")
        self.assertNotEqual(self.model.analysis.messages, before)
        self.model.use_machine(None)
        self.assertEqual([m for m in self.model.analysis.messages if "RPM" in m], [])

    def test_the_project_keeps_a_copy_after_the_machine_is_deleted(self):
        self.model.save_machine(lathe("a"))
        self.model.set_default_machine("a")
        self.model.use_machine("a")
        self.model.delete_machine("a")
        self.assertEqual(self.model.machines, ())
        self.assertIsNone(self.model.default_machine)
        self.assertEqual(self.model.machine.name, "a")
        self.assertEqual(self.model.add_project_machine_to_list(), "a")
        self.assertEqual([m.name for m in self.model.machines], ["a"])

    def test_the_machine_travels_with_the_project_file(self):
        project = replace(full_project(), machine=lathe("a"))
        self.assertEqual(project_from_json(project_to_json(project)).machine, lathe("a"))
        self.assertIsNone(project_from_json(project_to_json(full_project())).machine)

    def test_a_new_machine_gets_a_free_name_and_nothing_given(self):
        first, second = self.model.new_machine(), self.model.new_machine()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.model.find_machine(first).missing_values()), 5)
        self.assertFalse(self.model.is_machine_field_touched(first, "spindle_min_rpm"))

    def test_importing_marks_the_found_values_as_touched_and_names_what_is_missing(self):
        path = self.folder / "lathe.ini"
        path.write_text(SAMPLE_INI, encoding="utf-8")
        name, notes = self.model.import_machine("linuxcnc_ini", path)
        self.assertEqual(name, "lathe")
        self.assertTrue(self.model.is_machine_field_touched(name, "x_min_mm"))
        self.assertTrue(self.model.is_machine_field_touched(name, "spindle_max_rpm"))
        self.assertFalse(self.model.is_machine_field_touched(name, "spindle_power_kw"))
        self.assertTrue(any("still to enter: spindle power" in note for note in notes))
        again, _notes = self.model.import_machine("linuxcnc_ini", path)
        self.assertEqual(again, "lathe 2")

    def test_a_file_of_the_wrong_kind_is_refused_and_nothing_is_added(self):
        path = self.folder / "lathe.ini"
        path.write_text(SAMPLE_INI, encoding="utf-8")
        with self.assertRaises(ModelError):
            self.model.import_machine("wop_machine", path)
        self.assertEqual(self.model.machines, ())

    def test_export_and_import_of_the_own_format(self):
        self.model.save_machine(lathe("a"))
        target = self.folder / "a.machine.json"
        self.model.export_machine("a", target)
        name, _notes = self.model.import_machine("wop_machine", target)
        self.assertEqual(name, "a 2")
        self.assertEqual(replace(self.model.find_machine(name), name="a"), lathe("a"))

    def test_unknown_machines_are_refused_with_a_message(self):
        for action in (lambda: self.model.use_machine("x"), lambda: self.model.delete_machine("x"),
                       lambda: self.model.set_default_machine("x"),
                       lambda: self.model.export_machine("x", self.folder / "x.json")):
            with self.assertRaises(ModelError):
                action()

    def test_the_importer_list_is_offered(self):
        ids = [choice[0] for choice in self.model.importer_choices()]
        self.assertIn("linuxcnc_ini", ids)

    def test_a_threading_block_is_reported_on_a_machine_without_spindle_sync(self):
        self.model.save_machine(replace(lathe("nosync"), capabilities=frozenset(Capability) - {Capability.SPINDLE_SYNC}))
        self.model.add_block("threading")
        self.model.use_machine("nosync")
        self.assertTrue(any("spindle-synchronised moves" in m for m in self.model.analysis.messages))
