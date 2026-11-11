"""Sketch data: points, lines and arcs that share points (a shared point is a coincident join).

Coordinates are the program's (x = radius, z = axial). An arc is its centre, start point and end point plus a direction;
the end point is only a hint of the angle, the radius is the distance centre to start.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment
from .constants import AXIS_LINE, MIRROR_KINDS, ORIGIN, SLOT_LINE, SLOT_POINT
from .relations import Constraint, relation_for


class SketchError(ValueError):
    """The sketch operation cannot be done (unknown id, a piece without length, ...)."""


@dataclass(frozen=True)
class SketchPoint:
    point_id: int
    x: float
    z: float

    @property
    def position(self) -> Point:
        return Point(self.x, self.z)


@dataclass(frozen=True)
class SketchLine:
    line_id: int
    start: int  # point ids
    end: int
    construction: bool = False  # helper geometry: never part of the outline
    cutting: bool = False  # a cutting edge (tool shapes)
    centre_line: bool = False  # a centre line: a construction line that dimensions are measured across, as diameters
    reference: bool = False  # the sharp corner that a fillet or chamfer left: a construction line drawn thin


@dataclass(frozen=True)
class SketchArc:
    arc_id: int
    centre: int
    start: int
    end: int
    direction: ArcDirection = ArcDirection.CCW
    construction: bool = False
    cutting: bool = False
    reference: bool = False  # the sharp corner that a fillet or chamfer left: a construction arc drawn thin


Piece = SketchLine | SketchArc

LENGTH_KINDS = ("length", "equal_length", "midpoint")  # relations that describe how long a line is: they do not survive a line that grows back


@dataclass(frozen=True)
class CornerLink:
    """A fillet or chamfer as one unit (N43). The corner was sharp at `point`; the two pieces that met there were shortened to
    end at `ends` (`kept`), the old full pieces stay as thin `references`, and `bevel` (an arc or a line) joins the cut ends."""

    point: int
    kept: tuple[int, int]
    ends: tuple[int, int]
    references: tuple[int, int]
    bevel: int


class Sketch:
    """Points, lines and arcs by id. Ids are never reused inside one sketch."""

    def __init__(self) -> None:
        self.points: dict[int, SketchPoint] = {}
        self.lines: dict[int, SketchLine] = {}
        self.arcs: dict[int, SketchArc] = {}
        self.constraints: dict[int, Constraint] = {}
        self.labels: dict[str, int] = {}  # named points (tip ...): name -> point id
        self.helpers: set[int] = set()  # mirror points made for diameter dimensions: never shown, kept while a dimension uses them
        self.corners: dict[int, CornerLink] = {}  # fillets and chamfers by the id of their bevel piece
        self.locked_points: dict[str, int] = {}  # points the program supplies (safe point ...): key -> point id; they cannot be moved or deleted
        self.rapid_pieces: set[int] = set()  # the lines of a path that are rapid moves (the others are feed moves)
        self.piece_feeds: dict[int, float] = {}  # the feed (mm per revolution) of a piece of a path; no entry: the feed of the block
        self.locked_arcs: dict[str, int] = {}  # arcs the program supplies: key -> arc id
        self.locked_groups: dict[str, tuple[tuple[str, str], ...]] = {}  # per group of locked pieces: which pieces it had (`locked.py`)
        self.locked_lines: dict[str, int] = {}  # construction lines the program supplies (the part before a block ...): key -> line id
        self.next_id = 1

    def _new_id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def point(self, point_id: int) -> SketchPoint:
        if point_id not in self.points:
            raise SketchError(f"unknown point {point_id}")
        return self.points[point_id]

    def add_point(self, x: float, z: float) -> int:
        point_id = self._new_id()
        self.points[point_id] = SketchPoint(point_id, x, z)
        return point_id

    def move_point(self, point_id: int, x: float, z: float) -> None:
        self.points[point_id] = replace(self.point(point_id), x=x, z=z)

    def add_line(
        self, start: int, end: int, construction: bool = False, cutting: bool = False, centre_line: bool = False,
        reference: bool = False,
    ) -> int:
        self.point(start)
        self.point(end)
        if start == end:
            raise SketchError("a line needs two different points")
        line_id = self._new_id()
        self.lines[line_id] = SketchLine(line_id, start, end, construction or centre_line or reference, cutting, centre_line, reference)
        return line_id

    def add_arc(
        self,
        centre: int,
        start: int,
        end: int,
        direction: ArcDirection = ArcDirection.CCW,
        construction: bool = False,
        cutting: bool = False,
        reference: bool = False,
    ) -> int:
        for point_id in (centre, start, end):
            self.point(point_id)
        if centre in (start, end):
            raise SketchError("an arc centre must be its own point")
        arc_id = self._new_id()
        self.arcs[arc_id] = SketchArc(arc_id, centre, start, end, direction, construction or reference, cutting, reference)
        return arc_id

    def is_locked_point(self, point_id: int) -> bool:
        return point_id in self.locked_points.values()

    def is_locked_piece(self, piece_id: int) -> bool:
        return piece_id in self.locked_lines.values() or piece_id in self.locked_arcs.values()

    def pieces(self) -> list[Piece]:
        """All lines and arcs in the order they were made."""
        return sorted([*self.lines.values(), *self.arcs.values()], key=lambda p: p.line_id if isinstance(p, SketchLine) else p.arc_id)

    def selectable_pieces(self) -> list[Piece]:
        """The pieces the user can pick: all but the reference pieces of a fillet or chamfer (they go with their corner)."""
        return [p for p in self.pieces() if not p.reference]

    def link_corner(self, link: CornerLink) -> None:
        self.corners[link.bevel] = link

    def delete_piece(self, piece_id: int) -> None:
        """Remove a line or arc, then every point nothing uses any more."""
        if piece_id in self.lines:
            del self.lines[piece_id]
        elif piece_id in self.arcs:
            del self.arcs[piece_id]
        else:
            raise SketchError(f"unknown piece {piece_id}")
        self.drop_unused_points()

    def drop_unused_points(self) -> None:
        """Remove the points nothing uses. A mirror point (see `helpers`) is used while the relation that makes it a mirror
        point exists and another relation, the diameter dimension, refers to it; when the centre line or the point it
        mirrors goes, the dimension goes with it."""
        while True:
            self._repair_corners()
            self._prune_constraints()
            self.rapid_pieces &= set(self.lines)
            self.piece_feeds = {i: feed for i, feed in self.piece_feeds.items() if self._has_piece(i)}
            used = {p for line in self.lines.values() for p in (line.start, line.end)}
            used |= {p for arc in self.arcs.values() for p in (arc.centre, arc.start, arc.end)}
            used |= set(self.labels.values())  # a named point stays, even alone
            used |= set(self.locked_points.values())  # so does a locked one
            used |= self.helpers & self._points_of(MIRROR_KINDS) & self._points_of_other_relations()
            gone = [p for p in self.points if p not in used]
            for point_id in gone:
                del self.points[point_id]
            self.helpers &= set(self.points)
            if not gone:  # what the relations of the points that went referred to may be unused now: go round again
                return

    def _has_piece(self, piece_id: int) -> bool:
        return piece_id in self.lines or piece_id in self.arcs

    def _repair_corners(self) -> None:
        """A fillet or chamfer lives and dies as one unit (N43): when its bevel, one of its shortened pieces or one of its reference
        pieces is gone, the corner is undone. The shortened pieces that are left grow back to the sharp corner, the bevel and
        the reference pieces go. A reference piece that belongs to no corner (an old file, a mirror copy) becomes an ordinary helper line."""
        for bevel, link in list(self.corners.items()):
            gone = [piece for piece in link.kept if not self._has_piece(piece)]
            if self._has_piece(bevel) and not gone and all(self._has_piece(r) for r in link.references):
                continue
            self._unwind(link, gone)
            del self.corners[bevel]
        linked = {r for link in self.corners.values() for r in link.references}
        for line_id in [i for i, line in self.lines.items() if line.reference and i not in linked]:
            self.lines[line_id] = replace(self.lines[line_id], reference=False)
        for arc_id in [i for i, arc in self.arcs.items() if arc.reference and i not in linked]:
            self.arcs[arc_id] = replace(self.arcs[arc_id], reference=False)

    def _unwind(self, link: CornerLink, gone: list[int]) -> None:
        self.lines.pop(link.bevel, None)
        self.arcs.pop(link.bevel, None)
        for reference in link.references:
            self.lines.pop(reference, None)
            self.arcs.pop(reference, None)
        for piece_id, end in zip(link.kept, link.ends):
            if piece_id not in gone and self._has_piece(piece_id):
                self._grow_back(piece_id, end, link.point)

    def _grow_back(self, piece_id: int, cut_end: int, corner: int) -> None:
        """Let a shortened piece end at the sharp corner again. What describes its direction stays; what touches its cut end
        or its length goes."""
        piece = self.lines[piece_id] if piece_id in self.lines else self.arcs[piece_id]
        if cut_end not in (piece.start, piece.end):
            return
        far = piece.end if piece.start == cut_end else piece.start
        kept: dict[int, Constraint] = {}
        seen: set[tuple] = set()
        for constraint_id, constraint in self.constraints.items():
            slots = relation_for(constraint.kind).slots
            point_refs = [ref for slot, ref in zip(slots, constraint.refs) if slot == SLOT_POINT]
            if cut_end in point_refs:
                if constraint.kind in ("horizontal", "vertical") and set(constraint.refs) == {cut_end, far}:
                    constraint = replace(constraint, refs=tuple(corner if ref == cut_end else ref for ref in constraint.refs))
                else:
                    continue
            elif constraint.kind in LENGTH_KINDS and piece_id in constraint.refs:
                continue
            if (constraint.kind, constraint.refs) in seen:  # the same relation is there already (the sharp corner had it)
                continue
            seen.add((constraint.kind, constraint.refs))
            kept[constraint_id] = constraint
        self.constraints = kept
        self.update_piece(
            piece_id, start=corner if piece.start == cut_end else piece.start, end=corner if piece.end == cut_end else piece.end,
        )

    def _points_of(self, kinds: tuple[str, ...]) -> set[int]:
        found: set[int] = set()
        for constraint in self.constraints.values():
            if constraint.kind in kinds:
                slots = relation_for(constraint.kind).slots
                found |= {ref for slot, ref in zip(slots, constraint.refs) if slot == SLOT_POINT}
        return found

    def _points_of_other_relations(self) -> set[int]:
        found: set[int] = set()
        for constraint in self.constraints.values():
            if constraint.kind not in MIRROR_KINDS:
                slots = relation_for(constraint.kind).slots
                found |= {ref for slot, ref in zip(slots, constraint.refs) if slot == SLOT_POINT}
        return found

    def merge_points(self, keep: int, drop: int) -> None:
        """Make two points one (a join); pieces that would collapse to nothing are removed."""
        self.point(keep)
        self.point(drop)
        if keep == drop:
            return

        def swap(point_id: int) -> int:
            return keep if point_id == drop else point_id

        self.lines = {
            i: replace(line, start=swap(line.start), end=swap(line.end)) for i, line in self.lines.items()
        }
        self.arcs = {
            i: replace(arc, centre=swap(arc.centre), start=swap(arc.start), end=swap(arc.end))
            for i, arc in self.arcs.items()
        }
        self.lines = {i: line for i, line in self.lines.items() if line.start != line.end}
        self.arcs = {i: arc for i, arc in self.arcs.items() if arc.centre not in (arc.start, arc.end)}
        self.constraints = {
            i: replace(c, refs=self._swap_points(c, swap)) for i, c in self.constraints.items()
        }
        self.labels = {name: swap(point_id) for name, point_id in self.labels.items()}
        self.locked_points = {key: swap(point_id) for key, point_id in self.locked_points.items()}
        self.helpers = {swap(point_id) for point_id in self.helpers}
        self.corners = {
            bevel: replace(link, point=swap(link.point), ends=(swap(link.ends[0]), swap(link.ends[1])))
            for bevel, link in self.corners.items()
        }
        self.drop_unused_points()

    def label_point(self, point_id: int, name: str) -> None:
        """A name belongs to one point: it moves here from the old one, and a point has one name."""
        self.point(point_id)
        self.labels = {n: p for n, p in self.labels.items() if n != name and p != point_id}
        self.labels[name] = point_id

    def unlabel_point(self, point_id: int) -> None:
        self.labels = {n: p for n, p in self.labels.items() if p != point_id}
        self.drop_unused_points()

    def label_of(self, point_id: int) -> str:
        return next((name for name, p in self.labels.items() if p == point_id), "")

    def delete_point(self, point_id: int) -> None:
        """Remove a point that no line or arc uses (a named point on its own)."""
        self.point(point_id)
        if any(point_id in (l.start, l.end) for l in self.lines.values()) or any(
            point_id in (a.centre, a.start, a.end) for a in self.arcs.values()
        ):
            raise SketchError("The point belongs to a line or an arc")
        self.labels = {n: p for n, p in self.labels.items() if p != point_id}
        self.drop_unused_points()

    def update_piece(self, piece_id: int, **fields) -> None:
        """Change fields of a line or arc (its points, direction, construction flag)."""
        if piece_id in self.lines:
            self.lines[piece_id] = replace(self.lines[piece_id], **fields)
        elif piece_id in self.arcs:
            self.arcs[piece_id] = replace(self.arcs[piece_id], **fields)
        else:
            raise SketchError(f"unknown piece {piece_id}")

    def forget_piece_constraints(self, piece_id: int) -> None:
        """Remove the relations that refer to this line or arc itself (those between points stay)."""
        def refers(constraint: Constraint) -> bool:
            slots = relation_for(constraint.kind).slots
            return any(slot != SLOT_POINT and ref == piece_id for slot, ref in zip(slots, constraint.refs))

        self.constraints = {i: c for i, c in self.constraints.items() if not refers(c)}

    # --- relations and dimensions -------------------------------------------------------------------------------------

    def add_constraint(
        self, kind: str, refs: tuple[int, ...], values: tuple[float, ...] = (), offset: tuple[float, float] | None = None
    ) -> int:
        relation = relation_for(kind)
        refs = tuple(refs)
        if len(refs) != len(relation.slots) or not all(self._slot_exists(slot, ref) for slot, ref in zip(relation.slots, refs)):
            raise SketchError(f"{relation.label}: wrong things selected")
        if not relation.valid(refs):
            raise SketchError(f"{relation.label}: needs different things")
        for existing in self.constraints.values():
            if existing.kind == kind and existing.refs == refs:
                raise SketchError(f"{relation.label} is already there")
        constraint_id = self._new_id()
        self.constraints[constraint_id] = Constraint(constraint_id, kind, refs, tuple(values), offset)
        return constraint_id

    def remove_constraint(self, constraint_id: int) -> None:
        if constraint_id not in self.constraints:
            raise SketchError(f"unknown relation {constraint_id}")
        del self.constraints[constraint_id]
        self.drop_unused_points()  # a mirror point that only this relation was using goes with it

    def set_offset(self, constraint_id: int, offset: tuple[float, float]) -> None:
        """Move where a dimension is drawn (it measures the same)."""
        self.constraints[constraint_id] = replace(self.constraints[constraint_id], offset=offset)

    def set_values(self, constraint_id: int, values: tuple[float, ...]) -> None:
        self.constraints[constraint_id] = replace(self.constraints[constraint_id], values=tuple(values))

    def _slot_exists(self, slot: str, ref: int) -> bool:
        if slot == SLOT_POINT:
            return ref == ORIGIN or ref in self.points
        if slot == SLOT_LINE and ref == AXIS_LINE:  # the spindle axis is no line of the sketch, but a relation may use it
            return True
        return ref in (self.lines if slot == SLOT_LINE else self.arcs)

    def _swap_points(self, constraint: Constraint, swap) -> tuple[int, ...]:
        slots = relation_for(constraint.kind).slots
        return tuple(swap(ref) if slot == SLOT_POINT else ref for slot, ref in zip(slots, constraint.refs))

    def _prune_constraints(self) -> None:
        """Forget every relation that refers to something that is gone (or that joining points made meaningless)."""
        def alive(constraint: Constraint) -> bool:
            relation = relation_for(constraint.kind)
            exists = all(self._slot_exists(slot, ref) for slot, ref in zip(relation.slots, constraint.refs))
            return exists and relation.valid(constraint.refs)

        self.constraints = {i: c for i, c in self.constraints.items() if alive(c)}

    def constraint_points(self, constraint: Constraint) -> list[int]:
        """The ids of the sketch points the relation touches (the origin is left out), each once."""
        found: list[int] = []
        for slot, ref in zip(relation_for(constraint.kind).slots, constraint.refs):
            if slot == SLOT_POINT:
                ids = [ref]
            elif slot == SLOT_LINE:
                ids = [] if ref == AXIS_LINE else [self.lines[ref].start, self.lines[ref].end]
            else:
                ids = [self.arcs[ref].centre, self.arcs[ref].start, self.arcs[ref].end]
            found += [i for i in ids if i != ORIGIN and i not in found]
        return found

    def constraint_args(self, constraint: Constraint, coords: dict[int, tuple[float, float]] | None = None) -> list:
        """The geometry a relation sees: (x, z) per point, (start, end) per line, (centre, start, end) per arc."""
        def at(point_id: int) -> tuple[float, float]:
            if coords is not None and point_id in coords:
                return coords[point_id]
            return (0.0, 0.0) if point_id == ORIGIN else (self.points[point_id].x, self.points[point_id].z)

        args: list = []
        for slot, ref in zip(relation_for(constraint.kind).slots, constraint.refs):
            if slot == SLOT_POINT:
                args.append(at(ref))
            elif slot == SLOT_LINE and ref == AXIS_LINE:
                args.append(((0.0, 0.0), (0.0, 1.0)))  # x = 0, along z
            elif slot == SLOT_LINE:
                args.append((at(self.lines[ref].start), at(self.lines[ref].end)))
            else:
                arc = self.arcs[ref]
                args.append((at(arc.centre), at(arc.start), at(arc.end)))
        return args

    def signature(self) -> tuple:
        """Changes whenever the geometry or the relations change (a cache key for the analysis)."""
        return (
            tuple((i, p.x, p.z) for i, p in self.points.items()),
            tuple((i, l.start, l.end, l.construction, l.cutting, l.centre_line, l.reference) for i, l in self.lines.items()),
            tuple((i, a.centre, a.start, a.end, a.direction, a.construction, a.cutting, a.reference) for i, a in self.arcs.items()),
            tuple((i, c.kind, c.refs, c.values, c.offset) for i, c in self.constraints.items()),
            tuple(self.labels.items()),
            tuple(sorted(self.helpers)),
            tuple((b, c.point, c.kept, c.ends, c.references) for b, c in self.corners.items()),
            tuple(sorted(self.rapid_pieces)),
            tuple(sorted(self.piece_feeds.items())),
        )

    def segment(self, piece: Piece) -> Segment:
        """The geometry of a piece; an arc's end is put on the circle through its start."""
        if isinstance(piece, SketchLine):
            return LineSegment(self.point(piece.start).position, self.point(piece.end).position)
        centre = self.point(piece.centre).position
        start = self.point(piece.start).position
        end = self.point(piece.end).position
        if piece.end != piece.start:
            radius = centre.distance_to(start)
            reach = centre.distance_to(end)
            if reach == 0:
                raise SketchError("the end of an arc lies on its centre")
            end = Point(centre.x + (end.x - centre.x) * radius / reach, centre.z + (end.z - centre.z) * radius / reach)
        return ArcSegment(start, end, centre, piece.direction)


def arc_from_three_points(first: Point, through: Point, last: Point) -> tuple[Point, ArcDirection]:
    """Centre and direction of the circle arc that goes from `first` through `through` to `last`."""
    ax, az = first.x, first.z
    bx, bz = through.x, through.z
    cx, cz = last.x, last.z
    d = 2 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz))
    if d == 0:
        raise SketchError("the three points are on one line")
    a2, b2, c2 = ax * ax + az * az, bx * bx + bz * bz, cx * cx + cz * cz
    centre = Point(
        (a2 * (bz - cz) + b2 * (cz - az) + c2 * (az - bz)) / d,
        (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d,
    )
    cross = (bx - ax) * (cz - az) - (bz - az) * (cx - ax)
    return centre, ArcDirection.CCW if cross > 0 else ArcDirection.CW
