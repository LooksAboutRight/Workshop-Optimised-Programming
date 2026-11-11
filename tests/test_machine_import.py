import tempfile
import unittest
from pathlib import Path

from tests.test_linuxcnc_ini import SAMPLE_INI
from wop.adapters import machine_import_linuxcnc, machine_import_wop  # noqa: F401  (register)
from wop.adapters.machine_files import save_machine
from wop.adapters.machine_import import (
    IMPORTERS,
    ImporterRegistry,
    ImportFormatError,
    ImportResult,
    MachineImporter,
)
from wop.core.lathe.machine import AxisLimits, MachineDef


class RegistryTests(unittest.TestCase):
    """Requirement M8: a new format is one new file."""

    def test_a_dummy_importer_is_added_without_changing_anything_else(self):
        registry = ImporterRegistry()

        @registry.register
        class Dummy(MachineImporter):
            importer_id = "dummy"
            label = "Dummy"
            file_filter = "Dummy (*.dummy)"

            def read(self, path):
                return ImportResult(MachineDef("dummy"), frozenset({"name"}))

        self.assertEqual([i.importer_id for i in registry.all()], ["dummy"])
        self.assertEqual(registry.get("dummy").read(Path("x")).machine.name, "dummy")

    def test_an_importer_needs_an_id_and_a_label_and_ids_are_unique(self):
        registry = ImporterRegistry()
        with self.assertRaises(ValueError):
            registry.register(type("NoLabel", (MachineImporter,), {"importer_id": "a", "read": lambda s, p: None}))

        class One(MachineImporter):
            importer_id, label = "one", "One"

            def read(self, path):
                raise NotImplementedError

        registry.register(One)
        with self.assertRaises(ValueError):
            registry.register(One)
        with self.assertRaises(ValueError):
            registry.get("nothing")

    def test_the_two_first_formats_are_registered(self):
        ids = [i.importer_id for i in IMPORTERS.all()]
        self.assertIn("linuxcnc_ini", ids)
        self.assertIn("wop_machine", ids)


class FileTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)

    def test_the_ini_importer_says_what_it_found(self):
        path = self.folder / "lathe.ini"
        path.write_text(SAMPLE_INI, encoding="utf-8")
        result = IMPORTERS.get("linuxcnc_ini").read(path)
        self.assertEqual(result.machine.name, "lathe")
        self.assertEqual(result.found, {"unit_system", "default_x_mode", "axes", "min_rpm", "max_rpm"})
        self.assertTrue(any("spindle power" in note for note in result.notes))

    def test_an_ini_without_the_values_found_nothing_of_them(self):
        path = self.folder / "empty.ini"
        path.write_text("[EMC]\nVERSION = 1.1\n", encoding="utf-8")
        self.assertEqual(IMPORTERS.get("linuxcnc_ini").read(path).found, frozenset())

    def test_the_own_file_importer_reads_a_saved_machine(self):
        path = self.folder / "m.machine.json"
        machine = MachineDef("mine", axes=(AxisLimits("X", 0, 50),), spindle_power_kw=3)
        save_machine(path, machine)
        result = IMPORTERS.get("wop_machine").read(path)
        self.assertEqual(result.machine, machine)
        self.assertIn("axes", result.found)
        self.assertIn("spindle_power_kw", result.found)
        self.assertNotIn("min_rpm", result.found)

    def test_a_file_of_the_wrong_kind_gives_a_clear_message(self):
        ini = self.folder / "a.ini"
        ini.write_text(SAMPLE_INI, encoding="utf-8")
        with self.assertRaises(ImportFormatError) as raised:
            IMPORTERS.get("wop_machine").read(ini)
        self.assertIn("not a WOP machine file", str(raised.exception))
        machine_file = self.folder / "b.machine.json"
        save_machine(machine_file, MachineDef("m"))
        with self.assertRaises(ImportFormatError) as raised:
            IMPORTERS.get("linuxcnc_ini").read(machine_file)
        self.assertIn("not a LinuxCNC ini file", str(raised.exception))

    def test_a_missing_file_is_refused_with_a_message(self):
        for importer_id in ("linuxcnc_ini", "wop_machine"):
            with self.subTest(importer_id):
                with self.assertRaises(ImportFormatError):
                    IMPORTERS.get(importer_id).read(self.folder / "nothing")
