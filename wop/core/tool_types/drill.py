"""Drill on the spindle axis."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import DRILL_TIP_ANGLE_DEG, DRILL_TOOL_DIAMETER_MM, DRILL_TOOL_FLUTE_LENGTH_MM
from ..tooling.tool import Tool, ToolMaterial
from ..tooling.tool_presets import drill_tool
from .base import TOOL_TYPES, ToolType


@dataclass(frozen=True)
class DrillDefinition:
    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.HSS
    diameter_mm: float = DRILL_TOOL_DIAMETER_MM
    length_mm: float = DRILL_TOOL_FLUTE_LENGTH_MM  # cutting length
    tip_angle_deg: float = DRILL_TIP_ANGLE_DEG


@TOOL_TYPES.register
class DrillToolType(ToolType):
    type_name = "drill"
    label = "Drill"
    definition_class = DrillDefinition

    def build(self, number: int, definition: DrillDefinition) -> Tool:
        name = definition.name.strip() or self.label
        return drill_tool(number, name, definition.diameter_mm, definition.length_mm, definition.tip_angle_deg)
