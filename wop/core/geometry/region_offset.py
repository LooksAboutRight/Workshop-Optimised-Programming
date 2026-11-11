"""The exact offset of loops of lines and arcs (for `region.py`): every piece moved sideways whole (`raw_offset`: lines along their
normal, arcs with the same centre or past it, a round join at an outer corner, nothing at an inner one), the pieces cut where they cross
each other, kept only when their middle lies the whole distance from the old border, the pieces with a loose end taken out, then joined
(`offset_loops`). Also the capsule round a straight piece and the convex hull of a few points (the thin swept edges)."""

from __future__ import annotations

from ..constants import (
    CHAIN_SNAP_MM,
    GEOMETRY_TOLERANCE_MM,
    MIDPOINT_FRACTION,
    OFFSET_JOIN_TOLERANCE_MM,
    OFFSET_KEEP_TOLERANCE_MM,
    OFFSET_SIDE_FRACTION,
)
from .chains import ChainIndex, Loop, _join, box_of, oriented, split_at
from .distance import distance_to_segment
from .intersect import fraction_along, intersections, point_of
from .offset import _moved
from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .tidy import tidied


def raw_offset(loop: Loop, distance: float) -> list[Segment]:
    """Every piece of the loop moved sideways by `distance` (`offset.py`: lines along their normal, arcs with the same centre), whole:
    at an outer corner a round join around the old corner; at an inner corner nothing (the pieces are not cut back to their crossing
    here: a neighbour that is swallowed would take a part of the true border with it). The pieces need not follow each other: they are
    cut at their crossings and sorted out by their distance from the old border, then joined (`moved_whole`: an arc moved past its centre)."""
    pairs = [(piece, moved_whole(piece, distance)) for piece in loop]
    pairs = [(original, moved) for original, moved in pairs if moved is not None]
    found: list[Segment] = []
    for number, (original, moved) in enumerate(pairs):
        found.append(moved)
        following_original, following = pairs[(number + 1) % len(pairs)]
        end, start = moved.end, following.start
        if end.is_close(start, GEOMETRY_TOLERANCE_MM):
            continue
        corner = original.end if original.end.is_close(following_original.start, GEOMETRY_TOLERANCE_MM) else None
        if corner is None:
            continue  # a gap where an arc was left out: the neighbours cross each other there
        # the outer side of a turn: the arc round the old corner that keeps the whole distance from both pieces there (also at a spike,
        # where the loop turns back on itself and no direction says which side is out); at an inner corner neither arc does: nothing,
        # the two whole pieces cross each other there and the cut at their crossing (`offset_loops`) makes the corner
        # (of the arcs that do, the shorter: an outer join turns at most half way round; at a spike the wrong half lies on the pieces)
        # and that lies on the side the pieces moved to (its middle points the way the two moved ends point from the corner; at a spike
        # those cancel and the distance alone decides)
        side_x, side_z = end.x + start.x - 2 * corner.x, end.z + start.z - 2 * corner.z
        side = (side_x * side_x + side_z * side_z) ** 0.5 > abs(distance) * OFFSET_SIDE_FRACTION
        joins = []
        for direction in (ArcDirection.CCW, ArcDirection.CW):
            join = ArcSegment(end, start, corner, direction)
            middle = point_of(join, MIDPOINT_FRACTION)
            if side and (middle.x - corner.x) * side_x + (middle.z - corner.z) * side_z <= 0:
                continue
            if min(distance_to_segment(middle, piece) for piece in (original, following_original)) >= abs(distance) - OFFSET_KEEP_TOLERANCE_MM:
                joins.append(join)
        if joins:
            found.append(min(joins, key=lambda join: join.sweep))
    return found


def moved_whole(piece: Segment, distance: float) -> Segment | None:
    """The piece moved to its left by `distance` (`offset._moved`); an arc moved past its centre is the arc on the other side of
    the centre with the radius it has gone past (its points lie the whole distance from the arc, through the centre, and may be part of
    the border: a small notch between two parallel lines); None for an arc moved exactly onto its centre."""
    moved = _moved(piece, distance)
    if moved is not None or not isinstance(piece, ArcSegment):
        return moved
    radius = piece.radius + distance * piece.turn  # negative: past the centre
    if abs(radius) <= GEOMETRY_TOLERANCE_MM:
        return None
    scale = radius / piece.radius

    def through(point: Point) -> Point:
        return Point(piece.center.x + (point.x - piece.center.x) * scale, piece.center.z + (point.z - piece.center.z) * scale)

    return ArcSegment(through(piece.start), through(piece.end), piece.center, piece.direction)  # turned half way round: the same way


def offset_loops(loops: tuple[Loop, ...], distance: float) -> list[Loop]:
    """The loops of the region grown (positive) or shrunk (negative) by `distance` (see the top of the module). The loops are tidied
    first (`tidy.tidied`: steps and slivers of the snap distance out): a border with pieces of a few hundred-thousandths, as polygons
    have, makes the distance test too close to call."""
    loops = tuple(tidied(list(loops), CHAIN_SNAP_MM))
    raw: list[Loop] = []
    for loop in loops:
        pieces = tuple(piece for piece in loop if not (isinstance(piece, LineSegment) and piece.length <= GEOMETRY_TOLERANCE_MM))
        if pieces:
            moved = [piece for piece in raw_offset(pieces, distance) if piece.start.distance_to(piece.end) > GEOMETRY_TOLERANCE_MM or not isinstance(piece, LineSegment)]
            if moved:
                raw.append(tuple(moved))
    if not raw:
        return []
    index = ChainIndex(raw)
    cut: list[Segment] = []
    for loop in raw:
        for piece in loop:
            marks = [fraction_along(piece, cross) for other in index.near(box_of(piece), GEOMETRY_TOLERANCE_MM) if other is not piece for cross in intersections(piece, other)]
            cut += [part for part in split_at(piece, marks) if part.start.distance_to(part.end) > GEOMETRY_TOLERANCE_MM or not isinstance(part, LineSegment)]
    border = ChainIndex(list(loops))
    reach = abs(distance)
    kept = []
    for piece in cut:
        middle = point_of(piece, MIDPOINT_FRACTION)
        margin = reach + GEOMETRY_TOLERANCE_MM
        near = border.near((middle.x - margin, middle.z - margin, middle.x + margin, middle.z + margin), 0.0)
        if all(distance_to_segment(middle, other) >= reach - OFFSET_KEEP_TOLERANCE_MM for other in near):
            kept.append(piece)
    kept = without_loose_ends(kept, OFFSET_JOIN_TOLERANCE_MM)
    return _join(kept, OFFSET_JOIN_TOLERANCE_MM) if kept else []


def without_loose_ends(pieces: list[Segment], tolerance: float) -> list[Segment]:
    """The pieces less every one with a loose end (no other piece ends where it starts, or starts where it ends), again and again: a
    closed border has none. At an inner corner that is nearly straight the overshoot of a piece past the crossing lies only a few
    millionths nearer than the distance and passes the test; it is such a spur."""

    def cell(point: Point) -> tuple[int, int]:
        return round(point.x / tolerance), round(point.z / tolerance)

    def around(point: Point):
        x, z = cell(point)
        return [(x + i, z + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]

    alive = list(range(len(pieces)))
    while True:
        starts: dict[tuple[int, int], int] = {}
        ends: dict[tuple[int, int], int] = {}
        for number in alive:
            starts[cell(pieces[number].start)] = starts.get(cell(pieces[number].start), 0) + 1
            ends[cell(pieces[number].end)] = ends.get(cell(pieces[number].end), 0) + 1
        keep = [
            number for number in alive
            if any(ends.get(key, 0) for key in around(pieces[number].start)) and any(starts.get(key, 0) for key in around(pieces[number].end))
        ]
        if len(keep) == len(alive):
            return [pieces[number] for number in keep]
        alive = keep


def capsule(a: Point, b: Point, radius: float) -> Loop:
    """The area within `radius` of the straight piece from `a` to `b` (a circle when they are one point), counter-clockwise."""
    if a.is_close(b):
        top, bottom = Point(a.x + radius, a.z), Point(a.x - radius, a.z)
        return (ArcSegment(top, bottom, a, ArcDirection.CCW), ArcSegment(bottom, top, a, ArcDirection.CCW))
    length = a.distance_to(b)
    nx, nz = -(b.z - a.z) / length * radius, (b.x - a.x) / length * radius
    a_left, a_right, b_left, b_right = Point(a.x + nx, a.z + nz), Point(a.x - nx, a.z - nz), Point(b.x + nx, b.z + nz), Point(b.x - nx, b.z - nz)
    loop = (LineSegment(a_right, b_right), ArcSegment(b_right, b_left, b, ArcDirection.CCW), LineSegment(b_left, a_left), ArcSegment(a_left, a_right, a, ArcDirection.CCW))
    return oriented(loop, True)


def hull(points: list[Point]) -> list[Point]:
    """The convex hull of a few points, counter-clockwise in (x, z) (Andrew's monotone chain)."""
    unique = sorted({(round(p.x, 12), round(p.z, 12)) for p in points})
    if len(unique) <= 2:
        return [Point(x, z) for x, z in unique]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [Point(x, z) for x, z in lower[:-1] + upper[:-1]]
