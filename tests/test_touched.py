import unittest
from dataclasses import replace

from wop.core.program_model.touched import field_key, forget_owner, is_touched, mark_touched, mark_untouched

from tests.test_project import full_project
from wop.core.files.project_io import ProjectError, project_from_dict, project_from_json, project_to_dict, project_to_json
from wop.ui.app_model import AppModel


class TouchedFunctionTests(unittest.TestCase):
    def test_a_field_is_untouched_until_it_is_marked(self):
        touched = ()
        self.assertFalse(is_touched(touched, "raw_part", ("outer_radius_mm",)))
        touched = mark_touched(touched, "raw_part", ("outer_radius_mm",))
        self.assertTrue(is_touched(touched, "raw_part", ("outer_radius_mm",)))
        self.assertFalse(is_touched(touched, "raw_part", ("length_mm",)))

    def test_marking_twice_keeps_one_entry_and_the_order_is_stable(self):
        touched = mark_touched((), "b", ("z",))
        touched = mark_touched(touched, "a", ("x",))
        self.assertEqual(mark_touched(touched, "a", ("x",)), touched)
        self.assertEqual(touched, tuple(sorted(touched)))

    def test_a_nested_path_is_one_key(self):
        self.assertEqual(field_key("b1", ("spindle", "value")), "b1/spindle.value")

    def test_reset_makes_a_field_untouched_again(self):
        touched = mark_touched((), "a", ("x",))
        self.assertEqual(mark_untouched(touched, "a", ("x",)), ())

    def test_without_records_everything_counts_as_touched(self):
        self.assertTrue(is_touched(None, "a", ("x",)))
        self.assertIsNone(mark_touched(None, "a", ("x",)))
        self.assertIsNone(mark_untouched(None, "a", ("x",)))
        self.assertIsNone(forget_owner(None, "a"))

    def test_forgetting_an_owner_drops_only_its_fields(self):
        touched = (field_key("block:b1", ("x",)), field_key("block:b10", ("x",)), field_key("raw_part", ("x",)))
        self.assertEqual(
            forget_owner(touched, "block:b1"),
            (field_key("block:b10", ("x",)), field_key("raw_part", ("x",))),
        )


class TouchedProjectTests(unittest.TestCase):
    def test_the_marks_survive_save_and_load(self):
        project = replace(full_project(), touched=("b1/x", "raw_part/length_mm"))
        self.assertEqual(project_from_json(project_to_json(project)).touched, project.touched)

    def test_a_project_without_records_saves_without_the_key_and_loads_as_none(self):
        data = project_to_dict(full_project())
        self.assertNotIn("touched", data)
        self.assertIsNone(project_from_dict(data).touched)

    def test_an_empty_list_is_kept_as_recording(self):
        data = project_to_dict(replace(full_project(), touched=()))
        self.assertEqual(data["touched"], [])
        self.assertEqual(project_from_dict(data).touched, ())

    def test_a_damaged_list_is_refused(self):
        data = {**project_to_dict(full_project()), "touched": [1, 2]}
        with self.assertRaises(ProjectError):
            project_from_dict(data)


class TouchedModelTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.add_block("facing")
        self.model.dirty = False
        self.owner = self.model.block_owner(0)

    def test_a_new_project_and_a_new_block_are_all_untouched(self):
        self.assertEqual(self.model.project.touched, ())
        self.assertFalse(self.model.is_touched(self.owner, ("feed_mm_per_rev",)))

    def test_marking_touches_the_field_and_the_project_is_changed_but_not_replanned(self):
        calls = []
        self.model.subscribe(lambda: calls.append(1))
        self.model.set_touched(self.owner, ("feed_mm_per_rev",))
        self.assertTrue(self.model.is_touched(self.owner, ("feed_mm_per_rev",)))
        self.assertTrue(self.model.dirty)
        self.assertEqual(calls, [])

    def test_marking_an_already_touched_field_changes_nothing(self):
        self.model.set_touched(self.owner, ("a",))
        self.model.dirty = False
        self.model.set_touched(self.owner, ("a",))
        self.assertFalse(self.model.dirty)

    def test_reset_makes_the_field_untouched_again(self):
        self.model.set_touched(self.owner, ("a",))
        self.model.set_touched(self.owner, ("a",), touched=False)
        self.assertFalse(self.model.is_touched(self.owner, ("a",)))

    def test_a_deleted_block_does_not_hand_its_marks_to_a_new_block(self):
        self.model.set_touched(self.owner, ("feed_mm_per_rev",))
        self.model.delete_block(0)
        self.model.add_block("facing")
        self.assertEqual(self.model.block_owner(0), self.owner)
        self.assertFalse(self.model.is_touched(self.owner, ("feed_mm_per_rev",)))

    def test_marks_follow_a_moved_block(self):
        self.model.add_block("facing")
        self.model.set_touched(self.owner, ("x",))
        self.model.move_block(0, 1)
        self.assertTrue(self.model.is_touched(self.owner, ("x",)))
        self.assertEqual(self.model.block_owner(1), self.owner)

    def test_the_default_object_holds_the_default_values(self):
        from wop.core.program_model.touched import SETUP_OWNER

        setup = self.model.default_object(SETUP_OWNER)
        self.assertEqual(setup, AppModel().setup_form())
        block = self.model.default_object(self.owner)
        self.assertEqual(type(block), type(self.model.blocks[0]))
        self.assertIsNone(self.model.default_object("block:nothing"))

    def test_a_loaded_old_project_counts_as_touched(self):
        self.model.project = replace(self.model.project, touched=None)
        self.assertTrue(self.model.is_touched(self.owner, ("a",)))


class RenameOwnerTests(unittest.TestCase):
    def test_a_renamed_owner_keeps_its_marks_and_others_stay(self):
        from wop.core.program_model.touched import rename_owner

        touched = (field_key("machine:a", ("x",)), field_key("machine:ab", ("x",)))
        self.assertEqual(
            rename_owner(touched, "machine:a", "machine:z"),
            (field_key("machine:ab", ("x",)), field_key("machine:z", ("x",))),
        )
        self.assertIsNone(rename_owner(None, "a", "b"))
