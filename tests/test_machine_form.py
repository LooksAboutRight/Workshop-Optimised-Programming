import unittest

from wop.core.lathe.machine import AxisLimits, Capability, MachineDef, MachineError
from wop.core.program_model.units import UnitSystem, XInputMode
from wop.ui.block_forms import FieldKind, form_for
from wop.ui.machine_form import (
    MachineForm,
    form_from_machine,
    machine_from_form,
    touched_form_fields,
)


def lathe() -> MachineDef:
    return MachineDef(
        "lathe", unit_system=UnitSystem.IMPERIAL, default_x_mode=XInputMode.RADIUS,
        axes=(AxisLimits("X", -5, 100), AxisLimits("Z", -300, 10)), min_rpm=50, max_rpm=3000,
        spindle_power_kw=5.5, capabilities=frozenset({Capability.SPINDLE_SYNC}),
    )


class MachineFormTests(unittest.TestCase):
    def test_a_machine_survives_the_trip_through_the_form(self):
        self.assertEqual(machine_from_form(form_from_machine(lathe())), lathe())

    def test_an_empty_form_is_a_machine_with_nothing_given(self):
        machine = machine_from_form(MachineForm())
        self.assertEqual(machine.name, "New machine")
        self.assertEqual(machine.axes, ())
        self.assertEqual(len(machine.missing_values()), 5)

    def test_one_limit_of_an_axis_is_refused_until_the_other_is_given(self):
        with self.assertRaises(MachineError):
            machine_from_form(MachineForm(x_min_mm=0))
        self.assertEqual(machine_from_form(MachineForm(x_min_mm=0, x_max_mm=50)).axis("X").max_mm, 50)

    def test_bad_values_are_refused(self):
        for form in (MachineForm(name="  "), MachineForm(x_min_mm=5, x_max_mm=1),
                     MachineForm(spindle_min_rpm=500, spindle_max_rpm=100), MachineForm(spindle_power_kw=0)):
            with self.subTest(form=form):
                with self.assertRaises(MachineError):
                    machine_from_form(form)

    def test_axes_the_form_does_not_show_are_kept(self):
        base = MachineDef("m", axes=(AxisLimits("X", 0, 10), AxisLimits("C", 0, 360)))
        edited = machine_from_form(MachineForm(name="m", x_min_mm=0, x_max_mm=20), base)
        self.assertEqual(edited.axis("C"), AxisLimits("C", 0, 360))
        self.assertEqual(edited.axis("X").max_mm, 20)

    def test_every_capability_has_a_field(self):
        form = form_from_machine(MachineDef("m"))
        machine = machine_from_form(form)
        self.assertEqual(machine.capabilities, frozenset(Capability))

    def test_the_form_has_the_fields_the_user_needs(self):
        specs = {spec.path[0]: spec for spec in form_for(MachineForm())}
        self.assertEqual(specs["unit_system"].kind, FieldKind.CHOICE)
        self.assertEqual(specs["x_min_mm"].kind, FieldKind.OPTIONAL_FLOAT)
        self.assertEqual(specs["spindle_min_rpm"].unit, "RPM")
        self.assertEqual(specs["spindle_power_kw"].unit, "kW")
        self.assertEqual(specs["spindle_synchronised_moves"].kind, FieldKind.BOOL)

    def test_an_import_touches_the_fields_it_filled(self):
        machine = MachineDef("m", axes=(AxisLimits("X", 0, 10),), min_rpm=1, max_rpm=2)
        touched = touched_form_fields(frozenset({"axes", "min_rpm", "max_rpm"}), machine)
        self.assertEqual(set(touched), {"x_min_mm", "x_max_mm", "spindle_min_rpm", "spindle_max_rpm"})
        self.assertEqual(touched_form_fields(frozenset(), machine), ())
