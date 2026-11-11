"""The cut list of the analytic planner as the moves of the machine: `Rapid`, `LinearMove` and `ArcMove`.

The order is the order of the cut list (`roughing_cuts.Cut`): for every cut the retreat (feed moves back along the path the tool came by), the
rapids, the way in (with the plunge feed where it comes down at a wall or straight into the material, the feed otherwise), the line and its ride; at the end of the block
the retreat and the rapid to the safe point. The cut list is one continuous path (tested), so every move starts where the one before ended.
The finishing pass (`finishing_pass`) follows after it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import CHAIN_SNAP_MM, COMPENSATION_LEAD_MARGIN_MM, GEOMETRY_TOLERANCE_MM
from ..geometry.offset import tangent_at_start
from ..geometry import ArcSegment, LineSegment, Point, Segment
from ..nose_compensation import reference_path
from ..program_model.operations import ArcMove, CompensationSide, LinearMove, MoveRole, Rapid
from ..tooling.tool import Tool
from ..tooling.tool_reference import nose_circle
from ..geometry.chains import ChainError, Loop
from .cut_list import RoughingCuts
from .rapids import clear_way
from ..geometry.removal import cut
from .tool_outline import tool_loops


def _feed_moves(pieces: tuple[Segment, ...] | list[Segment], feed: float) -> list:
    return [
        ArcMove(piece.end, piece.center, piece.direction, feed) if isinstance(piece, ArcSegment) else LinearMove(piece.end, feed)
        for piece in pieces
    ]


def cut_operations(first: RoughingCuts, feed: float, plunge_feed: float) -> list:
    """The moves of the roughing, from where the block begins (the start of the first rapid) to the safe point. Where a feed move does not
    begin exactly where the tool stands (two walks met within the snap distance), a short straight feed move to its start comes first: an arc
    must begin on its circle."""
    operations: list = []
    here = first_point(first)

    def feeds(pieces, rate):
        nonlocal here
        for piece in pieces:
            if here is not None and not here.is_close(piece.start, GEOMETRY_TOLERANCE_MM):
                operations.append(LinearMove(piece.start, rate))
            operations.extend(_feed_moves([piece], rate))
            here = piece.end

    def rapids(pieces):
        nonlocal here
        for piece in pieces:
            operations.append(Rapid(piece.end))
            here = piece.end

    for listed in first.cuts:
        feeds(listed.retreat, feed)
        rapids(listed.rapid)
        feeds(listed.entry, feed if listed.source.open_high and not listed.plunged else plunge_feed)
        if not listed.start.is_close(listed.end):
            feeds([LineSegment(listed.start, listed.end)], feed)
        feeds(listed.ride, feed)
    feeds(first.leave_retreat, feed)
    rapids(first.leave_rapid)
    return operations


def first_point(first: RoughingCuts) -> Point | None:
    """Where the moves begin (the tool stands there before the first one)."""
    for listed in first.cuts:
        for pieces in (listed.retreat, listed.rapid, listed.entry):
            if pieces:
                return pieces[0].start
        return listed.start
    return None


def path_of(operations: list, start: Point) -> list[Segment]:
    """The moves as lines and arcs (for the tests and the pictures)."""
    found: list[Segment] = []
    here = start
    for operation in operations:
        if isinstance(operation, ArcMove):
            found.append(ArcSegment(here, operation.end, operation.center, operation.direction))
        else:
            found.append(LineSegment(here, operation.end))
        here = operation.end
    return found


def _rebuilt(way: tuple[list[Segment], list[Segment], list[Segment]], feed: float) -> list:
    lift, rapid, down = way
    return [*_feed_moves(lift, feed), *(Rapid(piece.end) for piece in rapid), *_feed_moves(down, feed)]


@dataclass(frozen=True)
class FinishingJob:
    """What the finishing pass of a block needs besides the material and where it begins and ends."""
    path: list[Segment]  # the nominal contour, from the front to the chuck
    tool: Tool  # its tip at its origin
    outside: bool
    compensate: bool  # a pass for a controller with cutter compensation (lead-in, lead-out, the contour point on every move)
    feed: float  # the finishing feed
    clearance: float  # the project's clearance (X12)
    clear_x: float  # the radius beyond the material the tool goes out to where no free way is found


def finishing_pass(job: FinishingJob, material: list[Loop], start: Point, finish: Point) -> list:
    """The finishing pass (the user's rule, 2026-10-23): the tool path along the whole contour (`reference_path`: the nose follows it) at the
    finishing feed, through the air too, never shortened and never left; from where the tool stands (`start`) to the safe point (`finish`).
    The way there and away are the rapids between the cuts (X12, `clear_way`): they keep the clearance from the material (`material` before
    the pass, what it leaves for the way away), the last stretch onto the material and the first one away from it are feed moves; where no
    such way is found, the tool goes out to `clear_x` first. `compensate`: a pass for a controller with cutter compensation: a lead-in along
    the first contour piece and a lead-out away from the part, the nose radius plus a margin long, and on every move its point of the nominal
    contour (the post writes those). Where the nose cannot follow the contour the checker reports what it does (`nose_follow.py` names the
    nose radius that would)."""
    path, tool, outside, compensate, feed, clearance = job.path, job.tool, job.outside, job.compensate, job.feed, job.clearance
    pieces = reference_path(path, tool, outside)
    sign = 1 if outside else -1
    loops = tool_loops(tool)
    moves: list = []
    if compensate:
        radius, _centre = nose_circle(tool)
        lead = radius + COMPENSATION_LEAD_MARGIN_MM
        first_index, first = pieces[0]
        tx, tz = tangent_at_start(path[first_index])
        begin = Point(max(path[first_index].start.x - tx * lead, 0), path[first_index].start.z - tz * lead)
        side = CompensationSide.RIGHT if outside else CompensationSide.LEFT  # the free side, looking along the travel (X up, Z right)
        moves.append(LinearMove(first.start, feed, path[first_index].start, MoveRole.LEAD_IN, side))
    else:
        begin = pieces[0][1].start
    followed: set[int] = set()
    for index, segment in pieces:
        join = compensate and index in followed  # the pieces after the first of a contour piece are the round joins at outer corners
        followed.add(index)
        nominal = path[index] if compensate and not join else None
        role = MoveRole.JOIN if join else MoveRole.NORMAL
        if isinstance(segment, ArcSegment):
            centre = nominal.center if isinstance(nominal, ArcSegment) else None
            moves.append(ArcMove(segment.end, segment.center, segment.direction, feed, None if nominal is None else nominal.end, centre, role))
        else:
            moves.append(LinearMove(segment.end, feed, None if nominal is None else nominal.end, role))
    end = pieces[-1][1].end
    if compensate:
        moves.append(LinearMove(Point(max(end.x + sign * lead, 0), end.z), feed, role=MoveRole.LEAD_OUT))
        end = moves[-1].end
    way_in = clear_way(start, begin, loops, material, clearance, down_cuts=True)
    head = _rebuilt(way_in, feed) if way_in is not None else _out_and_over(start, begin, job.clear_x, feed)
    try:
        after = cut(material, loops, path_of(moves, begin), CHAIN_SNAP_MM)[0]
    except ChainError:
        after = material  # the way away keeps off the material as it was before the pass
    way_out = clear_way(end, finish, loops, after, clearance)
    tail = _rebuilt(way_out, feed) if way_out is not None else _out_and_over(end, finish, job.clear_x, None)
    return [*head, *moves, *tail]


def _out_and_over(here: Point, target: Point, clear_x: float, feed: float | None) -> list:
    """Out to the clear radius, along Z and in to the target, where no free way was found; the last move is a feed move when `feed` is
    given (the target lies on the material)."""
    found: list = []
    for point in (Point(clear_x, here.z), Point(clear_x, target.z)):
        if not point.is_close(found[-1].end if found else here):
            found.append(Rapid(point))
    if not target.is_close(found[-1].end if found else here):
        found.append(LinearMove(target, feed) if feed is not None else Rapid(target))
    return found
