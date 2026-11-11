"""Areas in the X/Z plane as exact chains of lines and arcs (`chains.py`): the `Region` of the program.

It keeps its loops as they are given: an outer loop counter-clockwise, a hole clockwise, arcs stay arcs. The boolean is the trim-and-link of `chains.py`; only the questions that need a polygon (drawing, the triangles of the
3D view, the distance between two areas) use the loops with their arcs as short chords.

The offset (`offset`) is exact too: every loop moved sideways (`offset.offset_segments`: lines along their normal, arcs with
the same centre, a round join at an outer corner), the pieces cut where they cross each other, and only the pieces kept that lie the
whole distance from the old border (a swallowtail in an inner corner, a hole that grows shut, a thin part that shrinks away lie closer).
"""

from __future__ import annotations

from ..constants import (
    ARC_MAX_DEVIATION_MM,
    CHAIN_SNAP_MM,
    COLLISION_PENETRATION_TOLERANCE_MM,
    CUT_JITTER_MM,
    GEOMETRY_TOLERANCE_MM,
    MIDPOINT_FRACTION,
    MIN_POLYGON_POINTS,
    OFFSET_CACHE_SIZE,
)
from .chains import (
    INSIDE,
    ON,
    OUTSIDE,
    ChainError,
    ChainIndex,
    Loop,
    _inside,
    _pieces,
    _tangent,
    box_of,
    boxes_meet,
    split_at,
    difference,
    intersection,
    locate,
    loop_area,
    loops_box,
    oriented,
    polygon_loop,
    union,
    union_all,
)
from .distance import distance_to_segment
from .intersect import fraction_along, intersections, point_of
from .offset import tangent_at_start
from .primitives import ArcSegment, LineSegment, Point, Segment, segments_to_polyline
from .reflect import ACROSS_AXIS, ACROSS_FACE
from .region_offset import capsule, hull, offset_loops
from .region_types import Bounds, PolygonRings, RegionError
from .removal import _arc_pieces, _strip
from .tidy import tidied
from .tool_edges import translated_segment


class Region:
    """An area made of zero or more loops (outer loops counter-clockwise, holes clockwise). Immutable: every operation returns a new one."""

    __slots__ = ("_stored", "_parts", "_area", "_bounds", "_offsets", "_index")

    def __init__(self, loops: tuple[Loop, ...] | list[Loop] = (), parts: list[list[Loop]] | None = None) -> None:
        """Internal: use the class methods `empty`, `from_points`, `from_segments`, `from_loops`, `rectangle`. `parts`: the area as the
        union of these (each oriented), made only when the border is needed (a swept area: `overlaps` and `bounds` ask the parts)."""
        self._stored: tuple[Loop, ...] | None = None if parts else tuple(loop for loop in loops if _has_area(loop))
        self._parts = [part for part in parts if part] if parts else None
        self._area: float | None = None
        self._bounds: Bounds | None = None
        self._offsets: dict[float, Region] = {}  # offsets already made (a region never changes, so they stay valid)
        self._index: ChainIndex | None = None  # the index of its border, made when first asked (the same obstacle is asked often)

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        """Pickled (a plan sent to another process) without the caches: they are made again when asked."""
        return (Region, (self._stored,) if self._stored is not None else ((), self._parts))

    def _border_index(self) -> ChainIndex:
        if self._index is None:
            self._index = ChainIndex(list(self._loops))
        return self._index

    @property
    def _loops(self) -> tuple[Loop, ...]:
        if self._stored is None:
            self._stored = tuple(_union_of(self._parts or []))
            self._parts = None
        return self._stored

    def _pieces_of(self) -> list[list[Loop]]:
        """The parts of a region that is still a union to be made, else its loops as one part."""
        return self._parts if self._parts is not None else [list(self._loops)]

    # --- creation -----------------------------------------------------------

    @classmethod
    def empty(cls) -> Region:
        return cls()

    @classmethod
    def from_loops(cls, loops: list[Loop]) -> Region:
        """The area of loops that are already oriented (outer counter-clockwise, holes clockwise)."""
        return cls(loops)

    @classmethod
    def from_points(cls, points: list[Point]) -> Region:
        """Area inside the closed outline; the closing edge is implied."""
        if len(points) < MIN_POLYGON_POINTS:
            raise RegionError(f"an area needs at least {MIN_POLYGON_POINTS} points")
        loop = polygon_loop(points)
        if _crosses_itself(loop):
            raise RegionError("the outline crosses itself")
        if len(loop) < MIN_POLYGON_POINTS or abs(loop_area(loop)) <= 0:
            raise RegionError("the outline encloses no area")
        return cls((oriented(loop, True),))

    @classmethod
    def from_segments(cls, segments: list[Segment], max_deviation_mm: float = ARC_MAX_DEVIATION_MM) -> Region:
        """Area inside a closed chain of lines and arcs; the arcs stay arcs (`max_deviation_mm` is only there to match `Region`)."""
        pieces = [s for s in segments if s.start.distance_to(s.end) > GEOMETRY_TOLERANCE_MM or not isinstance(s, LineSegment)]
        if not pieces:
            raise RegionError("an area needs at least one piece")
        if not pieces[-1].end.is_close(pieces[0].start):
            pieces.append(LineSegment(pieces[-1].end, pieces[0].start))  # the closing edge is implied, as for points
        loop = tuple(pieces)
        if abs(loop_area(loop)) <= 0:
            raise RegionError("the outline encloses no area")
        return cls((oriented(loop, True),))

    @classmethod
    def rectangle(cls, min_x: float, min_z: float, max_x: float, max_z: float) -> Region:
        if max_x <= min_x or max_z <= min_z:
            raise RegionError("a rectangle needs max greater than min")
        min_x, min_z, max_x, max_z = float(min_x), float(min_z), float(max_x), float(max_z)  # a corner typed as 1 is the same as 1.0 everywhere after
        return cls((polygon_loop([Point(min_x, min_z), Point(max_x, min_z), Point(max_x, max_z), Point(min_x, max_z)]),))

    # --- questions ----------------------------------------------------------

    @property
    def loops(self) -> tuple[Loop, ...]:
        return self._loops

    @property
    def area(self) -> float:
        if self._area is None:
            self._area = max(sum(loop_area(loop) for loop in self._loops), 0.0)
        return self._area

    @property
    def is_empty(self) -> bool:
        return not self._parts if self._parts is not None else not self._loops

    @property
    def bounds(self) -> Bounds | None:
        if self.is_empty:
            return None
        if self._bounds is None:
            self._bounds = Bounds(*(float(value) for value in loops_box([loop for part in self._pieces_of() for loop in part])))  # plain floats
        return self._bounds

    def contains_point(self, point: Point) -> bool:
        """True if the point is inside or on the boundary."""
        return bool(self._loops) and self._border_index().locate(point, GEOMETRY_TOLERANCE_MM)[0] != OUTSIDE

    def strictly_contains_point(self, point: Point) -> bool:
        """True only if the point is inside; a point on the boundary does not count."""
        return bool(self._loops) and self._border_index().locate(point, GEOMETRY_TOLERANCE_MM)[0] == INSIDE

    def overlap_area(self, other: Region) -> float:
        return self.intersection(other).area

    def overlaps(self, other: Region) -> bool:
        """True if the two areas share any area (touching along an edge does not count)."""
        mine, theirs = self.bounds, other.bounds
        if mine is None or theirs is None:
            return False
        if mine.max_x < theirs.min_x or theirs.max_x < mine.min_x or mine.max_z < theirs.min_z or theirs.max_z < mine.min_z:
            return False
        mine_parts = [(part, loops_box(part), self._border_index() if self._parts is None else None) for part in self._pieces_of()]
        theirs_parts = [(part, loops_box(part), other._border_index() if other._parts is None else None) for part in other._pieces_of()]
        for mine_part, mine_box, mine_index in mine_parts:  # a union of parts overlaps when one of its parts does
            for theirs_part, theirs_box, theirs_index in theirs_parts:
                if mine_box[2] < theirs_box[0] or theirs_box[2] < mine_box[0] or mine_box[3] < theirs_box[1] or theirs_box[3] < mine_box[1]:
                    continue
                if _shares_area(mine_part, theirs_index or ChainIndex(theirs_part)) or _shares_area(theirs_part, mine_index or ChainIndex(mine_part)):
                    return True
        return False

    def distance_to(self, other: Region) -> float:
        """Smallest distance between the two areas (0 if they touch or overlap): from the borders with their arcs as short chords."""
        if self.is_empty or other.is_empty:
            return float("inf")
        if self.overlaps(other) or _corner_inside(self, other) or _corner_inside(other, self):
            return 0.0
        mine, theirs = _chords(self._loops), _chords(other._loops)
        best = float("inf")
        for a in mine:
            for b in theirs:
                if intersections(a, b):
                    return 0.0
                best = min(best, distance_to_segment(a.start, b), distance_to_segment(a.end, b), distance_to_segment(b.start, a), distance_to_segment(b.end, a))
        return best

    def penetrates(self, other: Region, tolerance_mm: float = COLLISION_PENETRATION_TOLERANCE_MM) -> bool:
        """True if the areas overlap by more than the tolerance (touching, or overlapping by less, is not penetration)."""
        if self.is_empty or other.is_empty:
            return False
        return self.shrunk_for_collision(tolerance_mm).overlaps(other.shrunk_for_collision(tolerance_mm))

    def shrunk_for_collision(self, tolerance_mm: float = COLLISION_PENETRATION_TOLERANCE_MM) -> Region:
        """The area as `penetrates` compares it (made once and kept, like every offset)."""
        return self.offset(-tolerance_mm / 2)

    def length_inside(self, points: list[Point], tolerance_mm: float = COLLISION_PENETRATION_TOLERANCE_MM) -> float:
        """Length of the path (a point list) that runs inside this area more than `tolerance_mm` from its border (a path along the edge
        counts as outside): the stretches inside, less the stretches near a piece of the border. No offset of the area is made."""
        if self.is_empty or len(points) < 2:
            return 0.0
        border = self._border_index()
        total = 0.0
        for a, b in zip(points, points[1:]):
            if a.is_close(b):
                continue
            line = LineSegment(a, b)
            box = (min(a.x, b.x) - tolerance_mm, min(a.z, b.z) - tolerance_mm, max(a.x, b.x) + tolerance_mm, max(a.z, b.z) + tolerance_mm)
            near = border.near(box, 0.0)
            marks = sorted({fraction_along(line, cross) for piece in near for cross in intersections(line, piece)} | {0.0, 1.0})
            inside = [(low, high) for low, high in zip(marks, marks[1:]) if high > low and border.inside(point_of(line, (low + high) / 2))]
            if not inside:
                continue
            close = _merged_intervals([found for piece in near for chord in _chords(((piece,),)) for found in [_near_interval(a, b, chord, tolerance_mm)] if found])
            total += sum(_length_outside(low, high, close) for low, high in inside) * line.length
        return total if total > GEOMETRY_TOLERANCE_MM else 0.0  # less is the rounding of the fractions, not a stretch inside

    # --- operations ---------------------------------------------------------

    def union(self, other: Region) -> Region:
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        if _apart(self, other):  # nothing to join: the loops of both
            return Region(self._loops + other._loops)
        return Region(_steady(union, self._loops, other._loops))

    def difference(self, other: Region) -> Region:
        if not self._loops or not other._loops or _apart(self, other):
            return self
        return Region(_steady(difference, self._loops, other._loops))

    def intersection(self, other: Region) -> Region:
        if not self._loops or not other._loops or _apart(self, other):
            return Region()
        return Region(_steady(intersection, self._loops, other._loops))

    def offset(self, distance_mm: float) -> Region:
        """Grow (positive) or shrink (negative) with rounded corners: exact (see the top)."""
        if distance_mm == 0 or self.is_empty:
            return self
        made = self._offsets.get(distance_mm)
        if made is None:
            made = _offset_of(self, distance_mm)
            if len(self._offsets) < OFFSET_CACHE_SIZE:
                self._offsets[distance_mm] = made
        return made

    def swept(self, dx: float, dz: float) -> Region:
        """The area this region covers while it moves by (dx, dz) in a straight line: the region at the start and at the end and the
        strip each piece of its border that faces the move draws (arcs as the pieces between their turning points). A point the region
        covers on the way has, looking back against the move, a piece of the border the region enters through, and that piece faces the
        move: the strips of the other pieces add nothing."""
        if self.is_empty or (dx == 0 and dz == 0):
            return self
        parts = [list(self._loops), list(self.translated(dx, dz)._loops)]
        for loop in self._loops:
            for piece in loop:
                for part in (_arc_pieces(piece, (dx, dz)) if isinstance(piece, ArcSegment) else [piece]):
                    tx, tz = tangent_at_start(split_at(part, [MIDPOINT_FRACTION])[-1])  # the direction in the middle of the part
                    if tz * dx - tx * dz <= 0:
                        continue  # the outside lies to the right of the travel; this part faces away from the move (or along it)
                    strip = _strip(part, (dx, dz))
                    if strip is not None:
                        parts.append([oriented(strip, True)])
        return Region(parts=parts)  # the union is made when the border is needed

    @classmethod
    def swept_edges(cls, a, b, dx: float, dz: float, half_width_mm: float) -> Region:
        """The thin area that straight edges (from the points `a` to the points `b`, arrays of shape (n, 2)) cover while they move by
        (dx, dz): for every edge the area it draws (the hull of its four corners), made `half_width_mm` thick so that an edge that moves
        along itself still has an area."""
        parts: list[list[Loop]] = []
        for (ax, az), (bx, bz) in zip(a, b):
            corners = hull([Point(ax, az), Point(bx, bz), Point(bx + dx, bz + dz), Point(ax + dx, az + dz)])
            if len(corners) >= MIN_POLYGON_POINTS:
                parts.append(offset_loops((oriented(polygon_loop(corners), True),), half_width_mm))
            else:
                parts.append([capsule(corners[0], corners[-1], half_width_mm)])
        return cls(parts=parts)  # the union is made when the border is needed

    def translated(self, dx: float, dz: float) -> Region:
        def moved(loops) -> list[Loop]:
            return [tuple(translated_segment(piece, dx, dz) for piece in loop) for loop in loops]

        if self._parts is not None:
            return Region(parts=[moved(part) for part in self._parts])
        return Region(moved(self._loops))

    def simplified(self, tolerance_mm: float) -> Region:
        """The same area: exact chains have no zigzags of chords to take out."""
        return self

    def mirrored(self) -> Region:
        """The area turned over the spindle axis (x becomes -x): the far side of a round part."""
        return Region(ACROSS_AXIS.loops(list(self._loops)))

    def mirrored_z(self) -> Region:
        """The area turned over the plane Z = 0 (z becomes -z): front and chuck side change places."""
        return Region(ACROSS_FACE.loops(list(self._loops)))

    def pieces(self) -> tuple[Region, ...]:
        """The separate pieces (an outer loop with the holes in it), each as a region of its own."""
        return tuple(Region((outer, *holes)) for outer, holes in _grouped(self._loops))

    def polygons(self) -> tuple[PolygonRings, ...]:
        """The separate polygons (arcs as short chords), for drawing and for path generation."""
        return tuple(
            PolygonRings(_ring(outer), tuple(_ring(hole) for hole in holes)) for outer, holes in _grouped(self._loops)
        )

    def triangles(self):
        """The area cut into triangles that cover exactly the area (holes stay open): an array of shape (n, 3, 2), for the 3D view."""
        from .triangulate import triangles_of  # late: only the 3D view asks (numpy)

        return triangles_of(self.polygons())


def _union_of(parts: list[list[Loop]]) -> list[Loop]:
    """The union of many regions in one pass (`chains.union_all`); where that cannot decide, one after the other with the retries of
    `_steady`."""
    try:
        return union_all(parts)
    except ChainError:
        covered: list[Loop] = []
        for part in parts:
            covered = _steady(union, tuple(covered), tuple(part)) if covered else list(part)
        return covered


def _has_area(loop: Loop) -> bool:
    """False for an empty loop and for one with no area (a line there and back, as a boolean can leave from a very short sweep: kept, such
    loops would be handed on and grow in number with every cut)."""
    return bool(loop) and abs(loop_area(loop)) > GEOMETRY_TOLERANCE_MM ** 2


def _apart(a: Region, b: Region) -> bool:
    """True when the boxes of the two areas do not even touch: no boolean is needed (the quick answer for a tool far from the part)."""
    mine, theirs = a.bounds, b.bounds
    return mine is None or theirs is None or mine.max_x < theirs.min_x or theirs.max_x < mine.min_x or mine.max_z < theirs.min_z or theirs.max_z < mine.min_z


def _steady(operation, a: tuple[Loop, ...], b: tuple[Loop, ...]) -> list[Loop]:
    """The boolean `operation` of two regions, tried again where it cannot decide (borders that nearly lie on each other): with both
    tidied (`tidy.tidied`), then with the second one moved by a few thousandths (`CUT_JITTER_MM`, as `removal.cut` does: far below the
    roughing accuracy). The error is raised only when all of them fail."""
    try:
        return operation(list(a), list(b))
    except ChainError:
        pass
    neat_a, neat_b = tidied(list(a), CHAIN_SNAP_MM), tidied(list(b), CHAIN_SNAP_MM)
    try:
        return operation(neat_a, neat_b)
    except ChainError:
        pass
    for dx, dz in CUT_JITTER_MM:
        try:
            return operation(neat_a, [tuple(translated_segment(piece, dx, dz) for piece in loop) for loop in neat_b])
        except ChainError:
            continue
    raise ChainError("the boolean of the two regions cannot be worked out")


def _offset_of(region: Region, distance_mm: float) -> Region:
    """The offset of the whole border; when its pieces do not join (two parts that touch at a point, a sliver beside them), the union of
    the offsets of the parts one by one: a grown union is the union of the grown parts; a shrunk one loses only a hair at the touch."""
    try:
        return Region(offset_loops(region._loops, distance_mm))
    except ChainError:
        parts = region.pieces()
        if len(parts) < 2:
            raise
        return Region(parts=[offset_loops(part._loops, distance_mm) for part in parts])


def _near_interval(a: Point, b: Point, piece: LineSegment, radius: float) -> tuple[float, float] | None:
    """The stretch (fractions of the way from `a` to `b`) that lies within `radius` of the straight piece: the path through the capsule
    round it (the band and the two discs at its ends; one stretch, the capsule is convex), or None."""
    dx, dz = b.x - a.x, b.z - a.z
    found: list[tuple[float, float]] = []
    for centre in (piece.start, piece.end):  # the discs: |a + t d - c| <= radius
        fx, fz = a.x - centre.x, a.z - centre.z
        qa, qb, qc = dx * dx + dz * dz, 2 * (fx * dx + fz * dz), fx * fx + fz * fz - radius * radius
        root = qb * qb - 4 * qa * qc
        if qa > 0 and root >= 0:
            found.append(((-qb - root ** 0.5) / (2 * qa), (-qb + root ** 0.5) / (2 * qa)))
    length = piece.length
    if length > 0:  # the band: 0 <= along <= length and |across| <= radius, both straight in the fraction
        ux, uz = (piece.end.x - piece.start.x) / length, (piece.end.z - piece.start.z) / length
        low, high = -float("inf"), float("inf")
        for start_value, rate, least, most in (
            ((a.x - piece.start.x) * ux + (a.z - piece.start.z) * uz, dx * ux + dz * uz, 0.0, length),
            (-(a.x - piece.start.x) * uz + (a.z - piece.start.z) * ux, -dx * uz + dz * ux, -radius, radius),
        ):
            if abs(rate) <= 1e-15:
                if not least <= start_value <= most:
                    low, high = 1.0, 0.0
                continue
            t0, t1 = (least - start_value) / rate, (most - start_value) / rate
            low, high = max(low, min(t0, t1)), min(high, max(t0, t1))
        if low <= high:
            found.append((low, high))
    if not found:
        return None
    low, high = max(0.0, min(f[0] for f in found)), min(1.0, max(f[1] for f in found))
    return (low, high) if low < high else None


def _merged_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _length_outside(low: float, high: float, close: list[tuple[float, float]]) -> float:
    """The length of the stretch from `low` to `high` (fractions) less the parts of it that lie in the merged stretches `close`."""
    covered = sum(max(0.0, min(high, c_high) - max(low, c_low)) for c_low, c_high in close)
    return max(0.0, high - low - covered)


def _shares_area(a: list[Loop], index: ChainIndex) -> bool:
    """True when a piece of the border of `a`, cut where it meets the border in `index`, lies inside that area, or on its border with both
    areas on its same side: the two areas share area there. The first such piece is enough (no joining, as the full intersection needs)."""
    if not index.items:
        return False
    reach = loops_box(index.loops)
    near = [segment for loop in a for segment in loop if boxes_meet(box_of(segment), reach, GEOMETRY_TOLERANCE_MM)]  # a piece away from the other area cannot share any of it
    for piece in _pieces([tuple(near)], index, GEOMETRY_TOLERANCE_MM):
        middle = point_of(piece, MIDPOINT_FRACTION)
        where, on = index.locate(middle, GEOMETRY_TOLERANCE_MM)
        if where == INSIDE:
            return True
        if where == ON and sum(x * y for x, y in zip(_tangent(piece, middle), _tangent(on, middle))) > 0:
            return True
    return False


def _crosses_itself(loop: Loop) -> bool:
    """True when two pieces of the loop that do not follow each other cross or touch."""
    count = len(loop)
    for i in range(count):
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue  # the last piece follows the first
            if intersections(loop[i], loop[j]):
                return True
    return False


def _grouped(loops: tuple[Loop, ...]) -> list[tuple[Loop, list[Loop]]]:
    """Every outer loop with the holes that lie in it (a hole belongs to the smallest outer loop around it)."""
    outers = [loop for loop in loops if loop_area(loop) > 0]
    holes = [loop for loop in loops if loop_area(loop) < 0]
    grouped: list[tuple[Loop, list[Loop]]] = [(outer, []) for outer in outers]
    for hole in holes:
        probe = hole[0].start
        around = [index for index, outer in enumerate(outers) if _inside(probe, [outer]) or locate(probe, [outer], GEOMETRY_TOLERANCE_MM)[0] != OUTSIDE]
        if around:
            smallest = min(around, key=lambda index: loop_area(outers[index]))
            grouped[smallest][1].append(hole)
    return grouped


def _ring(loop: Loop) -> tuple[Point, ...]:
    """The loop as a closed ring of points (the first point again at the end), arcs as short chords."""
    points = segments_to_polyline(list(loop))
    if points and not points[0].is_close(points[-1]):
        points.append(points[0])
    return tuple(points)


def _chords(loops: tuple[Loop, ...]) -> list[LineSegment]:
    pieces: list[LineSegment] = []
    for loop in loops:
        points = _ring(loop)
        pieces += [LineSegment(a, b) for a, b in zip(points, points[1:]) if not a.is_close(b)]
    return pieces


def _corner_inside(region: Region, other: Region) -> bool:
    """True when a corner of `other` lies in `region` (one area within the other: their borders need not meet)."""
    return any(region.contains_point(loop[0].start) for loop in other._loops)

