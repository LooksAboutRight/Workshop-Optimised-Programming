"""Boring bar: the standard shape of a boring bar with a head, drawn from a few dimensions (see boring_tool_shape)."""

from __future__ import annotations

from dataclasses import dataclass

from ..tooling.boring_tool_shape import boring_tool, boring_tool_shape
from ..constants import (
    BORING_TOOL_BAR_WIDTH_MM,
    BORING_TOOL_END_ANGLE_DEG,
    BORING_TOOL_FRONT_WIDTH_MM,
    BORING_TOOL_LENGTH_MM,
    BORING_TOOL_NOSE_RADIUS_MM,
    BORING_TOOL_WALL_ANGLE_DEG,
    BORING_TOOL_WALL_EDGE_LENGTH_MM,
)
from ..tooling.tool import Tool, ToolError, ToolMaterial
from .base import TOOL_TYPES, ToolType
from .hand import ToolHand


@dataclass(frozen=True)
class BoringDefinition:
    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.CARBIDE
    hand: ToolHand = ToolHand.RIGHT
    nose_radius_mm: float = BORING_TOOL_NOSE_RADIUS_MM
    wall_edge_length_mm: float = BORING_TOOL_WALL_EDGE_LENGTH_MM
    wall_edge_angle_deg: float = BORING_TOOL_WALL_ANGLE_DEG
    end_edge_angle_deg: float = BORING_TOOL_END_ANGLE_DEG
    front_width_mm: float = BORING_TOOL_FRONT_WIDTH_MM
    bar_width_mm: float = BORING_TOOL_BAR_WIDTH_MM
    length_mm: float = BORING_TOOL_LENGTH_MM

    def form_labels(self) -> dict[str, str]:
        return {
            "wall_edge_length_mm": "Wall edge length (at most; it ends at the bar)",
            "wall_edge_angle_deg": "Wall edge angle (to the facing direction)",
            "end_edge_angle_deg": "End edge angle (to the feed direction)",
            "front_width_mm": "Front width (whole front from the tip)",
            "bar_width_mm": "Bar width (full profile)",
            "length_mm": "Length of the bar",
        }


@TOOL_TYPES.register
class BoringToolType(ToolType):
    type_name = "boring"
    label = "Boring bar"
    definition_class = BoringDefinition

    @staticmethod
    def _shape(definition: BoringDefinition):
        return boring_tool_shape(
            definition.nose_radius_mm, definition.end_edge_angle_deg, definition.wall_edge_angle_deg,
            definition.wall_edge_length_mm, definition.front_width_mm, definition.bar_width_mm, definition.length_mm,
        )

    def build(self, number: int, definition: BoringDefinition) -> Tool:
        return boring_tool(
            number, definition.name.strip() or self.label, definition.nose_radius_mm, definition.end_edge_angle_deg,
            definition.wall_edge_angle_deg, definition.wall_edge_length_mm, definition.front_width_mm, definition.bar_width_mm,
            definition.length_mm, definition.hand is ToolHand.LEFT,
        )

    def info(self, definition: BoringDefinition) -> tuple[str, ...]:
        try:
            shape = self._shape(definition)
        except ToolError as error:
            return (str(error),)
        return (
            f"Angle between the two edges at the tip: {shape.tip_angle_deg:.1f} deg",
            f"Smallest bore: about {definition.front_width_mm:g} mm (the bar must stay inside the far wall)",
            "Right hand works on the near wall of the bore. Left hand is the mirror image in X: it works on the far wall, with the spindle reversed.",
        )
