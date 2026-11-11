"""Relations and dimensions in the sketch editor: what the selected things allow, and adding or removing them.

A part of `SketchSession` (a mixin: it uses the attributes and `_edit` of the session). The user selects things, then
picks a relation or dimension; `plan_*` works out which kind and which ids that means (or says why it cannot be done).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.sketch.constants import AXIS_LINE, ORIGIN, SLOT_POINT
from ..core.sketch.model import SketchError
from ..core.sketch.pick import piece_points
from ..core.sketch.relations import Constraint, relation_for
from .sketch_constants import PENDING_MIRROR

POSITIVE_KINDS = ("length", "distance", "distance_line", "radius", "diameter")  # dimensions that cannot be zero or negative


@dataclass(frozen=True)
class DimensionPlan:
    kind: str
    refs: tuple[int, ...]
    shown: float  # the measured value, in mm or degrees
    unit: str
    label: str


class SketchRelationsMixin:
    def _selection(self) -> tuple[list[int], list[int], list[int]]:
        """(points, lines, arcs) selected. A point that only belongs to a selected piece is not counted on its own."""
        owned: set[int] = set()
        for piece in self.sketch.pieces():
            if (piece.line_id if hasattr(piece, "line_id") else piece.arc_id) in self.selected_pieces:
                owned |= piece_points(piece)
        points = sorted(self.selected_points - owned)
        lines = sorted(i for i in self.selected_pieces if i in self.sketch.lines)
        arcs = sorted(i for i in self.selected_pieces if i in self.sketch.arcs)
        return points, lines, arcs

    def constraint_members(self) -> tuple[set[int], set[int]]:
        """(points, pieces) that the chosen relation or dimension acts on: shown like a selection, but not selected (Delete
        removes the relation, not the geometry). The origin counts as a point."""
        constraint = self.sketch.constraints.get(self.selected_constraint) if self.selected_constraint is not None else None
        if constraint is None:
            return set(), set()
        points, pieces = set(), set()
        for slot, ref in zip(relation_for(constraint.kind).slots, constraint.refs):
            if ref in self.sketch.helpers or ref == AXIS_LINE:  # the hidden mirror point of a diameter, the spindle axis (drawn by the picture)
                continue
            (points if slot == SLOT_POINT else pieces).add(ref)
        return points, pieces

    def _line_ends(self, line_id: int) -> tuple[int, int]:
        line = self.sketch.lines[line_id]
        return line.start, line.end

    def _meeting_point(self, first_ends: set[int], second_ends: set[int]) -> int:
        shared = sorted(first_ends & second_ends)
        if not shared:
            raise SketchError("Tangent: the two pieces must meet at a point")
        return shared[0]

    # --- relations ----------------------------------------------------------------------------------------------------

    def plan_relation(self, ui_kind: str) -> list[tuple[str, tuple[int, ...], tuple[float, ...]]]:
        """The constraints (kind, refs, values) that `ui_kind` means for the selection; raises SketchError if none."""
        points, lines, arcs = self._selection()
        plan = getattr(self, f"_plan_{ui_kind}", None)
        if plan is None:
            raise SketchError("unknown relation")
        return plan(points, lines, arcs)

    def _plan_horizontal(self, points, lines, arcs, kind: str = "horizontal"):
        if lines and not points and not arcs:
            return [(kind, self._line_ends(line), ()) for line in lines]
        if len(points) == 2 and not lines and not arcs:
            return [(kind, tuple(points), ())]
        raise SketchError("Select lines, or two points (a point and the origin: click the origin as the second point)")

    def _plan_vertical(self, points, lines, arcs):
        return self._plan_horizontal(points, lines, arcs, "vertical")

    def _two_lines(self, kind: str, points, lines, arcs):
        if len(lines) != 2 or points or arcs:
            raise SketchError("Select two lines")
        return [(kind, tuple(lines), ())]

    def _plan_parallel(self, points, lines, arcs):
        return self._two_lines("parallel", points, lines, arcs)

    def _plan_perpendicular(self, points, lines, arcs):
        return self._two_lines("perpendicular", points, lines, arcs)

    def _plan_equal(self, points, lines, arcs):
        if len(lines) == 2 and not points and not arcs:
            return [("equal_length", tuple(lines), ())]
        if len(arcs) == 2 and not points and not lines:
            return [("equal_radius", tuple(arcs), ())]
        raise SketchError("Select two lines, or two arcs / circles")

    def _plan_tangent(self, points, lines, arcs):
        if points:
            raise SketchError("Select a line and an arc, or two arcs")
        if len(lines) == 1 and len(arcs) == 1:
            arc = self.sketch.arcs[arcs[0]]
            touch = self._meeting_point(set(self._line_ends(lines[0])), {arc.start, arc.end})
            return [("tangent_line_arc", (lines[0], arcs[0], touch), ())]
        if len(arcs) == 2 and not lines:
            first, second = (self.sketch.arcs[a] for a in arcs)
            touch = self._meeting_point({first.start, first.end}, {second.start, second.end})
            return [("tangent_arcs", (arcs[0], arcs[1], touch), ())]
        raise SketchError("Select a line and an arc, or two arcs")

    def _plan_fixed(self, points, lines, arcs):
        every = set(self.selected_points)
        for piece in self.sketch.pieces():
            if (piece.line_id if hasattr(piece, "line_id") else piece.arc_id) in self.selected_pieces:
                every |= piece_points(piece)
        done = {c.refs[0] for c in self.sketch.constraints.values() if c.kind == "fixed"}
        todo = sorted(every - done)
        if not todo:
            raise SketchError("Select points or pieces that are not fixed yet")
        return [("fixed", (p,), (self.sketch.point(p).x, self.sketch.point(p).z)) for p in todo]

    def _plan_point_on(self, points, lines, arcs):
        if len(points) != 1 or len(lines) + len(arcs) != 1:
            raise SketchError("Select one point and one line or arc")
        if lines:
            if points[0] in self._line_ends(lines[0]):
                raise SketchError("The point is an end of that line already")
            return [("point_on_line", (points[0], lines[0]), ())]
        if points[0] in piece_points(self.sketch.arcs[arcs[0]]):
            raise SketchError("The point belongs to that arc already")
        return [("point_on_circle", (points[0], arcs[0]), ())]

    def _plan_midpoint(self, points, lines, arcs):
        if len(points) != 1 or len(lines) != 1 or arcs:
            raise SketchError("Select one point and one line")
        if points[0] in self._line_ends(lines[0]):
            raise SketchError("The point is an end of that line")
        return [("midpoint", (points[0], lines[0]), ())]

    def can_join(self) -> bool:
        return len(self._selection()[0]) == 2

    def available_relation(self, ui_kind: str) -> bool:
        if ui_kind == "join":
            return self.can_join()
        try:
            self.plan_relation(ui_kind)
        except SketchError:
            return False
        return True

    def apply_relation(self, ui_kind: str) -> bool:
        try:
            if ui_kind == "join":
                points = self._selection()[0]
                if len(points) != 2:
                    raise SketchError("Select two points to join")
                keep, drop = points
                ok = self._edit(lambda: self.sketch.merge_points(keep, drop))
                self.selected_points, self.selected_pieces = (set(), set()) if ok else (self.selected_points, self.selected_pieces)
                return ok
            plan = self.plan_relation(ui_kind)
        except SketchError as error:
            self.message = str(error)
            self._notify()
            return False

        def add_all() -> None:
            for kind, refs, values in plan:
                if kind in ("horizontal", "vertical"):
                    self._level(kind, refs)
                self.sketch.add_constraint(kind, refs, values)

        ok = self._edit(add_all)
        self._notify()
        return ok

    def _level(self, kind: str, refs: tuple[int, int]) -> None:
        """Turn the two points about their middle, keeping their distance, so that the solver does not shrink the line."""
        if ORIGIN in refs:
            return
        first, second = (self.sketch.point(r) for r in refs)
        length = first.position.distance_to(second.position)
        if length == 0:
            return
        mid_x, mid_z = (first.x + second.x) / 2, (first.z + second.z) / 2
        if kind == "horizontal":  # level in the picture: the same x, they differ in z
            sign = 1 if second.z >= first.z else -1
            ends = ((mid_x, mid_z - sign * length / 2), (mid_x, mid_z + sign * length / 2))
        else:
            sign = 1 if second.x >= first.x else -1
            ends = ((mid_x - sign * length / 2, mid_z), (mid_x + sign * length / 2, mid_z))
        self.sketch.move_point(refs[0], *ends[0])
        self.sketch.move_point(refs[1], *ends[1])

    # --- dimensions ---------------------------------------------------------------------------------------------------

    def plan_dimension(self, ui_kind: str) -> DimensionPlan:
        points, lines, arcs = self._selection()
        refs, kind = self._dimension_refs(ui_kind, points, lines, arcs)
        relation = relation_for(kind)
        measured = relation.measure(self.sketch.constraint_args(Constraint(0, kind, refs)))
        shown = relation.to_display(measured[0]) * self._scale(kind)
        return DimensionPlan(kind, refs, shown, relation.unit, self.kind_label(kind))

    def _dimension_refs(self, ui_kind: str, points, lines, arcs) -> tuple[tuple[int, ...], str]:
        if ui_kind in ("length", "along_z", "along_x"):
            pair = self._point_pair(points, lines, arcs)
            if ui_kind == "length" and lines and not points and not arcs and len(lines) == 1:
                return (lines[0],), "length"
            if ui_kind == "length":
                return pair, "distance"
            kind = "distance_z" if ui_kind == "along_z" else "distance_x"
            return self._ordered_for_positive(pair, kind), kind
        if ui_kind in ("radius", "diameter"):
            if len(arcs) != 1 or points or lines:
                raise SketchError("Select one arc or circle")
            return (arcs[0],), ui_kind
        if ui_kind == "angle":
            if len(lines) != 2 or points or arcs:
                raise SketchError("Select two lines")
            return tuple(lines), "angle"
        if ui_kind == "angle_z":
            if len(lines) != 1 or points or arcs:
                raise SketchError("Select one line")
            return (lines[0],), "angle_z"
        raise SketchError("unknown dimension")

    def _point_pair(self, points, lines, arcs) -> tuple[int, int]:
        if len(lines) == 1 and not points and not arcs:
            return self._line_ends(lines[0])
        if len(points) == 2 and not lines and not arcs:
            return points[0], points[1]
        if len(points) == 1 and not lines and not arcs:
            return ORIGIN, points[0]
        raise SketchError("Select a line, or two points, or one point")

    def _ordered_for_positive(self, pair: tuple[int, int], kind: str) -> tuple[int, int]:
        args = self.sketch.constraint_args(Constraint(0, kind, pair))
        return pair if relation_for(kind).measure(args)[0] >= 0 else (pair[1], pair[0])

    def _scale(self, kind: str, refs: tuple[int, ...] = ()) -> float:
        """Along-X dimensions are shown as diameters when the project is typed in diameters. A dimension to a mirror
        point (across a centre line) already is a diameter: nothing to do."""
        across = any(ref == PENDING_MIRROR or ref in self.sketch.helpers for ref in refs)
        return self.target.x_scale if kind == "distance_x" and not across else 1

    def kind_label(self, kind: str, refs: tuple[int, ...] = ()) -> str:
        label = relation_for(kind).label
        if any(ref == PENDING_MIRROR or ref in self.sketch.helpers for ref in refs):  # across a centre line
            return "Diameter (across a centre line)"
        return label.replace("radius", "diameter") if self._scale(kind, refs) != 1 else label

    def display_value(self, constraint: Constraint) -> float:
        """The value of a dimension as the user sees it."""
        shown = relation_for(constraint.kind).to_display(constraint.values[0]) * self._scale(constraint.kind, constraint.refs)
        return abs(shown) if constraint.kind == "angle" else shown  # the sign of an angle is only its turning direction

    def add_dimension(self, plan: DimensionPlan, shown: float) -> bool:
        relation = relation_for(plan.kind)
        if plan.kind in POSITIVE_KINDS and shown <= 0:
            self.message = f"{relation.label} must be more than zero"
            self._notify()
            return False
        value = relation.from_display(shown / self._scale(plan.kind, plan.refs))
        ok = self._edit(lambda: self.sketch.add_constraint(plan.kind, plan.refs, (value,)))
        self._notify()
        return ok

    def edit_dimension(self, constraint_id: int, shown: float) -> bool:
        constraint = self.sketch.constraints[constraint_id]
        relation = relation_for(constraint.kind)
        if constraint.kind in POSITIVE_KINDS and shown <= 0:
            self.message = f"{relation.label} must be more than zero"
            self._notify()
            return False
        value = relation.from_display(shown / self._scale(constraint.kind, constraint.refs))
        if constraint.kind == "angle":
            value = math.copysign(value, constraint.values[0])  # the turning direction stays
        ok = self._edit(lambda: self.sketch.set_values(constraint_id, (value, *constraint.values[1:])))
        self._notify()
        return ok

    def remove_constraint(self, constraint_id: int) -> None:
        self._edit(lambda: self.sketch.remove_constraint(constraint_id))
        if self.selected_constraint == constraint_id:
            self.selected_constraint = None
        self._notify()
