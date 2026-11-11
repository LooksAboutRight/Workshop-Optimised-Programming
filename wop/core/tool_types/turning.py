"""Turning tool: the standard shape of a hand-ground or brazed tool, drawn from a few dimensions (see turning_tool_shape)."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    TURNING_TOOL_EDGE_LENGTH_MM,
    TURNING_TOOL_FRONT_ANGLE_DEG,
    TURNING_TOOL_LENGTH_MM,
    TURNING_TOOL_NOSE_RADIUS_MM,
    TURNING_TOOL_SIDE_ANGLE_DEG,
    TURNING_TOOL_WIDTH_MM,
)
from ..tooling.tool import Tool, ToolError, ToolMaterial
from ..tooling.turning_tool_shape import turning_tool, turning_tool_shape
from .base import TOOL_TYPES, ToolType
from .hand import ToolHand


@dataclass(frozen=True)
class TurningDefinition:
    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.CARBIDE
    hand: ToolHand = ToolHand.RIGHT
    nose_radius_mm: float = TURNING_TOOL_NOSE_RADIUS_MM
    side_edge_length_mm: float = TURNING_TOOL_EDGE_LENGTH_MM
    side_edge_angle_deg: float = TURNING_TOOL_SIDE_ANGLE_DEG
    front_edge_angle_deg: float = TURNING_TOOL_FRONT_ANGLE_DEG
    width_mm: float = TURNING_TOOL_WIDTH_MM
    length_mm: float = TURNING_TOOL_LENGTH_MM

    def form_fields(self) -> tuple[str, ...]:
        return ("number", "name", "material", "hand", "nose_radius_mm", "side_edge_length_mm", "side_edge_angle_deg",
                "front_edge_angle_deg", "width_mm", "length_mm")

    def form_labels(self) -> dict[str, str]:
        return {
            "side_edge_length_mm": "Side edge length (cutting edge)",
            "side_edge_angle_deg": "Side edge angle (to the feed direction)",
            "front_edge_angle_deg": "Front edge angle (to the facing direction)",
            "width_mm": "Width of the tool",
            "length_mm": "Length of the tool",
        }


@TOOL_TYPES.register
class TurningToolType(ToolType):
    type_name = "turning"
    label = "Turning tool"
    definition_class = TurningDefinition

    @staticmethod
    def _shape(definition: TurningDefinition):
        return turning_tool_shape(
            definition.nose_radius_mm, definition.side_edge_angle_deg, definition.front_edge_angle_deg,
            definition.side_edge_length_mm, definition.width_mm, definition.length_mm,
        )

    def build(self, number: int, definition: TurningDefinition) -> Tool:
        name = definition.name.strip() or self.label
        return turning_tool(
            number, name, definition.hand is ToolHand.LEFT, definition.nose_radius_mm, definition.side_edge_angle_deg,
            definition.front_edge_angle_deg, definition.side_edge_length_mm, definition.width_mm, definition.length_mm,
        )

    def info(self, definition: TurningDefinition) -> tuple[str, ...]:
        try:
            shape = self._shape(definition)
        except ToolError as error:
            return (str(error),)
        return (
            f"Angle between the two edges at the tip: {shape.tip_angle_deg:.1f} deg",
            "Right hand cuts towards the chuck; left hand is the mirror image.",
        )
