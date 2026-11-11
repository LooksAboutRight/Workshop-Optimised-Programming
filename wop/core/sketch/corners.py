"""Fillet and chamfer of a corner where two pieces (lines or arcs) meet.

The two original pieces and the corner point stay, as thin dashed reference pieces (construction pieces that are not part
of the outline), so the sharp corner can still be dimensioned. Two new pieces are made that match them: each shares the
far end of its old piece, and its new end is held on the old piece. A fillet joins the new pieces with an arc that is tied to
both by tangent relations and a radius dimension; a chamfer joins them with a straight line and gets a distance
dimension from the corner to each of its ends, so it is fully defined and can be changed. The whole is one unit
(`CornerLink`, see `Sketch._repair_corners`).

Geometry: a line is cut where the fillet circle touches it, or at the distance of the chamfer along it. An arc is cut where
the fillet circle touches it (the fillet circle lies inside the angle between the pieces, the solution nearest to the corner),
or at the chamfer's straight distance from the corner (a chord of the arc). The new arc keeps the centre of the old one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import ArcDirection
from .constants import ANGLE_EPSILON, POINT_TOLERANCE
from .model import CornerLink, Piece, Sketch, SketchArc, SketchError, SketchLine

XZ = tuple[float, float]
TOO_BIG = "The value is too big for the pieces"
NO_FIT = "A fillet of that radius does not fit between the two pieces"


@dataclass(frozen=True)
class _Side:
    """One of the two pieces that meet at the corner, seen from the corner."""

    piece: Piece
    far: int  # the point at the other end of the piece
    direction: XZ  # unit vector from the corner along the piece (the tangent for an arc)
    length: float  # the length of the line, or of the arc, from the corner to the far end
    centre: XZ | None = None  # an arc: its centre, radius, which way round it runs away from the corner, where the corner is on it, how far it goes
    radius: float = 0.0
    away_turn: int = 1
    angle0: float = 0.0
    extent: float = 0.0

    @property
    def is_arc(self) -> bool:
        return self.centre is not None

    @property
    def piece_id(self) -> int:
        return self.piece.arc_id if isinstance(self.piece, SketchArc) else self.piece.line_id


@dataclass(frozen=True)
class _Corner:
    point_id: int
    x: float
    z: float
    first: _Side
    second: _Side
    angle: float  # between the two pieces at the corner, 0 to pi

    @property
    def sides(self) -> tuple[_Side, _Side]:
        return self.first, self.second


def _side(sketch: Sketch, piece: Piece, point_id: int) -> _Side:
    corner = sketch.point(point_id)
    if isinstance(piece, SketchLine):
        far = piece.end if piece.start == point_id else piece.start
        end = sketch.point(far)
        length = corner.position.distance_to(end.position)
        return _Side(piece, far, ((end.x - corner.x) / length, (end.z - corner.z) / length), length)
    segment = sketch.segment(piece)
    at_start = piece.start == point_id
    away_turn = segment.turn if at_start else -segment.turn
    angle0 = segment.start_angle if at_start else segment.end_angle
    direction = (-math.sin(angle0) * away_turn, math.cos(angle0) * away_turn)
    return _Side(
        piece, piece.end if at_start else piece.start, direction, segment.radius * segment.sweep,
        (segment.center.x, segment.center.z), segment.radius, away_turn, angle0, segment.sweep,
    )


def _read_corner(sketch: Sketch, point_id: int) -> _Corner:
    lines = [line for line in sketch.lines.values() if point_id in (line.start, line.end) and not line.construction]
    arcs = [arc for arc in sketch.arcs.values() if point_id in (arc.start, arc.end) and arc.start != arc.end and not arc.construction]
    centre_of = [arc for arc in sketch.arcs.values() if point_id == arc.centre]
    pieces: list[Piece] = sorted([*lines, *arcs], key=lambda p: p.arc_id if isinstance(p, SketchArc) else p.line_id)
    if len(pieces) != 2 or centre_of:
        raise SketchError("A corner needs exactly two lines or arcs that meet at the point")
    first, second = (_side(sketch, piece, point_id) for piece in pieces)
    cosine = max(-1.0, min(1.0, first.direction[0] * second.direction[0] + first.direction[1] * second.direction[1]))
    angle = math.acos(cosine)
    if math.sin(angle) < ANGLE_EPSILON:
        raise SketchError("The two pieces run along each other")
    corner = sketch.point(point_id)
    return _Corner(point_id, corner.x, corner.z, first, second, angle)


def is_corner(sketch: Sketch, point_id: int) -> bool:
    """Is this point a place where a fillet or chamfer can be made?"""
    try:
        _read_corner(sketch, point_id)
    except SketchError:
        return False
    return True


# --- where the corner is cut ------------------------------------------------------------------------------------------------

def _along_line(corner: _Corner, side: _Side, amount: float) -> XZ:
    return corner.x + side.direction[0] * amount, corner.z + side.direction[1] * amount


def _chamfer_end(corner: _Corner, side: _Side, distance: float) -> XZ:
    """The point on the piece at the straight distance from the corner."""
    if not side.is_arc:
        if distance >= side.length:
            raise SketchError(TOO_BIG)
        return _along_line(corner, side, distance)
    if distance >= 2 * side.radius or 2 * math.asin(distance / (2 * side.radius)) >= side.extent:
        raise SketchError(TOO_BIG)
    angle = side.angle0 + side.away_turn * 2 * math.asin(distance / (2 * side.radius))
    return side.centre[0] + side.radius * math.cos(angle), side.centre[1] + side.radius * math.sin(angle)


def _fillet_between_lines(corner: _Corner, radius: float) -> tuple[XZ, list[XZ]]:
    back = radius / math.tan(corner.angle / 2)
    if back >= corner.first.length or back >= corner.second.length:
        raise SketchError(TOO_BIG)
    bisector = (
        corner.first.direction[0] + corner.second.direction[0], corner.first.direction[1] + corner.second.direction[1],
    )
    reach = radius / math.sin(corner.angle / 2) / math.hypot(*bisector)
    return (corner.x + bisector[0] * reach, corner.z + bisector[1] * reach), [_along_line(corner, s, back) for s in corner.sides]


def _offset(side: _Side, corner: _Corner, bisector: XZ, radius: float):
    """Where the centre of a circle of this radius lies when it touches the piece on the side of the angle: on a parallel line,
    or on a concentric circle."""
    if not side.is_arc:
        normal = (-side.direction[1], side.direction[0])
        if normal[0] * bisector[0] + normal[1] * bisector[1] < 0:
            normal = (-normal[0], -normal[1])
        return ("line", (corner.x + normal[0] * radius, corner.z + normal[1] * radius), side.direction)
    towards_centre = (side.centre[0] - corner.x, side.centre[1] - corner.z)
    inside = towards_centre[0] * bisector[0] + towards_centre[1] * bisector[1] > 0
    rho = side.radius - radius if inside else side.radius + radius
    if rho <= POINT_TOLERANCE:
        raise SketchError(NO_FIT)
    return ("circle", side.centre, rho)


def _line_circle(origin: XZ, direction: XZ, centre: XZ, rho: float) -> list[XZ]:
    ox, oz = origin[0] - centre[0], origin[1] - centre[1]
    b = direction[0] * ox + direction[1] * oz
    c = ox * ox + oz * oz - rho * rho
    discriminant = b * b - c
    if discriminant < 0:
        return []
    root = math.sqrt(discriminant)
    return [(origin[0] + direction[0] * t, origin[1] + direction[1] * t) for t in (-b - root, -b + root)]


def _circle_circle(first: tuple[XZ, float], second: tuple[XZ, float]) -> list[XZ]:
    (c1, r1), (c2, r2) = first, second
    dx, dz = c2[0] - c1[0], c2[1] - c1[1]
    distance = math.hypot(dx, dz)
    if distance < POINT_TOLERANCE or distance > r1 + r2 or distance < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + distance * distance) / (2 * distance)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mid = (c1[0] + dx * a / distance, c1[1] + dz * a / distance)
    return [(mid[0] - dz * h / distance, mid[1] + dx * h / distance), (mid[0] + dz * h / distance, mid[1] - dx * h / distance)]


def _tangent_point(side: _Side, corner: _Corner, centre: XZ) -> XZ | None:
    """Where a circle with this centre touches the piece, if that is on the piece (between the corner and the far end)."""
    if not side.is_arc:
        reach = (centre[0] - corner.x) * side.direction[0] + (centre[1] - corner.z) * side.direction[1]
        if not POINT_TOLERANCE < reach < side.length - POINT_TOLERANCE:
            return None
        return _along_line(corner, side, reach)
    vx, vz = centre[0] - side.centre[0], centre[1] - side.centre[1]
    norm = math.hypot(vx, vz)
    if norm < POINT_TOLERANCE:
        return None
    touch = (side.centre[0] + vx / norm * side.radius, side.centre[1] + vz / norm * side.radius)
    angle = math.atan2(touch[1] - side.centre[1], touch[0] - side.centre[0])
    travelled = ((angle - side.angle0) * side.away_turn) % math.tau
    return touch if POINT_TOLERANCE < travelled < side.extent - POINT_TOLERANCE else None


def _fillet_general(corner: _Corner, radius: float) -> tuple[XZ, list[XZ]]:
    """The fillet circle of this radius inside the angle between two pieces, one of them an arc: the solution nearest to the corner."""
    sum_x = corner.first.direction[0] + corner.second.direction[0]
    sum_z = corner.first.direction[1] + corner.second.direction[1]
    length = math.hypot(sum_x, sum_z)
    bisector = (sum_x / length, sum_z / length)
    one, two = (_offset(side, corner, bisector, radius) for side in corner.sides)
    if one[0] == "circle" and two[0] == "circle":
        candidates = _circle_circle((one[1], one[2]), (two[1], two[2]))
    elif one[0] == "line":
        candidates = _line_circle(one[1], one[2], two[1], two[2])
    else:
        candidates = _line_circle(two[1], two[2], one[1], one[2])
    best = None
    for centre in candidates:
        if (centre[0] - corner.x) * bisector[0] + (centre[1] - corner.z) * bisector[1] <= 0:
            continue
        touches = [_tangent_point(side, corner, centre) for side in corner.sides]
        if None in touches:
            continue
        distance = math.hypot(centre[0] - corner.x, centre[1] - corner.z)
        if best is None or distance < best[0]:
            best = (distance, centre, touches)
    if best is None:
        raise SketchError(NO_FIT)
    return best[1], best[2]


# --- making the new pieces --------------------------------------------------------------------------------------------------

def _cut(sketch: Sketch, point_id: int, side: _Side, position: XZ) -> tuple[int, int]:
    """Keep the old piece as a reference piece and make a new piece beside it that ends at `position`, on the old piece.

    Returns the id of the new piece and of its new end point."""
    end = sketch.add_point(*position)
    old = side.piece
    if isinstance(old, SketchLine):
        # the new line keeps the way round of the old one, so a contour still runs the way it was drawn
        new = sketch.add_line(end, side.far, cutting=old.cutting) if old.start == point_id else sketch.add_line(side.far, end, cutting=old.cutting)
        sketch.update_piece(old.line_id, construction=True, reference=True, cutting=False)
        sketch.add_constraint("point_on_line", (end, old.line_id))
    else:
        if old.start == point_id:
            new = sketch.add_arc(old.centre, end, old.end, old.direction, cutting=old.cutting)
        else:
            new = sketch.add_arc(old.centre, old.start, end, old.direction, cutting=old.cutting)
        sketch.update_piece(old.arc_id, construction=True, reference=True, cutting=False)
        sketch.add_constraint("point_on_circle", (end, old.arc_id))
    if piece_id_of(old) in sketch.rapid_pieces:  # what a path says about a piece goes to the shortened piece
        sketch.rapid_pieces.add(new)
    if piece_id_of(old) in sketch.piece_feeds:
        sketch.piece_feeds[new] = sketch.piece_feeds[piece_id_of(old)]
    return new, end


def piece_id_of(piece: Piece) -> int:
    return piece.line_id if isinstance(piece, SketchLine) else piece.arc_id


def _bevel_like_its_pieces(sketch: Sketch, bevel: int, corner: _Corner) -> None:
    """In a path the new piece of a corner is rapid when both pieces were, and has a feed of its own only when both pieces have the
    same one (otherwise it gets the feed of the block)."""
    first, second = corner.first.piece_id, corner.second.piece_id
    if first in sketch.rapid_pieces and second in sketch.rapid_pieces and bevel in sketch.lines:
        sketch.rapid_pieces.add(bevel)
    feed = sketch.piece_feeds.get(first)
    if feed is not None and feed == sketch.piece_feeds.get(second):
        sketch.piece_feeds[bevel] = feed


def _tangent(sketch: Sketch, new: int, bevel: int, touch: int) -> None:
    kind = "tangent_line_arc" if new in sketch.lines else "tangent_arcs"
    sketch.add_constraint(kind, (new, bevel, touch))


def _cutting(corner: _Corner) -> bool:
    return corner.first.piece.cutting or corner.second.piece.cutting


def _link(point_id: int, corner: _Corner, kept: tuple[int, int], ends: tuple[int, int], bevel: int) -> CornerLink:
    return CornerLink(point_id, kept, ends, (corner.first.piece_id, corner.second.piece_id), bevel)


def fillet_corner(sketch: Sketch, point_id: int, radius: float) -> int:
    """Round the corner with an arc of this radius; returns the arc id."""
    if radius <= 0:
        raise SketchError("The radius must be more than zero")
    corner = _read_corner(sketch, point_id)
    if corner.first.is_arc or corner.second.is_arc:
        centre_at, touches = _fillet_general(corner, radius)
    else:
        centre_at, touches = _fillet_between_lines(corner, radius)
    cutting = _cutting(corner)
    (first, end_first), (second, end_second) = (_cut(sketch, point_id, s, t) for s, t in zip(corner.sides, touches))
    centre = sketch.add_point(*centre_at)
    c, s, e = (sketch.point(i) for i in (centre, end_first, end_second))
    turn = (s.x - c.x) * (e.z - c.z) - (s.z - c.z) * (e.x - c.x)
    arc = sketch.add_arc(centre, end_first, end_second, ArcDirection.CCW if turn >= 0 else ArcDirection.CW, cutting=cutting)
    _tangent(sketch, first, arc, end_first)
    _tangent(sketch, second, arc, end_second)
    sketch.add_constraint("radius", (arc,), (radius,))
    _bevel_like_its_pieces(sketch, arc, corner)
    sketch.link_corner(_link(point_id, corner, (first, second), (end_first, end_second), arc))
    return arc


def chamfer_corner(sketch: Sketch, point_id: int, distance: float) -> int:
    """Cut the corner with a straight line, `distance` from the corner along each piece (for an arc: the straight distance);
    returns the new line id."""
    if distance <= 0:
        raise SketchError("The distance must be more than zero")
    corner = _read_corner(sketch, point_id)
    ends = [_chamfer_end(corner, side, distance) for side in corner.sides]
    cutting = _cutting(corner)
    (first, end_first), (second, end_second) = (_cut(sketch, point_id, s, t) for s, t in zip(corner.sides, ends))
    line = sketch.add_line(end_first, end_second, cutting=cutting)
    sketch.add_constraint("distance", (point_id, end_first), (distance,))
    sketch.add_constraint("distance", (point_id, end_second), (distance,))
    _bevel_like_its_pieces(sketch, line, corner)
    sketch.link_corner(_link(point_id, corner, (first, second), (end_first, end_second), line))
    return line
