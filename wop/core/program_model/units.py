"""Unit and radius/diameter handling (requirements B7, M6).

Internally everything is millimetres and radius. Conversion happens only at
the boundary: user input, display, files and G-code.
"""

from enum import Enum

from ..constants import MM_PER_INCH


class UnitSystem(Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class XInputMode(Enum):
    """How an X position is typed in and shown (the Dia./Rad. toggle)."""

    RADIUS = "radius"
    DIAMETER = "diameter"


def length_to_mm(value: float, unit: UnitSystem) -> float:
    """Convert a length in the given unit system to millimetres."""
    if unit is UnitSystem.IMPERIAL:
        return value * MM_PER_INCH
    return value


def length_from_mm(value_mm: float, unit: UnitSystem) -> float:
    """Convert a length in millimetres to the given unit system."""
    if unit is UnitSystem.IMPERIAL:
        return value_mm / MM_PER_INCH
    return value_mm
