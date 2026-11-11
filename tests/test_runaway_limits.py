"""A value typed with too many digits (0.0001 for 0.1, 1000000 for 100) must give a clear reason, not a frozen program.

The number boxes allow 0.0001 and 1000000, so these are reachable. Every case here once ran for minutes.
"""

import unittest
from dataclasses import replace
from pathlib import Path

from wop.core.constants import MAX_GROOVE_PLUNGES, MAX_PASS_LEVELS, MAX_SAMPLES_PER_SEGMENT, MAX_THREAD_PASSES
from wop.core.passes import pass_levels

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "blocks"


class PassLevelTests(unittest.TestCase):
    def test_a_reasonable_number_of_passes_is_fine(self):
        self.assertEqual(len(pass_levels(0, 15, 1)), 15)
        self.assertEqual(len(pass_levels(0, 15, 15 / MAX_PASS_LEVELS)), MAX_PASS_LEVELS)

    def test_far_too_many_passes_are_refused_with_a_reason(self):
        with self.assertRaises(ValueError) as caught:
            pass_levels(0, 15, 0.0001)
        self.assertIn("depth of cut", str(caught.exception))


class SampleLimitTests(unittest.TestCase):
    def test_a_move_of_a_million_millimetres_is_refused(self):
        from wop.core.geometry import LineSegment, Point
        from wop.core.reach import sample_segments

        self.assertEqual(len(sample_segments([LineSegment(Point(0, 0), Point(0, -100))], 0.5)), 201)
        with self.assertRaises(ValueError) as caught:
            sample_segments([LineSegment(Point(0, 0), Point(0, -1_000_000))], 0.5)
        self.assertIn("Preferences", str(caught.exception))
        self.assertGreater(1_000_000 / 0.5, MAX_SAMPLES_PER_SEGMENT)


class BlocksAreLeftOutWithAReasonTests(unittest.TestCase):
    def left_out(self, example, **changes):
        from wop.core.program_model.program import plan_program
        from wop.core.files.project_io import project_from_json

        program = project_from_json((EXAMPLES / f"{example}.wop.json").read_text(encoding="utf-8")).program
        index = [i for i, block in enumerate(program.blocks) if block.type_name == example][0]
        block = replace(program.blocks[index], **changes)
        plan = plan_program(replace(program, blocks=program.blocks[:index] + (block,) + program.blocks[index + 1:]))
        return plan.left_out

    def assert_left_out(self, example, **changes):
        left = self.left_out(example, **changes)
        self.assertEqual(len(left), 1, changes)
        self.assertTrue(left[0].reason)
        return left[0].reason

    def test_a_groove_a_million_wide(self):
        self.assertIn(str(MAX_GROOVE_PLUNGES), self.assert_left_out("grooving", width_mm=1_000_000))

    def test_a_groove_with_pecks_of_a_tenth_of_a_micron(self):
        self.assertIn("peck", self.assert_left_out("grooving", peck_depth_mm=0.0001))

    def test_a_finishing_allowance_as_large_as_the_groove(self):
        self.assertIn("allowance", self.assert_left_out("grooving", finish_allowance_mm=1_000_000))
        self.assertIn("allowance", self.assert_left_out("grooving", finish_allowance_mm=2))  # the example groove is 4 wide

    def test_a_thread_with_too_many_passes(self):
        self.assertIn(str(MAX_THREAD_PASSES), self.assert_left_out("threading", first_cut_depth_mm=0.0001))
        self.assertIn(str(MAX_THREAD_PASSES), self.assert_left_out("threading", degression=1_000_000))
        self.assertIn("spring", self.assert_left_out("threading", spring_passes=1_000_000))

    def test_a_thread_a_million_millimetres_long(self):
        self.assert_left_out("threading", start_z_mm=1_000_000)

    def test_facing_with_an_overtravel_of_a_million(self):
        self.assert_left_out("facing", overtravel_mm=1_000_000)

    def test_the_normal_examples_are_not_left_out(self):
        for name in ("grooving", "threading", "facing", "turning", "drilling"):
            with self.subTest(block=name):
                self.assertEqual(self.left_out(name), ())


if __name__ == "__main__":
    unittest.main()
