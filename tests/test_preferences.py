"""File > Preferences: the table against the constants modules, the rules, the file and the window."""

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from wop.core.files import convention_overrides
from wop.core.conventions import CHOICE, MARKER, CONVENTIONS, GROUPS, MATERIAL, RULES, Convention, check_value, conventions_by_group, rule_text
from wop.ui.preferences_model import PreferencesModel

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QComboBox

    APP = QApplication.instance() or QApplication([])

WORD_EDGE = chr(92) + "b"  # the regular expression for the edge of a word
MODULES = tuple(dict.fromkeys(c.module for c in CONVENTIONS))


class TableMatchesTheCodeTests(unittest.TestCase):
    def test_every_editable_constant_has_an_entry_and_every_entry_is_editable(self):
        for module_name in MODULES:
            module = importlib.import_module(module_name)
            with self.subTest(module=module_name):
                self.assertIn(MARKER, vars(module))
                above = set(convention_overrides.editable_names(vars(module)))
                listed = {c.name for c in CONVENTIONS if c.module == module_name}
                self.assertEqual(above - listed, set(), "a constant above NOT_EDITABLE_BELOW has no entry in core/conventions.py (ask the user: editable or not)")
                self.assertEqual(listed - above, set(), "an entry names a constant that is not above NOT_EDITABLE_BELOW")

    def test_every_entry_has_a_known_heading_rule_and_text(self):
        for convention in CONVENTIONS:
            with self.subTest(name=convention.name):
                self.assertIn(convention.group, GROUPS)
                self.assertIn(convention.rule, RULES)
                self.assertTrue(convention.meaning)
                self.assertEqual(bool(convention.choices), convention.rule == CHOICE)

    def test_every_heading_is_used_and_every_entry_is_under_one(self):
        sections = conventions_by_group()
        self.assertEqual([group for group, _entries in sections], list(GROUPS))
        self.assertTrue(all(entries for _group, entries in sections))
        self.assertEqual(sum(len(entries) for _group, entries in sections), len(CONVENTIONS))

    def test_the_defaults_obey_their_own_rules(self):
        model = PreferencesModel(Path("no/such/conventions.json"))
        for _group, rows in model.groups():
            for row in rows:
                if row.convention.rule != MATERIAL:
                    with self.subTest(name=row.convention.name):
                        self.assertIsNone(check_value(row.convention, row.default))


class EveryEditableConstantWorksTests(unittest.TestCase):
    def test_every_editable_constant_is_used_somewhere(self):
        """A row in Preferences that changes nothing would be a lie (DEFAULT_CLEARANCE_MM once was one)."""
        import re

        root = Path(__file__).resolve().parent.parent
        sources = {path: path.read_text(encoding="utf-8") for folder in ("wop", "tools") for path in (root / folder).rglob("*.py")}
        skipped = {"conventions.py", "constants.py", "app_constants.py"}  # the table and the definitions are not uses
        for convention in CONVENTIONS:
            with self.subTest(name=convention.name):
                pattern = re.compile(WORD_EDGE + convention.name + WORD_EDGE)
                self.assertTrue(any(pattern.search(text) for path, text in sources.items() if path.name not in skipped), "nothing uses this constant")


class NewProjectSafePositionsTests(unittest.TestCase):
    def test_a_new_project_starts_with_the_positions_that_follow_its_part(self):
        from wop.core.constants import DEFAULT_FRONT_Z_MM
        from wop.ui.app_constants import DEFAULT_NEW_PART_DIAMETER_MM, SAFE_RADIUS_BEYOND_PART_MM, SAFE_Z_IN_FRONT_MM
        from wop.ui.app_model import new_project
        from wop.ui.setup_form import safe_positions

        safety = new_project().program.safety
        self.assertEqual(safe_positions(DEFAULT_NEW_PART_DIAMETER_MM, DEFAULT_FRONT_Z_MM), (safety.safe_radius_mm, safety.safe_z_mm))
        self.assertEqual(safety.safe_radius_mm, DEFAULT_NEW_PART_DIAMETER_MM / 2 + SAFE_RADIUS_BEYOND_PART_MM)
        self.assertEqual(safety.safe_z_mm, DEFAULT_FRONT_Z_MM + SAFE_Z_IN_FRONT_MM)

    def test_the_positions_follow_a_bigger_part(self):
        from wop.ui.app_constants import SAFE_RADIUS_BEYOND_PART_MM, SAFE_Z_IN_FRONT_MM
        from wop.ui.setup_form import safe_positions

        self.assertEqual(safe_positions(100, -5), (50 + SAFE_RADIUS_BEYOND_PART_MM, -5 + SAFE_Z_IN_FRONT_MM))


class RuleTests(unittest.TestCase):
    def _check(self, rule, value, choices=()):
        return check_value(Convention("X", GROUPS[0], "m", rule, choices=choices), value)

    def test_positive_and_non_negative(self):
        self.assertIsNone(self._check("positive", 0.1))
        self.assertTrue(self._check("positive", 0))
        self.assertTrue(self._check("positive", -1))
        self.assertIsNone(self._check("non_negative", 0))
        self.assertTrue(self._check("non_negative", -0.1))
        self.assertIsNone(self._check("any_number", -5))

    def test_whole_numbers(self):
        self.assertIsNone(self._check("whole_positive", 3.0))
        self.assertTrue(self._check("whole_positive", 0))
        self.assertTrue(self._check("whole_positive", 2.5))
        self.assertIsNone(self._check("whole_non_negative", 0))

    def test_share_and_angle(self):
        self.assertIsNone(self._check("share", 1))
        self.assertTrue(self._check("share", 0))
        self.assertTrue(self._check("share", 1.1))
        self.assertIsNone(self._check("angle", 29.5))
        self.assertTrue(self._check("angle", 90))
        self.assertTrue(self._check("angle", -1))

    def test_choice_and_material(self):
        self.assertIsNone(self._check("choice", 2.0, (1, 2)))
        self.assertTrue(self._check("choice", 3, (1, 2)))
        self.assertIsNone(self._check("material", "Brass"))
        self.assertTrue(self._check("material", "  "))

    def test_no_number_goes_through(self):
        for bad in ("1", True, None, float("nan"), float("inf")):
            with self.subTest(value=bad):
                self.assertTrue(self._check("positive", bad))

    def test_every_rule_can_be_written_in_words(self):
        for rule in RULES:
            self.assertTrue(rule_text(Convention("X", GROUPS[0], "m", rule, choices=(1, 2))))


class FileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "sub" / "conventions.json"

    def test_a_missing_file_is_created_empty(self):
        self.assertTrue(convention_overrides.ensure_file(self.path))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})

    def test_an_existing_file_is_left_alone(self):
        self.path.parent.mkdir()
        self.path.write_text('{"PECK_RETRACT_MM": 1}', encoding="utf-8")
        convention_overrides.ensure_file(self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"PECK_RETRACT_MM": 1})

    def test_a_value_the_rule_refuses_is_not_applied(self):
        self.path.parent.mkdir()
        self.path.write_text('{"PATH_CHECK_STEP_MM": 0, "PECK_RETRACT_MM": 1.5}', encoding="utf-8")
        namespace = {"PATH_CHECK_STEP_MM": 0.5, "PECK_RETRACT_MM": 0.5}
        replaced = convention_overrides.apply_overrides(namespace, "wop.core.constants", self.path)
        self.assertEqual(namespace, {"PATH_CHECK_STEP_MM": 0.5, "PECK_RETRACT_MM": 1.5})
        self.assertEqual(replaced, {"PECK_RETRACT_MM": 0.5})


class ModelTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "conventions.json"
        convention_overrides.ensure_file(self.path)
        self.model = PreferencesModel(self.path)

    def test_a_new_file_changes_nothing(self):
        self.assertEqual(self.model.changed_values(), {})
        self.assertFalse(self.model.needs_restart())
        self.assertEqual(self.model.problems, [])

    def test_a_good_entry_is_taken_and_marked_and_needs_a_restart(self):
        self.assertIsNone(self.model.set_text("PECK_RETRACT_MM", "1,5"))
        row = self.model.row("PECK_RETRACT_MM")
        self.assertEqual((row.value, row.changed), (1.5, True))
        self.assertTrue(self.model.needs_restart())

    def test_a_wrong_entry_is_refused_and_the_value_kept(self):
        before = self.model.row("PATH_CHECK_STEP_MM").value
        self.assertTrue(self.model.set_text("PATH_CHECK_STEP_MM", "0"))
        self.assertTrue(self.model.set_text("PATH_CHECK_STEP_MM", "abc"))
        self.assertEqual(self.model.row("PATH_CHECK_STEP_MM").value, before)

    def test_whole_number_constants_stay_whole(self):
        self.model.set_text("THREAD_SPRING_PASSES", "3")
        self.assertIsInstance(self.model.row("THREAD_SPRING_PASSES").value, int)
        self.assertTrue(self.model.set_text("THREAD_SPRING_PASSES", "2.5"))

    def test_only_changed_values_are_saved_and_reset_takes_them_out(self):
        self.model.set_text("PECK_RETRACT_MM", "1.5")
        self.model.set_text("POWER_EFFICIENCY", str(self.model.row("POWER_EFFICIENCY").default))  # the default again
        self.model.save()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"PECK_RETRACT_MM": 1.5})
        self.model.reset("PECK_RETRACT_MM")
        self.model.save()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})

    def test_a_saved_file_is_read_back_and_a_bad_entry_is_reported(self):
        self.path.write_text('{"PECK_RETRACT_MM": 2, "PATH_CHECK_STEP_MM": -1, "NO_SUCH": 1}', encoding="utf-8")
        again = PreferencesModel(self.path)
        self.assertEqual(again.row("PECK_RETRACT_MM").value, 2)
        self.assertEqual(again.row("PATH_CHECK_STEP_MM").value, again.row("PATH_CHECK_STEP_MM").default)
        self.assertEqual(len(again.problems), 2)

    def test_a_file_that_is_not_json_is_reported(self):
        self.path.write_text("{not json", encoding="utf-8")
        again = PreferencesModel(self.path)
        self.assertEqual(len(again.problems), 1)
        self.assertIn(self.path.name, again.problems[0])

    def test_a_text_choice_takes_a_word_and_refuses_another(self):
        self.assertIsNone(self.model.set_text("GROOVE_ONE_SIDED_MODE", "percent"))
        self.assertEqual(self.model.row("GROOVE_ONE_SIDED_MODE").value, "percent")
        self.assertTrue(self.model.set_text("GROOVE_ONE_SIDED_MODE", "inch"))
        self.model.save()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"GROOVE_ONE_SIDED_MODE": "percent"})

    def test_the_percentage_rule(self):
        self.assertIsNone(self.model.set_text("GROOVE_ONE_SIDED_CUT_PERCENT", "100"))
        self.assertTrue(self.model.set_text("GROOVE_ONE_SIDED_CUT_PERCENT", "101"))
        self.assertTrue(self.model.set_text("GROOVE_ONE_SIDED_CUT_PERCENT", "0"))

    def test_the_fixed_text_has_the_tables_and_not_the_editable_values(self):
        text = self.model.fixed_text()
        self.assertIn("BUILTIN_MATERIALS", text)
        self.assertIn("HOLDER_LENGTHS_MM", text)
        self.assertNotIn("PECK_RETRACT_MM", text)
        self.assertNotIn("NOT_EDITABLE_BELOW", text)


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class DialogTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.preferences_dialog import PreferencesDialog

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "conventions.json"
        convention_overrides.ensure_file(self.path)
        model = AppModel(settings_path=Path(folder.name) / "settings.json")
        self.dialog = PreferencesDialog(None, model, PreferencesModel(self.path))
        self.addCleanup(self.dialog.deleteLater)

    def test_there_is_a_box_for_every_convention(self):
        self.assertEqual(set(self.dialog._editors), {c.name for c in CONVENTIONS})

    def test_typing_a_good_value_saves_marks_and_asks_for_a_restart(self):
        box = self.dialog._editors["PECK_RETRACT_MM"]
        box.setText("1.5")
        self.dialog._edited("PECK_RETRACT_MM")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"PECK_RETRACT_MM": 1.5})
        self.assertIn("0.5", self.dialog._editors["PECK_RETRACT_MM"].toolTip())  # the tip names the default
        self.assertTrue(self.dialog._resets["PECK_RETRACT_MM"].isEnabled())
        self.assertFalse(self.dialog._restart.isHidden())

    def test_typing_a_wrong_value_marks_the_box_and_saves_nothing(self):
        box = self.dialog._editors["PATH_CHECK_STEP_MM"]
        box.setText("0")
        self.dialog._edited("PATH_CHECK_STEP_MM")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})
        self.assertTrue(box.styleSheet())
        self.assertIn("PATH_CHECK_STEP_MM", self.dialog._message.text())

    def test_reset_brings_the_default_back(self):
        box = self.dialog._editors["PECK_RETRACT_MM"]
        box.setText("1.5")
        self.dialog._edited("PECK_RETRACT_MM")
        self.dialog._reset("PECK_RETRACT_MM")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})
        self.assertEqual(box.text(), "0.5")
        self.assertFalse(self.dialog._resets["PECK_RETRACT_MM"].isEnabled())

    def test_a_value_at_its_default_is_grey_and_a_changed_one_is_not(self):
        from PySide6.QtGui import QPalette

        box = self.dialog._editors["PECK_RETRACT_MM"]
        grey = lambda: box.palette().color(QPalette.Text) == self.dialog._dim  # noqa: E731
        self.assertTrue(grey())
        box.setText("1.5")
        self.dialog._edited("PECK_RETRACT_MM")
        self.assertFalse(grey())
        self.dialog._reset("PECK_RETRACT_MM")
        self.assertTrue(grey())

    def test_typing_the_default_again_makes_the_row_grey_and_the_file_empty(self):
        box = self.dialog._editors["PECK_RETRACT_MM"]
        box.setText("1.5")
        self.dialog._edited("PECK_RETRACT_MM")
        box.setText("0.5")
        self.dialog._edited("PECK_RETRACT_MM")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})
        self.assertFalse(self.dialog._resets["PECK_RETRACT_MM"].isEnabled())

    def test_every_box_has_the_reset_menu(self):
        from PySide6.QtCore import Qt

        self.assertTrue(all(editor.contextMenuPolicy() == Qt.CustomContextMenu for editor in self.dialog._editors.values()))

    def test_choices_and_materials_are_dropdowns(self):
        self.assertIsInstance(self.dialog._editors["THREAD_DEGRESSION_CONSTANT_AREA"], QComboBox)
        materials = self.dialog._editors["DEFAULT_NEW_PART_MATERIAL"]
        self.assertIsInstance(materials, QComboBox)
        self.assertGreater(materials.count(), 1)


if __name__ == "__main__":
    unittest.main()
