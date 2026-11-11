"""Step E: the moves of a cut list run once more, in the order the machine makes them, on the material: the collisions and the material left.

Every move is tested with the real tool (not the planning copy):
  - against the part and its allowance (`RoughingCuts.keep`): no edge may go into it, feed or rapid (the snap distance `CUT_END_SNAP_MM` is the
    tolerance: the end of a cut may lie that far inside, the user's roughing accuracy);
  - a feed move: the edges that are not cutting (the holder) may not go into the material that stands where they are: the material the
    cutting edges of the same move have taken before is gone (a block tool whose back face trails behind its cutting face). Tested in three
    steps: free of the material before the move, nothing to report; in the material that is still there after it, a collision; in between,
    the material is cut up to the place along the move and the holder tested against that. Then the material the cutting edges sweep is
    removed (`removal.cut`);
  - a rapid: no edge may go into the material, and the tool grown by the clearance less `RAPID_CLEARANCE_TOLERANCE_MM` may not either (the
    user's rule X12: every move closer to the material than one clearance is a feed move).
A move is first tested with boxes: the box of its path grown by the box of the tool (or of the edges that matter) holds every place of the tool
along the move, so when no piece of the region lies in that box and the box is not inside the region, the move is proven free with no other
test. Otherwise the exact test of the walk (`tip_walk.first_blocked`: the move cut where a contact begins or ends, a test in the middle and at
the end of each part) finds the first place where the tool goes in. The material after the last move is what the next block gets.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..constants import CUT_END_SNAP_MM, GEOMETRY_TOLERANCE_MM, RAPID_CLEARANCE_TOLERANCE_MM
from ..geometry import LineSegment, Point, Segment
from ..geometry.intersect import fraction_along, point_of
from ..geometry.chains import Box, ChainError, Loop, box_of, difference, loops_box, split_at
from .cut_list import RoughingCuts
from .mirror import MIRROR_X
from ..geometry.penetration import RegionIndex, blocked_by_material, blocked_by_part
from ..geometry.removal import cut
from .tip_walk import RegionCurves, first_blocked, marks_along
from ..geometry.tool_edges import ToolLoop, grown_loops


class ReplayKind(Enum):
    PART = "the tool goes into the part or its allowance"
    HOLDER = "a part of the tool that does not cut goes into the material"
    RAPID = "a rapid move goes through the material"
    CLOSE = "a rapid move comes closer to the material than the clearance"


@dataclass(frozen=True)
class ReplayFinding:
    kind: ReplayKind
    cut: int  # the number of the cut in the list (the number of cuts: the end of the block)
    place: Point  # the place of the tool tip where it goes in


@dataclass(frozen=True)
class Move:
    cut: int
    piece: Segment
    rapid: bool


@dataclass(frozen=True)
class Replay:
    findings: tuple[ReplayFinding, ...]
    residual: tuple[Loop, ...]  # the material after the last move
    moves: int  # the moves tested
    proven_by_box: int  # tests (part, holder or rapid) the box alone decided
    exact_tests: int  # tests that needed the exact test along the move
    not_worked_out: int  # feed moves whose removal the boolean could not work out (the material is left as it was: on the safe side)


def moves_of(first: RoughingCuts) -> list[Move]:
    """The moves of the cut list in the order the machine makes them."""
    moves: list[Move] = []
    for number, listed in enumerate(first.cuts):
        moves += [Move(number, piece, False) for piece in listed.retreat]
        moves += [Move(number, piece, True) for piece in listed.rapid]
        moves += [Move(number, piece, False) for piece in listed.entry]
        if not listed.start.is_close(listed.end):
            moves.append(Move(number, LineSegment(listed.start, listed.end), False))
        moves += [Move(number, piece, False) for piece in listed.ride]
    end = len(first.cuts)
    moves += [Move(end, piece, False) for piece in first.leave_retreat]
    moves += [Move(end, piece, True) for piece in first.leave_rapid]
    return [move for move in moves if move.piece.length > GEOMETRY_TOLERANCE_MM]


def _grown(piece: Segment, reach: Box) -> Box:
    x0, z0, x1, z1 = box_of(piece)
    rx0, rz0, rx1, rz1 = reach
    return x0 + rx0, z0 + rz0, x1 + rx1, z1 + rz1


def _box_clear(piece: Segment, reach: Box, region: RegionIndex, margin: float) -> bool:
    """True when the box of every place of the tool along the piece meets no piece of the region and does not lie inside it."""
    box = _grown(piece, reach)
    return not region.near(box, margin) and not region.inside(Point(box[0], box[1]))


class _Tester:
    """The tests of one tool against one region, with the box proof first."""

    def __init__(self, tool: list[ToolLoop], region: RegionIndex, reach: Box, blocked) -> None:
        self.curves = RegionCurves(tool, region)
        self.region, self.reach, self.blocked = region, reach, blocked
        self.boxed = self.exact = 0

    def first_place(self, piece: Segment, margin: float) -> Point | None:
        if _box_clear(piece, self.reach, self.region, margin):
            self.boxed += 1
            return None
        self.exact += 1
        return first_blocked(piece, [self.curves], self.blocked)


def _holder_place(
    piece: Segment, tool: list[ToolLoop], material: list[Loop], left: Callable[[], list[Loop]], tester: _Tester, tolerance: float,
) -> Point | None:
    """The first place along a feed move where an edge that does not cut is in material that stands at that moment (see the top), or None.
    `left`: the material after the move, worked out only when the holder meets the material before it (a cut is dear, the box proof is not)."""
    if tester.first_place(piece, tolerance) is None:
        return None  # free of the material before the move
    after = RegionIndex(left())
    marks = marks_along(piece, [tester.curves])
    for low, high in zip(marks, marks[1:]):
        for at in ((low + high) / 2, high):
            place = point_of(piece, at)
            if not blocked_by_material(tool, tester.region, place, tolerance):
                continue
            begins = point_of(piece, low)  # where the part begins: the place the holder first meets that material
            if blocked_by_material(tool, after, place, tolerance):
                return begins  # material that this move does not take: it is there when the holder comes
            try:
                now = RegionIndex(cut(material, tool, split_at(piece, [fraction_along(piece, place)])[:1], tolerance)[0])
            except ChainError:
                return begins  # cannot be worked out: reported, on the safe side
            if blocked_by_material(tool, now, place, tolerance):
                return begins
    return None


def holder_meets(piece: Segment, tool: list[ToolLoop], material: list[Loop], tolerance: float, axis=None) -> Point | None:
    """The first place along the feed move `piece` where an edge of `tool` that does not cut meets the material that stands at that moment
    (`material` before the move), or None: the test of the replay (HOLDER), for the planner to stop a move there. `axis`: the reflection over
    the axis when the material holds both sides of it (what the move takes is gone on the other side too)."""
    holder_edges = [[edge.segment for edge in loop if not edge.cutting] for loop in tool]
    if not any(holder_edges) or not material:
        return None
    stock = RegionIndex(material)
    tester = _Tester(tool, stock, loops_box([edges for edges in holder_edges if edges]), lambda at: blocked_by_material(tool, stock, at, tolerance))
    def left() -> list[Loop]:
        try:
            after, taken = cut(material, tool, [piece], tolerance)
            if axis is not None and taken:
                after = difference(after, axis.loops(taken), tolerance)
        except ChainError:
            after = material  # on the safe side: nothing taken
        return after

    return _holder_place(piece, tool, material, left, tester, tolerance)


def replay(first: RoughingCuts, tool: list[ToolLoop], tolerance: float) -> Replay:
    """The moves of `first` run on its material with the real `tool`: what goes wrong where, and the material left."""
    keep = RegionIndex(list(first.keep))
    whole = loops_box([[edge.segment for edge in loop] for loop in tool])
    holder_edges = [[edge.segment for edge in loop if not edge.cutting] for loop in tool]
    holder = loops_box([edges for edges in holder_edges if edges]) if any(holder_edges) else None
    part = _Tester(tool, keep, whole, lambda at: blocked_by_part(tool, keep, at, CUT_END_SNAP_MM))
    findings: list[ReplayFinding] = []
    material = list(first.material)
    moves = moves_of(first)
    boxed = exact = failed = 0
    room = first.clearance - RAPID_CLEARANCE_TOLERANCE_MM
    grown = grown_loops(tool, room) if room > GEOMETRY_TOLERANCE_MM else None
    grown_reach = loops_box([[edge.segment for edge in loop] for loop in grown]) if grown else None
    if moves and blocked_by_part(tool, keep, moves[0].piece.start, CUT_END_SNAP_MM):
        findings.append(ReplayFinding(ReplayKind.PART, moves[0].cut, moves[0].piece.start))
    for move in moves:
        place = part.first_place(move.piece, CUT_END_SNAP_MM)
        if place is not None:
            findings.append(ReplayFinding(ReplayKind.PART, move.cut, place))
        stock = RegionIndex(material)
        if move.rapid:
            tester = _Tester(tool, stock, whole, lambda at, s=stock: blocked_by_part(tool, s, at, CUT_END_SNAP_MM))
            place = tester.first_place(move.piece, tolerance)
            if place is not None:
                findings.append(ReplayFinding(ReplayKind.RAPID, move.cut, place))
            elif grown is not None:
                close = _Tester(grown, stock, grown_reach, lambda at, s=stock: blocked_by_part(grown, s, at, CUT_END_SNAP_MM))
                place = close.first_place(move.piece, tolerance)
                if place is not None:
                    findings.append(ReplayFinding(ReplayKind.CLOSE, move.cut, place))
                boxed, exact = boxed + close.boxed, exact + close.exact
            boxed, exact = boxed + tester.boxed, exact + tester.exact
            continue
        try:
            after, taken = cut(material, tool, [move.piece], tolerance)
            if first.both_sides and taken:  # the part turns: what is taken on one side of the axis is gone on the other side too
                after = difference(after, MIRROR_X.loops(taken), tolerance)
        except ChainError:
            failed += 1
            after = material  # on the safe side: nothing taken
        if holder is not None:
            tester = _Tester(tool, stock, holder, lambda at, s=stock: blocked_by_material(tool, s, at, tolerance))
            place = _holder_place(move.piece, tool, material, lambda: after, tester, tolerance)
            if place is not None:
                findings.append(ReplayFinding(ReplayKind.HOLDER, move.cut, place))
            boxed, exact = boxed + tester.boxed, exact + tester.exact
        material = after
    return Replay(tuple(findings), tuple(material), len(moves), boxed + part.boxed, exact + part.exact, failed)
