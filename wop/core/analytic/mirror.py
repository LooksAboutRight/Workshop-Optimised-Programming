"""Reflections of a planning case: a case the planner does not know is turned into one it does, planned, and turned back.

The planner cuts lines along Z, from the front towards the chuck (towards smaller Z), with the body of the tool towards larger Z and the free
side towards larger X. Three reflections bring other cases to that one:
  - `MIRROR_Z` (z -> -z): a left-hand tool (its body towards smaller Z, cutting towards the front) becomes a right-hand one;
  - `SWAP_XZ` (x <-> z): lines across X (cutting from the outside towards the axis, the front is the free side) become lines along Z;
  - `MIRROR_X` (x -> -x): an inside block (the free side is the bore, towards the axis) becomes an outside one, at negative X.
`roughing_cuts` applies them one after the other (an inside block across X: mirrored in X, then swapped).
The part and its allowance (the region no tool may enter) and the path of the tool reference along the contour are made in the real
coordinates first and reflected afterwards: the part is closed through the chuck side and the axis side, and they must stay where they are.

All are reflections (`geometry/reflect.py`), so the same rules hold: every arc turns the other way round; a reflected loop is travelled the other way (pieces
reversed, each one turned round), so it keeps its sense of turning; every helper that expects counter-clockwise loops gets one. A reflected
path keeps its order of travel from the front to the chuck: under `MIRROR_Z` and `SWAP_XZ` it is travelled the other way, under `MIRROR_X`
(Z stays) the same way. A wanted line keeps its high end (the larger coordinate along the line) under `SWAP_XZ` and under `MIRROR_X` along Z;
under `MIRROR_Z`, and under `MIRROR_X` across X, its two ends change places.
"""

from __future__ import annotations

from dataclasses import replace

from ..geometry import Point
from ..geometry.reflect import Reflection, other_way, turned_round
from ..contour import NamedPoint
from ..program_model.operations import ArcMove, CompensationSide, LinearMove, Operation, Rapid
from ..tooling.tool import Tool, ToolSegment, ToolShape
from .wanted_lines import WantedLine, WantedPlan


class Flip(Reflection):
    """One reflection of a planning case: the geometry (`geometry/reflect.py`) and the types of the planner."""

    def line(self, wanted: WantedLine) -> WantedLine:
        along_z = abs(wanted.high.x - wanted.low.x) <= abs(wanted.high.z - wanted.low.z)
        turned = (self.in_x and not along_z) or (not self.in_x and not self.swap and along_z)  # the coordinate along the line changes sign
        if not turned:  # the coordinate along the line stays the larger one at the high end
            return replace(wanted, high=self.point(wanted.high), low=self.point(wanted.low))
        return replace(wanted, high=self.point(wanted.low), low=self.point(wanted.high), open_high=wanted.open_low, open_low=wanted.open_high)

    def plan(self, wanted: WantedPlan) -> WantedPlan:
        return WantedPlan(tuple(self.loops(wanted.removal)), tuple(self.line(item) for item in wanted.lines))

    def operation(self, move: Operation) -> Operation:
        """A move of the machine reflected (a finishing pass planned in a frame): arcs turn the other way round, and the side of the tool for
        cutter compensation changes (left of the travel becomes right). Block begin and end and the spindle stay as they are."""
        if isinstance(move, Rapid):
            return Rapid(self.point(move.end))
        if isinstance(move, LinearMove):
            side = None if move.side is None else (CompensationSide.LEFT if move.side is CompensationSide.RIGHT else CompensationSide.RIGHT)
            return replace(move, end=self.point(move.end), contour_end=self._maybe(move.contour_end), side=side)
        if isinstance(move, ArcMove):
            return replace(
                move, end=self.point(move.end), center=self.point(move.center), direction=other_way(move.direction),
                contour_end=self._maybe(move.contour_end), contour_center=self._maybe(move.contour_center),
            )
        return move

    def _maybe(self, at: Point | None) -> Point | None:
        return None if at is None else self.point(at)

    def _shape(self, shape: ToolShape) -> ToolShape:
        pieces = [ToolSegment(self.segment(piece.segment), piece.role) for piece in reversed(shape.pieces)]
        return ToolShape(tuple(ToolSegment(turned_round(piece.segment), piece.role) for piece in pieces))

    def tool(self, real: Tool) -> Tool:
        """The tool reflected (its named points with it)."""
        points = tuple(NamedPoint(named.name, *_coordinates(self.point(Point(named.x, named.z)))) for named in real.points)
        return replace(real, shape=self._shape(real.shape), points=points)


def _coordinates(at: Point) -> tuple[float, float]:
    return at.x, at.z


MIRROR_Z = Flip(False)  # a left-hand tool planned as a right-hand one
SWAP_XZ = Flip(True)  # lines across X planned as lines along Z
MIRROR_X = Flip(False, True)  # an inside block planned as an outside one
