"""Picture of a planned program as an SVG file (requirement V1).

Z runs to the right, X (radius) up, so the chuck is on the left and the tool
comes from the right and above. Shown: raw part, material left after the
chosen block, material removed by it, rapid moves (dashed) and cutting moves
(one colour per block). The file opens in any web browser.

Colours come from a `ColorSet` (requirement V4). The legend is optional
(`with_legend`): the window draws it as an overlay of its own (requirement V3), so
the picture then holds only the drawing and its size never depends on the number
of blocks. Files keep the legend in the picture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from ..core.geometry import ArcSegment, Point, Segment, segments_to_polyline
from ..core.program_model.operations import ArcMove, LinearMove, Rapid, plain_moves
from ..core.program_model.program import ProgramPlan
from ..core.geometry.region import Region
from ..core.verify import Finding
from ..core.lathe.workholding import PlacedWorkholding
from . import ui_constants as ui
from .theme import LIGHT_COLORS, ColorSet, mix_colors


@dataclass(frozen=True)
class _View:
    """Maps millimetres (z, x) to picture pixels."""

    min_z: float
    max_x: float
    scale: float
    line_scale: float = 1.0  # < 1 when the window shows the picture enlarged: line widths, dashes, marks and text shrink by it

    def width(self, px: float) -> str:
        """A line width or font size of the picture, as the SVG attribute text."""
        return f"{px * self.line_scale:.4g}"

    def size(self, px: float) -> float:
        return px * self.line_scale

    def dash(self, text: str) -> str:
        return " ".join(f"{float(part) * self.line_scale:.4g}" for part in text.split())

    def px(self, point: Point) -> tuple[float, float]:
        return (
            ui.PICTURE_MARGIN_PX + (point.z - self.min_z) * self.scale,
            ui.PICTURE_MARGIN_PX + (self.max_x - point.x) * self.scale,
        )


@dataclass(frozen=True)
class Legend:
    """What the legend says: (colour, text) for every block shown, and the explanation lines."""

    blocks: tuple[tuple[str, str], ...] = ()
    key: tuple[str, ...] = ui.LEGEND_KEY_LINES


@dataclass(frozen=True)
class StepView:
    """What the picture shows when stepping through (V2): the material at that moment and the tool.

    The moves of the last shown block are drawn only up to `moves_done` (the moves count as in `StepFrame.move_number`).
    """

    material: Region
    tool_body: Region
    holder_outlines: tuple[tuple[Point, ...], ...] = ()
    moves_done: int = 0


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _region_path(region: Region, view: _View) -> str:
    parts = []
    for polygon in region.polygons():
        for ring in (polygon.exterior, *polygon.holes):
            coordinates = [view.px(point) for point in ring]
            parts.append(
                "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in coordinates) + " Z"
            )
    return " ".join(parts)


def _polygon_element(region: Region, view: _View, fill: str, stroke: str) -> str:
    if region.is_empty:
        return ""
    return (
        f'<path d="{_region_path(region, view)}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{view.width(ui.OUTLINE_WIDTH_PX)}" fill-rule="evenodd"/>'
    )


def _extent_points(plan: ProgramPlan, extra_points: tuple[Point, ...] = (), whole: bool = False) -> list[Point]:
    """What the picture shows by default: the raw part, the cutting moves and `extra_points`. The rapid moves (to the
    tool change position, the safe position) are drawn but may run out of the picture; with `whole` they are in it."""
    points: list[Point] = list(extra_points)
    bounds = plan.stock.bounds
    if bounds is not None:
        # x = 0 is the spindle axis; it is always in the picture.
        points += [Point(0, bounds.min_z), Point(bounds.max_x, bounds.max_z)]
    position: Point | None = None
    for operation in (m for op in plan.operations for m in plain_moves(op)):
        end = getattr(operation, "end", None)
        if isinstance(operation, ArcMove) and position is not None:
            points += _arc_points(position, operation)
        elif isinstance(end, Point) and (whole or not isinstance(operation, Rapid)):
            points.append(end)
        if isinstance(end, Point):
            position = end
    return points


def _make_view(points: list[Point], line_scale: float = 1.0) -> tuple[_View, float]:
    min_z = min(p.z for p in points)
    max_z = max(p.z for p in points)
    min_x = min(p.x for p in points)
    max_x = max(p.x for p in points)
    width = ui.PICTURE_WIDTH_PX - 2 * ui.PICTURE_MARGIN_PX
    scale = width / max(max_z - min_z, 1)
    height = (max_x - min_x) * scale + 2 * ui.PICTURE_MARGIN_PX
    if height < ui.MIN_PICTURE_HEIGHT_PX:
        height = ui.MIN_PICTURE_HEIGHT_PX
    return _View(min_z, max_x, scale, line_scale), height


def _arc_points(start: Point, move: ArcMove) -> list[Point]:
    arc = ArcSegment(start, move.end, move.center, move.direction)
    return arc.to_polyline()


def _last_block(plan: ProgramPlan, upto_block: int | None) -> int:
    last = len(plan.blocks) - 1 if upto_block is None else upto_block
    if upto_block is not None and not 0 <= last < len(plan.blocks):
        raise ValueError("there is no such block")
    return last


def block_color(colors: ColorSet, number: int) -> str:
    """The colour of the cutting moves of block `number` (0-based); the colours repeat."""
    return colors.block_colors[number % len(colors.block_colors)]


def legend_for(plan: ProgramPlan, upto_block: int | None = None, colors: ColorSet = LIGHT_COLORS) -> Legend:
    """The legend of the picture up to `upto_block` (None: the whole program)."""
    last = _last_block(plan, upto_block)
    rows = []
    for block_plan in plan.blocks[: last + 1]:
        block = block_plan.block
        rows.append((
            block_color(colors, block_plan.program_index),
            f"{block_plan.number}: {block.display_label()} {block.title}".strip(),
        ))
    return Legend(tuple(rows))


def _workholding_element(segments: tuple, view: _View, color: str, opacity: float, css_class: str) -> str:
    """One closed outline of the chuck body or the jaws as a filled, slightly transparent shape."""
    if not segments:
        return ""
    coordinates = [view.px(point) for point in segments_to_polyline(list(segments))]
    path = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in coordinates) + " Z"
    return (
        f'<path class="{css_class}" d="{path}" fill="{color}" fill-opacity="{opacity}" stroke="{color}" '
        f'stroke-width="{view.width(ui.WORKHOLDING_LINE_WIDTH_PX)}"/>'
    )


def _tool_elements(step: StepView, view: _View, colors: ColorSet) -> str:
    parts = []
    if not step.tool_body.is_empty:
        parts.append(_polygon_element(step.tool_body, view, colors.tool_cutter, colors.tool_cutter).replace(
            "<path ", f'<path fill-opacity="{ui.TOOL_FILL_OPACITY}" ', 1))
    for outline in step.holder_outlines:
        coordinates = [view.px(point) for point in outline]
        parts.append(
            '<polyline fill="none" stroke="%s" stroke-width="%s" points="%s"/>'
            % (colors.tool_holder, view.width(ui.TOOL_OUTLINE_WIDTH_PX), " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in coordinates))
        )
    return "\n".join(parts)


def render_svg(
    plan: ProgramPlan,
    upto_block: int | None = None,
    findings: list[Finding] | None = None,
    colors: ColorSet = LIGHT_COLORS,
    with_legend: bool = True,
    step: StepView | None = None,
    extra_points: tuple[Point, ...] = (),
    workholding: PlacedWorkholding | None = None,
    outline: tuple[Segment, ...] = (),
    fit: tuple[Point, ...] = (),
    order_colors: tuple[str, str] | None = None,
    rapids: bool = True,
    line_scale: float = 1.0,
    whole: bool = False,
) -> str:
    """The picture as SVG text.

    upto_block: show only the moves of blocks 0..upto_block (and the material
    left after that block). None shows the whole program.
    findings: collision findings (verify_plan); each is marked with a red cross, and
    listed in the legend when there is one.
    colors: the colour set; with no background in it the picture is transparent.
    with_legend: write the legend (blocks, findings, explanation) below the drawing.
    step: show the material and the tool of one step instead of the material after block `upto_block`.
    extra_points: positions that must be inside the picture, for example the safe positions: every tool path goes
    there, so the picture does not jump to a smaller scale when the first block is added.
    workholding: the placed chuck body and jaws, drawn behind the material (None: nothing, the flat clamping plane).
    outline: the finished shape of the block chosen in the flow list, dashed in its own colour (above the material, below
    the paths and the tool).
    fit: show only the part of the picture around these points (a zoom; what lies outside is cut off by the picture edge).
    order_colors: colour the cutting moves by the order they are made in, from the first colour to the second (the picture of a style).
    rapids: False leaves the rapid moves out.
    line_scale: 1 / the zoom of the window, so the lines keep their width on the screen when the picture is enlarged.
    whole: the picture holds all the rapid moves too (to the tool change position); the part and the cutting moves are
    the "home" view, written into the picture as `data-home` (`svg_home`), which a window shows first and zooms out of.
    """
    last = _last_block(plan, upto_block)
    home = None
    if whole and not fit:
        home_points = _extent_points(plan, extra_points)
        view, height = _make_view(_extent_points(plan, extra_points, whole=True), line_scale)
        home = _home_rect(home_points, view)
    else:
        view, height = _make_view(list(fit) if fit else _extent_points(plan, extra_points), line_scale)
    shown = plan.blocks[: last + 1]
    material = step.material if step else shown[-1].material_after if shown else plan.stock
    elements = _ground_elements(plan, shown, material, view, colors, workholding, outline)
    elements += _path_elements(shown, view, colors, step, order_colors, rapids)
    if step:
        elements.append(_tool_elements(step, view, colors))

    legend_rows = list(legend_for(plan, upto_block, colors).blocks)
    finding_elements, finding_rows = _finding_elements(findings or [], last, step, view, colors)
    elements += finding_elements
    legend_rows += finding_rows

    total_height = height
    if with_legend:
        legend_elements, total_height = _legend_elements(legend_rows, height, colors)
        elements += legend_elements
    return _document(elements, total_height, colors, home)


def _ground_elements(
    plan: ProgramPlan, shown: tuple, material: Region, view: _View, colors: ColorSet,
    workholding: PlacedWorkholding | None, outline: tuple[Segment, ...],
) -> list[str]:
    """What lies under the tool paths: the workholding, the far side of the part, the stock and the material, what was cut off, the axis and the finished outline."""
    elements = []
    if workholding is not None:
        elements.append(_workholding_element(
            workholding.chuck, view, colors.tool_holder, ui.WORKHOLDING_CHUCK_OPACITY, "workholding-chuck"))
        elements.append(_workholding_element(
            workholding.jaws, view, colors.tool_holder, ui.WORKHOLDING_JAWS_OPACITY, "workholding-jaws"))
    elements += [
        # the far side of the round part, faint and first, so everything else is drawn over it
        _polygon_element(material.mirrored(), view, colors.far_side_fill, colors.far_side_stroke),
        _polygon_element(plan.stock, view, colors.stock_fill, colors.stock_stroke),
        _polygon_element(material, view, colors.residual_fill, colors.residual_stroke),
    ]
    if shown and not shown[-1].cut_off.is_empty:  # what the last block shown cut off, only for that block
        elements.append(_polygon_element(shown[-1].cut_off, view, "none", block_color(colors, shown[-1].program_index)).replace(
            "<path ", f'<path stroke-dasharray="{view.dash("4 3")}" class="cut-off" ', 1))

    axis_start = view.px(Point(0, view.min_z))
    axis_end = view.px(Point(0, view.min_z + (ui.PICTURE_WIDTH_PX - 2 * ui.PICTURE_MARGIN_PX) / view.scale))
    elements.append(
        f'<line x1="{_fmt(axis_start[0])}" y1="{_fmt(axis_start[1])}" x2="{_fmt(axis_end[0])}" '
        f'y2="{_fmt(axis_end[1])}" stroke="{colors.axis}" stroke-width="{view.width(1)}" stroke-dasharray="{view.dash("2 4")}"/>'
    )

    if outline:
        line = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in (view.px(p) for p in segments_to_polyline(list(outline))))
        elements.append(
            f'<polyline class="finished-outline" fill="none" stroke="{colors.finished_outline}" '
            f'stroke-width="{view.width(ui.FINISHED_OUTLINE_WIDTH_PX)}" stroke-dasharray="{view.dash(ui.FINISHED_OUTLINE_DASH)}" points="{line}"/>'
        )
    return elements


def _path_elements(
    shown: tuple, view: _View, colors: ColorSet, step: StepView | None, order_colors: tuple[str, str] | None, rapids: bool,
) -> list[str]:
    """The rapid and cutting moves of the blocks shown, and the number of each block at its first cutting move."""
    elements = []
    position: Point | None = None
    cutting = sum(isinstance(m, (LinearMove, ArcMove)) for b in shown for op in b.operations for m in plain_moves(op))
    cut_number = 0
    for block_plan in shown:
        color = block_color(colors, block_plan.program_index)
        label_placed = False
        limit = step.moves_done if step and block_plan is shown[-1] else None
        drawn = 0
        for operation in (m for op in block_plan.operations for m in plain_moves(op)):
            if limit is not None and isinstance(operation, (Rapid, LinearMove, ArcMove)):
                if drawn >= limit:
                    break
                drawn += 1
            if isinstance(operation, Rapid):
                if position is not None and rapids:
                    x1, y1 = view.px(position)
                    x2, y2 = view.px(operation.end)
                    elements.append(
                        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" '
                        f'stroke="{colors.rapid if order_colors is None else colors.key_text}" stroke-dasharray="{view.dash(ui.RAPID_DASH)}" '
                        f'stroke-width="{view.width(ui.LINE_WIDTH_PX)}"/>'
                    )
                position = operation.end
            elif isinstance(operation, (LinearMove, ArcMove)) and position is not None:
                points = (
                    [position, operation.end]
                    if isinstance(operation, LinearMove)
                    else _arc_points(position, operation)
                )
                coordinates = [view.px(p) for p in points]
                if order_colors is not None:
                    color = mix_colors(order_colors[0], order_colors[1], cut_number / max(cutting - 1, 1))
                    cut_number += 1
                elements.append(
                    '<polyline fill="none" stroke="%s" stroke-width="%s" points="%s"/>'
                    % (color, view.width(ui.LINE_WIDTH_PX), " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in coordinates))
                )
                if not label_placed and order_colors is None:
                    x, y = coordinates[0]
                    # A scale, not a smaller font: Qt refuses a font of less than one pixel (a warning for every label).
                    elements.append(
                        f'<text transform="translate({_fmt(x + view.size(ui.LABEL_OFFSET_PX))} '
                        f'{_fmt(y - view.size(ui.LABEL_OFFSET_PX))}) scale({view.line_scale:.4g})" '
                        f'font-size="{ui.LABEL_FONT_PX}" fill="{color}">{block_plan.number}</text>'
                    )
                    label_placed = True
                position = operation.end
            else:
                end = getattr(operation, "end", None)
                if isinstance(end, Point):
                    position = end
    return elements


def _finding_elements(
    findings: list[Finding], last: int, step: StepView | None, view: _View, colors: ColorSet,
) -> tuple[list[str], list[tuple[str, str]]]:
    """A red cross for every finding shown, and its row for the legend."""
    elements, rows = [], []
    for finding in findings:
        if finding.block_index > last or (step and finding.block_index == last and finding.move_number > step.moves_done):
            continue  # stepping: the cross appears with the move that causes it
        x, y = view.px(finding.position)
        size = view.size(ui.FINDING_MARK_PX)
        elements.append(
            f'<path d="M {_fmt(x - size)} {_fmt(y - size)} L {_fmt(x + size)} {_fmt(y + size)} '
            f'M {_fmt(x - size)} {_fmt(y + size)} L {_fmt(x + size)} {_fmt(y - size)}" '
            f'stroke="{colors.finding}" stroke-width="{view.width(ui.FINDING_WIDTH_PX)}" fill="none"/>'
        )
        rows.append((colors.finding, finding.message))
    return elements, rows


def _legend_elements(legend_rows: list[tuple[str, str]], height: float, colors: ColorSet) -> tuple[list[str], float]:
    """The legend below the drawing (the rows, then the explanation lines) and the height of the whole picture."""
    elements = []
    key_lines = ui.LEGEND_KEY_LINES
    legend_height = (len(legend_rows) + len(key_lines)) * ui.LEGEND_LINE_HEIGHT_PX
    for row, (color, text) in enumerate(legend_rows):
        y = height + ui.LEGEND_LINE_HEIGHT_PX * (row + 1)
        elements.append(
            f'<text x="{ui.PICTURE_MARGIN_PX}" y="{y}" font-size="{ui.LABEL_FONT_PX}" '
            f'fill="{color}">{escape(text)}</text>'
        )
    for row, text in enumerate(key_lines):
        y = height + ui.LEGEND_LINE_HEIGHT_PX * (len(legend_rows) + row + 1)
        elements.append(
            f'<text x="{ui.PICTURE_MARGIN_PX}" y="{y}" font-size="{ui.LABEL_FONT_PX}" '
            f'fill="{colors.key_text}">{escape(text)}</text>'
        )
    return elements, height + legend_height + ui.LEGEND_LINE_HEIGHT_PX


def _home_rect(points: list[Point], view: _View) -> tuple[float, float, float, float]:
    """The rectangle (x, y, width, height in picture units) round these points, with the margin of the picture."""
    left, top = view.px(Point(max(p.x for p in points), min(p.z for p in points)))
    right, bottom = view.px(Point(min(p.x for p in points), max(p.z for p in points)))
    margin = ui.PICTURE_MARGIN_PX
    return (left - margin, top - margin, right - left + 2 * margin, bottom - top + 2 * margin)


HOME_ATTRIBUTE = re.compile(r'data-home="([-\d.eE]+) ([-\d.eE]+) ([-\d.eE]+) ([-\d.eE]+)"')


def svg_home(text: str) -> tuple[float, float, float, float] | None:
    """The home rectangle of a picture made with `whole` (None: the picture is shown as it is)."""
    found = HOME_ATTRIBUTE.search(text[:400])
    return None if found is None else tuple(float(part) for part in found.groups())  # type: ignore[return-value]


def _document(
    elements: list[str], total_height: float, colors: ColorSet, home: tuple[float, float, float, float] | None = None,
) -> str:
    """The elements as one SVG text."""
    # A background gets its real size (a "100%" rectangle was drawn too small by the Qt SVG widget).
    background = (
        f'<rect width="{ui.PICTURE_WIDTH_PX}" height="{_fmt(total_height)}" fill="{colors.background}"/>\n'
        if colors.background
        else ""
    )
    body = "\n".join(element for element in elements if element)
    home_text = "" if home is None else " data-home=\"" + " ".join(_fmt(part) for part in home) + "\""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"{home_text} width="{ui.PICTURE_WIDTH_PX}" '
        f'height="{_fmt(total_height)}" viewBox="0 0 {ui.PICTURE_WIDTH_PX} {_fmt(total_height)}">\n'
        f"{background}{body}\n</svg>\n"
    )
