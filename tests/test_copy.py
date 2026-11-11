import unittest
from dataclasses import replace

from wop.ui.app_model import AppModel, ModelError
from wop.core.program_model.touched import block_owner


class CopyBlockTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.add_block("facing")
        self.model.add_block("turning")
        self.model.replace_block(0, replace(self.model.blocks[0], name="Face"))

    def test_the_copy_stands_right_after_the_original_and_is_selected(self):
        self.model.copy_block(0)
        self.assertEqual([b.type_name for b in self.model.blocks], ["facing", "facing", "turning"])
        self.assertEqual(self.model.selected, 1)
        self.assertEqual(len({b.block_id for b in self.model.blocks}), 3)

    def test_the_copy_has_the_same_values_and_a_title_with_copy(self):
        self.model.copy_block(0)
        first, second = self.model.blocks[0], self.model.blocks[1]
        self.assertEqual(second.name, "Face copy")
        self.assertEqual(replace(second, block_id=first.block_id, name=first.name), first)

    def test_the_touched_marks_are_copied(self):
        self.model.set_touched(block_owner(self.model.blocks[0].block_id), ("feed",), True)
        self.model.copy_block(0)
        self.assertTrue(self.model.is_touched(block_owner(self.model.blocks[1].block_id), ("feed",)))
        self.model.set_touched(block_owner(self.model.blocks[0].block_id), ("feed",), False)
        self.assertTrue(self.model.is_touched(block_owner(self.model.blocks[1].block_id), ("feed",)))

    def test_a_copy_is_one_step_for_undo(self):
        self.model.copy_block(0)
        self.model.undo()
        self.assertEqual(len(self.model.blocks), 2)

    def test_a_copy_is_ticked_for_export(self):
        self.model.copy_block(0)
        self.assertTrue(self.model.is_ticked(1))


class CopyRestMaterialTests(unittest.TestCase):
    def test_a_copy_of_a_roughing_block_makes_no_cut(self):
        from pathlib import Path

        model = AppModel()
        model.open(Path(__file__).parent / "data" / "projects" / "contour_bump_pocket.wop.json")
        model.copy_block(1)
        first, copy = model.analysis.plan.blocks[1], model.analysis.plan.blocks[2]
        self.assertGreater(first.result.removed.area, 0)
        # the same block again makes no cut (the user's rule, 2026-10-22): it may see the material the first one could not reach (the wedge
        # on the falling wall of the pocket, the back of the tool keeps its free angle), but it does not move into it; a note says so
        from wop.core.program_model.operations import ArcMove, LinearMove

        self.assertFalse([op for op in copy.result.operations if isinstance(op, (LinearMove, ArcMove))])
        self.assertLess(copy.result.removed.area, 0.01)
        self.assertTrue(any("cannot reach" in message for message in copy.result.messages))


class CopyContourTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.first = self.model.new_contour()
        self.second = self.model.new_contour()

    def test_the_copy_follows_its_original_and_is_chosen(self):
        new_id = self.model.copy_contour(self.first)
        ids = [c.contour_id for c in self.model.program.contours]
        self.assertEqual(ids, [self.first, new_id, self.second])
        self.assertEqual(self.model.selected_contour, new_id)
        self.assertEqual(self.model.program.contours[1].name, self.model.program.contours[0].name + " copy")

    def test_blocks_keep_the_original(self):
        self.model.add_block("turning_contour")
        index = len(self.model.blocks) - 1
        self.model.replace_block(index, replace(self.model.blocks[index], contour_id=self.first))
        self.model.copy_contour(self.first)
        self.assertEqual(self.model.blocks[index].contour_id, self.first)

    def test_an_unknown_contour_is_refused(self):
        with self.assertRaises(ModelError):
            self.model.copy_contour("nope")


if __name__ == "__main__":
    unittest.main()
