"""Mirror pieces of a sketch about a line, the Z axis (x = 0, the spindle axis) or the X axis (z = 0).

The copies share a point with the original where the original point lies on the axis. Every other point gets a mirror
point tied to the original by a symmetric relation, so moving or dimensioning one side moves the other.
"""

from __future__ import annotations

from ..geometry import ArcDirection, Point
from .constants import MIRROR_KINDS, ORIGIN, POINT_TOLERANCE
from .model import Piece, Sketch, SketchArc, SketchError, SketchLine
from .pick import piece_points

AXIS_Z = "z"
AXIS_X = "x"


class _Reflection:
    def __init__(self, sketch: Sketch, axis: str | int) -> None:
        self.axis = axis
        if isinstance(axis, int):
            line = sketch.lines[axis]
            self.a, self.b = sketch.point(line.start).position, sketch.point(line.end).position
            self.length = self.a.distance_to(self.b)
            if self.length == 0:
                raise SketchError("The mirror line has no length")

    def distance(self, point: Point) -> float:
        """Distance from the axis (a point with distance 0 stays where it is)."""
        if self.axis == AXIS_Z:
            return abs(point.x)
        if self.axis == AXIS_X:
            return abs(point.z)
        dx, dz = (self.b.x - self.a.x) / self.length, (self.b.z - self.a.z) / self.length
        return abs(dx * (point.z - self.a.z) - dz * (point.x - self.a.x))

    def reflect(self, point: Point) -> Point:
        if self.axis == AXIS_Z:
            return Point(-point.x, point.z)
        if self.axis == AXIS_X:
            return Point(point.x, -point.z)
        dx, dz = (self.b.x - self.a.x) / self.length, (self.b.z - self.a.z) / self.length
        vx, vz = point.x - self.a.x, point.z - self.a.z
        along = vx * dx + vz * dz
        return Point(self.a.x + 2 * along * dx - vx, self.a.z + 2 * along * dz - vz)


def reflect_position(sketch: Sketch, position: Point, axis: str | int) -> Point:
    """Where a position lands when it is mirrored about the axis (AXIS_Z, AXIS_X or the id of a line)."""
    return _Reflection(sketch, axis).reflect(position)


def find_mirror_helper(sketch: Sketch, point_id: int, axis: str | int) -> int | None:
    """The mirror point of a point about the axis, if there is one already."""
    for constraint in sketch.constraints.values():
        if constraint.kind not in MIRROR_KINDS or point_id not in constraint.refs[:2]:
            continue
        other = constraint.refs[1] if constraint.refs[0] == point_id else constraint.refs[0]
        if other in sketch.helpers and _same_axis(constraint, axis):
            return other
    return None


def _same_axis(constraint, axis: str | int) -> bool:
    if axis == AXIS_Z:
        return constraint.kind == "symmetric_axis_z"
    return constraint.kind == "symmetric" and constraint.refs[2] == axis


def mirror_helper(sketch: Sketch, point_id: int, axis: str | int) -> int:
    """The mirror point of a point about the axis; made (hidden, tied by a symmetric relation) if it does not exist.
    A dimension from the point to its mirror point is the distance across the axis: the diameter."""
    found = find_mirror_helper(sketch, point_id, axis)
    if found is not None:
        return found
    position = reflect_position(sketch, sketch.point(point_id).position, axis)
    helper = sketch.add_point(position.x, position.z)
    sketch.helpers.add(helper)
    if axis == AXIS_Z:
        sketch.add_constraint("symmetric_axis_z", (point_id, helper))
    else:
        sketch.add_constraint("symmetric", (point_id, helper, axis))
    return helper


def _try_add(sketch: Sketch, kind: str, refs: tuple[int, ...]) -> None:
    try:
        sketch.add_constraint(kind, refs)
    except SketchError:
        pass  # already there


def _hold_on_axis(sketch: Sketch, point_id: int, axis: str | int) -> None:
    if axis == AXIS_Z:
        _try_add(sketch, "horizontal", (point_id, ORIGIN))
    elif axis == AXIS_X:
        _try_add(sketch, "vertical", (point_id, ORIGIN))
    elif point_id not in (sketch.lines[axis].start, sketch.lines[axis].end):
        _try_add(sketch, "point_on_line", (point_id, axis))


def mirror_pieces(sketch: Sketch, piece_ids: list[int], axis: str | int) -> list[int]:
    """Copy the pieces mirrored about the axis (AXIS_Z, AXIS_X or the id of a line); returns the new piece ids."""
    reflection = _Reflection(sketch, axis)
    pieces: list[Piece] = [p for p in sketch.pieces() if _id(p) in piece_ids and _id(p) != axis]
    if not pieces:
        raise SketchError("Select the pieces to mirror")
    mapping: dict[int, int] = {}
    for piece in pieces:
        for point_id in sorted(piece_points(piece)):
            if point_id in mapping:
                continue
            position = sketch.point(point_id).position
            if reflection.distance(position) <= POINT_TOLERANCE:
                mapping[point_id] = point_id
                _hold_on_axis(sketch, point_id, axis)
            else:
                mirrored = reflection.reflect(position)
                mapping[point_id] = sketch.add_point(mirrored.x, mirrored.z)
                _symmetric(sketch, point_id, mapping[point_id], axis)
    created: list[int] = []
    for piece in pieces:
        if isinstance(piece, SketchLine):
            if mapping[piece.start] == piece.start and mapping[piece.end] == piece.end:
                continue  # lies on the axis: its mirror image is itself
            created.append(sketch.add_line(mapping[piece.start], mapping[piece.end], piece.construction, piece.cutting, piece.centre_line, piece.reference))
        else:
            turned = ArcDirection.CW if piece.direction is ArcDirection.CCW else ArcDirection.CCW
            created.append(
                sketch.add_arc(
                    mapping[piece.centre], mapping[piece.start], mapping[piece.end], turned, piece.construction, piece.cutting
                )
            )
    return created


def _symmetric(sketch: Sketch, original: int, mirrored: int, axis: str | int) -> None:
    if axis == AXIS_Z:
        _try_add(sketch, "symmetric_axis_z", (original, mirrored))
    elif axis == AXIS_X:
        _try_add(sketch, "symmetric_axis_x", (original, mirrored))
    else:
        _try_add(sketch, "symmetric", (original, mirrored, axis))


def _id(piece: Piece) -> int:
    return piece.arc_id if isinstance(piece, SketchArc) else piece.line_id
