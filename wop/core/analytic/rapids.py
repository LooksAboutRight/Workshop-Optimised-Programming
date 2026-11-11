"""The ways between the cuts of a roughing block (X12: a rapid keeps one clearance from the material, every move closer to it is a feed
move): the rise out of the clearance, the rapid legs, the retreat back along the cut before when the tool is in a notch, the long way out
beyond the stock when nothing else is free, and the first and last move of the block. `clear_way` is the same for moves outside the cut
list (the finishing pass, facing)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..constants import CUT_END_SNAP_MM, GEOMETRY_TOLERANCE_MM
from ..geometry import LineSegment, Point, Segment
from ..geometry.intersect import fraction_along
from ..geometry.distance import distance_to_segment
from ..geometry.chains import Loop, loops_box, reversed_segment, split_at
from ..geometry.contacts import first_free, free_all_along
from .cut_list import Cut, CutKind
from ..geometry.penetration import RegionIndex, blocked_by_part
from ..geometry.tool_edges import grown_loops


@dataclass(frozen=True)
class RapidTool:
    """The tool as the ways between the cuts see it."""
    real: list  # the tool (its edge loops)
    grown: list  # the tool grown by the clearance: a rapid keeps that room from the material (X12)
    clearance: float
    free: tuple[int, int] = (1, 1)  # the free side along X and along Z (`Frame.free`): the lane over the material lies only that way

    @staticmethod
    def of(real: list, clearance: float, free: tuple[int, int] = (1, 1)) -> RapidTool:
        return RapidTool(real, grown_loops(real, clearance), clearance, free)


UP_OR_FRONT = ((1.0, 0.0), (0.0, 1.0))  # the directions the tool rises out of the clearance in: along X or along Z, whichever is nearer


def leg_free(a: Point, b: Point, tool: list, stock: RegionIndex, tolerance: float) -> bool:
    """True when the whole tool (its tip going from a to b) penetrates nothing of the stock: a rapid does not cut."""
    length = a.distance_to(b)
    if length <= GEOMETRY_TOLERANCE_MM:
        return True
    vector = ((b.x - a.x) / length, (b.z - a.z) / length)
    return free_all_along(tool, stock, a, vector, length, tolerance)


def _legs(here: Point, target: Point, tool: list, stock: RegionIndex, lane: float) -> list[Segment] | None:
    """Rapid legs from `here` to `target` on which `tool` penetrates nothing of the stock: the straight line, one of the two ways round the
    corner (X first, Z first), or up to the lane above the stock, along it and down. None when none is free."""
    for via in ([], [Point(here.x, target.z)], [Point(target.x, here.z)], [Point(lane, here.z), Point(lane, target.z)]):
        points = [here, *via, target]
        if all(leg_free(a, b, tool, stock, CUT_END_SNAP_MM) for a, b in zip(points, points[1:])):  # a rapid may stand a few thousandths inside: the end of a cut was moved onto the contour
            return [LineSegment(a, b) for a, b in zip(points, points[1:]) if a.distance_to(b) > GEOMETRY_TOLERANCE_MM]
    return None


def _clear_above(place: Point, grown: list, real: list | None, stock: RegionIndex, lane: float, away: tuple[float, float] = (1.0, 0.0)) -> Point | None:
    """The first place from `place` in the direction `away` (straight up, larger X; or towards the front, larger Z) where the grown tool is
    clear of the stock (exact: from the contacts along the move), when the real tool may go there (`real` None: not tested, the move may
    cut); `place` itself when it is clear; None when there is none before `lane` (the coordinate along `away`)."""
    if not blocked_by_part(grown, stock, place, CUT_END_SNAP_MM):
        return place
    length = lane - (place.x if away[0] else place.z)
    if length <= GEOMETRY_TOLERANCE_MM:
        return None
    part = first_free(grown, stock, place, away, length, CUT_END_SNAP_MM)
    if part is None:
        return None
    low, high = part
    for rise in (min(low + CUT_END_SNAP_MM, (low + high) / 2), (low + high) / 2):  # a hair into the free stretch: at its very start the tool touches
        up = Point(place.x + away[0] * rise, place.z + away[1] * rise)
        if not blocked_by_part(grown, stock, up, CUT_END_SNAP_MM):
            return up if real is None or leg_free(place, up, real, stock, CUT_END_SNAP_MM) else None
    return None


def _nearest_clear(place: Point, grown: list, real: list | None, stock: RegionIndex, lanes: tuple[float, float], sides: tuple) -> Point | None:
    """The nearest of the clear places of `_clear_above` over the directions `sides` (`lanes`: the X and the Z to search up to). A later
    direction is only searched as far as the nearest place found so far."""
    best = None
    for away in sides:
        lane = lanes[0] if away[0] else lanes[1]
        if best is not None:
            lane = min(lane, (place.x if away[0] else place.z) + place.distance_to(best))
        up = _clear_above(place, grown, real, stock, lane, away)
        if up is not None and (best is None or place.distance_to(up) < place.distance_to(best)):
            best = up
    return best


def _rapid(
    here: Point, target: Point, tool: RapidTool, stock_loops: list[Loop], down_cuts: bool = False,
) -> tuple[list[Segment], list[Segment], list[Segment]] | None:
    """The way from `here` to `target` as (feed moves, rapid moves, feed moves), or None. The user's rules (2026-10-22): a rapid keeps the
    clearance from the material, and every move closer to it than one clearance is a feed move (X12). Where the tool stands within the
    clearance (the end of a cut) it first rises in X, at feed, to the first place where the grown tool is clear (`_clear_above`, the rise
    tested with the real tool); the rapid legs are tested with the tool grown by the clearance; a target on the material is reached by a
    rapid to the first clear place above it and a feed move down. Only when no such way is free the way is planned with the real tool, and
    then all of it at feed (it touches no material, but keeps no room). The tool rises and comes down along X or along Z, whichever is
    nearer; the lane over the material lies on the free side only, never towards the chuck. `down_cuts`: the feed move down to `target` may
    cut (the start of a finishing pass in the allowance), so it is not tested with the real tool."""
    if here.is_close(target, GEOMETRY_TOLERANCE_MM):
        return [], [], []
    real, grown, clearance, sx = tool.real, tool.grown, tool.clearance, tool.free[0]
    stock = RegionIndex(stock_loops)
    box = loops_box(stock_loops) if stock_loops else None
    rise = box[2] + clearance if box else max(here.x, target.x)  # above the highest material: as far as the rise out of the clearance looks
    lanes = (rise + clearance, (box[3] if box else max(here.z, target.z)) + 2 * clearance)
    lane = ((box[2] if sx > 0 else box[0]) + sx * clearance) if box else (max if sx > 0 else min)(here.x, target.x)  # beyond the material on the free side
    begin, lift = here, []
    up = _nearest_clear(here, grown, real, stock, lanes, UP_OR_FRONT)
    if up is not None and not up.is_close(here):
        begin, lift = up, [LineSegment(here, up)]
    end, down = target, []
    above = _nearest_clear(target, grown, None if down_cuts else real, stock, lanes, UP_OR_FRONT)
    if above is not None and not above.is_close(target):
        end, down = above, [LineSegment(above, target)]
    legs = _legs(begin, end, grown, stock, lane + sx * clearance)
    if legs is not None:
        return lift, legs, down
    legs = _legs(here, target, real, stock, lane)
    return (legs, [], []) if legs is not None else None


def clear_way(
    here: Point, target: Point, tool: list, material: list[Loop], clearance: float, down_cuts: bool = False,
) -> tuple[list[Segment], list[Segment], list[Segment]] | None:
    """The way of the rapids between the cuts (`_rapid`, X12) for moves made outside the cut list (the finishing pass): (feed moves, rapid
    moves, feed moves) from `here` to `target` on `material`, rising and coming down along X or Z, whichever is nearer."""
    return _rapid(here, target, RapidTool.of(tool, clearance), material, down_cuts)


def _trimmed(entry: tuple[Segment, ...], place: Point) -> tuple[Segment, ...] | None:
    """The way in from `place` on, when the tool already stands on it (the end of the cut before lies on the way in): the rest of the path from
    there. None when `place` is not on the path."""
    for index, piece in enumerate(entry):
        if distance_to_segment(place, piece) <= CUT_END_SNAP_MM:
            rest = [] if place.is_close(piece.end, CUT_END_SNAP_MM) else [split_at(piece, [fraction_along(piece, place)])[-1]]
            path = [*rest, *entry[index + 1:]]
            begins = path[0].start if path else piece.end
            if not place.is_close(begins):  # a few thousandths off the way in: a short feed move onto it, so the path has no jump
                path.insert(0, LineSegment(place, begins))
            return tuple(path)
    return None


def _leaving(before: Cut) -> list[tuple[Point, list[Segment]]]:
    """The places the tool can go back to, nearest first, with the moves that take it there: the path of the cut before, backwards (a dip pass,
    or the ride, the line and the way in), each piece reversed. These moves were cut by the tool itself, so the way is free."""
    trail = list(before.ride) if before.kind is CutKind.DIP else [*before.entry, LineSegment(before.start, before.end), *before.ride]
    trail = [piece for piece in trail if piece.length > GEOMETRY_TOLERANCE_MM]  # a cut that begins where it ends has no line
    here = trail[-1].end if trail else before.end
    found, moves = [(here, [])], []
    for piece in reversed(trail):
        moves = [*moves, reversed_segment(piece)]
        found.append((piece.start, list(moves)))
    return found


def _way(
    places: list[tuple[Point, list[Segment]]], entry: tuple[Segment, ...], start: Point, tool: RapidTool, material: list[Loop],
) -> tuple[tuple[Segment, ...], tuple[Segment, ...], tuple[Segment, ...]] | None:
    """The way from the first of `places` (nearest first, each with the moves that take the tool back to it) to the start of a cut: the (way in,
    retreat, rapid) for the first place that works, or None. Where the tool already stands on the way in only the rest of it is kept."""
    for place, retreat in places:
        if entry:
            rest = _trimmed(entry, place)
        elif place.is_close(start, CUT_END_SNAP_MM):  # the tool is there, a few thousandths at most: a short feed move closes the path
            rest = () if place.is_close(start) else (LineSegment(place, start),)
        else:
            rest = None
        if rest is not None:
            return rest, tuple(retreat), ()
        found = _rapid(place, entry[0].start if entry else start, tool, material)
        if found is not None:
            lift, rapid, down = found
            return (*down, *entry), (*retreat, *lift), tuple(rapid)
    return None


def connect_cuts(
    cuts: list[Cut], snapshots: dict[int, list[Loop]], tool: RapidTool, stock: list[Loop], begin: Point | None, finish: Point | None,
) -> tuple[list[Cut], tuple[Segment, ...], tuple[Segment, ...], int]:
    """Every cut gets its way from the cut before (a joined one goes on where the one before ended; the first begins at the point `begin` where
    the block starts, tested against the stock): where the tool already stands on the way in, only the rest of it is kept; otherwise a rapid
    from the end of the cut before to where the way in begins (tested against the material after the cut before), and when none is free from
    there the tool first goes back along the path it came by (`retreat`, feed moves) to a place from which one is. The block ends with the
    same from the last cut to the point `finish`. Where no free way is found, the tool takes the long way (`_long_way`: out beyond the stock,
    along and in; the checker says whether it is free). Returns the cuts, the retreat and the rapid of the end of the block, and the number
    of places no free way was found for."""
    connected, unconnected = [], 0
    box = loops_box(stock) if stock else (0.0, 0.0, 0.0, 0.0)
    (sx, sz), clearance = tool.free, tool.clearance
    clear = ((box[2] if sx > 0 else box[0]) + sx * clearance, (box[3] if sz > 0 else box[1]) + sz * clearance)  # beyond the stock on the free sides
    for index, listed in enumerate(cuts):
        if listed.joined or (index == 0 and begin is None):
            connected.append(listed)
            continue
        before = cuts[index - 1] if index else None
        places = _leaving(before) if before is not None else [(begin, [])]
        way = _way(places, listed.entry, listed.start, tool, snapshots[id(before)] if before is not None else stock)
        unconnected += way is None
        if way is None:
            target = listed.entry[0].start if listed.entry else listed.start
            material = snapshots[id(before)] if before is not None else stock
            connected.append(replace(listed, rapid=_long_way(places[0][0], target, clear, tool, material)))
        else:
            connected.append(replace(listed, entry=way[0], retreat=way[1], rapid=way[2]))
    leave = _way(_leaving(cuts[-1]), (), finish, tool, snapshots[id(cuts[-1])]) if cuts and finish is not None else None
    if cuts and finish is not None and leave is None:
        unconnected += 1
        leave = ((), (), _long_way(_leaving(cuts[-1])[0][0], finish, clear, tool, snapshots[id(cuts[-1])]))
    return connected, (leave[1] if leave else ()), (leave[2] if leave else ()), unconnected


def _long_way(
    here: Point, target: Point, clear: tuple[float, float], tool: RapidTool, material: list[Loop],
) -> tuple[Segment, ...]:
    """The rapids out beyond the stock, along and in to the target, where no free way was found: out in X (`clear[0]`) or in front in Z
    (`clear[1]`), on the free sides, the first that is free of the material; when neither is, the one out in X (the checker reports it)."""
    beyond_x = max if tool.free[0] > 0 else min
    beyond_z = max if tool.free[1] > 0 else min
    out_x = [here, Point(beyond_x(here.x, clear[0]), here.z), Point(beyond_x(target.x, clear[0]), target.z), target]
    out_z = [here, Point(here.x, beyond_z(here.z, clear[1])), Point(target.x, beyond_z(target.z, clear[1])), target]
    stock = RegionIndex(material)
    for corners in (out_x, out_z):
        if all(leg_free(a, b, tool.real, stock, CUT_END_SNAP_MM) for a, b in zip(corners, corners[1:])):
            break
    else:
        corners = out_x
    return tuple(LineSegment(a, b) for a, b in zip(corners, corners[1:]) if not a.is_close(b))
