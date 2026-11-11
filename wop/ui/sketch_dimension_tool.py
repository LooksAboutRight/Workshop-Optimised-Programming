"""The Dimension tool of the sketch editor: one tool for every dimension, like in a CAD package.

Click what to dimension (a line, an arc or circle, a point or the origin), a second point or line if there is one, then
click where the dimension goes. Where it goes decides what is measured between two points or along a line: next to the
line its length, to the side of it the distance along X, above or below it the distance along Z. An arc gets a radius,
a circle a diameter, two lines an angle. The value is the one the sketch has now; it is changed afterwards by a double
click on the number.

A centre line (one the user made, or the spindle axis of a turning contour) turns a distance into a diameter: a point
and a centre line, or a line along the centre line and the centre line, are dimensioned from the point to its mirror
point on the other side, across the centre line (see `mirror_helper`). A line that is not parallel to the centre line
gets an angle instead.

A part of `SketchSession` (a mixin: it uses the attributes and `_edit` of the session).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from ..core.geometry import LineSegment, Point
from ..core.sketch.constants import AXIS_LINE, ORIGIN, PARALLEL_SINE
from ..core.sketch.mirror import AXIS_Z, find_mirror_helper, mirror_helper, reflect_position
from ..core.sketch.model import SketchArc, SketchError
from ..core.geometry.distance import distance_to_segment
from ..core.sketch.pick import piece_id
from ..core.sketch.relations import Constraint, relation_for
from .sketch_constants import AXIS_ID, DEFAULT_DIMENSION_OFFSET, DIMENSION_NEAR_FACTOR, PENDING_MIRROR
from .sketch_dimension_graphic import KIND_ALONG_X, KIND_ALONG_Z, DimensionGraphic, graphic, placement_kind, sector_flips
from .sketch_relations import POSITIVE_KINDS

PICK_POINT = "point"
PICK_LINE = "line"
PICK_ARC = "arc"
PICK_CENTRE = "centre"  # a centre line, or the spindle axis (AXIS_ID)

READY = (
    [PICK_LINE], [PICK_ARC], [PICK_POINT, PICK_POINT], [PICK_LINE, PICK_LINE],
    [PICK_POINT, PICK_CENTRE], [PICK_CENTRE, PICK_POINT], [PICK_LINE, PICK_CENTRE], [PICK_CENTRE, PICK_LINE],
)


@dataclass(frozen=True)
class DimensionDraft:
    """A dimension as it would be made if the user clicked now."""

    kind: str
    refs: tuple[int, ...]  # may hold PENDING_MIRROR: the mirror point that is made when the dimension is placed
    values: tuple[float, ...]  # inside the sketch (mm, radians); an angle also has the flips of its two rays
    offset: tuple[float, float]
    drawing: DimensionGraphic
    text: str
    mirror_of: tuple[int, str | int] | None = None  # (point, centre line) the mirror point is made for


def _tuple(point: Point) -> tuple[float, float]:
    return point.x, point.z


class SketchDimensionToolMixin:
    def _position_of(self, point_id: int) -> Point:
        return Point(0, 0) if point_id == ORIGIN else self.sketch.point(point_id).position

    def _dimension_hit(self, position: Point, tolerance: float) -> tuple[str, int] | None:
        """What is under the mouse: a point of the sketch, else the origin, else a line or an arc, else the spindle axis."""
        point = self.pickable_point(position, tolerance)
        if point is not None:
            return PICK_POINT, point
        if position.distance_to(Point(0, 0)) <= tolerance:
            return PICK_POINT, ORIGIN
        piece = self.pick_piece(position, tolerance)
        if piece is not None:
            if isinstance(piece, SketchArc):
                return PICK_ARC, piece_id(piece)
            return (PICK_CENTRE if piece.centre_line or self.sketch.is_locked_piece(piece_id(piece)) else PICK_LINE), piece_id(piece)  # the part outline of a path is measured to like a centre line
        if self.mode.centre_line and abs(position.x) <= tolerance:
            return PICK_CENTRE, AXIS_ID
        return None

    def dimension_ready(self) -> bool:
        """Is everything picked that a dimension needs (the next click places it)?"""
        return [kind for kind, _ in self.dim_picks] in READY

    def clear_dimension_picks(self) -> None:
        self.dim_picks = []
        self._sync_pick_selection()

    def _sync_pick_selection(self) -> None:
        """What is picked is drawn like a selection (the origin and the spindle axis are drawn by the picture itself)."""
        self.selected_points = {i for kind, i in self.dim_picks if kind == PICK_POINT and i != ORIGIN}
        self.selected_pieces = {i for kind, i in self.dim_picks if kind != PICK_POINT and i != AXIS_ID}

    def dimension_click(self, position: Point, tolerance: float) -> None:
        self.message = ""
        hit = self._dimension_hit(position, tolerance)
        picks = self.dim_picks
        if not picks:
            if hit is None:
                self.message = "Click a line, an arc or a circle, or a point"
            else:
                picks.append(hit)
        elif len(picks) == 1:
            self._second_pick(picks, hit, position, tolerance)
        else:
            self._place_dimension(position, tolerance)
        self._sync_pick_selection()
        self._notify()

    def _second_pick(self, picks: list, hit: tuple[str, int] | None, position: Point, tolerance: float) -> None:
        first = picks[0][0]
        other = None if hit is None else hit[0]
        if hit is not None and hit != picks[0] and (
            (first == PICK_POINT and other in (PICK_POINT, PICK_CENTRE))
            or (first == PICK_LINE and other in (PICK_LINE, PICK_CENTRE))  # a second line: the angle; a centre line: the diameter
            or (first == PICK_CENTRE and other in (PICK_POINT, PICK_LINE))
        ):
            picks.append(hit)
        elif first == PICK_POINT:
            self.message = "Click a second point or a centre line (Esc stops)"
        elif first == PICK_CENTRE:
            self.message = "Click a point or a line to dimension from the centre line (Esc stops)"
        else:
            self._place_dimension(position, tolerance)

    # --- what the picks and the mouse make ----------------------------------------------------------------------------

    def _centre_ends(self, ref: int) -> tuple[Point, Point]:
        """Two points on a centre line (the spindle axis runs along Z through the origin)."""
        if ref == AXIS_ID:
            return Point(0, 0), Point(0, 1)
        return self._position_of(self.sketch.lines[ref].start), self._position_of(self.sketch.lines[ref].end)

    @staticmethod
    def _axis_of(ref: int) -> str | int:
        return AXIS_Z if ref == AXIS_ID else ref

    def _parallel_to_centre(self, line_id: int, centre: int) -> bool:
        start, end = self._line_ends(line_id)
        a, b = self._position_of(start), self._position_of(end)
        c, d = self._centre_ends(centre)
        along, centre_along = (b.x - a.x, b.z - a.z), (d.x - c.x, d.z - c.z)
        length = (along[0] ** 2 + along[1] ** 2) ** 0.5 * (centre_along[0] ** 2 + centre_along[1] ** 2) ** 0.5
        return length > 0 and abs(along[0] * centre_along[1] - along[1] * centre_along[0]) / length < PARALLEL_SINE

    def _made(
        self, kind: str, refs: tuple[int, ...], args: list, mouse: Point, values: tuple[float, ...] | None = None,
        mirror_of: tuple[int, str | int] | None = None,
    ) -> DimensionDraft:
        relation = relation_for(kind)
        values = relation.measure(args) if values is None else values
        anchor = relation.anchor(args)
        shown = abs(relation.to_display(values[0])) * self._scale(kind, refs)
        text = f"{shown:g}" + ("°" if relation.unit == "deg" else "")
        offset = (mouse.x - anchor[0], mouse.z - anchor[1])
        return DimensionDraft(kind, refs, values, offset, graphic(kind, args, mouse, values), text, mirror_of)

    def _pair_draft(
        self, first: int, second: int, at_first: Point, at_second: Point, whole: tuple[str, tuple[int, ...]],
        mouse: Point, near: float, mirror_of: tuple[int, str | int] | None = None,
    ) -> DimensionDraft:
        """A dimension between two points (the ends of a line, two points, or a point and its mirror point)."""
        chosen = placement_kind(at_first, at_second, mouse, near)
        kind, refs = whole
        if chosen == KIND_ALONG_Z:
            kind, backwards = "distance_z", at_second.z < at_first.z
        elif chosen == KIND_ALONG_X:
            kind, backwards = "distance_x", at_second.x < at_first.x
        else:
            backwards = False
        if kind != whole[0]:  # along Z or X: a positive number, so the point with the smaller coordinate comes first
            refs = (second, first) if backwards else (first, second)
        low, high = (at_second, at_first) if backwards and kind != whole[0] else (at_first, at_second)
        args = [(_tuple(low), _tuple(high))] if kind == "length" else [_tuple(low), _tuple(high)]
        return self._made(kind, refs, args, mouse, mirror_of=mirror_of)

    def _beside_centre(self, point: int, centre: int, mouse: Point) -> bool:
        """Is the mouse on the same side of the centre line as the point (a radius), not across it (the diameter)?"""
        start, end = self._centre_ends(centre)
        along = (end.x - start.x, end.z - start.z)

        def side(position: Point) -> float:
            return along[0] * (position.z - start.z) - along[1] * (position.x - start.x)

        return side(self._position_of(point)) * side(mouse) > 0

    def _radius_draft(self, point: int, centre: int, mouse: Point) -> DimensionDraft:
        """From a point to a centre line (the spindle axis too): the radius, the distance square to the line."""
        if point == ORIGIN and centre == AXIS_ID:
            raise SketchError("The origin is on the spindle axis")
        refs = (point, AXIS_LINE if centre == AXIS_ID else centre)
        return self._made("distance_line", refs, self.sketch.constraint_args(Constraint(0, "distance_line", refs)), mouse)

    def _across_centre_draft(self, point: int, centre: int, mouse: Point, near: float) -> DimensionDraft:
        """From a point to its mirror point across a centre line: the diameter."""
        if point == ORIGIN:
            raise SketchError("Click a point of the sketch, not the origin")
        axis = self._axis_of(centre)
        helper = find_mirror_helper(self.sketch, point, axis)
        here = self._position_of(point)
        there = reflect_position(self.sketch, here, axis) if helper is None else self._position_of(helper)
        partner = PENDING_MIRROR if helper is None else helper
        return self._pair_draft(
            point, partner, here, there, ("distance", (point, partner)), mouse, near,
            mirror_of=(point, axis) if helper is None else None,
        )

    def _angle_draft(self, refs: tuple[int, ...], mouse: Point) -> DimensionDraft:
        refs = tuple(sorted(refs))  # the spindle axis (-1) comes first
        args = self.sketch.constraint_args(Constraint(0, "angle", refs))
        flips = sector_flips(args, mouse)  # the angle between the rays that are on the side of the mouse
        values = (relation_for("angle").measure(args, (0, *flips))[0], *flips)
        return self._made("angle", refs, args, mouse, values)

    def _draft(self, mouse: Point, tolerance: float) -> DimensionDraft:
        kinds = [kind for kind, _ in self.dim_picks]
        ids = [i for _, i in self.dim_picks]
        near = DIMENSION_NEAR_FACTOR * tolerance
        if kinds == [PICK_ARC]:
            arc = self.sketch.arcs[ids[0]]
            kind, refs = ("diameter" if arc.start == arc.end else "radius"), (ids[0],)
            return self._made(kind, refs, self.sketch.constraint_args(Constraint(0, kind, refs)), mouse)
        if kinds == [PICK_LINE, PICK_LINE]:
            return self._angle_draft(tuple(sorted(ids)), mouse)
        if PICK_CENTRE in kinds:
            centre = ids[kinds.index(PICK_CENTRE)]
            other_kind, other = next((k, i) for k, i in self.dim_picks if k != PICK_CENTRE)
            if other_kind == PICK_LINE and not self._parallel_to_centre(other, centre):  # the angle between the two lines: the spindle axis is a line like any other
                return self._angle_draft((AXIS_LINE if centre == AXIS_ID else centre, other), mouse)
            point = other if other_kind == PICK_POINT else self._line_ends(other)[0]  # a parallel line: from its start
            if self.sketch.is_locked_piece(centre) or self._beside_centre(point, centre, mouse):  # between the thing and the centre line, or beyond the thing: the radius (to the part outline always the distance)
                return self._radius_draft(point, centre, mouse)
            return self._across_centre_draft(point, centre, mouse, near)  # across the centre line: the diameter
        if kinds == [PICK_LINE]:
            first, second = self._line_ends(ids[0])
            whole = ("length", (ids[0],))
        else:
            first, second = ids
            whole = ("distance", (first, second))
        return self._pair_draft(first, second, self._position_of(first), self._position_of(second), whole, mouse, near)

    def dimension_draft(self) -> DimensionDraft | None:
        """The dimension that follows the mouse (None when it is not ready or the mouse has not moved yet)."""
        if not self.dimension_ready() or self.mouse is None:
            return None
        try:
            return self._draft(self.mouse, self.mouse_tolerance)
        except SketchError:
            return None

    def _place_dimension(self, position: Point, tolerance: float) -> None:
        try:
            draft = self._draft(position, tolerance)
            if draft.kind in POSITIVE_KINDS and draft.values[0] <= 0:
                raise SketchError(f"{relation_for(draft.kind).label} must be more than zero")

            def make() -> None:
                refs = draft.refs
                if draft.mirror_of is not None:
                    helper = mirror_helper(self.sketch, *draft.mirror_of)
                    refs = tuple(helper if ref == PENDING_MIRROR else ref for ref in refs)
                self.sketch.add_constraint(draft.kind, refs, draft.values, draft.offset)

            self._edit(make)
        except SketchError as error:
            self.message = str(error)
        self.dim_picks = []  # ready for the next one

    # --- moving a placed dimension ------------------------------------------------------------------------------------

    def dimension_at(self, position: Point, tolerance: float) -> int | None:
        """The placed dimension whose dimension line, extension line or arc is under the position (the newest first)."""
        if not self.show_dimensions:
            return None
        for constraint in reversed(list(self.sketch.constraints.values())):
            if not relation_for(constraint.kind).dimension:
                continue
            drawing, _text = self.dimension_drawing(constraint)
            pieces = [*drawing.lines, *zip(drawing.curve, drawing.curve[1:])]
            if any(a != b and distance_to_segment(position, LineSegment(a, b)) <= tolerance for a, b in pieces):
                return constraint.constraint_id
        return None

    def begin_dimension_drag(self, constraint_id: int, position: Point) -> None:
        """The button went down on a dimension: choose it, and let the mouse move it while the button is held."""
        constraint = self.sketch.constraints[constraint_id]
        self.selected_constraint = constraint_id
        self._dim_drag = (constraint_id, position, constraint.offset or DEFAULT_DIMENSION_OFFSET)
        self._drag_undo = copy.deepcopy(self.sketch)
        self._drag_mode = "dimension"
        self._notify()

    def _allowed_move(self, constraint: Constraint, delta: tuple[float, float]) -> tuple[float, float]:
        """How far a dimension may move for a mouse movement: a dimension along Z only up and down (its line is horizontal), along
        X only sideways, a length only away from or towards the line it measures; radius, diameter and angle any way."""
        if constraint.kind == "distance_z":
            return delta[0], 0.0
        if constraint.kind == "distance_x":
            return 0.0, delta[1]
        if constraint.kind == "distance_line":  # the dimension line slides along the centre line
            (start, end) = self.sketch.constraint_args(constraint)[1]
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            if length == 0:
                return delta
            ux, uz = (end[0] - start[0]) / length, (end[1] - start[1]) / length
            along = delta[0] * ux + delta[1] * uz
            return ux * along, uz * along
        if constraint.kind in ("length", "distance"):
            args = self.sketch.constraint_args(constraint)
            first, second = args[0] if constraint.kind == "length" else (args[0], args[1])
            length = math.hypot(second[0] - first[0], second[1] - first[1])
            if length == 0:
                return delta
            normal = (-(second[1] - first[1]) / length, (second[0] - first[0]) / length)  # square to the line, in (x, z)
            along = delta[0] * normal[0] + delta[1] * normal[1]
            return normal[0] * along, normal[1] * along
        return delta

    def move_dimension(self, position: Point) -> None:
        constraint_id, start, base = self._dim_drag
        constraint = self.sketch.constraints.get(constraint_id)
        if constraint is None:
            return
        if self._drag_undo is not None:  # the first movement: now it is a change that can be undone
            self._push_snapshot(self._drag_undo)
            self._drag_undo = None
        moved = self._allowed_move(constraint, (position.x - start.x, position.z - start.z))
        self.sketch.set_offset(constraint_id, (base[0] + moved[0], base[1] + moved[1]))

    def dimension_drawing(self, constraint: Constraint) -> tuple[DimensionGraphic, str]:
        """The drawing and the number of a placed dimension."""
        relation = relation_for(constraint.kind)
        args = self.sketch.constraint_args(constraint)
        anchor = relation.anchor(args)
        offset = constraint.offset or DEFAULT_DIMENSION_OFFSET
        shown = self.display_value(constraint)
        text = f"{shown:g}" + ("°" if relation.unit == "deg" else "")
        place = Point(anchor[0] + offset[0], anchor[1] + offset[1])
        return graphic(constraint.kind, args, place, constraint.values), text
