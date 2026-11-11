import json
import unittest

from wop.core.constants import BUILTIN_MATERIALS
from wop.core.material import Material, MaterialError, MaterialLibrary
from wop.core.files.material_io import library_from_dict, library_to_dict


class MaterialTests(unittest.TestCase):
    def test_builtin_materials_are_offered(self):
        names = [m.name for m in MaterialLibrary().all()]
        self.assertEqual(names, [name for name, _ in BUILTIN_MATERIALS])
        for expected in ("Mild steel", "Stainless steel", "Aluminium", "Brass", "Cast iron"):
            self.assertIn(expected, names)

    def test_builtin_materials_have_cutting_data(self):
        for material in MaterialLibrary().all():
            self.assertTrue(material.has_cutting_data)
            self.assertIsNone(material.power_check_warning())

    def test_added_material_appears(self):
        library = MaterialLibrary().with_material(Material("Titanium", 1500))
        self.assertEqual(library.all()[-1].name, "Titanium")
        self.assertTrue(library.is_user_defined("Titanium"))

    def test_edited_builtin_replaces_the_default(self):
        library = MaterialLibrary().with_material(Material("mild steel", 2000))
        self.assertEqual(library.find("Mild steel").specific_cutting_force_n_mm2, 2000)
        self.assertEqual(len(library.all()), len(BUILTIN_MATERIALS))

    def test_removing_the_edit_brings_back_the_default(self):
        library = MaterialLibrary().with_material(Material("Mild steel", 2000)).without("Mild steel")
        self.assertEqual(library.find("Mild steel").specific_cutting_force_n_mm2, 1800)

    def test_material_without_cutting_data_warns(self):
        material = Material("Mystery metal")
        self.assertFalse(material.has_cutting_data)
        self.assertIn("no power check", material.power_check_warning())

    def test_unknown_material(self):
        self.assertIsNone(MaterialLibrary().find("Unobtainium"))

    def test_invalid_material_is_rejected(self):
        with self.assertRaises(MaterialError):
            Material("  ")
        with self.assertRaises(MaterialError):
            Material("x", -5)
        with self.assertRaises(MaterialError):
            MaterialLibrary((Material("a", 1), Material("A", 2)))


class SaveLoadTests(unittest.TestCase):
    def test_changes_survive_a_restart(self):
        """Requirement M5: edited and added materials are still there after loading."""
        library = (
            MaterialLibrary()
            .with_material(Material("Mild steel", 2000))
            .with_material(Material("Titanium", 1500))
            .with_material(Material("Mystery metal"))
        )
        text = json.dumps(library_to_dict(library))
        loaded = library_from_dict(json.loads(text))
        self.assertEqual(loaded, library)
        self.assertEqual(loaded.find("Mild steel").specific_cutting_force_n_mm2, 2000)
        self.assertFalse(loaded.find("Mystery metal").has_cutting_data)

    def test_bad_data_is_rejected(self):
        good = library_to_dict(MaterialLibrary().with_material(Material("A", 1)))
        for mutate in (
            lambda d: d.pop("materials"),
            lambda d: d.update(format=9),
            lambda d: d["materials"][0].update(specific_cutting_force_n_mm2="x"),
            lambda d: d["materials"][0].update(specific_cutting_force_n_mm2=-1),
        ):
            data = json.loads(json.dumps(good))
            mutate(data)
            with self.subTest(data=data):
                with self.assertRaises(MaterialError):
                    library_from_dict(data)


if __name__ == "__main__":
    unittest.main()
