"""Grooving tool: a blade with a rounded front on a holder, outside or inside, right or left hand (see groove_tool_shape)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..constants import (
    GROOVE_TOOL_BLADE_REACH_MM,
    GROOVE_TOOL_BLADE_WIDTH_MM,
    GROOVE_TOOL_CORNER_RADIUS_MM,
    GROOVE_TOOL_FRONT_ANGLE_DEG,
    GROOVE_TOOL_HOLDER_WIDTH_MM,
    GROOVE_TOOL_TYPE_HOLDER_LENGTH_MM,
)
from ..tooling.groove_tool_shape import groove_tool, groove_tool_shape
from ..tooling.tool import Tool, ToolError, ToolMaterial
from .base import TOOL_TYPES, ToolType
from .hand import ToolHand


class TouchOffCorner(Enum):
    LEFT = "left corner (smaller Z)"
    RIGHT = "right corner (larger Z)"


@dataclass(frozen=True)
class GrooveDefinition:
    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.COATED_CARBIDE
    hand: ToolHand = ToolHand.RIGHT
    inside: bool = False
    blade_width_mm: float = GROOVE_TOOL_BLADE_WIDTH_MM
    reach_mm: float = GROOVE_TOOL_BLADE_REACH_MM
    corner_radius_mm: float = GROOVE_TOOL_CORNER_RADIUS_MM
    front_angle_deg: float = GROOVE_TOOL_FRONT_ANGLE_DEG
    holder_width_mm: float = GROOVE_TOOL_HOLDER_WIDTH_MM
    holder_length_mm: float = GROOVE_TOOL_TYPE_HOLDER_LENGTH_MM
    touch_off: TouchOffCorner = TouchOffCorner.LEFT

    def form_fields(self) -> tuple[str, ...]:
        return ("number", "name", "material", "hand", "inside", "blade_width_mm", "reach_mm", "corner_radius_mm", "front_angle_deg",
                "holder_width_mm", "holder_length_mm", "touch_off")

    def form_labels(self) -> dict[str, str]:
        length, width = ("along Z", "along X") if self.inside else ("along X", "across Z")
        return {
            "blade_width_mm": "Blade width (across Z)",
            "reach_mm": "Blade reach (from the tip)",
            "corner_radius_mm": "Corner radius (both corners)",
            "front_angle_deg": "Front angle (inside the blade, left corner)",
            "holder_width_mm": f"Holder width ({width})",
            "holder_length_mm": f"Holder length ({length})",
            "touch_off": "Touch-off corner",
        }


@TOOL_TYPES.register
class GrooveToolType(ToolType):
    type_name = "groove"
    label = "Grooving tool"
    definition_class = GrooveDefinition

    def build(self, number: int, definition: GrooveDefinition) -> Tool:
        return groove_tool(
            number, definition.name.strip() or self.label, definition.hand is ToolHand.LEFT, definition.inside,
            definition.touch_off is TouchOffCorner.RIGHT, definition.corner_radius_mm, definition.front_angle_deg,
            definition.blade_width_mm, definition.reach_mm, definition.holder_width_mm, definition.holder_length_mm,
        )

    def info(self, definition: GrooveDefinition) -> tuple[str, ...]:
        try:
            groove_tool_shape(
                definition.corner_radius_mm, definition.front_angle_deg, definition.blade_width_mm, definition.reach_mm,
                definition.holder_width_mm, definition.holder_length_mm, definition.inside,
            )
        except ToolError as error:
            return (str(error),)
        lines = ["Right hand: the blade is flush with the left side of the holder. Left hand is the mirror image in Z (outside) or in X (inside)."]
        if definition.hand is ToolHand.LEFT and definition.inside:
            lines.append("A left-hand inside tool works on the far wall of the bore, with the spindle reversed (set it in the block): only the turning blocks plan that so far.")
        return tuple(lines)
