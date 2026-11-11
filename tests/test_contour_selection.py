import unittest

from wop.ui.app_model import AppModel


class ContourSelectionTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()

    def test_a_new_contour_is_chosen_and_invalid_until_it_is_drawn(self):
        contour_id = self.model.new_contour()
        self.assertEqual(self.model.selected_contour, contour_id)
        self.assertEqual(self.model.chosen_contour().contour_id, contour_id)
        contour = self.model.program.contour(contour_id)
        self.assertFalse(contour.is_valid)
        self.assertIn("Sketch editor", contour.error)

    def test_the_name_can_be_changed_and_is_one_step_for_undo(self):
        contour_id = self.model.new_contour()
        self.model.rename_contour(contour_id, "Shaft")
        self.assertEqual(self.model.chosen_contour().name, "Shaft")
        self.model.undo()
        self.assertNotEqual(self.model.chosen_contour().name, "Shaft")

    def test_undoing_the_new_contour_clears_the_choice(self):
        self.model.new_contour()
        self.model.undo()
        self.assertIsNone(self.model.selected_contour)
        self.assertIsNone(self.model.chosen_contour())

    def test_choosing_a_block_leaves_the_contour(self):
        self.model.add_block("turning_contour")
        self.model.new_contour()
        self.model.select(0)
        self.assertIsNone(self.model.selected_contour)

    def test_deleting_the_chosen_contour_clears_the_choice(self):
        contour_id = self.model.new_contour()
        self.model.delete_contour(contour_id, with_blocks=False)
        self.assertIsNone(self.model.selected_contour)

    def test_the_picture_of_a_stored_contour_is_valid_svg_also_when_it_is_empty(self):
        import xml.etree.ElementTree as ET

        from wop.ui.contour_picture import contour_svg

        contour_id = self.model.new_contour()
        ET.fromstring(contour_svg(self.model.program.contour(contour_id)))


if __name__ == "__main__":
    unittest.main()
