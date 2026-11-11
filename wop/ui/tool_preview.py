"""Picture of one tool outline as SVG (requirement T8): cutting edges and holder in their colours, the touch-off point marked.

Z runs to the right and X up, as in the program picture, so the tool is seen as it works.
"""

from __future__ import annotations

from html import escape

from ..core.geometry import Point, segments_to_polyline
from ..core.tooling.tool import Tool, ToolSegmentRole
from . import ui_constants as ui
from .theme import LIGHT_COLORS, ColorSet

TOOL_PICTURE_WIDTH_PX = 400
TOOL_PICTURE_HEIGHT_PX = 300
TOOL_PICTURE_MARGIN_PX = 30
TOOL_LINE_WIDTH_PX = 2.5
TOOL_TIP_RADIUS_PX = 4
TOOL_MIN_SPAN_MM = 1


def tool_svg(tool: Tool, colors: ColorSet = LIGHT_COLORS) -> str:
    """The tool as an SVG picture."""
    drawn = [(piece.role, segments_to_polyline([piece.segment])) for piece in tool.shape.pieces]
    points = [p for _role, line in drawn for p in line] + [Point(0, 0)] + [point.position for point in tool.points]
    min_x, max_x = min(p.x for p in points), max(p.x for p in points)
    min_z, max_z = min(p.z for p in points), max(p.z for p in points)
    span_x, span_z = max(max_x - min_x, TOOL_MIN_SPAN_MM), max(max_z - min_z, TOOL_MIN_SPAN_MM)
    usable_w = TOOL_PICTURE_WIDTH_PX - 2 * TOOL_PICTURE_MARGIN_PX
    usable_h = TOOL_PICTURE_HEIGHT_PX - 2 * TOOL_PICTURE_MARGIN_PX
    scale = min(usable_w / span_z, usable_h / span_x)

    def px(point: Point) -> tuple[float, float]:
        return (
            TOOL_PICTURE_MARGIN_PX + (point.z - min_z) * scale,
            TOOL_PICTURE_HEIGHT_PX - TOOL_PICTURE_MARGIN_PX - (point.x - min_x) * scale,
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TOOL_PICTURE_WIDTH_PX}" '
        f'height="{TOOL_PICTURE_HEIGHT_PX}" viewBox="0 0 {TOOL_PICTURE_WIDTH_PX} {TOOL_PICTURE_HEIGHT_PX}">'
    ]
    if colors.background:
        parts.append(f'<rect width="{TOOL_PICTURE_WIDTH_PX}" height="{TOOL_PICTURE_HEIGHT_PX}" fill="{colors.background}"/>')
    for role, line in drawn:
        color = colors.tool_cutter if role is ToolSegmentRole.CUTTER else colors.tool_holder
        coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in (px(p) for p in line))
        parts.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="{TOOL_LINE_WIDTH_PX}"/>')
    tip_x, tip_y = px(Point(0, 0))
    parts.append(f'<circle cx="{tip_x:.2f}" cy="{tip_y:.2f}" r="{TOOL_TIP_RADIUS_PX}" fill="{colors.finding}"/>')
    parts.append(  # the origin of the tool is its touch-off point (`Program.equipped_tool` puts the tool there)
        f'<text x="{tip_x + TOOL_TIP_RADIUS_PX + 2:.2f}" y="{tip_y + ui.LABEL_FONT_PX:.2f}" font-size="{ui.LABEL_FONT_PX}" '
        f'fill="{colors.finding}">touch-off point</text>'
    )
    for named in tool.points:  # named points: a ring and the name
        x, y = px(named.position)
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{TOOL_TIP_RADIUS_PX}" fill="none" stroke="{colors.text}" stroke-width="1.5"/>'
            f'<text x="{x + TOOL_TIP_RADIUS_PX + 2:.2f}" y="{y - TOOL_TIP_RADIUS_PX:.2f}" font-size="{ui.LABEL_FONT_PX}" '
            f'fill="{colors.text}">{escape(named.name)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
