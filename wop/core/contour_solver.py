"""Turn a ContourDefinition into exact line and arc segments (requirement C2).

Corners between two straight lines are rounded (tangent arc) or chamfered.
Rounding and chamfering is limited to line-to-line corners for now.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import ANGLE_TOLERANCE_RAD, GEOMETRY_TOLERANCE_MM
from .contour import (
    ArcRadiusStep,
    Contour,
    ContourDefinition,
    ContourError,
    Corner,
    CornerKind,
    LineStep,
    Step,
)
from .geometry import (
    ArcDirection,
    ArcSegment,
    LineSegment,
    Point,
    Segment,
    arc_from_endpoints,
    segments_to_polyline,
    signed_area,
)


@dataclass(frozen=True)
class _CornerGeometry:
    in_point: Point  # where the incoming line ends
    out_point: Point  # where the outgoing line starts
    connector: Segment  # tangent arc or chamfer line between them
    distance_mm: float  # how far both lines are shortened


def solve_contour(definition: ContourDefinition) -> list[Segment]:
    """Resolve all steps into segments. Raises ContourError with the step index."""
    return [segment for _step, segment in solve_contour_tagged(definition)]


def solve_contour_tagged(definition: ContourDefinition) -> list[tuple[int, Segment]]:
    """The segments of the contour, each with the index of the step it belongs to.

    The connector of a corner (fillet or chamfer) belongs to the step that has the corner.
    """
    if not definition.steps:
        raise ContourError("the contour has no steps")
    steps = definition.steps
    points = [definition.start] + [step.end for step in steps]
    corners = _solve_corners(steps, points)
    segments: list[tuple[int, Segment]] = []
    for index, step in enumerate(steps):
        start, end = points[index], points[index + 1]
        try:
            if isinstance(step, LineStep):
                pieces = _line_with_corners(index, start, end, corners)
                for number, piece in enumerate(pieces):
                    is_connector = index in corners and number == 0
                    segments.append((index - 1 if is_connector else index, piece))
            elif isinstance(step, ArcRadiusStep):
                segments.append(
                    (index, arc_from_endpoints(start, end, step.radius_mm, step.direction, step.large_arc))
                )
            else:
                segments.append((index, ArcSegment(start, end, step.center, step.direction)))
        except ContourError:
            raise
        except ValueError as error:
            raise ContourError(f"step {index + 1}: {error}", index) from error
    last = segments[-1][1].end
    if definition.closed and not last.is_close(definition.start, GEOMETRY_TOLERANCE_MM):
        segments.append((len(steps), LineSegment(last, definition.start)))  # the closing line belongs to no step
    return segments


def build_contour(contour_id: str, name: str, definition: ContourDefinition) -> Contour:
    """Solve a definition and keep both the input and the result (with the cutting flags and the named points)."""
    _check_points(definition)
    tagged = solve_contour_tagged(definition)
    segments = tuple(segment for _step, segment in tagged)
    if definition.closed and abs(signed_area(segments_to_polyline(list(segments)))) <= GEOMETRY_TOLERANCE_MM:
        raise ContourError("a closed shape needs an area (the lines run back over each other)")
    steps = definition.steps
    cutting = tuple(step < len(steps) and steps[step].cutting for step, _segment in tagged)
    if not any(cutting):
        cutting = ()  # no cutting edge marked: the same as a contour of a part
    return Contour(contour_id, name, segments, definition, "", cutting, definition.points)


def _check_points(definition: ContourDefinition) -> None:
    seen: set[str] = set()
    for point in definition.points:
        if not point.name.strip():
            raise ContourError("a point needs a name")
        if point.name in seen:
            raise ContourError(f"the point name {point.name!r} is used twice")
        seen.add(point.name)


def _solve_corners(steps: tuple[Step, ...], points: list[Point]) -> dict[int, _CornerGeometry]:
    """Corner geometry per vertex index (vertex 0 is the start point)."""
    corners: dict[int, _CornerGeometry] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, LineStep) or step.corner.kind is CornerKind.NONE:
            continue
        vertex = index + 1
        if vertex >= len(steps):
            raise ContourError(f"step {index + 1}: a corner needs a following line", index)
        if not isinstance(steps[vertex], LineStep):
            raise ContourError(
                f"step {index + 1}: rounding or chamfering is only supported between two straight lines",
                index,
            )
        corners[vertex] = _corner_geometry(
            points[index], points[vertex], points[vertex + 1], step.corner, index
        )
    return corners


def _corner_geometry(
    previous: Point, vertex: Point, following: Point, corner: Corner, index: int
) -> _CornerGeometry:
    label = f"step {index + 1}"
    if corner.size_mm <= GEOMETRY_TOLERANCE_MM:
        raise ContourError(f"{label}: the corner size must be greater than zero", index)
    length_in = vertex.distance_to(previous)
    length_out = vertex.distance_to(following)
    if length_in <= GEOMETRY_TOLERANCE_MM or length_out <= GEOMETRY_TOLERANCE_MM:
        raise ContourError(f"{label}: a line next to the corner has zero length", index)

    # unit vectors from the vertex back along the incoming and forward along the outgoing line
    ux, uz = (previous.x - vertex.x) / length_in, (previous.z - vertex.z) / length_in
    wx, wz = (following.x - vertex.x) / length_out, (following.z - vertex.z) / length_out
    cross = ux * wz - uz * wx
    dot = ux * wx + uz * wz
    if abs(cross) <= ANGLE_TOLERANCE_RAD:
        raise ContourError(
            f"{label}: the two lines are collinear or fold back, so a corner makes no sense", index
        )
    half_angle = math.acos(max(-1, min(1, dot))) / 2

    is_fillet = corner.kind is CornerKind.FILLET
    distance = corner.size_mm / math.tan(half_angle) if is_fillet else corner.size_mm
    in_point = Point(vertex.x + ux * distance, vertex.z + uz * distance)
    out_point = Point(vertex.x + wx * distance, vertex.z + wz * distance)

    if is_fillet:
        bisector_x, bisector_z = ux + wx, uz + wz
        bisector_length = math.hypot(bisector_x, bisector_z)
        center_distance = corner.size_mm / math.sin(half_angle)
        center = Point(
            vertex.x + bisector_x / bisector_length * center_distance,
            vertex.z + bisector_z / bisector_length * center_distance,
        )
        direction = ArcDirection.CCW if cross < 0 else ArcDirection.CW
        connector: Segment = ArcSegment(in_point, out_point, center, direction)
    else:
        connector = LineSegment(in_point, out_point)
    return _CornerGeometry(in_point, out_point, connector, distance)


def _line_with_corners(
    index: int, start: Point, end: Point, corners: dict[int, _CornerGeometry]
) -> list[Segment]:
    """The corner connector at the line's start (if any) followed by the shortened line."""
    incoming = corners.get(index)
    outgoing = corners.get(index + 1)
    length = start.distance_to(end)
    if length <= GEOMETRY_TOLERANCE_MM:
        raise ContourError(f"step {index + 1}: the line has zero length", index)
    trim_start = incoming.distance_mm if incoming else 0
    trim_end = outgoing.distance_mm if outgoing else 0
    remaining = length - trim_start - trim_end
    if remaining < -GEOMETRY_TOLERANCE_MM:
        raise ContourError(
            f"step {index + 1}: the corners on this line are too large for its length", index
        )
    result: list[Segment] = []
    if incoming:
        result.append(incoming.connector)
    if remaining > GEOMETRY_TOLERANCE_MM:
        line_start = incoming.out_point if incoming else start
        line_end = outgoing.in_point if outgoing else end
        result.append(LineSegment(line_start, line_end))
    return result
