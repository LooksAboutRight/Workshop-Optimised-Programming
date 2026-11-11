"""Turning tool: insert on a rectangular ISO holder (ISO 5608), typed as codes or chosen part by part."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import HOLDER_DEFAULT_CODE, HOLDER_GUESS_NOTES, HOLDER_HANDS, HOLDER_STYLES
from ..tooling.holder_designation import (
    HolderParts,
    format_holder_code,
        parse_holder_code,
    section_size,
    sections_for,
    style_label,
    style_row,
)
from ..tooling.holder_tools import holder_tool
from ..tooling.tool import Tool
from .base import TOOL_TYPES
from .iso_parts import IsoDefinition, IsoToolType, Options, insert_options, with_current


@dataclass(frozen=True)
class HolderDefinition(IsoDefinition):
    holder_code: str = HOLDER_DEFAULT_CODE
    clamping: str = "P"
    shape: str = "C"
    style: str = "L"
    clearance: str = "N"
    hand: str = "R"
    section: str = "2525"
    length: str = "M"
    insert_size: str = "12"
    tolerance: str = "M"
    insert_type: str = "G"
    thickness: str = "04"
    corner_radius: str = "08"

    def form_fields(self) -> tuple[str, ...]:
        """Only what changes the 2D shape (the other parts are kept and appear in the codes)."""
        return ("number", "name", "material", "holder_code", "insert_code", "shape", "style", "hand", "section",
                "length", "insert_size", "corner_radius")

    def field_choices(self) -> dict[str, Options]:
        """The dropdowns of the form: the parts, restricted to what fits the other parts."""
        _l, kappa, _offset, _cutting = style_row(self.style)
        lists = insert_options(self, kappa)
        lists["style"] = with_current(tuple((row[0], style_label(row[0])) for row in HOLDER_STYLES), self.style)
        sections = sections_for(self.style)
        lists["section"] = with_current(tuple((s, f"{s[:2]} x {s[2:]}") for s in sections), self.section)
        return lists


@TOOL_TYPES.register
class HolderToolType(IsoToolType):
    type_name = "holder"
    label = "Turning tool (ISO holder)"
    definition_class = HolderDefinition
    code_field = "holder_code"

    def parts_of_code(self, text: str) -> dict[str, str]:
        parts = parse_holder_code(text)
        return {
            "clamping": parts.clamping, "shape": parts.shape, "style": parts.style, "clearance": parts.clearance,
            "hand": parts.hand, "section": parts.section, "length": parts.length, "insert_size": parts.size,
        }

    def code_of_parts(self, definition: HolderDefinition) -> str:
        return format_holder_code(HolderParts(
            definition.clamping, definition.shape, definition.style, definition.clearance, definition.hand,
            definition.section, definition.length, definition.insert_size,
        ))

    def kappa_deg(self, definition: HolderDefinition) -> float:
        return style_row(definition.style)[1]

    def build(self, number: int, definition: HolderDefinition) -> Tool:
        designation = self.insert_of(definition)
        name = definition.name.strip() or f"{definition.holder_code} {designation.text}"
        return holder_tool(number, name, designation, definition.style, definition.hand, definition.section, definition.length)

    def info(self, definition: HolderDefinition) -> tuple[str, ...]:
        try:
            designation = self.insert_of(definition)
            height, width = section_size(definition.section)
            hands = dict(HOLDER_HANDS)
            lines = (
                f"Holder style: {style_label(definition.style)}",
                f"Hand: {hands.get(definition.hand, definition.hand)}",
                f"Shank: {height} x {width} mm",
                f"Insert: {designation.shape_letter} = {designation.shape_name}, edge {designation.edge_length_mm:.1f} mm",
                f"Corner radius: {designation.nose_radius_mm:g} mm",
            )
            return lines + HOLDER_GUESS_NOTES
        except ValueError as error:
            return (str(error),)
