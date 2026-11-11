"""The picture of a stored contour: Z to the right, X up (like the program picture).

Cutting edges (tool shapes) are drawn in the cutter colour, named points as a ring with their name. With no background in
`colors` the picture is transparent; a background has the real size. A contour without segments gives an empty picture.
"""

from __future__ import annotations

from html import escape

from ..core.contour import Contour
from ..core.geometry import Point, segments_to_polyline
from . import ui_constants as ui
from .contour_picture_constants import PREVIEW_HEIGHT_PX, PREVIEW_MARGIN_PX, PREVIEW_WIDTH_PX
from .theme import LIGHT_COLORS, ColorSet


def contour_svg(contour: Contour, colors: ColorSet = LIGHT_COLORS) -> str:
    """The contour as an SVG picture."""
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PREVIEW_WIDTH_PX}" '
        f'height="{PREVIEW_HEIGHT_PX}" viewBox="0 0 {PREVIEW_WIDTH_PX} {PREVIEW_HEIGHT_PX}">'
    )
    parts = [head]
    if colors.background:
        parts.append(f'<rect width="{PREVIEW_WIDTH_PX}" height="{PREVIEW_HEIGHT_PX}" fill="{colors.background}"/>')
    lines = [segments_to_polyline([segment]) for segment in contour.segments]
    points = [point for line in lines for point in line] + [named.position for named in contour.points]
    if points:
        min_x, max_x = min(p.x for p in points), max(p.x for p in points)
        min_z, max_z = min(p.z for p in points), max(p.z for p in points)
        span_x, span_z = max(max_x - min_x, 1), max(max_z - min_z, 1)
        scale = min((PREVIEW_WIDTH_PX - 2 * PREVIEW_MARGIN_PX) / span_z, (PREVIEW_HEIGHT_PX - 2 * PREVIEW_MARGIN_PX) / span_x)

        def at(point: Point) -> tuple[float, float]:
            return (
                PREVIEW_MARGIN_PX + (point.z - min_z) * scale,
                PREVIEW_HEIGHT_PX - PREVIEW_MARGIN_PX - (point.x - min_x) * scale,
            )

        for index, line in enumerate(lines):
            cutting = index < len(contour.cutting) and contour.cutting[index]
            colour = colors.tool_cutter if cutting else colors.block_colors[0]
            text = " ".join("%.2f,%.2f" % at(point) for point in line)
            parts.append(f'<polyline points="{text}" fill="none" stroke="{colour}" stroke-width="{ui.LINE_WIDTH_PX * 2}"/>')
        for named in contour.points:  # named points: a ring and the name
            x, y = at(named.position)
            colour = colors.block_colors[2]
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{ui.FINDING_MARK_PX}" fill="none" stroke="{colour}" stroke-width="{ui.LINE_WIDTH_PX}"/>')
            parts.append(
                f'<text x="{x + ui.FINDING_MARK_PX + 2:.2f}" y="{y - ui.FINDING_MARK_PX:.2f}" '
                f'font-size="{ui.LABEL_FONT_PX}" fill="{colour}">{escape(named.name)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)
