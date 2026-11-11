"""The spindle state through the plan: the stepper shows it, the check finds a cut with the spindle stopped (WH0)."""

import unittest
from dataclasses import replace

from wop.core.program_model.operations import (
    LinearMove,
    SetSpindle,
    SpindleMode,
    SpindleSetting,
    StopSpindle,
    spindle_after,
    spindle_text,
)

from tests.reference_program import reference_program
from wop.core.program_model.program import plan_program
from wop.core.verify import FindingKind, verify_plan
from wop.ui.stepper import Stepper

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1200)
CSS = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 180, 3000)


class SpindleHelperTests(unittest.TestCase):
    def test_only_set_and_stop_change_the_state(self):
        self.assertEqual(spindle_after(None, SetSpindle(RPM)), RPM)
        self.assertIsNone(spindle_after(RPM, StopSpindle()))
        self.assertEqual(spindle_after(RPM, object()), RPM)

    def test_texts(self):
        self.assertEqual(spindle_text(None), "off")
        self.assertEqual(spindle_text(RPM), "1200 rpm")
        self.assertEqual(spindle_text(CSS), "CSS 180 m/min (max 3000 rpm)")


class SpindleInThePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = reference_program()
        cls.plan = plan_program(cls.program)

    def test_every_cutting_step_of_the_reference_program_has_the_spindle_on(self):
        stepper = Stepper(self.program, self.plan)
        cutting = [f for f in stepper.frames if f.is_cutting]
        self.assertTrue(cutting)
        self.assertTrue(all(f.spindle_on for f in cutting))
        self.assertIn("Spindle:", cutting[0].text)

    def test_a_program_starts_with_the_spindle_stopped(self):
        first = Stepper(self.program, self.plan).frame(0)
        self.assertFalse(first.spindle_on)
        self.assertTrue(first.text.endswith("Spindle: off"))

    def test_the_reference_program_has_no_spindle_finding(self):
        kinds = [f.kind for f in verify_plan(self.program, self.plan)]
        self.assertNotIn(FindingKind.SPINDLE_OFF, kinds)

    def test_a_cut_without_a_spindle_start_is_found(self):
        blocks = tuple(
            replace(b, operations=tuple(op for op in b.operations if not isinstance(op, SetSpindle)))
            for b in self.plan.blocks
        )
        broken = replace(self.plan, blocks=blocks)
        findings = [f for f in verify_plan(self.program, broken) if f.kind is FindingKind.SPINDLE_OFF]
        self.assertTrue(findings)
        self.assertIn("spindle stopped", findings[0].message)
        stepper = Stepper(self.program, broken)
        self.assertFalse(any(f.spindle_on for f in stepper.frames if isinstance(f.move, LinearMove)))


if __name__ == "__main__":
    unittest.main()
