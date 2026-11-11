"""Save and load the machine definition as plain data (requirements M1, A6)."""

from __future__ import annotations

from ..constants import DEFAULT_POSTPROCESSOR_ID, MACHINE_FORMAT_VERSION, REMOVED_CAPABILITIES
from ..lathe.machine import AxisLimits, Capability, MachineDef, MachineError
from ..program_model.units import UnitSystem, XInputMode


def machine_to_dict(machine: MachineDef) -> dict:
    return {
        "format": MACHINE_FORMAT_VERSION,
        "name": machine.name,
        "unit_system": machine.unit_system.value,
        "default_x_mode": machine.default_x_mode.value,
        "axes": [
            {"name": axis.name, "min_mm": axis.min_mm, "max_mm": axis.max_mm}
            for axis in machine.axes
        ],
        "min_rpm": machine.min_rpm,
        "max_rpm": machine.max_rpm,
        "spindle_power_kw": machine.spindle_power_kw,
        "max_velocity_x_mm_min": machine.max_velocity_x_mm_min,
        "max_velocity_z_mm_min": machine.max_velocity_z_mm_min,
        "capabilities": sorted(capability.value for capability in machine.capabilities),
        # A capability that is in neither list (a file from before it existed) counts as on.
        "capabilities_off": sorted(c.value for c in Capability if c not in machine.capabilities),
        "postprocessor": machine.postprocessor,
        "change_radius_mm": machine.change_radius_mm,
        "change_z_mm": machine.change_z_mm,
        "machine_change_radius_mm": machine.machine_change_radius_mm,
        "machine_change_z_mm": machine.machine_change_z_mm,
    }


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MachineError(f"expected a number, got {value!r}")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise MachineError(f"expected text, got {value!r}")
    return value


def _capabilities(data: dict) -> frozenset[Capability]:
    on = {Capability(value) for value in data["capabilities"] if value not in REMOVED_CAPABILITIES}
    off = {Capability(value) for value in data.get("capabilities_off", ()) if value not in REMOVED_CAPABILITIES}
    unknown = set(Capability) - on - off  # newer than the file
    return frozenset(on | unknown)


def machine_from_dict(data: dict) -> MachineDef:
    """Rebuild a machine definition. Raises MachineError for wrong data."""
    try:
        if data["format"] != MACHINE_FORMAT_VERSION:
            raise MachineError(f"unsupported machine format {data['format']!r}")
        axes = tuple(
            AxisLimits(
                item["name"],
                _number_or_none(item["min_mm"]),
                _number_or_none(item["max_mm"]),
            )
            for item in data["axes"]
        )
        return MachineDef(
            name=data["name"],
            unit_system=UnitSystem(data["unit_system"]),
            default_x_mode=XInputMode(data["default_x_mode"]),
            axes=axes,
            min_rpm=_number_or_none(data["min_rpm"]),
            max_rpm=_number_or_none(data["max_rpm"]),
            spindle_power_kw=_number_or_none(data["spindle_power_kw"]),
            max_velocity_x_mm_min=_number_or_none(data.get("max_velocity_x_mm_min")),
            max_velocity_z_mm_min=_number_or_none(data.get("max_velocity_z_mm_min")),
            capabilities=_capabilities(data),
            postprocessor=_text(data.get("postprocessor", DEFAULT_POSTPROCESSOR_ID)),
            change_radius_mm=_number_or_none(data.get("change_radius_mm")),
            change_z_mm=_number_or_none(data.get("change_z_mm")),
            machine_change_radius_mm=_number_or_none(data.get("machine_change_radius_mm")),
            machine_change_z_mm=_number_or_none(data.get("machine_change_z_mm")),
        )
    except MachineError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise MachineError(f"invalid machine data: {error!r}") from error
