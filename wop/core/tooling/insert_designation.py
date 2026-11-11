"""ISO insert designation (requirement T9): "CNMG 120408" read position by position.

Position 1 shape, 2 clearance, 3 tolerance, 4 type (hole, chipbreaker), 5 size (edge length), 6 thickness,
7 corner radius; then optionally the edge preparation, the hand and a manufacturer code after a hyphen.
Only shape, size and corner radius change the 2D picture; the rest is kept and shown decoded.
A wrong designation is reported with the number and the name of the position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..constants import (
    INSERT_CLEARANCES,
    INSERT_CODE_WIDTH,
    INSERT_CORNER_RADII_MM,
    INSERT_EDGE_PREPARATIONS,
    INSERT_HANDS,
    INSERT_INSCRIBED_CIRCLES_MM,
    INSERT_LETTER_POSITIONS,
    INSERT_POSITION_CLEARANCE,
    INSERT_POSITION_NAMES,
    INSERT_POSITION_RADIUS,
    INSERT_POSITION_SHAPE,
    INSERT_POSITION_SIZE,
    INSERT_POSITION_THICKNESS,
    INSERT_POSITION_TOLERANCE,
    INSERT_POSITION_TYPE,
    INSERT_POSITIONS,
    INSERT_SHAPES_SUPPORTED,
    INSERT_SQUARE_LETTER,
    INSERT_TRIANGLE_LETTER,
    INSERT_SHAPES_UNSUPPORTED,
    INSERT_SIZE_ROUNDING_MM,
    INSERT_THICKNESSES_MM,
    INSERT_TOLERANCES,
    INSERT_TYPES,
)
from .tool import ToolError

_REST = re.compile(r"^([FETS])?([RLN])?(?:-([A-Z0-9]+))?$")


class DesignationError(ToolError):
    """The designation is wrong at a position (1-based); `position` is 0 when it is wrong as a whole."""

    def __init__(self, position: int, message: str) -> None:
        name = INSERT_POSITION_NAMES[position - 1] if position else ""
        super().__init__(f"position {position} ({name}): {message}" if position else message)
        self.position = position


@dataclass(frozen=True)
class InsertDesignation:
    text: str  # normalised, for example "CNMG 120408"
    shape_letter: str
    shape_name: str
    tip_angle_deg: float  # the acute corner
    edge_length_mm: float
    inscribed_circle_mm: float
    clearance_deg: float | None
    tolerance: str
    type_text: str
    thickness_mm: float
    nose_radius_mm: float
    edge_preparation: str = ""
    hand: str = ""
    manufacturer: str = ""
    is_square_or_triangle: bool = False

    def lines(self) -> tuple[str, ...]:
        """The designation decoded, one line per position (the form shows them under the entry)."""
        clearance = "other" if self.clearance_deg is None else f"{self.clearance_deg:g} degrees"
        lines = [
            f"Shape: {self.shape_letter} = {self.shape_name}, tip angle {self.tip_angle_deg:g} degrees",
            f"Clearance: {clearance} (not used in the 2D picture)",
            f"Tolerance: {self.tolerance} (not used)",
            f"Type: {self.type_text} (not used)",
            f"Size: edge length {self.edge_length_mm:.1f} mm, inscribed circle {self.inscribed_circle_mm:g} mm",
            f"Thickness: {self.thickness_mm:g} mm",
            f"Corner radius: {self.nose_radius_mm:g} mm",
        ]
        if self.edge_preparation:
            lines.append(f"Edge preparation: {self.edge_preparation}")
        if self.hand:
            lines.append(f"Hand: {self.hand}")
        if self.manufacturer:
            lines.append(f"Manufacturer code: {self.manufacturer}")
        return tuple(lines)


def _characters(text: str) -> tuple[list[str], str]:
    """The first INSERT_POSITIONS positions' characters (spaces skipped) and what follows them."""
    wanted = INSERT_LETTER_POSITIONS + (INSERT_POSITIONS - INSERT_LETTER_POSITIONS) * INSERT_CODE_WIDTH
    characters: list[str] = []
    for index, character in enumerate(text):
        if len(characters) == wanted:
            return characters, text[index:].strip()
        if not character.isspace():
            characters.append(character)
    return characters, ""


def _position_of(index: int) -> int:
    """The 1-based position the character with this 0-based index belongs to."""
    if index < INSERT_LETTER_POSITIONS:
        return index + 1
    return INSERT_LETTER_POSITIONS + (index - INSERT_LETTER_POSITIONS) // INSERT_CODE_WIDTH + 1


def _lookup(table: tuple, key: str):
    return next((row for row in table if row[0] == key), None)


def _size(factor: float, shape_letter: str, code: str) -> tuple[float, float]:
    """(edge length, inscribed circle) in mm for the size code; the code is checked against the standard series."""
    if not code.isdigit():
        raise DesignationError(INSERT_POSITION_SIZE, f"'{code}' is not a size code (two digits, the edge length in mm rounded down)")
    for circle in INSERT_INSCRIBED_CIRCLES_MM:
        length = circle * factor
        if int(length + INSERT_SIZE_ROUNDING_MM) == int(code):
            return length, circle
    raise DesignationError(INSERT_POSITION_SIZE, f"size {code} does not fit shape {shape_letter} with a standard inscribed circle")


def parse_designation(text: str) -> InsertDesignation:
    """Read an ISO insert designation. Raises DesignationError, naming the wrong position."""
    upper = text.upper()
    characters, rest = _characters(upper)
    needed = INSERT_LETTER_POSITIONS + (INSERT_POSITIONS - INSERT_LETTER_POSITIONS) * INSERT_CODE_WIDTH
    if len(characters) < needed:
        position = _position_of(len(characters))
        raise DesignationError(position, "the designation ends before this position (example: CNMG 120408)")
    letters = characters[:INSERT_LETTER_POSITIONS]
    for index, letter in enumerate(letters):
        if not letter.isalpha():
            raise DesignationError(index + 1, f"'{letter}' must be a letter")
    size = "".join(characters[INSERT_LETTER_POSITIONS : INSERT_LETTER_POSITIONS + INSERT_CODE_WIDTH])
    thickness = "".join(characters[INSERT_LETTER_POSITIONS + INSERT_CODE_WIDTH : INSERT_LETTER_POSITIONS + 2 * INSERT_CODE_WIDTH])
    radius = "".join(characters[INSERT_LETTER_POSITIONS + 2 * INSERT_CODE_WIDTH :])

    shape_letter, clearance_letter, tolerance_letter, type_letter = letters
    shape_row = _lookup(INSERT_SHAPES_SUPPORTED, shape_letter)
    if shape_row is None:
        if _lookup(INSERT_SHAPES_UNSUPPORTED, shape_letter):
            raise DesignationError(INSERT_POSITION_SHAPE, f"shape {shape_letter} is not supported yet (only S, T, C, D, E, M, V)")
        raise DesignationError(INSERT_POSITION_SHAPE, f"'{shape_letter}' is not an insert shape letter")
    clearance_row = _lookup(INSERT_CLEARANCES, clearance_letter)
    if clearance_row is None:
        raise DesignationError(INSERT_POSITION_CLEARANCE, f"'{clearance_letter}' is not a clearance letter")
    tolerance_row = _lookup(INSERT_TOLERANCES, tolerance_letter)
    if tolerance_row is None:
        raise DesignationError(INSERT_POSITION_TOLERANCE, f"'{tolerance_letter}' is not a tolerance letter")
    type_row = _lookup(INSERT_TYPES, type_letter)
    if type_row is None:
        raise DesignationError(INSERT_POSITION_TYPE, f"'{type_letter}' is not an insert type letter")
    edge_length, circle = _size(shape_row[-1], shape_letter, size)
    thickness_row = _lookup(INSERT_THICKNESSES_MM, thickness)
    if thickness_row is None:
        raise DesignationError(INSERT_POSITION_THICKNESS, f"'{thickness}' is not a thickness code")
    radius_row = _lookup(INSERT_CORNER_RADII_MM, radius)
    if radius_row is None:
        raise DesignationError(INSERT_POSITION_RADIUS, f"'{radius}' is not a corner radius code (00, 04, 08, 12, ...)")

    match = _REST.match("".join(rest.split()))
    if match is None:
        raise DesignationError(0, f"'{rest}' after the seven positions is not an edge preparation, a hand and a '-' manufacturer code")
    preparation_letter, hand_letter, manufacturer = (group or "" for group in match.groups())
    preparation = _lookup(INSERT_EDGE_PREPARATIONS, preparation_letter)
    hand = _lookup(INSERT_HANDS, hand_letter)
    return InsertDesignation(
        text=f"{''.join(letters)} {size}{thickness}{radius}{preparation_letter}{hand_letter}"
        + (f"-{manufacturer}" if manufacturer else ""),
        shape_letter=shape_letter,
        shape_name=shape_row[1],
        tip_angle_deg=shape_row[2],
        edge_length_mm=edge_length,
        inscribed_circle_mm=circle,
        clearance_deg=clearance_row[1],
        tolerance=tolerance_row[1],
        type_text=type_row[1],
        thickness_mm=thickness_row[1],
        nose_radius_mm=radius_row[1],
        edge_preparation=preparation[1] if preparation else "",
        hand=hand[1] if hand else "",
        manufacturer=manufacturer,
        is_square_or_triangle=shape_letter in (INSERT_SQUARE_LETTER, INSERT_TRIANGLE_LETTER),
    )
