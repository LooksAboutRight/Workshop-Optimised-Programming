import json
import unittest

from wop.core.lathe.machine import (
    AxisLimits,
    Capability,
    MachineDef,
    MachineError,
    check_extents,
    check_rpm,
)
from wop.core.files.machine_io import machine_from_dict, machine_to_dict
from wop.core.program_model.units import UnitSystem, XInputMode


def lathe() -> MachineDef:
    return MachineDef(
        "test lathe",
        axes=(AxisLimits("X", -5, 100), AxisLimits("Z", -300, 10)),
        min_rpm=50,
        max_rpm=3000,
        spindle_power_kw=5.5,
    )


class DefinitionTests(unittest.TestCase):
    def test_complete_machine_has_nothing_missing(self):
        self.assertEqual(lathe().missing_values(), [])

    def test_missing_values_are_reported(self):
        missing = MachineDef("empty").missing_values()
        self.assertEqual(
            missing,
            ["X axis limits", "Z axis limits", "minimum RPM", "maximum RPM", "spindle power"],
        )

    def test_axis_helpers(self):
        axis = lathe().axis("Z")
        self.assertEqual(axis.travel_mm, 310)
        self.assertEqual(axis.reach_mm, 300)
        self.assertIsNone(lathe().axis("C"))

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(MachineError):
            AxisLimits("X", 10, 10)
        with self.assertRaises(MachineError):
            MachineDef("m", min_rpm=500, max_rpm=100)
        with self.assertRaises(MachineError):
            MachineDef("m", spindle_power_kw=0)
        with self.assertRaises(MachineError):
            MachineDef("m", axes=(AxisLimits("X", 0, 1), AxisLimits("X", 0, 2)))


class CapabilityTests(unittest.TestCase):
    def test_all_capabilities_are_on_by_default(self):
        machine = MachineDef("m")
        for capability in Capability:
            self.assertTrue(machine.has(capability))

    def test_capability_can_be_switched_off(self):
        machine = MachineDef(
            "m", capabilities=frozenset(Capability) - {Capability.CONSTANT_SURFACE_SPEED}
        )
        self.assertFalse(machine.has(Capability.CONSTANT_SURFACE_SPEED))
        self.assertTrue(machine.has(Capability.SPINDLE_SYNC))


class NewerFieldsTests(unittest.TestCase):
    """Requirements M10, M11."""

    def test_spindle_synchronised_moves_are_a_capability_and_on_by_default(self):
        self.assertTrue(MachineDef("m").has(Capability.SPINDLE_SYNC))

    def test_the_off_capability_survives_a_round_trip(self):
        machine = MachineDef(
            "m", capabilities=frozenset(Capability) - {Capability.SPINDLE_SYNC},
        )
        loaded = machine_from_dict(json.loads(json.dumps(machine_to_dict(machine))))
        self.assertEqual(loaded, machine)
        self.assertFalse(loaded.has(Capability.SPINDLE_SYNC))

    def test_a_file_from_before_a_capability_existed_has_it_on(self):
        data = machine_to_dict(MachineDef("m"))
        data["capabilities"] = [c for c in data["capabilities"] if c != Capability.SPINDLE_SYNC.value]
        del data["capabilities_off"]
        loaded = machine_from_dict(data)
        self.assertTrue(loaded.has(Capability.SPINDLE_SYNC))


class FeasibilityTests(unittest.TestCase):
    """Requirement M3."""

    def test_fitting_cut_gives_no_message(self):
        self.assertEqual(check_extents(lathe(), 50, 200), [])
        self.assertEqual(check_rpm(lathe(), 1000), [])

    def test_cut_beyond_the_extents(self):
        self.assertEqual(len(check_extents(lathe(), 150, 200)), 1)
        self.assertEqual(len(check_extents(lathe(), 50, 400)), 1)
        self.assertEqual(len(check_extents(lathe(), 150, 400)), 2)

    def test_rpm_outside_the_limits(self):
        self.assertEqual(len(check_rpm(lathe(), 20)), 1)
        self.assertEqual(len(check_rpm(lathe(), 5000)), 1)

    def test_unknown_limits_are_not_checked(self):
        machine = MachineDef("m")
        self.assertEqual(check_extents(machine, 1000, 1000), [])
        self.assertEqual(check_rpm(machine, 100000), [])


class SaveLoadTests(unittest.TestCase):
    def round_trip(self, machine):
        return machine_from_dict(json.loads(json.dumps(machine_to_dict(machine))))

    def test_round_trip(self):
        machine = lathe()
        self.assertEqual(self.round_trip(machine), machine)

    def test_incomplete_machine_round_trip(self):
        machine = MachineDef("m", unit_system=UnitSystem.IMPERIAL, default_x_mode=XInputMode.RADIUS)
        self.assertEqual(self.round_trip(machine), machine)

    def test_extra_axis_survives(self):
        """Requirement A6."""
        machine = MachineDef("m", axes=(AxisLimits("X", 0, 100), AxisLimits("C", 0, 360)))
        self.assertEqual(self.round_trip(machine).axis("C"), AxisLimits("C", 0, 360))

    def test_switched_off_capability_survives(self):
        machine = MachineDef("m", capabilities=frozenset({Capability.SPINDLE_SYNC}))
        self.assertEqual(self.round_trip(machine).capabilities, machine.capabilities)

    def test_bad_data_is_rejected(self):
        good = machine_to_dict(lathe())
        for mutate in (
            lambda d: d.pop("axes"),
            lambda d: d.update(format=99),
            lambda d: d.update(unit_system="furlong"),
            lambda d: d.update(capabilities=["teleport"]),
            lambda d: d.update(max_rpm="fast"),
        ):
            data = json.loads(json.dumps(good))
            mutate(data)
            with self.subTest(data=data):
                with self.assertRaises(MachineError):
                    machine_from_dict(data)
        with self.assertRaises(MachineError):
            machine_from_dict([1, 2])


if __name__ == "__main__":
    unittest.main()
