"""Designation codes of tool holders: ISO 5608 (rectangular shank) and ISO 6261 (boring bars).

Holder: "PCLNR 2525 M12" = clamping P, insert shape C, style L, clearance N, hand R, shank 25 x 25, length M, insert size 12
(an optional tolerance letter and a "-" manufacturer code are accepted and ignored).
Boring bar: "S25S-PCLNR 12" = type S, diameter 25, length S, clamping P, shape C, style L, clearance N, hand R, insert size 12
(an optional "-" and two digits for the flats are accepted and ignored).
Insert shape, clearance and size are the codes of ISO 1832 (see insert_designation.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..constants import (
    BORING_BARS,
    BORING_STYLES,
    BORING_TYPES,
    FLAT_ANGLE_DEG,
    HOLDER_CLAMPING,
    HOLDER_HANDS,
    HOLDER_LENGTHS_MM,
    HOLDER_MIN_SECONDARY_ANGLE_DEG,
    HOLDER_OFFSET_F_MM,
    HOLDER_SECTION_DIGITS,
    HOLDER_SECTIONS,
    HOLDER_STRAIGHT_F_FACTOR,
    HOLDER_STYLE_SECTIONS,
    HOLDER_STYLES,
    INSERT_CLEARANCES,
    INSERT_INSCRIBED_CIRCLES_MM,
    INSERT_SHAPES_SUPPORTED,
    INSERT_SIZE_ROUNDING_MM,
)
from .tool import ToolError

_HOLDER = re.compile(r"^([A-Z])([A-Z])([A-Z])([A-Z])([RLN])(\d{2})(\d{2})([A-Z])(\d{2})([A-Z])?(?:-([A-Z0-9]{1,3}))?$")
_BAR = re.compile(r"^([A-Z])(\d{2})([A-Z])-?([A-Z])([A-Z])([A-Z])([A-Z])([RLN])(\d{2})(?:-?(\d{2}))?$")


class HolderError(ToolError):
    """A holder code is wrong; the message names the position."""


@dataclass(frozen=True)
class HolderParts:
    """The parts of a rectangular holder code (ISO 5608)."""

    clamping: str
    shape: str
    style: str
    clearance: str
    hand: str
    section: str  # height and width, "2525"
    length: str
    size: str  # insert size code, "12"


@dataclass(frozen=True)
class BarParts:
    """The parts of a boring bar code (ISO 6261)."""

    bar_type: str
    diameter: str  # "25"
    length: str
    clamping: str
    shape: str
    style: str
    clearance: str
    hand: str
    size: str


# --- lookups ---------------------------------------------------------------------------


def _row(table: tuple, key: str):
    return next((row for row in table if row[0] == key), None)


def style_row(letter: str) -> tuple:
    row = _row(HOLDER_STYLES, letter)
    if row is None:
        raise HolderError(f"'{letter}' is not a holder style letter")
    return row


def style_label(letter: str) -> str:
    row = _row(HOLDER_STYLES, letter)
    if row is None:
        return letter
    _l, kappa, offset, cutting = row
    return f"{letter} - {kappa:g} deg, {'offset' if offset else 'straight'} shank, {cutting}"


def bar_style_row(letter: str) -> tuple:
    row = _row(BORING_STYLES, letter)
    if row is None:
        raise HolderError(f"'{letter}' is not a boring bar style letter (known here: {', '.join(r[0] for r in BORING_STYLES)})")
    return row


def length_mm(letter: str) -> float:
    row = _row(HOLDER_LENGTHS_MM, letter)
    if row is None:
        raise HolderError(f"'{letter}' is not a tool length letter")
    return row[1]


def sections_for(style: str) -> tuple[str, ...]:
    """The standard shank sizes of a style; every size when the style has no standard sizes."""
    row = _row(HOLDER_STYLE_SECTIONS, style)
    return HOLDER_SECTIONS if row is None else row[1]


def section_size(section: str) -> tuple[int, int]:
    """(height h, width b) in mm of a section code such as "2525"."""
    if len(section) != 2 * HOLDER_SECTION_DIGITS or not section.isdigit():
        raise HolderError(f"'{section}' is not a shank size (four digits: height and width)")
    return int(section[:HOLDER_SECTION_DIGITS]), int(section[HOLDER_SECTION_DIGITS:])


def offset_f_mm(width_mm: float, offset: bool) -> float:
    """Dimension f: from the tip to the far side of the shank (guessed, see constants)."""
    if not offset:
        return width_mm * HOLDER_STRAIGHT_F_FACTOR
    row = next((r for r in HOLDER_OFFSET_F_MM if r[0] == width_mm), None)
    if row is None:
        raise HolderError(f"no f dimension known for a shank {width_mm:g} mm wide")
    return row[1]


def secondary_angle_deg(kappa_deg: float, tip_angle_deg: float) -> float:
    """The end cutting edge angle: what is left of the straight angle after the edge angle and the insert tip."""
    return FLAT_ANGLE_DEG - kappa_deg - tip_angle_deg


def shape_fits(kappa_deg: float, shape_letter: str) -> bool:
    row = _row(INSERT_SHAPES_SUPPORTED, shape_letter)
    return row is not None and secondary_angle_deg(kappa_deg, row[2]) >= HOLDER_MIN_SECONDARY_ANGLE_DEG


def shapes_for_kappa(kappa_deg: float) -> tuple[str, ...]:
    """The supported insert shapes that fit a holder with this edge angle."""
    return tuple(row[0] for row in INSERT_SHAPES_SUPPORTED if shape_fits(kappa_deg, row[0]))


def insert_size_codes(shape_letter: str) -> tuple[str, ...]:
    """The size codes (edge length in mm, two digits) of the standard inscribed circles for an insert shape."""
    row = _row(INSERT_SHAPES_SUPPORTED, shape_letter)
    if row is None:
        return ()
    codes = {f"{int(circle * row[-1] + INSERT_SIZE_ROUNDING_MM):0{HOLDER_SECTION_DIGITS}d}" for circle in INSERT_INSCRIBED_CIRCLES_MM}
    return tuple(sorted(codes))


def bar_row(diameter_mm: int) -> tuple[int, int, int]:
    row = next((r for r in BORING_BARS if r[0] == diameter_mm), None)
    if row is None:
        raise HolderError(f"'{diameter_mm}' is not a standard boring bar diameter")
    return row


# --- reading and writing the codes ----------------------------------------------------------------


def _checked(table: tuple, key: str, position: str, what: str) -> None:
    if _row(table, key) is None:
        raise HolderError(f"{position}: '{key}' is not a {what}")


def parse_holder_code(text: str) -> HolderParts:
    """Read an ISO 5608 code of a rectangular holder. Raises HolderError."""
    compact = "".join(text.upper().split())
    match = _HOLDER.match(compact)
    if match is None:
        raise HolderError(
            "the holder code must look like PCLNR 2525 M12 (clamping, insert shape, style, clearance, hand, "
            "height and width, length, insert size)"
        )
    clamping, shape, style, clearance, hand, height, width, length, size, *_optional = match.groups()
    _checked(HOLDER_CLAMPING, clamping, "clamping", "clamping letter (C, M, P, S)")
    _checked(INSERT_SHAPES_SUPPORTED, shape, "insert shape", "supported insert shape (S, T, C, D, E, M, V)")
    style_row(style)
    _checked(INSERT_CLEARANCES, clearance, "clearance", "clearance letter")
    _checked(HOLDER_HANDS, hand, "hand", "hand letter (R, L, N)")
    length_mm(length)
    return HolderParts(clamping, shape, style, clearance, hand, height + width, length, size)


def format_holder_code(parts: HolderParts) -> str:
    return (
        f"{parts.clamping}{parts.shape}{parts.style}{parts.clearance}{parts.hand} {parts.section} {parts.length}{parts.size}"
    )


def parse_bar_code(text: str) -> BarParts:
    """Read an ISO 6261 code of a boring bar. Raises HolderError."""
    compact = "".join(text.upper().split())
    match = _BAR.match(compact)
    if match is None:
        raise HolderError(
            "the boring bar code must look like S25S-PCLNR 12 (type, diameter, length - clamping, insert shape, "
            "style, clearance, hand, insert size)"
        )
    bar_type, diameter, length, clamping, shape, style, clearance, hand, size, *_optional = match.groups()
    _checked(BORING_TYPES, bar_type, "type", "boring bar type letter")
    bar_row(int(diameter))
    length_mm(length)
    _checked(HOLDER_CLAMPING, clamping, "clamping", "clamping letter (C, M, P, S)")
    _checked(INSERT_SHAPES_SUPPORTED, shape, "insert shape", "supported insert shape (S, T, C, D, E, M, V)")
    bar_style_row(style)
    _checked(INSERT_CLEARANCES, clearance, "clearance", "clearance letter")
    _checked(HOLDER_HANDS, hand, "hand", "hand letter (R, L, N)")
    return BarParts(bar_type, diameter, length, clamping, shape, style, clearance, hand, size)


def format_bar_code(parts: BarParts) -> str:
    return (
        f"{parts.bar_type}{parts.diameter}{parts.length}-{parts.clamping}{parts.shape}{parts.style}"
        f"{parts.clearance}{parts.hand} {parts.size}"
    )
