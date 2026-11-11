"""A finding names its block and its move as the stepper shows them, and in the stepper its cross appears with that move (the user's
idea, 2026-10-30)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


class FindingMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_collision_demo import demo_model

        cls.model = demo_model()
        cls.analysis = cls.model.verify_now()
        cls.stepper = cls.model.stepper()

    def test_the_move_number_is_the_one_next_to_the_step(self):
        self.assertTrue(self.analysis.findings)
        for finding in self.analysis.findings:
            with self.subTest(finding=finding.message):
                frames = [
                    f for f in self.stepper.frames
                    if f.block_index == finding.block_index and f.operation_index == finding.operation_index
                ]
                self.assertIn(finding.move_number, [f.move_number for f in frames])

    def test_the_text_names_block_and_move(self):
        for finding in self.analysis.findings:
            self.assertIn(f"move {finding.move_number}:", finding.message)
            self.assertIn("radius", finding.message)  # the place stays, behind the move

    def test_in_the_stepper_the_cross_comes_with_its_move(self):
        finding = self.analysis.findings[0]
        frame = next(f for f in self.stepper.frames if f.block_index == finding.block_index and f.move_number == finding.move_number)
        before = frame.index - 1
        self.assertGreaterEqual(before, 0)
        self.assertNotIn(finding.message, self.model.picture(step=before))
        self.assertIn(finding.message, self.model.picture(step=frame.index))


if __name__ == "__main__":
    unittest.main()
