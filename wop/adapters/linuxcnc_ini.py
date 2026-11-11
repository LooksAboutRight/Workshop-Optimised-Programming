"""Read the machine definition from a LinuxCNC ini file (requirement M2).

Values that are not in the ini stay None in the machine definition (the user
is asked for them), and a note says what was assumed. Key names follow the
LinuxCNC 2.9 documentation and still have to be checked against the ini of
the real machine.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from wop.core.lathe.machine import AxisLimits, MachineDef
from wop.core.program_model.units import UnitSystem, XInputMode, length_to_mm

from . import linuxcnc_constants as names


class IniError(ValueError):
    """The ini file cannot be read."""


@dataclass(frozen=True)
class IniReading:
    machine: MachineDef
    notes: tuple[str, ...]  # what was missing or assumed, for the user
    found: frozenset[str] = frozenset()  # names of the MachineDef fields the ini really gave (not assumed)


def _parse(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(
        strict=False, interpolation=None, allow_no_value=True, inline_comment_prefixes=("#", ";")
    )
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise IniError(f"cannot read the ini file: {error}") from error
    return parser


def _get(parser: configparser.ConfigParser, section: str, key: str) -> str | None:
    if not parser.has_section(section):
        return None
    value = parser.get(section, key, fallback=None)
    return value.strip() if value else None


def _float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _units(parser, notes: list[str], found: set[str]) -> UnitSystem:
    text = _get(parser, names.INI_SECTION_TRAJ, names.INI_KEY_LINEAR_UNITS)
    if text is not None:
        if text.lower() in names.INI_METRIC_NAMES:
            found.add("unit_system")
            return UnitSystem.METRIC
        if text.lower() in names.INI_IMPERIAL_NAMES:
            found.add("unit_system")
            return UnitSystem.IMPERIAL
    notes.append("linear units not found in the ini: metric assumed")
    return UnitSystem.METRIC


def _x_mode(parser, notes: list[str], found: set[str]) -> XInputMode:
    code = _get(parser, names.INI_SECTION_RS274NGC, names.INI_KEY_STARTUP_CODE) or ""
    words = code.upper().split()
    if names.INI_DIAMETER_CODE in words:
        found.add("default_x_mode")
        return XInputMode.DIAMETER
    if names.INI_RADIUS_CODE in words:
        found.add("default_x_mode")
        return XInputMode.RADIUS
    notes.append("no G7 or G8 in the startup code: radius mode (LinuxCNC default) assumed")
    return XInputMode.RADIUS


def _axes(parser, unit: UnitSystem, notes: list[str]) -> tuple[AxisLimits, ...]:
    coordinates = (
        _get(parser, names.INI_SECTION_TRAJ, names.INI_KEY_COORDINATES)
        or names.INI_DEFAULT_COORDINATES
    )
    axes = []
    # 'X Z' and 'XZ' are both used in real ini files.
    for letter in "".join(coordinates.upper().split()):
        section = names.INI_AXIS_SECTION_PREFIX + letter
        low = _float(_get(parser, section, names.INI_KEY_MIN_LIMIT))
        high = _float(_get(parser, section, names.INI_KEY_MAX_LIMIT))
        if low is None or high is None or high <= low:
            notes.append(f"no usable limits for axis {letter} in the ini")
            continue
        axes.append(AxisLimits(letter, length_to_mm(low, unit), length_to_mm(high, unit)))
    return tuple(axes)


def _velocity(parser, unit: UnitSystem, letter: str, notes: list[str]) -> float | None:
    """The fastest move of an axis in mm/min (the ini has units per second)."""
    value = _float(_get(parser, names.INI_AXIS_SECTION_PREFIX + letter, names.INI_KEY_MAX_VELOCITY))
    if value is None or value <= 0:
        notes.append(f"no maximum velocity for axis {letter} in the ini")
        return None
    return length_to_mm(value, unit) * names.INI_SECONDS_PER_MINUTE


def machine_from_ini_text(text: str, name: str) -> IniReading:
    parser = _parse(text)
    notes: list[str] = []
    found: set[str] = set()
    unit = _units(parser, notes, found)
    x_mode = _x_mode(parser, notes, found)
    axes = _axes(parser, unit, notes)
    if axes:
        found.add("axes")
    min_rpm = _float(_get(parser, names.INI_SECTION_SPINDLE, names.INI_KEY_MIN_RPM))
    max_rpm = _float(_get(parser, names.INI_SECTION_SPINDLE, names.INI_KEY_MAX_RPM))
    if min_rpm is None or max_rpm is None or min_rpm > max_rpm:
        notes.append("spindle speed limits not found in the ini")
        min_rpm = max_rpm = None
    else:
        found.update(("min_rpm", "max_rpm"))
    notes.append("spindle power is not in the ini: please enter it")
    velocity_x, velocity_z = _velocity(parser, unit, "X", notes), _velocity(parser, unit, "Z", notes)
    if velocity_x is not None:
        found.add("max_velocity_x_mm_min")
    if velocity_z is not None:
        found.add("max_velocity_z_mm_min")
    machine = MachineDef(
        name=name, unit_system=unit, default_x_mode=x_mode, axes=axes,
        min_rpm=min_rpm, max_rpm=max_rpm,
        max_velocity_x_mm_min=velocity_x, max_velocity_z_mm_min=velocity_z,
    )
    return IniReading(machine, tuple(notes), frozenset(found))


def read_machine_from_ini(path: Path, name: str | None = None) -> IniReading:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return machine_from_ini_text(text, name or Path(path).stem)
