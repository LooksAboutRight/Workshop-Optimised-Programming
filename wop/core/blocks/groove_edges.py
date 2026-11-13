"""The edge of a groove wall: a chamfer or a fillet where the wall meets the surface (requirement B3).

The right edge belongs to the wall nearer the face (the higher Z, the right in the picture), the left edge to the wall nearer the
chuck. The edge is cut away from the part outside the groove, so the corner of the part is broken: a cut-off with a chamfer on the
part. The size is the length along the wall and along the surface (a chamfer of 45 degrees, a fillet of that radius).

Everything here is plain geometry in the (X radius, Z) plane. The blade cuts an edge with its corner (the right corner of the blade
for the right edge, the left corner for the left one), which comes down along the line or the arc; the blade body stands in the
groove, so the groove must be open at least as deep as the edge is large when the edge is cut (the styles see to that).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment
from ..geometry.region import Region

QUARTER_TURN_TOLERANCE = 1e-6  # a quarter circle: the sweep of the arc from the surface to the wall


class EdgeKind(Enum):
    NONE = "none"
    CHAMFER = "chamfer"
    FILLET = "fillet"


@dataclass(frozen=True)
class EdgeMoves:
    """How the corner of the blade cuts one edge, in corner coordinates (the Z of the blade corner).

    `lead` is where the corner comes down to from the clear radius, `pieces` the cutting moves from there (a line, or a line and an arc)."""

    lead: Point
    pieces: tuple[Segment, ...]


def _ends(size_mm: float, high: bool, surface: float, wall_z: float, sign: int) -> tuple[Point, Point, Point]:
    """(the point on the surface, the point on the wall, the corner of the groove wall at the surface)."""
    outward = 1 if high else -1  # towards the part beyond the wall
    return (
        Point(surface, wall_z + outward * size_mm), Point(surface - sign * size_mm, wall_z), Point(surface, wall_z),
    )


def _fillet(start: Point, end: Point, centre: Point) -> ArcSegment:
    for direction in (ArcDirection.CCW, ArcDirection.CW):
        arc = ArcSegment(start, end, centre, direction)
        if abs(arc.sweep - 3.141592653589793 / 2) < QUARTER_TURN_TOLERANCE:
            return arc
    raise ValueError("the fillet is not a quarter circle")


def edge_pieces(kind: EdgeKind, size_mm: float, high: bool, surface: float, wall_z: float, sign: int) -> tuple[Segment, ...]:
    """The edge as drawn, from the point on the surface to the point on the wall (nothing for no edge)."""
    if kind is EdgeKind.NONE or size_mm <= 0:
        return ()
    start, end, _corner = _ends(size_mm, high, surface, wall_z, sign)
    if kind is EdgeKind.CHAMFER:
        return (LineSegment(start, end),)
    outward = 1 if high else -1
    return (_fillet(start, end, Point(surface - sign * size_mm, wall_z + outward * size_mm)),)


def edge_region(kind: EdgeKind, size_mm: float, high: bool, surface: float, wall_z: float, sign: int) -> Region:
    """The material the edge takes off the part: between the corner of the wall and the edge."""
    pieces = edge_pieces(kind, size_mm, high, surface, wall_z, sign)
    if not pieces:
        return Region.empty()
    start, end, corner = _ends(size_mm, high, surface, wall_z, sign)
    return Region.from_segments([LineSegment(corner, start), *pieces, LineSegment(end, corner)])


def edge_moves(
    kind: EdgeKind, size_mm: float, high: bool, surface: float, wall_z: float, sign: int, clearance: float,
) -> EdgeMoves:
    """The moves of the blade corner: down from the clear radius along the line (a chamfer, 45 degrees, started `clearance` before the
    surface) or along the surface (a fillet), then the cut."""
    start, end, _corner = _ends(size_mm, high, surface, wall_z, sign)
    outward = 1 if high else -1
    if kind is EdgeKind.CHAMFER:
        lead = Point(surface + sign * clearance, start.z + outward * clearance)
        return EdgeMoves(lead, (LineSegment(lead, end),))
    lead = Point(surface + sign * clearance, start.z)
    return EdgeMoves(lead, (LineSegment(lead, start), *edge_pieces(kind, size_mm, high, surface, wall_z, sign)))
