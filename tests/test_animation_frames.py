import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from animation_frames import timeline, count_frames, draw_frame, iter_frames, spindle_rpm
from tests.reference_program import reference_program
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.program import plan_program


class AnimationFramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = reference_program()
        cls.plan = plan_program(cls.program)
        cls.frames = list(iter_frames(cls.program, cls.plan, step_mm=2.0))

    def test_frames_are_numbered_in_order_and_match_the_count(self):
        self.assertEqual([f.number for f in self.frames], list(range(len(self.frames))))
        self.assertEqual(len(self.frames), count_frames(self.program, self.plan, step_mm=2.0))

    def test_a_smaller_step_gives_more_frames(self):
        self.assertGreater(count_frames(self.program, self.plan, 0.5), count_frames(self.program, self.plan, 2.0))

    def test_the_last_frame_of_each_block_shows_the_planned_material(self):
        last = {}
        for frame in self.frames:
            last[frame.block_index] = frame
        for block_index, frame in last.items():
            self.assertIs(frame.material, self.plan.blocks[block_index].residual_after)

    def test_material_never_grows_inside_a_block(self):
        previous = None
        for frame in self.frames:
            if previous is not None and previous.block_index == frame.block_index:
                self.assertLessEqual(frame.material.area, previous.material.area + 1e-6)
            previous = frame

    def test_a_frame_draws_as_svg(self):
        text = draw_frame(self.plan, self.frames[len(self.frames) // 2])
        self.assertIn("<svg", text)

    def test_a_frame_draws_as_a_3d_svg_with_the_tool_and_steps_per_turn_makes_it_coarser(self):
        import xml.etree.ElementTree as ET

        frame = self.frames[len(self.frames) // 2]
        fine = draw_frame(self.plan, frame, view="3d", steps_per_turn=48)
        coarse = draw_frame(self.plan, frame, view="3d", steps_per_turn=24)
        ET.fromstring(fine)
        self.assertLess(coarse.count("<polygon"), fine.count("<polygon"))
        self.assertIn("fill-opacity", fine)  # the tool is drawn see-through
        with self.assertRaises(ValueError):
            draw_frame(self.plan, frame, view="top")

    def test_blocks_option_limits_the_frames(self):
        some = list(iter_frames(self.program, self.plan, 2.0, blocks=range(1)))
        self.assertTrue(some)
        self.assertEqual({f.block_index for f in some}, {0})

    def test_the_cheap_timeline_matches_the_frames(self):
        line = timeline(self.program, self.plan, step_mm=2.0)
        self.assertEqual(len(line), len(self.frames))
        self.assertEqual([b for b, _ in line], [f.block_index for f in self.frames])
        for (_, seconds), frame in zip(line, self.frames):
            self.assertAlmostEqual(seconds, frame.seconds)

    def test_wanted_and_first_number_pick_the_same_frames_of_a_block(self):
        last_block = self.frames[-1].block_index
        in_block = [f for f in self.frames if f.block_index == last_block]
        picked = list(iter_frames(self.program, self.plan, 2.0, blocks=range(last_block, last_block + 1),
                                  first_number=in_block[0].number, wanted={in_block[-1].number}))
        self.assertEqual([f.number for f in picked], [in_block[-1].number])
        self.assertAlmostEqual(picked[0].material.area, in_block[-1].material.area)

    def test_bad_step_is_refused(self):
        with self.assertRaises(ValueError):
            list(iter_frames(self.program, self.plan, step_mm=0))

    def test_rpm_for_both_modes(self):
        self.assertEqual(spindle_rpm(None, 10), 0.0)
        self.assertEqual(spindle_rpm(SpindleSetting(SpindleMode.CONSTANT_RPM, 800), 10), 800)
        css = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120, 1000)
        self.assertEqual(spindle_rpm(css, 0.5), 1000)
        self.assertAlmostEqual(spindle_rpm(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120), 10), 120000 / (2 * 3.141592653589793 * 10), 4)


if __name__ == "__main__":
    unittest.main()
