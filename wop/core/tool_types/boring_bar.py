"""Boring bar with an insert (ISO 6261, bar sizes of ISO 5609), typed as codes or chosen part by part."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import BORING_BARS, BORING_DEFAULT_CODE, BORING_GUESS_NOTES, BORING_STYLES, BORING_TYPES, HOLDER_HANDS
from ..tooling.holder_designation import BarParts, bar_row, bar_style_row, format_bar_code, parse_bar_code
from ..tooling.holder_tools import bar_tool
from ..tooling.tool import Tool
from .base import TOOL_TYPES
from .iso_parts import IsoDefinition, IsoToolType, Options, insert_options, with_current


@dataclass(frozen=True)
class BoringBarDefinition(IsoDefinition):
    bar_code: str = BORING_DEFAULT_CODE
    bar_type: str = "S"
    diameter: str = "25"
    length: str = "S"
    clamping: str = "P"
    shape: str = "C"
    style: str = "L"
    clearance: str = "N"
    hand: str = "R"
    insert_size: str = "12"
    tolerance: str = "M"
    insert_type: str = "G"
    thickness: str = "04"
    corner_radius: str = "08"

    def form_fields(self) -> tuple[str, ...]:
        """Only what changes the 2D shape (the other parts are kept and appear in the codes)."""
        return ("number", "name", "material", "bar_code", "insert_code", "diameter", "length", "shape", "style", "hand",
                "insert_size", "corner_radius")

    def field_choices(self) -> dict[str, Options]:
        lists = insert_options(self, bar_style_row(self.style)[1])
        lists["bar_type"] = with_current(tuple((row[0], f"{row[0]} - {row[1]}") for row in BORING_TYPES), self.bar_type)
        lists["diameter"] = with_current(tuple((str(row[0]), f"{row[0]} mm") for row in BORING_BARS), self.diameter)
        lists["style"] = with_current(
            tuple((row[0], f"{row[0]} - {row[1]:g} deg, {row[2]}") for row in BORING_STYLES), self.style
        )
        return lists


@TOOL_TYPES.register
class BoringBarToolType(IsoToolType):
    type_name = "boring_bar"
    label = "Boring bar (ISO)"
    definition_class = BoringBarDefinition
    code_field = "bar_code"

    def parts_of_code(self, text: str) -> dict[str, str]:
        parts = parse_bar_code(text)
        return {
            "bar_type": parts.bar_type, "diameter": parts.diameter, "length": parts.length, "clamping": parts.clamping,
            "shape": parts.shape, "style": parts.style, "clearance": parts.clearance, "hand": parts.hand,
            "insert_size": parts.size,
        }

    def code_of_parts(self, definition: BoringBarDefinition) -> str:
        return format_bar_code(BarParts(
            definition.bar_type, definition.diameter, definition.length, definition.clamping, definition.shape,
            definition.style, definition.clearance, definition.hand, definition.insert_size,
        ))

    def kappa_deg(self, definition: BoringBarDefinition) -> float:
        return bar_style_row(definition.style)[1]

    def build(self, number: int, definition: BoringBarDefinition) -> Tool:
        designation = self.insert_of(definition)
        name = definition.name.strip() or f"{definition.bar_code} {designation.text}"
        return bar_tool(
            number, name, designation, self.kappa_deg(definition), definition.hand, int(definition.diameter), definition.length
        )

    def info(self, definition: BoringBarDefinition) -> tuple[str, ...]:
        try:
            designation = self.insert_of(definition)
            _d, f_mm, smallest_bore = bar_row(int(definition.diameter))
            hands = dict(HOLDER_HANDS)
            lines = (
                f"Bar: diameter {definition.diameter} mm, smallest bore {smallest_bore} mm",
                f"Style: {bar_style_row(definition.style)[0]} ({bar_style_row(definition.style)[1]:g} deg)",
                f"Hand: {hands.get(definition.hand, definition.hand)}",
                f"Insert: {designation.shape_letter} = {designation.shape_name}, edge {designation.edge_length_mm:.1f} mm",
                f"Corner radius: {designation.nose_radius_mm:g} mm",
            )
            return lines + BORING_GUESS_NOTES
        except ValueError as error:
            return (str(error),)
