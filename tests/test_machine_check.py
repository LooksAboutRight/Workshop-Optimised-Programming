import unittest
from dataclasses import replace

from wop.core.lathe.machine import AxisLimits, Capability, MachineDef

from tests.reference_program import reference_program
from wop.core.blocks.threading import ThreadingBlock
from wop.core.lathe.machine_check import check_against_machine, required_capabilities
from wop.core.program_model.operations import CoolantMode, SpindleMode
from wop.core.program_model.program import plan_program


def machine(without=()):
    return MachineDef(
        "m", axes=(AxisLimits("X", -5, 100), AxisLimits("Z", -300, 10)), min_rpm=50, max_rpm=3000,
        spindle_power_kw=5.5, capabilities=frozenset(Capability) - set(without),
    )


class CapabilityCheckTests(unittest.TestCase):
    def setUp(self):
        self.program = reference_program()
        self.plan = plan_program(self.program)

    def messages(self, mach):
        return [m for m in check_against_machine(self.program, self.plan, mach) if "no " in m and "machine has" in m]

    def test_a_machine_with_every_capability_gives_no_capability_message(self):
        self.assertEqual(self.messages(machine()), [])

    def test_constant_surface_speed_is_checked(self):
        found = self.messages(machine({Capability.CONSTANT_SURFACE_SPEED}))
        self.assertTrue(found)
        self.assertTrue(all("constant surface speed" in m for m in found))

    def test_coolant_is_not_checked(self):
        # a coolant is only a code: the machine just does not act on it when it has none (the user decided)
        self.assertFalse(any("coolant" in m for m in self.messages(machine(set()))))

    def test_threading_needs_spindle_synchronised_moves(self):
        self.assertEqual(ThreadingBlock.required_capabilities, {Capability.SPINDLE_SYNC})
        thread = ThreadingBlock.example("t1", self.program.tools[0].number, self.program.blocks[1].spindle)
        self.assertEqual(
            required_capabilities(replace(thread, coolant=CoolantMode.NONE)) - {Capability.CONSTANT_SURFACE_SPEED},
            {Capability.SPINDLE_SYNC},
        )

    def test_a_block_that_needs_nothing_special_needs_nothing(self):
        block = replace(self.program.blocks[1], coolant=CoolantMode.NONE)  # constant RPM, no coolant
        self.assertEqual(block.spindle.mode, SpindleMode.CONSTANT_RPM)
        self.assertEqual(required_capabilities(block), set())
