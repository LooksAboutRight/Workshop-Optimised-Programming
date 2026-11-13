"""The unit the window shows lengths in (the preference DISPLAY_UNITS), independent of the unit of the G-code.

The program, the files and the planner stay in millimetres; only what is shown and typed in a form or a dimension is
converted. Toolkit-free, so it can be tested.
"""

from __future__ import annotations

import re

from ..core.constants import MM_PER_INCH

MM_PER_METRE = 1000
from . import app_constants
from .ui_constants import DISPLAY_UNIT_INCH, INCH_UNITS, INCHES_PER_FOOT

SIZE_UNITS = tuple(INCH_UNITS)  # the units of a form field that change with the display unit


def is_inch() -> bool:
    return app_constants.DISPLAY_UNITS == DISPLAY_UNIT_INCH


def length_scale(unit: str) -> float:
    """The factor from the stored value to the shown one for a field with this unit (1 when it does not change)."""
    if not is_inch() or unit not in INCH_UNITS:
        return 1
    if unit == "m/min":  # metres to feet
        return MM_PER_METRE / MM_PER_INCH / INCHES_PER_FOOT
    return 1 / MM_PER_INCH


def shown_unit(unit: str) -> str:
    """The unit as written next to a number."""
    return INCH_UNITS[unit] if is_inch() and unit in INCH_UNITS else unit


def to_shown(value: float, unit: str) -> float:
    return value * length_scale(unit)


def from_shown(value: float, unit: str) -> float:
    return value / length_scale(unit)


_LENGTH_IN_TEXT = re.compile(r"(?<![\w.,])(-?\d+(?:\.\d+)?)( ?)(m/min|mm(?:/rev|/min| per rev(?:olution)?| per min(?:ute)?)?)(?![\w²])")


def _inches_text(inches: float) -> str:
    text = f"{inches:.3g}" if abs(inches) >= 0.01 else f"{inches:.2g}"
    return f"{float(text):.6f}".rstrip("0").rstrip(".") or "0"  # no exponent


def shown_text(text: str) -> str:
    """A message with the lengths in it ("0.2 mm", "0.2 mm/rev") in the unit the window shows. Metric: the text as it is.
    Lengths of a range ("1 to 5 mm") and ISO sizes in a text are not told apart: the messages avoid them."""
    if not is_inch() or "mm" not in text:
        return text

    def convert(found: re.Match) -> str:
        unit = found.group(3).replace(" per revolution", "/rev").replace(" per rev", "/rev")
        unit = unit.replace(" per minute", "/min").replace(" per min", "/min")
        return f"{_inches_text(to_shown(float(found.group(1)), unit))}{found.group(2)}{INCH_UNITS.get(unit, unit)}"

    return _LENGTH_IN_TEXT.sub(convert, text)
