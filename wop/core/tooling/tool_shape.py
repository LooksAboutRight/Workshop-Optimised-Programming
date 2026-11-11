"""Tool shapes and the contour editor (a tool shape is edited as a closed contour).

`shape_to_definition` turns the shape of any tool (made by a tool type or drawn) into a closed contour definition with
cutting flags and named points, ready for the contour editor. `tool_from_contour` does the way back: the cutting flags
become the roles of the pieces, so what the user marked as cutting edge may touch the material and the rest never.
A tool that was changed in the editor is a free shape: it keeps no tool type and no type form (`kind` is empty).
"""

from __future__ import annotations

from dataclasses import replace

from ..contour import ArcCenterStep, Contour, ContourDefinition, ContourError, LineStep, NamedPoint, Step
from ..geometry import ArcSegment
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape


def shape_to_definition(shape: ToolShape, points: tuple[NamedPoint, ...] = ()) -> ContourDefinition:
    """The outline as a closed chain of steps: a line for each line piece, an arc by centre for each arc piece."""
    steps: list[Step] = []
    for piece in shape.pieces:
        cutting = piece.role is ToolSegmentRole.CUTTER
        segment = piece.segment
        if isinstance(segment, ArcSegment):
            steps.append(ArcCenterStep(segment.end, segment.center, segment.direction, cutting))
        else:
            steps.append(LineStep(segment.end, cutting=cutting))
    return ContourDefinition(shape.pieces[0].segment.start, tuple(steps), True, points)


def tool_from_contour(tool: Tool, contour: Contour) -> Tool:
    """The tool with the outline of the contour (closed, valid) and its named points; it becomes a free shape."""
    if not contour.is_valid:
        raise ToolError(contour.error or "the shape has no valid outline")
    if not contour.is_closed:
        raise ToolError("the shape is not closed")
    cutting = contour.cutting or (False,) * len(contour.segments)
    pieces = tuple(
        ToolSegment(segment, ToolSegmentRole.CUTTER if flag else ToolSegmentRole.HOLDER)
        for segment, flag in zip(contour.segments, cutting)
    )
    try:
        shape = ToolShape(pieces)
    except ContourError as error:  # not expected: a valid contour is connected
        raise ToolError(str(error)) from error
    return replace(tool, shape=shape, kind="", definition=None, points=contour.points, sketch=contour.sketch)
