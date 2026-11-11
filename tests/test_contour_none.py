import unittest

from dataclasses import replace

from wop.core.contour import Contour, ContourDefinition, LineStep
from wop.core.geometry import Point
from wop.core.blocks.base import NO_CONTOUR
from wop.ui.app_model import AppModel, default_contour


def model_with_contour_block():
    model = AppModel()
    model.add_block("facing")
    model.add_block("turning_contour")
    return model


class NoContourTests(unittest.TestCase):
    def test_a_new_contour_block_has_no_contour_and_is_left_out(self):
        model = model_with_contour_block()
        self.assertEqual(model.blocks[1].contour_id, NO_CONTOUR)
        self.assertEqual(model.program.contours, ())
        plan = model.analysis.plan
        self.assertEqual([p.number for p in plan.blocks], [1])
        self.assertEqual([left.number for left in plan.left_out], [2])
        self.assertIn("no contour set", model.block_note(1))
        self.assertEqual(model.block_note(0), "")
        self.assertTrue(any("is left out" in m for m in model.analysis.messages))

    def test_the_gcode_of_such_a_program_is_marked_incomplete(self):
        model = model_with_contour_block()
        result = model.gcode()
        self.assertFalse(result.complete)
        self.assertIn("INCOMPLETE - DO NOT RUN", result.text)
        self.assertIn("no contour set", result.text)

    def test_choosing_a_contour_clears_the_mark(self):
        model = model_with_contour_block()
        model.set_contour(default_contour(model.program))
        model.replace_block(1, replace(model.blocks[1], contour_id="contour1"))
        self.assertEqual(model.analysis.plan.left_out, ())
        self.assertTrue(model.gcode().complete)
        self.assertEqual(model.block_note(1), "")

    def test_an_invalid_contour_leaves_its_blocks_out_and_later_blocks_get_a_note(self):
        model = model_with_contour_block()
        broken = Contour("contour1", "Broken", (), ContourDefinition(Point(10, 0), (LineStep(Point(10, -5)),)), "angle missing")
        model.set_contour(broken)
        model.replace_block(1, replace(model.blocks[1], contour_id="contour1"))
        model.add_block("facing")  # block 3 comes after the left-out block 2
        self.assertEqual([left.number for left in model.analysis.plan.left_out], [2])
        self.assertIn("not valid", model.block_note(1))
        note = next(m for m in model.analysis.messages if "is left out" in m)
        self.assertIn("block 3", note)

    def test_the_form_offers_none_first(self):
        from wop.ui.block_forms import FormContext, form_for

        specs = {s.path: s for s in form_for(model_with_contour_block().blocks[1], FormContext(contours=(("c1", "A"),)))}
        choices = specs[("contour_id",)].choices
        self.assertEqual([c.value for c in choices], [NO_CONTOUR, "c1"])


class DeleteContourTests(unittest.TestCase):
    def setUp(self):
        self.model = model_with_contour_block()
        self.model.set_contour(default_contour(self.model.program))
        self.model.replace_block(1, replace(self.model.blocks[1], contour_id="contour1"))

    def test_users_are_listed(self):
        self.assertEqual(self.model.contour_users("contour1"), (1,))

    def test_delete_with_the_blocks(self):
        self.model.delete_contour("contour1", with_blocks=True)
        self.assertEqual([b.type_name for b in self.model.blocks], ["facing"])
        self.assertEqual(self.model.program.contours, ())

    def test_delete_and_keep_the_blocks(self):
        self.model.delete_contour("contour1", with_blocks=False)
        self.assertEqual(len(self.model.blocks), 2)
        self.assertEqual(self.model.blocks[1].contour_id, NO_CONTOUR)
        self.assertEqual(self.model.program.contours, ())
        self.assertEqual([left.number for left in self.model.analysis.plan.left_out], [2])


class UndoRedoTests(unittest.TestCase):
    def test_undo_and_redo_walk_through_the_changes(self):
        model = AppModel()
        self.assertFalse(model.can_undo)
        model.add_block("facing")
        model.add_block("turning")
        self.assertTrue(model.can_undo)
        self.assertTrue(model.undo())
        self.assertEqual([b.type_name for b in model.blocks], ["facing"])
        self.assertTrue(model.can_redo)
        self.assertTrue(model.redo())
        self.assertEqual(len(model.blocks), 2)
        self.assertFalse(model.can_redo)

    def test_a_new_change_ends_the_redo_chain(self):
        model = AppModel()
        model.add_block("facing")
        model.undo()
        model.add_block("turning")
        self.assertFalse(model.can_redo)
        self.assertEqual([b.type_name for b in model.blocks], ["turning"])

    def test_the_touched_mark_goes_with_its_edit_through_undo_and_redo(self):
        model = AppModel()
        model.add_block("facing")
        owner = model.block_owner(0)
        model.replace_block(0, replace(model.blocks[0], feed_mm_per_rev=0.3))
        model.set_touched(owner, ("feed_mm_per_rev",))
        model.undo()
        self.assertFalse(model.is_touched(owner, ("feed_mm_per_rev",)))
        model.redo()
        self.assertEqual(model.blocks[0].feed_mm_per_rev, 0.3)
        self.assertTrue(model.is_touched(owner, ("feed_mm_per_rev",)))

    def test_undo_at_the_start_does_nothing(self):
        model = AppModel()
        self.assertFalse(model.undo())
        self.assertFalse(model.redo())

    def test_undo_restores_a_deleted_contour_and_the_selection_stays_valid(self):
        model = model_with_contour_block()
        model.set_contour(default_contour(model.program))
        model.undo()
        self.assertEqual(model.program.contours, ())
        model.undo()
        model.undo()
        self.assertEqual(model.blocks, ())
        self.assertIsNone(model.selected)

    def test_opening_or_starting_a_project_clears_the_history(self):
        model = AppModel()
        model.add_block("facing")
        model.new()
        self.assertFalse(model.can_undo)

    def test_listeners_hear_about_undo(self):
        model = AppModel()
        model.add_block("facing")
        calls = []
        model.subscribe(lambda: calls.append(1))
        model.undo()
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
