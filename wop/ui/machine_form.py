"""The machine as one flat form (requirements M1, M7, M9, M10, M11), without any GUI toolkit.

`MachineDef` holds axes as a list and capabilities as a set; the form needs one field per value.
`MachineForm` has them (the form fields are made from the dataclass, see block_forms.py) and
the two functions turn one into the other. Values the user has not given are None.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..core.constants import DEFAULT_POSTPROCESSOR_ID
from ..core.lathe.machine import X_AXIS, Z_AXIS, AxisLimits, Capability, MachineDef, MachineError
from ..core.program_model.units import UnitSystem, XInputMode

DEFAULT_MACHINE_NAME = "New machine"
# MachineDef field name -> the MachineForm fields it fills (for "imported values count as touched", U6)
FORM_FIELDS_OF = {
    "name": ("name",),
    "unit_system": ("unit_system",),
    "default_x_mode": ("default_x_mode",),
    "axes": ("x_min_mm", "x_max_mm", "z_min_mm", "z_max_mm"),
    "min_rpm": ("spindle_min_rpm",),
    "max_rpm": ("spindle_max_rpm",),
    "spindle_power_kw": ("spindle_power_kw",),
    "max_velocity_x_mm_min": ("x_max_velocity_mm_min",),
    "max_velocity_z_mm_min": ("z_max_velocity_mm_min",),
    "capabilities": (
        "constant_surface_speed",
        "spindle_synchronised_moves",
    ),
    "postprocessor": ("postprocessor",),
    "change_radius_mm": ("change_radius_mm",),
    "change_z_mm": ("change_z_mm",),
    "machine_change_radius_mm": ("machine_change_radius_mm",),
    "machine_change_z_mm": ("machine_change_z_mm",),
}
CAPABILITY_FIELDS = (
    (Capability.CONSTANT_SURFACE_SPEED, "constant_surface_speed"),
    (Capability.SPINDLE_SYNC, "spindle_synchronised_moves"),
)


@dataclass(frozen=True)
class MachineForm:
    name: str = DEFAULT_MACHINE_NAME
    unit_system: UnitSystem = UnitSystem.METRIC
    default_x_mode: XInputMode = XInputMode.DIAMETER
    x_min_mm: float | None = None  # X limits are radii
    x_max_mm: float | None = None
    z_min_mm: float | None = None
    z_max_mm: float | None = None
    spindle_min_rpm: float | None = None
    spindle_max_rpm: float | None = None
    spindle_power_kw: float | None = None
    x_max_velocity_mm_min: float | None = None  # fastest move of the axes (X radial), from the ini when it is read
    z_max_velocity_mm_min: float | None = None
    constant_surface_speed: bool = True
    spindle_synchronised_moves: bool = True
    postprocessor: str = DEFAULT_POSTPROCESSOR_ID  # the controller the G-code is written for
    change_radius_mm: float | None = None  # tool change position X radius; empty: follows the part
    change_z_mm: float | None = None  # tool change position Z; empty: follows the part
    machine_change_radius_mm: float | None = None  # tool change position in machine coordinates (G53), X radius; empty: no machine move
    machine_change_z_mm: float | None = None  # ... and Z


def form_from_machine(machine: MachineDef) -> MachineForm:
    x_axis, z_axis = machine.axis(X_AXIS), machine.axis(Z_AXIS)
    capabilities = {field: machine.has(capability) for capability, field in CAPABILITY_FIELDS}
    return MachineForm(
        name=machine.name,
        unit_system=machine.unit_system,
        default_x_mode=machine.default_x_mode,
        x_min_mm=None if x_axis is None else x_axis.min_mm,
        x_max_mm=None if x_axis is None else x_axis.max_mm,
        z_min_mm=None if z_axis is None else z_axis.min_mm,
        z_max_mm=None if z_axis is None else z_axis.max_mm,
        spindle_min_rpm=machine.min_rpm,
        spindle_max_rpm=machine.max_rpm,
        spindle_power_kw=machine.spindle_power_kw,
        x_max_velocity_mm_min=machine.max_velocity_x_mm_min,
        z_max_velocity_mm_min=machine.max_velocity_z_mm_min,
        postprocessor=machine.postprocessor,
        change_radius_mm=machine.change_radius_mm,
        change_z_mm=machine.change_z_mm,
        machine_change_radius_mm=machine.machine_change_radius_mm,
        machine_change_z_mm=machine.machine_change_z_mm,
        **capabilities,
    )


def _axis(letter: str, low: float | None, high: float | None) -> list[AxisLimits]:
    if low is None and high is None:
        return []
    if low is None or high is None:
        raise MachineError(f"axis {letter}: give both limits, or none")
    return [AxisLimits(letter, low, high)]


def machine_from_form(form: MachineForm, base: MachineDef | None = None) -> MachineDef:
    """The machine the form describes. `base` supplies what the form does not show (extra axes).

    Raises MachineError for values that cannot be a machine.
    """
    name = form.name.strip()
    if not name:
        raise MachineError("a machine needs a name")
    others = [axis for axis in (base.axes if base else ()) if axis.name not in (X_AXIS, Z_AXIS)]
    axes = tuple(_axis(X_AXIS, form.x_min_mm, form.x_max_mm) + _axis(Z_AXIS, form.z_min_mm, form.z_max_mm) + others)
    capabilities = frozenset(
        capability for capability, field in CAPABILITY_FIELDS if getattr(form, field)
    )
    return replace(
        base or MachineDef(name),
        name=name,
        unit_system=form.unit_system,
        default_x_mode=form.default_x_mode,
        axes=axes,
        min_rpm=form.spindle_min_rpm,
        max_rpm=form.spindle_max_rpm,
        spindle_power_kw=form.spindle_power_kw,
        max_velocity_x_mm_min=form.x_max_velocity_mm_min,
        max_velocity_z_mm_min=form.z_max_velocity_mm_min,
        capabilities=capabilities,
        postprocessor=form.postprocessor,
        change_radius_mm=form.change_radius_mm,
        change_z_mm=form.change_z_mm,
        machine_change_radius_mm=form.machine_change_radius_mm,
        machine_change_z_mm=form.machine_change_z_mm,
    )


def touched_form_fields(found: frozenset[str], machine: MachineDef) -> tuple[str, ...]:
    """The form fields an import filled with real values (U6): the names `found` maps to, where a value is set."""
    form = form_from_machine(machine)
    fields = []
    for name in sorted(found):
        for field in FORM_FIELDS_OF.get(name, ()):
            if name != "axes" or getattr(form, field) is not None:
                fields.append(field)
    return tuple(fields)
