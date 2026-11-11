import unittest

from tests.reference_program import reference_program
from wop.core.program_model.program import plan_program
from wop.ui.app_model import AppModel
from wop.ui.stepper import Stepper


class StepperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = reference_program()
        cls.plan = plan_program(cls.program)
        cls.stepper = Stepper(cls.program, cls.plan)

    def test_every_block_with_moves_has_steps_in_order(self):
        frames = self.stepper.frames
        self.assertGreater(len(frames), 0)
        self.assertEqual([f.index for f in frames], list(range(len(frames))))
        self.assertEqual([f.block_index for f in frames], sorted(f.block_index for f in frames))

    def test_move_numbers_count_within_the_block(self):
        first = self.stepper.first_step_of_block(0)
        frame = self.stepper.frame(first)
        self.assertEqual(frame.move_number, 1)
        last = self.stepper.frame(self.stepper.block_end(first))
        self.assertEqual(last.move_number, last.moves_in_block)

    def test_the_first_move_has_no_start_and_later_ones_start_where_the_last_ended(self):
        self.assertIsNone(self.stepper.frame(0).start)
        self.assertEqual(self.stepper.frame(1).start, self.stepper.frame(0).end)

    def test_the_last_step_of_a_block_shows_the_planned_material(self):
        for block_index, block_plan in enumerate(self.plan.blocks):
            first = self.stepper.first_step_of_block(block_index)
            if first is None:
                continue
            material = self.stepper.material(self.stepper.block_end(first))
            self.assertIs(material, block_plan.residual_after)

    def test_material_only_shrinks_inside_a_block(self):
        first = self.stepper.first_step_of_block(1)
        end = self.stepper.block_end(first)
        before = self.plan.blocks[1].residual_before.area
        previous = before
        for index in range(first, end + 1):
            area = self.stepper.material(index).area
            self.assertLessEqual(area, previous + 1e-6)
            previous = area

    def test_the_background_work_gives_the_same_materials_as_asking_one_by_one(self):
        background = Stepper(self.program, self.plan)
        background.precompute(0)
        self.assertTrue(background.wait_precompute(120))
        self.assertEqual(len(background._materials), background.count)
        lazy = Stepper(self.program, self.plan)
        for index in range(0, lazy.count, max(1, lazy.count // 15)):
            self.assertAlmostEqual(background.material(index).area, lazy.material(index).area)

    def test_the_background_work_starts_at_the_asked_step_and_covers_the_steps_before_it_too(self):
        background = Stepper(self.program, self.plan)
        start = background.count // 2
        background.precompute(start)
        self.assertTrue(background.wait_precompute(120))
        self.assertIn(start, background._materials)
        self.assertIn(0, background._materials)

    def test_a_step_asked_for_during_the_background_work_is_right_and_the_work_can_be_stopped(self):
        background = Stepper(self.program, self.plan)
        background.precompute(0)
        late = background.count - 1
        asked = background.material(late).area  # may be worked out here or by the thread: the same value
        background.stop_precompute()
        self.assertTrue(background.wait_precompute(120))
        self.assertAlmostEqual(asked, Stepper(self.program, self.plan).material(late).area)

    def test_the_background_work_is_limited(self):
        from unittest import mock

        limited = Stepper(self.program, self.plan)
        with mock.patch("wop.ui.stepper.MAX_PRECOMPUTED_STEPS", 5):
            limited.precompute(0)
            self.assertTrue(limited.wait_precompute(120))
        self.assertLess(len(limited._materials), limited.count)

    def test_asking_for_a_late_step_first_gives_the_same_as_going_step_by_step(self):
        fresh = Stepper(self.program, self.plan)
        first = fresh.first_step_of_block(1)
        middle = first + (fresh.block_end(first) - first) // 2
        direct = fresh.material(middle).area
        walked = self.stepper
        for index in range(first, middle + 1):
            walked.material(index)
        self.assertAlmostEqual(direct, walked.material(middle).area)

    def test_the_tool_tip_is_at_the_end_of_the_step(self):
        frame = self.stepper.frame(3)
        body = self.stepper.tool_body(3)
        self.assertFalse(body.is_empty)
        box = body.bounds
        self.assertLessEqual(box.min_z, frame.end.z + 1e-6)
        self.assertGreaterEqual(box.max_z, frame.end.z - 1e-6)

    def test_block_start_and_end_belong_to_the_same_block(self):
        index = self.stepper.count // 2
        block = self.stepper.frame(index).block_index
        self.assertEqual(self.stepper.frame(self.stepper.block_start(index)).block_index, block)
        self.assertEqual(self.stepper.frame(self.stepper.block_end(index)).block_index, block)

    def test_collisions_of_a_move_are_found_by_block_and_operation(self):
        from wop.core.geometry import Point
        from wop.core.verify import Finding, FindingKind

        frame = self.stepper.frame(2)
        mine = Finding(frame.block_index, frame.operation_index, Point(0, 0), FindingKind.GOUGE, "m", "r")
        other = Finding(frame.block_index + 1, frame.operation_index, Point(0, 0), FindingKind.GOUGE, "m", "r")
        self.assertEqual(self.stepper.collisions(2, [mine, other]), [mine])

    def test_no_such_step(self):
        with self.assertRaises(IndexError):
            self.stepper.frame(self.stepper.count)

    def test_text_names_the_block_number_and_tool(self):
        text = self.stepper.frame(0).text
        self.assertIn("Block 1", text)
        self.assertIn("T1", text)


class StepPictureTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.add_block("facing")
        self.model.add_block("turning")

    def test_the_stepper_is_kept_until_the_plan_changes(self):
        first = self.model.stepper()
        self.assertIs(first, self.model.stepper())
        self.model.add_block("turning")
        self.assertIsNot(first, self.model.stepper())

    def test_a_step_picture_has_the_tool_and_fewer_moves_than_the_whole(self):
        stepper = self.model.stepper()
        whole = self.model.picture(with_legend=False)
        early = self.model.picture(step=1, with_legend=False)
        self.assertIn(self.model.colors.tool_cutter, early)
        self.assertNotIn(self.model.colors.tool_cutter, whole)
        self.assertLess(early.count("<polyline"), whole.count("<polyline"))
        self.assertGreater(stepper.count, 2)

    def test_a_step_in_3d_has_the_tool_too(self):
        with_tool = self.model.scene3d(step=1, steps_per_turn=24)
        self.assertTrue(with_tool.fills)
        self.assertEqual(with_tool.fills[0].color, self.model.colors.tool_cutter)
        self.assertEqual(self.model.scene3d(steps_per_turn=24).fills, ())

    def test_a_step_that_does_not_exist_draws_the_normal_picture(self):
        self.assertEqual(self.model.picture(step=10_000), self.model.picture())

    def test_step_view_gives_the_block_of_the_step(self):
        stepper = self.model.stepper()
        last = stepper.count - 1
        self.assertEqual(self.model.step_view(last)[0], stepper.frame(last).block_index)
        self.assertIsNone(self.model.step_view(-1))


if __name__ == "__main__":
    unittest.main()
