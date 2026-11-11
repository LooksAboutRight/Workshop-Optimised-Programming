"""Machine definition (requirements M1, M3, M7, A6).

Values that are not known are None; missing_values() lists them so the user
can be asked. Capabilities: the user switches off what the machine lacks.
A new capability is one new entry in the Capability enum (plus the
postprocessor feature list).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..constants import DEFAULT_POSTPROCESSOR_ID
from ..program_model.units import UnitSystem, XInputMode


class MachineError(ValueError):
    """The machine data is not usable."""


class Capability(Enum):
    CONSTANT_SURFACE_SPEED = "constant surface speed"
    SPINDLE_SYNC = "spindle-synchronised moves"  # needed for threading (M10)
    # later: SUB_SPINDLE, LIVE_TOOLING


@dataclass(frozen=True)
class AxisLimits:
    """Travel limits of one axis in machine coordinates, in mm (X as radius)."""

    name: str
    min_mm: float
    max_mm: float

    def __post_init__(self) -> None:
        if not self.name:
            raise MachineError("an axis needs a name")
        if self.max_mm <= self.min_mm:
            raise MachineError(f"axis {self.name}: maximum must be greater than minimum")

    @property
    def travel_mm(self) -> float:
        return self.max_mm - self.min_mm

    @property
    def reach_mm(self) -> float:
        """Largest distance from the zero position in either direction."""
        return max(abs(self.min_mm), abs(self.max_mm))


X_AXIS = "X"
Z_AXIS = "Z"


@dataclass(frozen=True)
class MachineDef:
    name: str
    unit_system: UnitSystem = UnitSystem.METRIC
    default_x_mode: XInputMode = XInputMode.DIAMETER  # default for input and G-code mode
    axes: tuple[AxisLimits, ...] = ()
    min_rpm: float | None = None
    max_rpm: float | None = None
    spindle_power_kw: float | None = None
    max_velocity_x_mm_min: float | None = None  # fastest move of the X axis (radial), mm/min; None: not known
    max_velocity_z_mm_min: float | None = None
    capabilities: frozenset[Capability] = field(default_factory=lambda: frozenset(Capability))
    # What belongs to the machine and not to one part (the controller, the turret position).
    postprocessor: str = DEFAULT_POSTPROCESSOR_ID  # id of the postprocessor (O7)
    change_radius_mm: float | None = None  # the tool change position X (radius); None: follows the part
    change_z_mm: float | None = None  # ... and Z; None: follows the part
    # The tool change position in MACHINE coordinates (G53): the post moves there before every tool change, whatever the work offset is.
    machine_change_radius_mm: float | None = None  # X (radius); None: the post writes no machine move
    machine_change_z_mm: float | None = None

    def __post_init__(self) -> None:
        names = [axis.name for axis in self.axes]
        if len(set(names)) != len(names):
            raise MachineError("an axis is listed twice")
        for label, value in (("minimum RPM", self.min_rpm), ("maximum RPM", self.max_rpm)):
            if value is not None and value < 0:
                raise MachineError(f"{label} must not be negative")
        if self.min_rpm is not None and self.max_rpm is not None and self.min_rpm > self.max_rpm:
            raise MachineError("minimum RPM is greater than maximum RPM")
        if self.spindle_power_kw is not None and self.spindle_power_kw <= 0:
            raise MachineError("spindle power must be greater than zero")
        for label, value in (("X", self.max_velocity_x_mm_min), ("Z", self.max_velocity_z_mm_min)):
            if value is not None and value <= 0:
                raise MachineError(f"the maximum velocity of {label} must be greater than zero")

    def axis(self, name: str) -> AxisLimits | None:
        for axis in self.axes:
            if axis.name == name:
                return axis
        return None

    def has(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def missing_values(self) -> list[str]:
        """Names of the required values that are not set (requirement M1)."""
        missing = []
        if self.axis(X_AXIS) is None:
            missing.append("X axis limits")
        if self.axis(Z_AXIS) is None:
            missing.append("Z axis limits")
        if self.min_rpm is None:
            missing.append("minimum RPM")
        if self.max_rpm is None:
            missing.append("maximum RPM")
        if self.spindle_power_kw is None:
            missing.append("spindle power")
        return missing


def check_extents(machine: MachineDef, max_radius_mm: float, z_span_mm: float) -> list[str]:
    """Messages if a cut cannot fit the machine (requirement M3).

    Approximate: work offsets are unknown, so sizes are compared with the
    axis reach (X) and travel (Z). Unknown limits are not checked.
    """
    messages = []
    x_axis = machine.axis(X_AXIS)
    if x_axis is not None and max_radius_mm > x_axis.reach_mm:
        messages.append(
            f"radius {max_radius_mm:g} mm is beyond the X reach of {x_axis.reach_mm:g} mm"
        )
    z_axis = machine.axis(Z_AXIS)
    if z_axis is not None and z_span_mm > z_axis.travel_mm:
        messages.append(
            f"length {z_span_mm:g} mm is beyond the Z travel of {z_axis.travel_mm:g} mm"
        )
    return messages


def check_feed_speed(machine: MachineDef, speed_mm_min: float, x_share: float, z_share: float) -> list[str]:
    """Messages if a feed move is faster than an axis can go. `x_share` and `z_share` are the parts (0..1) of the
    move along X and Z; unknown velocities are not checked."""
    messages = []
    for label, limit, share in (
        ("X", machine.max_velocity_x_mm_min, x_share),
        ("Z", machine.max_velocity_z_mm_min, z_share),
    ):
        along = speed_mm_min * share
        if limit is not None and along > limit:
            messages.append(f"the feed moves at {along:.0f} mm/min along {label}, the machine's maximum is {limit:.0f} mm/min")
    return messages


def check_rpm(machine: MachineDef, rpm: float) -> list[str]:
    """Messages if the spindle speed is outside the machine limits (requirement M3)."""
    messages = []
    if machine.min_rpm is not None and rpm < machine.min_rpm:
        messages.append(f"{rpm:g} RPM is below the minimum of {machine.min_rpm:g} RPM")
    if machine.max_rpm is not None and rpm > machine.max_rpm:
        messages.append(f"{rpm:g} RPM is above the maximum of {machine.max_rpm:g} RPM")
    return messages
