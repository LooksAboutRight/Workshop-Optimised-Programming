"""The frame of a roughing block: every case turned into the one the planner knows, and back.

The one case: outside, lines along Z, the tool cutting from the front towards the chuck with its body over the layers already cut. The
frame is built from questions, asked in this order, each answered by a reflection (`mirror.py`):
  1. inside? mirror in X (the bore becomes an outside; the part is made after this step, in coordinates where X is the radius);
  2. a left-hand tool (body towards the chuck)? mirror in Z;
  3. lines across X? swap X and Z.
What the reflections cannot hide is carried as data: the sides that are really free (the outside of the part and the front, never the
chuck: the rapids go only there) and the axis (an inside block has material on both sides of it).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..geometry import Point
from ..tooling.tool import Tool
from ..tooling.tool_back_angle import back_direction
from . import mirror
from .cut_list import Cut, RoughingCuts


@dataclass(frozen=True)
class Frame:
    side: tuple[mirror.Flip, ...]  # applied before the part is made (inside: mirror in X)
    work: tuple[mirror.Flip, ...]  # applied after it (a left-hand tool: mirror in Z; lines across X: swap)
    both_sides: bool  # the material holds both sides of the axis (an inside block)

    @staticmethod
    def of(outside: bool, across: bool, tool: Tool) -> Frame:
        side = () if outside else (mirror.MIRROR_X,)
        for flip in side:
            tool = flip.tool(tool)
        work = ((mirror.MIRROR_Z,) if back_direction(tool) < 0 else ()) + ((mirror.SWAP_XZ,) if across else ())
        return Frame(side, work, not outside)

    @property
    def flips(self) -> tuple[mirror.Flip, ...]:
        return self.side + self.work

    @property
    def axis(self) -> mirror.Flip | None:
        """The reflection over the real axis in the planner's coordinates, when the material holds both sides of it."""
        if not self.both_sides:
            return None
        axis = mirror.MIRROR_X
        for flip in self.work:
            if flip is mirror.SWAP_XZ:
                axis = mirror.MIRROR_Z if axis is mirror.MIRROR_X else mirror.MIRROR_X
        return axis

    @property
    def column_beside_part(self) -> bool:
        """Lines across X: the column above the end of a line runs along Z beside the part, not away from it. There only the material joined
        to the line counts as its top, and a ride ends where it no longer cuts (`cut_limits.column_top`, `holder_stop`): beside a part that
        is wider towards the front the ride would otherwise follow the contour up past what stands under it, again for every line."""
        return mirror.SWAP_XZ in self.work

    @property
    def free(self) -> tuple[int, int]:
        """The free side along X and along Z in the planner's coordinates (+1 or -1): where the outside of the part (the bore, inside) and the
        front of it lie. The rapids leave the material only that way, never towards the chuck."""
        signs = {}
        for vector in (Point(1.0, 0.0), Point(0.0, 1.0)):  # after the side step: out of the part, and the front
            for flip in self.work:
                vector = flip.point(vector)
            along_x = abs(vector.x) > abs(vector.z)
            signs[0 if along_x else 1] = 1 if (vector.x if along_x else vector.z) > 0 else -1
        return signs[0], signs[1]

    @staticmethod
    def point_through(flips: tuple[mirror.Flip, ...], at: Point | None) -> Point | None:
        for flip in flips:
            at = flip.point(at) if at is not None else None
        return at

    def back(self, found: RoughingCuts) -> RoughingCuts:
        """A cut list planned in the frame, in the real coordinates (each reflection is its own inverse: they are undone in reverse order)."""
        for flip in reversed(self.flips):
            found = _reflected(found, flip)
        return replace(found, both_sides=self.both_sides)


def _reflected_cut(listed: Cut, flip: mirror.Flip) -> Cut:
    return replace(
        listed, start=flip.point(listed.start), end=flip.point(listed.end), ride=flip.moves(listed.ride), source=flip.line(listed.source),
        entry=flip.moves(listed.entry), retreat=flip.moves(listed.retreat), rapid=flip.moves(listed.rapid),
    )


def _reflected(first: RoughingCuts, flip: mirror.Flip) -> RoughingCuts:
    return replace(
        first, cuts=tuple(_reflected_cut(listed, flip) for listed in first.cuts), tools=tuple(tuple(flip.point(p) for p in outline) for outline in first.tools),
        removed=tuple(flip.loops(first.removed)), residual=tuple(flip.loops(first.residual)), leave_retreat=flip.moves(first.leave_retreat),
        leave_rapid=flip.moves(first.leave_rapid), material=tuple(flip.loops(first.material)), keep=tuple(flip.loops(first.keep)),
        wanted=tuple(flip.loops(first.wanted)),
    )
