"""Workholding in the application model: the library, the Setup fields, the shape editor and the picture (WH2)."""

import unittest
from dataclasses import replace

from wop.core.lathe.workholding import CHUCK_KIND, JAWS_KIND

from wop.ui.app_model import AppModel, ModelError
from wop.ui.block_forms import FieldKind, form_for


class WorkholdingModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.new_library("workholding", "Test")  # start empty, not with the Example
        self.jaws = self.model.add_workholding_item(JAWS_KIND)
        self.chuck = self.model.add_workholding_item(CHUCK_KIND)

    def _use(self, **changes):
        self.model.set_setup_form(replace(self.model.setup_form(), **changes))

    def test_add_lists_the_items_and_the_view_is_shown(self):
        self.assertEqual([i.name for i in self.model.workholding_library], [self.jaws, self.chuck])
        self.assertTrue(self.model.workholding_view)
        self.assertFalse(self.model.tools_view)
        self.assertEqual(self.model.workholding_names(JAWS_KIND), (self.jaws,))
        self.assertFalse(self.model.dirty)  # the library is the application's, not the project's

    def test_none_is_the_default_and_a_choice(self):
        self.assertIsNone(self.model.program.workholding)
        self._use(workholding=self.jaws)
        self.assertIsNotNone(self.model.program.workholding)
        self._use(workholding="")
        self.assertIsNone(self.model.program.workholding)
        self.assertIn("flat clamping plane", self.model.workholding_note())

    def test_choosing_jaws_puts_a_step_on_the_part_by_default(self):
        self._use(workholding=self.jaws)
        holding = self.model.program.workholding
        self.assertEqual(holding.anchor, "step 1")  # the first point that is not the mount point
        self.assertIn("step 1", self.model.workholding_note())
        self.assertIn("step 2", self.model.jaw_point_names())

    def test_unknown_item_is_refused(self):
        with self.assertRaises(ModelError):
            self._use(workholding="nope")

    def test_editing_an_item_updates_the_project_copy(self):
        self._use(workholding=self.jaws)
        form = replace(self.model.workholding_form(self.jaws), name="Soft", jaw_count=4)
        self.model.edit_workholding(self.jaws, form)
        self.assertEqual(self.model.program.workholding.jaws.name, "Soft")
        self.assertEqual(self.model.program.workholding.jaws.jaw_count, 4)
        self.assertEqual(self.model.workholding_library[0].name, "Soft")

    def test_impossible_values_are_a_model_error(self):
        form = replace(self.model.workholding_form(self.jaws), jaw_count=1)
        with self.assertRaises(ModelError):
            self.model.edit_workholding(self.jaws, form)

    def test_delete_keeps_the_project_copy(self):
        self._use(workholding=self.jaws)
        self.model.remove_workholding(self.jaws)
        self.assertEqual(self.model.workholding_library[0].name, self.chuck)
        self.assertIsNotNone(self.model.program.workholding.jaws)
        self.assertEqual(self.model.workholding_names(JAWS_KIND), (self.jaws,))


    def test_storing_a_shape_keeps_a_closed_shape_only(self):
        outline = next(i for i in self.model.workholding_library if i.name == self.jaws).outline
        self.model.set_workholding_shape(self.jaws, outline)
        open_shape = replace(outline, segments=outline.segments[:-1])
        with self.assertRaises(ModelError):
            self.model.set_workholding_shape(self.jaws, open_shape)

    def test_picture_shows_the_jaws_and_the_chuck(self):
        self.assertNotIn("workholding-jaws", self.model.picture())
        self.model.edit_workholding(self.jaws, replace(self.model.workholding_form(self.jaws), chuck=self.chuck))
        self._use(workholding=self.jaws)
        svg = self.model.picture()
        self.assertIn("workholding-jaws", svg)
        self.assertIn("workholding-chuck", svg)


    def test_setup_form_offers_the_lists(self):
        self._use(workholding=self.jaws)
        specs = {s.path: s for s in form_for(self.model.setup_form(), self.model.form_context())}
        self.assertEqual(specs[("workholding",)].kind, FieldKind.CHOICE)
        self.assertIn(("jaw_anchor",), specs)
        self._use(workholding="")
        names = {s.path for s in form_for(self.model.setup_form(), self.model.form_context())}
        self.assertNotIn(("jaw_anchor",), names)

    def test_jaws_bring_their_chuck_body_and_a_chuck_body_alone_is_a_choice(self):
        self.model.edit_workholding(self.jaws, replace(self.model.workholding_form(self.jaws), chuck=self.chuck))
        self._use(workholding=self.jaws)
        self.assertEqual(self.model.program.workholding.chuck.name, self.chuck)
        self._use(workholding=self.chuck)
        holding = self.model.program.workholding
        self.assertIsNone(holding.jaws)
        self.assertEqual(holding.chuck.name, self.chuck)
        self.assertEqual(self.model.setup_form().workholding, self.chuck)

    def test_renaming_or_removing_a_chuck_body_follows_in_the_jaws(self):
        self.model.edit_workholding(self.jaws, replace(self.model.workholding_form(self.jaws), chuck=self.chuck))
        self.model.edit_workholding(self.chuck, replace(self.model.workholding_form(self.chuck), name="Big chuck"))
        self.assertEqual(self.model.workholding_library[0].chuck, "Big chuck")
        self.model.remove_workholding("Big chuck")
        self.assertEqual(self.model.workholding_library[0].chuck, "")

    def test_the_chuck_dropdown_of_the_jaws_form_lists_the_chuck_bodies(self):
        specs = {s.path[0]: s for s in form_for(self.model.workholding_form(self.jaws))}
        self.assertEqual([c.value for c in specs["chuck"].choices], ["", self.chuck])


if __name__ == "__main__":
    unittest.main()
