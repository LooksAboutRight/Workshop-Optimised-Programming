"""The postprocessor the user sees is the postprocessor that is used.

The project keeps a copy of its machine (so it opens on a PC without that machine). When the machine list has an entry
with the same name, that entry is what Setup and the machine dialog show, so it must be what the export uses: the copy
may never differ from it. These tests run many ways of changing machines and projects and check that rule after each
one (a project made on 2026-10-18 exported with an old post while the list showed another one).
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.post_helpers import install_reference_post


ROOT = Path(__file__).parent.parent


def shown_and_used_agree(test, model):
    """What the list shows for the machine of the project is the machine of the project, and its post is the post used."""
    machine = model.project.machine
    if machine is None:
        return
    listed = model.find_machine(machine.name)
    if listed is not None:
        test.assertEqual(machine, listed, "the copy in the project differs from the entry of the list")
        test.assertEqual(model.postprocessor_id, listed.postprocessor)


class MachineSyncTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel

        self.folders = [tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()]
        for folder in self.folders:
            self.addCleanup(folder.cleanup)
        self.AppModel = AppModel

    def model(self, which=0):
        install_reference_post(Path(self.folders[which].name), "fanuc")  # the reference post, imported as the user does
        return self.AppModel(settings_path=Path(self.folders[which].name) / "settings.json")

    def machine_with_post(self, model, post_id, name=None):
        """A machine of the list (made if needed) that uses this post."""
        name = name or model.new_machine()
        model.save_machine(replace(model.find_machine(name), postprocessor=post_id), old_name=name)
        return name

    def stale_project_file(self):
        """A project file whose copy of the machine uses 'linuxcnc' while the list of the second settings folder says 'fanuc'."""
        first = self.model(0)
        name = self.machine_with_post(first, "linuxcnc")
        first.open(ROOT / "examples" / "reference.wop.json")
        first.use_machine(name)
        path = Path(self.folders[0].name) / "project.wop.json"
        first.save(path)
        second = self.model(1)
        self.machine_with_post(second, "fanuc", name=second.new_machine())  # the same default name
        self.assertEqual(second.machines[0].name, name)
        return path, name, second

    def test_opening_a_project_with_an_older_copy_uses_the_entry_of_the_list(self):
        path, name, second = self.stale_project_file()
        second.open(path)
        self.assertEqual(second.postprocessor_id, "fanuc")
        shown_and_used_agree(self, second)
        self.assertTrue(second.dirty)  # the file is older than what is shown
        notice = second.take_notice()
        self.assertIn(name, notice)
        self.assertIn("linuxcnc -> fanuc", notice)
        self.assertEqual(second.take_notice(), "")  # told once

    def test_the_export_uses_the_post_that_is_shown(self):
        path, _name, second = self.stale_project_file()
        second.open(path)
        text = second.gcode().text
        self.assertTrue(text.startswith("%"))  # the Fanuc post starts with %, the LinuxCNC post does not
        self.assertEqual(second.post_title(), second.post_library.posts["fanuc"].name)

    def test_a_project_whose_machine_is_not_in_the_list_keeps_its_copy(self):
        path, _name, second = self.stale_project_file()
        second.delete_machine(second.machines[0].name)
        second.open(path)
        self.assertEqual(second.postprocessor_id, "linuxcnc")
        self.assertEqual(second.take_notice(), "")

    def test_editing_the_listed_machine_changes_the_project_at_once(self):
        model = self.model()
        name = self.machine_with_post(model, "linuxcnc")
        model.use_machine(name)
        self.machine_with_post(model, "fanuc", name=name)
        self.assertEqual(model.postprocessor_id, "fanuc")
        shown_and_used_agree(self, model)

    def test_undo_and_redo_never_bring_an_old_copy_back(self):
        model = self.model()
        name = self.machine_with_post(model, "linuxcnc")
        model.use_machine(name)
        self.machine_with_post(model, "fanuc", name=name)
        model.add_block("turning")
        for _ in range(4):
            model.undo()
            shown_and_used_agree(self, model)
        for _ in range(4):
            model.redo()
            shown_and_used_agree(self, model)
        self.assertEqual(model.postprocessor_id, "fanuc")

    def test_files_changed_outside_the_program_are_followed(self):
        model = self.model()
        name = self.machine_with_post(model, "linuxcnc")
        model.use_machine(name)
        other = self.AppModel(settings_path=model.settings_path)  # another program on the same files
        self.machine_with_post(other, "generic", name=name)
        model.reload_changed_files()
        self.assertEqual(model.postprocessor_id, "generic")
        shown_and_used_agree(self, model)

    def test_every_way_of_changing_machines_keeps_shown_and_used_together(self):
        model = self.model()
        model.open(ROOT / "examples" / "reference.wop.json")
        first = self.machine_with_post(model, "linuxcnc")
        second = self.machine_with_post(model, "generic")
        steps = (
            lambda: model.use_machine(first),
            lambda: self.machine_with_post(model, "fanuc", name=first),
            lambda: model.undo(),
            lambda: model.use_machine(second),
            lambda: self.machine_with_post(model, "linuxcnc", name=second),
            lambda: model.redo(),
            lambda: model.use_machine(first),
            lambda: model.add_block("facing"),
            lambda: model.undo(),
            lambda: model.undo(),
            lambda: self.machine_with_post(model, "generic", name=first),
            lambda: model.redo(),
            lambda: model.add_project_machine_to_list(),
            lambda: model.delete_machine(second),
            lambda: model.use_machine(None),
            lambda: model.undo(),
            lambda: model.undo(),
        )
        for number, step in enumerate(steps):
            step()
            with self.subTest(step=number):
                shown_and_used_agree(self, model)


if __name__ == "__main__":
    unittest.main()
