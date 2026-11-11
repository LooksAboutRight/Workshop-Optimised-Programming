"""Shared parts of the two ISO holder tool types (turning holder, boring bar): codes and dropdowns kept in step.

The user may type the holder code, type the insert code, or choose the parts in the dropdowns. `reconcile` makes the
other representations follow whatever was changed last; dropdown values that no longer fit are repaired.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..constants import (
    HOLDER_CLAMPING,
    HOLDER_HANDS,
    HOLDER_LENGTHS_MM,
    INSERT_CLEARANCES,
    INSERT_CODE_WIDTH,
    INSERT_CORNER_RADII_MM,
    INSERT_DEFAULT_DESIGNATION,
    INSERT_SHAPES_SUPPORTED,
    INSERT_THICKNESSES_MM,
    INSERT_TOLERANCES,
    INSERT_TYPES,
)
from ..tooling.holder_designation import HolderError, insert_size_codes, shape_fits
from ..tooling.insert_designation import InsertDesignation, parse_designation
from ..tooling.tool import ToolMaterial
from .base import ToolType

Options = tuple[tuple[str, str], ...]  # (value, label)


@dataclass(frozen=True)
class IsoDefinition:
    """Number, name, material and the parts of the insert code (the holder parts are added by the two types)."""

    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.COATED_CARBIDE
    insert_code: str = INSERT_DEFAULT_DESIGNATION


def split_insert_code(text: str) -> dict[str, str]:
    """The parts of an insert code that the forms show: shape, clearance, tolerance, type, size, thickness, corner radius."""
    designation = parse_designation(text)
    letters, digits = designation.text.split()[:2]
    width = INSERT_CODE_WIDTH
    return {
        "shape": letters[0],
        "clearance": letters[1],
        "tolerance": letters[2],
        "insert_type": letters[-1],
        "insert_size": digits[:width],
        "thickness": digits[width : 2 * width],
        "corner_radius": digits[2 * width :],
    }


def join_insert_code(parts: Any) -> str:
    return (
        f"{parts.shape}{parts.clearance}{parts.tolerance}{parts.insert_type} "
        f"{parts.insert_size}{parts.thickness}{parts.corner_radius}"
    )


def with_current(options: Options, current: str) -> Options:
    """The options; the current value is added when the dropdown would not show it (a typed code outside the lists)."""
    return options if any(value == current for value, _label in options) else options + ((current, current),)


def insert_options(definition: Any, kappa_deg: float) -> dict[str, Options]:
    """The dropdown lists of the insert parts and the shared parts (shape, clearance, size)."""
    shapes = tuple((row[0], f"{row[0]} - {row[1]}") for row in INSERT_SHAPES_SUPPORTED if shape_fits(kappa_deg, row[0]))
    clearances = tuple((row[0], f"{row[0]} - {'other' if row[1] is None else f'{row[1]} deg'}") for row in INSERT_CLEARANCES)
    sizes = tuple((code, f"{code} mm edge") for code in insert_size_codes(definition.shape))
    return {
        "clamping": tuple((row[0], f"{row[0]} - {row[1]}") for row in HOLDER_CLAMPING),
        "shape": with_current(shapes, definition.shape),
        "clearance": with_current(clearances, definition.clearance),
        "hand": tuple((row[0], f"{row[0]} - {row[1]}") for row in HOLDER_HANDS),
        "length": tuple((row[0], f"{row[0]} - {row[1]:g} mm") for row in HOLDER_LENGTHS_MM),
        "insert_size": with_current(sizes, definition.insert_size),
        "tolerance": tuple((row[0], f"{row[0]} - {row[1]}") for row in INSERT_TOLERANCES),
        "insert_type": tuple((row[0], f"{row[0]} - {row[1]}") for row in INSERT_TYPES),
        "thickness": tuple((row[0], f"{row[0]} - {row[1]:g} mm") for row in INSERT_THICKNESSES_MM),
        "corner_radius": tuple((row[0], f"{row[0]} - {row[1]:g} mm") for row in INSERT_CORNER_RADII_MM),
    }


def nearest_size(size: str, shape_letter: str) -> str:
    """The size code of the shape that is closest to `size` (kept when it is valid)."""
    codes = insert_size_codes(shape_letter)
    if size in codes or not codes:
        return size
    return min(codes, key=lambda code: abs(int(code) - int(size)) if size.isdigit() else 0)


class IsoToolType(ToolType):
    """Base of the holder and the boring bar type: the code and the parts follow each other."""

    code_field = ""  # name of the holder code field

    def parts_of_code(self, text: str) -> dict[str, str]:
        raise NotImplementedError

    def code_of_parts(self, definition: Any) -> str:
        raise NotImplementedError

    def kappa_deg(self, definition: Any) -> float:
        raise NotImplementedError

    def repair(self, definition: Any) -> Any:
        """Make dropdown values that no longer fit (after another one was changed) fit again."""
        kappa = self.kappa_deg(definition)
        if not shape_fits(kappa, definition.shape):
            fitting = [row[0] for row in INSERT_SHAPES_SUPPORTED if shape_fits(kappa, row[0])]
            if not fitting:
                raise HolderError("no supported insert shape fits this style")
            definition = replace(definition, shape=fitting[0])
        return replace(definition, insert_size=nearest_size(definition.insert_size, definition.shape))

    def _codes_follow(self, definition: Any) -> Any:
        definition = replace(definition, insert_code=join_insert_code(definition))
        return replace(definition, **{self.code_field: self.code_of_parts(definition)})

    def reconcile(self, old: Any, new: Any) -> Any:
        """Bring the codes and the parts in step with what was changed (code typed, insert code typed, or a dropdown)."""
        if getattr(new, self.code_field) != getattr(old, self.code_field):
            new = replace(new, **self.parts_of_code(getattr(new, self.code_field)))
            return replace(new, insert_code=join_insert_code(new))
        if new.insert_code != old.insert_code:
            new = replace(new, **split_insert_code(new.insert_code))
            return replace(new, **{self.code_field: self.code_of_parts(new)})
        return self._codes_follow(self.repair(new))

    def insert_of(self, definition: Any) -> InsertDesignation:
        """The insert of a definition; it must agree with the holder parts."""
        designation = parse_designation(definition.insert_code)
        if designation.shape_letter != definition.shape or split_insert_code(definition.insert_code)["insert_size"] != definition.insert_size:
            raise HolderError("the insert and the holder disagree about the insert shape or size")
        if not shape_fits(self.kappa_deg(definition), designation.shape_letter):
            raise HolderError(f"insert shape {designation.shape_letter} does not fit this holder style (the end cutting edge angle would be negative)")
        return designation
