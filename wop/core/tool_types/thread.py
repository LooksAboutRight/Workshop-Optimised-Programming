"""Threading tool: a V point (pointed, or with a flat) on a body, outside or inside, right or left hand (see thread_tool_shape)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..constants import (
    THREAD_TOOL_CUTTING_HEIGHT_MM,
    THREAD_TOOL_FLAT_MM,
    THREAD_TOOL_INCLUDED_ANGLE_DEG,
    THREAD_TOOL_LENGTH_MM,
    THREAD_TOOL_NOSE_RADIUS_MM,
    THREAD_TOOL_TIP_DISTANCE_MM,
    THREAD_TOOL_WIDTH_MM,
)
from ..tooling.thread_tool_shape import thread_tool, thread_tool_shape
from ..tooling.tool import Tool, ToolError, ToolMaterial
from .base import TOOL_TYPES, ToolType
from .hand import ToolHand


@dataclass(frozen=True)
class ThreadDefinition:
    number: int = 0  # the tool number (set by the model when the form is shown)
    name: str = ""
    material: ToolMaterial = ToolMaterial.COATED_CARBIDE
    hand: ToolHand = ToolHand.RIGHT
    inside: bool = False
    included_angle_deg: float = THREAD_TOOL_INCLUDED_ANGLE_DEG
    lead_angle_deg: float = THREAD_TOOL_INCLUDED_ANGLE_DEG / 2  # the leading flank from the radial direction; follows the included angle while the tool is symmetric
    nose_radius_mm: float = THREAD_TOOL_NOSE_RADIUS_MM
    flat_mm: float = THREAD_TOOL_FLAT_MM
    cutting_height_mm: float = THREAD_TOOL_CUTTING_HEIGHT_MM
    tip_distance_mm: float = THREAD_TOOL_TIP_DISTANCE_MM
    width_mm: float = THREAD_TOOL_WIDTH_MM
    length_mm: float = THREAD_TOOL_LENGTH_MM

    def form_fields(self) -> tuple[str, ...]:
        return ("number", "name", "material", "hand", "inside", "included_angle_deg", "lead_angle_deg", "nose_radius_mm", "flat_mm",
                "cutting_height_mm", "tip_distance_mm", "width_mm", "length_mm")

    def form_labels(self) -> dict[str, str]:
        length, width = ("along Z", "along X") if self.inside else ("along X", "across Z")
        return {
            "included_angle_deg": "Included angle (between the flanks)",
            "lead_angle_deg": "Lead angle (leading flank to X)",
            "nose_radius_mm": "Tip radius",
            "flat_mm": "Tip flat (before rounding)",
            "cutting_height_mm": "Cutting height (point to body)",
            "tip_distance_mm": "Point to cutting side face",
            "width_mm": f"Width ({width})",
            "length_mm": f"Length ({length})",
        }


@TOOL_TYPES.register
class ThreadToolType(ToolType):
    type_name = "thread"
    label = "Threading tool"
    definition_class = ThreadDefinition

    def reconcile(self, old: ThreadDefinition, new: ThreadDefinition) -> ThreadDefinition:
        """A symmetric tool stays symmetric when the included angle is changed (the lead angle follows until it is set apart)."""
        if new.included_angle_deg != old.included_angle_deg and old.lead_angle_deg == old.included_angle_deg / 2 == new.lead_angle_deg:
            return replace(new, lead_angle_deg=new.included_angle_deg / 2)
        return new

    @staticmethod
    def _shape(definition: ThreadDefinition):
        return thread_tool_shape(
            definition.nose_radius_mm, definition.flat_mm, definition.included_angle_deg, definition.lead_angle_deg,
            definition.cutting_height_mm, definition.tip_distance_mm, definition.width_mm, definition.length_mm, definition.inside,
        )

    def build(self, number: int, definition: ThreadDefinition) -> Tool:
        return thread_tool(
            number, definition.name.strip() or self.label, definition.hand is ToolHand.LEFT, definition.inside, definition.nose_radius_mm,
            definition.flat_mm, definition.included_angle_deg, definition.lead_angle_deg, definition.cutting_height_mm,
            definition.tip_distance_mm, definition.width_mm, definition.length_mm,
        )

    def info(self, definition: ThreadDefinition) -> tuple[str, ...]:
        try:
            _pieces, _tip, text = self._shape(definition)
        except ToolError as error:
            return (str(error),)
        lines = [text, "Right hand: the leading flank is on the smaller-Z side. Left hand is the mirror image in Z (outside) or in X (inside)."]
        if definition.hand is ToolHand.LEFT and definition.inside:
            lines.append("A left-hand inside tool works on the far wall of the bore, with the spindle reversed (set it in the block): only the turning blocks plan that so far.")
        return tuple(lines)
