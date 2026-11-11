"""A walk of the tool tip along the part: up the wall, over the nose, as the tool stays in touch with it.

The curves of `tip_curves.py` are the places where the tool touches the part. From a place on such a curve the walk follows the curve in the
direction that leads up (to the height `goal`), as far as the tool may stand (the planning tool penetrates nothing deeper than the
tolerance) and the curve keeps rising. Where it ends (a corner of the part, another contact that comes first) the curves through that place
are searched again and the one that leads highest is taken. So the back of the tool on a sloping wall, the nose on a round corner and a corner of the part
on the edge of the tool are all the same rule. The walk is also the way a tool goes from a place to the start of a plunge.

Where the tool may stand along a piece of a curve is found without a scan: whether the tool penetrates something changes only where a second
contact begins or ends, that is where the piece crosses another contact curve (or one ends on it). The piece is cut at those places and a
test in the middle and at the end of each part says whether the tool may stand there (the end too: past a place where the tool only touches a
piece it goes into it gradually, and in the middle of the part it may still be less deep than the tolerance); the first part where it may not
ends the way, exactly where that part begins. The same holds against the standing stock (its contact curves are made when a piece of the stock is first near a way) and for a
straight move (`contacts.events`).
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass

from ..constants import CUT_END_SNAP_MM, FOLLOW_SNAP_MM, GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION, TIP_WALK_MAX_PIECES
from ..curve_walk import locate
from ..geometry import LineSegment, Point, Segment
from ..geometry.intersect import fraction_along, intersections, point_of
from ..geometry.distance import distance_to_segment
from ..geometry.chains import Box, box_of, boxes_meet, crossing_value, loops_box, monotone, reversed_segment, split_at
from ..geometry.contacts import events, free_intervals
from ..geometry.penetration import RegionIndex, blocked_by_material, blocked_by_part, penetrations
from .tip_curves import contact_curves, piece_curves, tool_features
from ..geometry.tool_edges import ToolLoop, placed


class TipCurves:
    """The contact curves of a tool and a part, with their boxes."""

    def __init__(self, tool: list[ToolLoop], pieces: list[Segment]) -> None:
        self.curves = contact_curves(tool, pieces)
        self.boxes: list[Box] = [box_of(curve) for curve in self.curves]
        self.span = max((max(x1 - x0, z1 - z0) for x0, z0, x1, z1 in self.boxes), default=0.0)  # longer than any way along the curves

    def near(self, point: Point, slack: float) -> list[Segment]:
        return self.near_box((point.x, point.z, point.x, point.z), slack)

    def near_box(self, box: Box, slack: float) -> list[Segment]:
        return [curve for curve, curve_box in zip(self.curves, self.boxes) if boxes_meet(box, curve_box, slack)]


def tool_box(tool: list[ToolLoop]) -> Box:
    """The box of a tool (its tip at the origin)."""
    return loops_box([[edge.segment for edge in loop] for loop in tool])


class RegionCurves:
    """The contact curves of a tool and a region (the standing stock, the part), made for a piece of the region when it is first near a way:
    the region has many pieces and a way meets only a few of them."""

    def __init__(self, tool: list[ToolLoop], region: RegionIndex) -> None:
        self.edges, self.corners = tool_features(tool)
        self.reach = tool_box(tool)
        self.region = region
        self.made: dict[Segment, list[tuple[Box, Segment]]] = {}

    def near_box(self, box: Box, slack: float) -> list[Segment]:
        """The curves whose boxes meet the box of the tip places: only pieces of the stock that the tool can touch from there make curves."""
        x0, z0, x1, z1 = box
        rx0, rz0, rx1, rz1 = self.reach
        found: list[Segment] = []
        for piece in self.region.near((x0 + rx0, z0 + rz0, x1 + rx1, z1 + rz1), slack):
            if piece not in self.made:
                self.made[piece] = [(box_of(curve), curve) for curve in piece_curves(self.edges, self.corners, piece)]
            found += [curve for curve_box, curve in self.made[piece] if boxes_meet(box, curve_box, slack)]
        return found


Sources = list[TipCurves | RegionCurves]


def marks_along(piece: Segment, sources: Sources) -> list[float]:
    """The fractions along the piece where a contact begins or ends (it crosses a contact curve, or one ends on it), with 0 and 1; marks
    closer to each other than the tolerance are one."""
    found: list[float] = []
    for source in sources:
        for curve in source.near_box(box_of(piece), GEOMETRY_TOLERANCE_MM):
            points = intersections(piece, curve) + [p for p in (curve.start, curve.end) if distance_to_segment(p, piece) <= GEOMETRY_TOLERANCE_MM]
            found += [fraction_along(piece, p) for p in points]
    marks = [0.0]
    for mark in sorted(min(max(f, 0.0), 1.0) for f in found):
        if (mark - marks[-1]) * piece.length > GEOMETRY_TOLERANCE_MM:
            marks.append(mark)
    if (1 - marks[-1]) * piece.length > GEOMETRY_TOLERANCE_MM or len(marks) == 1:
        marks.append(1.0)
    else:
        marks[-1] = 1.0
    return marks


def _from(curve: Segment, at: Point, forward: bool) -> Segment | None:
    """The part of the curve from the place `at` (on it) to its end, or back to its start (the part is turned to run away from `at`)."""
    target = curve.end if forward else curve.start
    if at.is_close(target):
        return None
    parts = split_at(curve, [fraction_along(curve, at)])
    if at.is_close(curve.start if forward else curve.end):
        return curve if forward else reversed_segment(curve)
    part = parts[-1] if forward else parts[0]
    return part if forward else reversed_segment(part)


def _rising(piece: Segment, goal: float, up: int, flat: bool) -> list[Segment]:
    """The beginning of the piece where it keeps rising (or stays level when `flat`), to the height `goal` at the most."""
    kept: list[Segment] = []
    for part in monotone(piece, 0):
        rise = up * (part.end.x - part.start.x)
        if rise < -GEOMETRY_TOLERANCE_MM or (rise <= GEOMETRY_TOLERANCE_MM and not flat):
            break
        if up * (part.end.x - goal) >= 0:
            reach = Point(goal, crossing_value(part, goal, 0))
            head = split_at(part, [fraction_along(part, reach)])[0]
            if head.start.distance_to(head.end) > GEOMETRY_TOLERANCE_MM:
                kept.append(head)
            break
        kept.append(part)
    return kept


def first_blocked(piece: Segment, sources: Sources, blocked: Callable[[Point], bool]) -> Point | None:
    """Where along the piece (a line or an arc) `blocked` begins to hold: the start of the first part between two places where a contact begins
    or ends (`marks_along`) where it holds in the middle or at the end; exact, as the walk. None when it holds nowhere (the start is not tested)."""
    marks = marks_along(piece, sources)
    for low, high in zip(marks, marks[1:]):
        if blocked(point_of(piece, (low + high) / 2)) or blocked(point_of(piece, high)):
            return point_of(piece, low)
    return None


def _free(
    parts: list[Segment], tool: list[ToolLoop], keep: RegionIndex, tolerance: float, curves: TipCurves, stock: RegionCurves | None = None,
) -> list[Segment]:
    """The beginning of the parts where the tool may stand, up to the exact place where it stops. With `stock` (the material that stands)
    the edges that are not cutting may not be in it either: a holder does not cut."""

    def blocked(place: Point) -> bool:
        return blocked_by_part(tool, keep, place, tolerance) or (stock is not None and blocked_by_material(tool, stock.region, place, tolerance))

    sources: Sources = [curves] if stock is None else [curves, stock]
    kept: list[Segment] = []
    for part in parts:
        marks = marks_along(part, sources)
        for low, high in zip(marks, marks[1:]):
            if blocked(point_of(part, (low + high) / 2)) or blocked(point_of(part, high)):
                if low > 0:
                    kept.extend(split_at(part, [low])[:1])
                return kept
        kept.append(part)
    return kept


def _walked(way: Segment, avoid: list[Segment]) -> bool:
    """True when the way runs along a piece of the path already walked (the way back)."""
    middle = point_of(way, MIDPOINT_FRACTION)
    return any(distance_to_segment(middle, piece) <= GEOMETRY_TOLERANCE_MM for piece in avoid)


def _progress(here: Point, end: Point, up: int, flat: bool) -> float:
    """How far the way leads: up, or when `flat` (the walk over a bump) down and back along the line, so a level top counts."""
    return up * (end.x - here.x) + ((here.z - end.z) if flat else 0)


@dataclass(frozen=True)
class _Walk:
    """What stays the same all along a walk: the contact curves, the planning tool, the part it keeps off and the tolerance."""

    curves: TipCurves
    tool: list[ToolLoop]
    keep: RegionIndex
    tolerance: float


def _best(walk: _Walk, here: Point, goal: float, up: int, flat: bool, avoid: list[Segment]) -> list[Segment]:
    """From the place `here`, the way along one curve that leads farthest (empty when no curve leads on from here). A curve that cannot
    lead farther than the best one so far, even if the tool could stand all along it, is not tested (not with `flat`: there a way can
    lead back, so its end is no bound)."""
    best: list[Segment] = []
    reached = 0.0
    for curve in walk.curves.near(here, FOLLOW_SNAP_MM):
        place = locate([curve], here, FOLLOW_SNAP_MM)
        if place is None:
            continue
        for forward in (True, False):
            piece = _from(curve, place.point, forward)
            if piece is None:
                continue
            rising = _rising(piece, goal, up, flat)
            if not rising or (not flat and _progress(here, rising[-1].end, up, flat) <= max(reached, GEOMETRY_TOLERANCE_MM)):
                continue
            way = _free(rising, walk.tool, walk.keep, walk.tolerance, walk.curves)
            if way and not _walked(way[0], avoid) and _progress(here, way[-1].end, up, flat) > max(reached, GEOMETRY_TOLERANCE_MM):
                best, reached = way, _progress(here, way[-1].end, up, flat)
    return best


def _slide(curves: TipCurves, here: Point, heading: tuple[float, float], tool: list[ToolLoop], keep: RegionIndex, tolerance: float) -> Point | None:
    """Where the tip, going on from `here` in the direction `heading`, first touches the part (the end of the free stretch from `here`, found
    exactly): the end of a line that stopped at a wall before the real tool (its rounded nose) touched it. `here` itself when the tool is
    blocked at once; None when it touches nothing."""
    free = free_intervals(tool, keep, here, heading, curves.span, tolerance, 0.0)
    reach = next((end for begin, end in free if begin <= GEOMETRY_TOLERANCE_MM), 0.0)
    if curves.span - reach <= GEOMETRY_TOLERANCE_MM:
        return None
    return Point(here.x + heading[0] * reach, here.z + heading[1] * reach)


def tip_walk(
    curves: TipCurves, start: Point, goal: float, up: int, tool: list[ToolLoop], keep: RegionIndex, tolerance: float,
    heading: tuple[float, float] | None = None, flat: bool = False, avoid: list[Segment] | None = None,
) -> list[Segment]:
    """From the tip place `start` (the planning `tool` touching the part) up to the radius `goal` (`up` is +1 when up means larger radius), along
    the contact curves, as far as the tool may stand. When `start` is on no curve (a line that ended at the wall, the tool not yet touching) the
    tip first goes on in the direction `heading` to the first one. With `flat` (the walk over the top of a bump, down to `goal` on the other side: `up` is
    -1) a level stretch leads on too, and the way back along `avoid` (the way up) is not taken. Empty when no curve leads up from there. The first piece may start a little (up to `CUT_END_SNAP_MM`) away from `start`: the caller
    moves the end of its line there."""
    walk = _Walk(curves, tool, keep, tolerance)
    on_a_curve = any(locate([curve], start, FOLLOW_SNAP_MM) for curve in curves.near(start, FOLLOW_SNAP_MM))
    if heading is not None and not on_a_curve:
        return _slid_and_walked(walk, start, goal, up, heading, flat, avoid)
    path = _walked_from(walk, start, goal, up, flat, list(avoid or []))
    if not path and heading is not None:  # the tool touches only what leads nowhere (the floor under the end of a line): on to the wall first
        return _slid_and_walked(walk, start, goal, up, heading, flat, avoid)
    return path


def _slid_and_walked(
    walk: _Walk, start: Point, goal: float, up: int, heading: tuple[float, float], flat: bool, avoid: list[Segment] | None,
) -> list[Segment]:
    """The tip goes on from `start` in the direction `heading` to the first place where the tool meets the part (`_slide`), then walks."""
    touch = _slide(walk.curves, start, heading, walk.tool, walk.keep, walk.tolerance)
    if touch is None:
        return []
    path: list[Segment] = [LineSegment(start, touch)] if start.distance_to(touch) > GEOMETRY_TOLERANCE_MM else []
    return _walked_from(walk, touch, goal, up, flat, list(avoid or []), path)


def _walked_from(
    walk: _Walk, here: Point, goal: float, up: int, flat: bool, walked: list[Segment], before: list[Segment] | None = None,
) -> list[Segment]:
    """The way so far (`before`) and on along the contact curves from `here` (see `tip_walk`): a gap to the way so far is joined, not bridged."""
    path: list[Segment] = list(before or [])
    for _ in range(TIP_WALK_MAX_PIECES):
        if up * (here.x - goal) >= -GEOMETRY_TOLERANCE_MM:
            break
        way = _best(walk, here, goal, up, flat, walked)
        if not way:
            break
        if not here.is_close(way[0].start):
            if path:  # a gap of a few thousandths between two curves: the straight piece next to it is moved, no tiny move (see `_joined`)
                path, way = _joined(path, here, way)
            elif here.distance_to(way[0].start) > CUT_END_SNAP_MM:  # a first gap that small is left to the caller, who moves the end of its line
                path.append(LineSegment(here, way[0].start))
        path += way
        walked += way
        here = way[-1].end
    return path


def _clear_part(piece: Segment, tool: list[ToolLoop], stock: RegionCurves, tolerance: float) -> list[Segment] | None:
    """The beginning of the piece up to the first place where the tool is clear of the stock (exact: where its last contact with the stock
    ends), [] when that is the start of the piece, None when the tool is in the stock along the whole piece."""
    marks = marks_along(piece, [stock])
    for low, high in zip(marks, marks[1:]):
        if not penetrations(tool, stock.region, point_of(piece, (low + high) / 2), tolerance):
            return split_at(piece, [low])[:1] if low > 0 else []
    return None


def _joined(walked: list[Segment], place: Point, way: list[Segment]) -> tuple[list[Segment], list[Segment]]:
    """The way so far and the next pieces, made to meet: a gap up to the snap distance is closed by moving the end of the last straight piece
    (or the start of the first one), a bigger one by a connecting line, so no sliver of a few thousandths of a millimetre is left in the path."""
    if place.distance_to(way[0].start) <= CUT_END_SNAP_MM:
        if walked and isinstance(walked[-1], LineSegment) and walked[-1].end.is_close(place):
            return [*walked[:-1], LineSegment(walked[-1].start, way[0].start)], way
        if isinstance(way[0], LineSegment):
            return walked, [LineSegment(place, way[0].end), *way[1:]]
    return [*walked, LineSegment(place, way[0].start)], way


def _straight_out(
    place: Point, away: tuple[float, float], length: float, tool: list[ToolLoop], keep: RegionIndex, stock: RegionIndex, tolerance: float,
    first_tolerance: float,
) -> list[Segment] | None:
    """A straight move from `place` in the direction `away` to the first place where the tool is clear of the stock, when the tool may stand all
    along it ([] when it is clear at `place`). None when it meets the part (or a holder meets the stock) first, or is not clear within `length`.
    Exact: the move is cut where a contact with the part or the stock begins or ends (`contacts.events`), a test in the middle and at the end of each part.
    The first part is tested against the part with `first_tolerance`: the start of a cut may lie a few thousandths inside it."""
    base = placed(tool, place)
    marks = [0.0]
    for at in sorted(events(base, keep, away, length) + events(base, stock, away, length)):
        if at - marks[-1] > GEOMETRY_TOLERANCE_MM:
            marks.append(min(at, length))
    for low, high in zip(marks, marks[1:]):
        middle = (low + high) / 2
        probe, end = (Point(place.x + away[0] * at, place.z + away[1] * at) for at in (middle, high))
        part_tolerance = first_tolerance if low == 0 else tolerance
        if any(blocked_by_part(tool, keep, at, part_tolerance) or blocked_by_material(tool, stock, at, tolerance) for at in (probe, end)):
            return None
        if not penetrations(tool, stock, probe, tolerance):
            return [LineSegment(place, Point(place.x + away[0] * low, place.z + away[1] * low))] if low > GEOMETRY_TOLERANCE_MM else []
    return None


def _clear_length(place: Point, away: tuple[float, float], tool: list[ToolLoop], stock: RegionIndex) -> float:
    """How far the tool goes from `place` in the direction `away` until its box is one tool size beyond the box of the stock: the first place
    where it is clear of the stock comes before that, and the last part of the move lies wholly outside (its middle is clear)."""
    x_low, z_low, x_high, z_high = loops_box(stock.loops)
    t_x_low, t_z_low, t_x_high, t_z_high = tool_box(tool)
    lengths = []
    for along, here, low, high, t_low, t_high in ((away[0], place.x, x_low, x_high, t_x_low, t_x_high), (away[1], place.z, z_low, z_high, t_z_low, t_z_high)):
        if along > GEOMETRY_TOLERANCE_MM:
            lengths.append((high - here - t_low + (t_high - t_low)) / along)
        elif along < -GEOMETRY_TOLERANCE_MM:
            lengths.append((here + t_high - low + (t_high - t_low)) / -along)
    return max(min(lengths, default=0.0), 0.0)


def way_out(
    curves: TipCurves, start: Point, tool: list[ToolLoop], keep: RegionIndex, stock: RegionIndex, tolerance: float,
    heading: tuple[float, float] | None = None, away: tuple[float, float] | None = None,
) -> list[Segment] | None:
    """The shortest way from the tip place `start` along the contact curves to a place where the tool is clear of the standing stock (it may
    still touch the part): the way a tool takes out of a pocket or out from under a lip, up, sideways or down, wherever the curves lead. The
    tool (the planning copy) may stand on every place of the way: it penetrates no part, and its edges that are not cutting stay out of the
    stock. The way is walked backwards from the cut; the cut then goes along it the other way round. [] when the tool is clear at `start`;
    None when `start` is not a place to stand or no way leads out (a tool wider than the opening of the notch it stands in). When `start`
    touches nothing, the tip first goes on in `heading` to the first contact (or out into the air). Where the contact ends (the top of a wall)
    and the tool is still in the stock, it may go straight on in the direction `away` (out of the pocket) to the first place where it is clear."""

    # the start of a cut may lie a few thousandths inside the part: the end of a stretch was put on the end of the wanted line
    if blocked_by_part(tool, keep, start, max(tolerance, CUT_END_SNAP_MM)) or blocked_by_material(tool, stock, start, tolerance):
        return None
    if not penetrations(tool, stock, start, tolerance):
        return []
    stock_curves = RegionCurves(tool, stock)
    first: list[Segment] = []
    here = start
    if not any(locate([curve], start, FOLLOW_SNAP_MM) for curve in curves.near(start, FOLLOW_SNAP_MM)):
        if heading is None:
            return None
        touch = _slide(curves, start, heading, tool, keep, tolerance)
        reach = touch if touch is not None else Point(start.x + heading[0] * curves.span, start.z + heading[1] * curves.span)
        run = LineSegment(start, reach)
        for part in _free([run], tool, keep, tolerance, curves, stock_curves):
            air = _clear_part(part, tool, stock_curves, tolerance)
            if air is not None:
                return [*first, *air]
            first.append(part)
        if touch is None or not first or not first[-1].end.is_close(touch):
            return None
        here = touch
    order = 0
    queue: list[tuple[float, int, Point, tuple[Segment, ...]]] = [(0.0, order, here, tuple(first))]
    seen = {(round(here.x / FOLLOW_SNAP_MM), round(here.z / FOLLOW_SNAP_MM))}
    visits = 0
    while queue and visits < TIP_WALK_MAX_PIECES:
        cost, _order, place, path = heapq.heappop(queue)
        visits += 1
        if away is not None:
            length = _clear_length(place, away, tool, stock)
            leave = _straight_out(place, away, length, tool, keep, stock, tolerance, max(tolerance, CUT_END_SNAP_MM) if place.is_close(start) else tolerance)
            if leave is not None:
                return [*path, *leave]
        for curve in curves.near(place, FOLLOW_SNAP_MM):
            found = locate([curve], place, FOLLOW_SNAP_MM)
            if found is None:
                continue
            for forward in (True, False):
                piece = _from(curve, found.point, forward)
                if piece is None:
                    continue
                way = _free([piece], tool, keep, tolerance, curves, stock_curves)
                walked = list(path)
                if way and not place.is_close(way[0].start):
                    walked, way = _joined(walked, place, way)
                length = cost
                for part in way:
                    air = _clear_part(part, tool, stock_curves, tolerance)
                    if air is not None:
                        return [*walked, *air]
                    walked.append(part)
                    length += part.length
                if not way:
                    continue
                end = way[-1].end
                key = (round(end.x / FOLLOW_SNAP_MM), round(end.z / FOLLOW_SNAP_MM))
                if key not in seen:
                    seen.add(key)
                    order += 1
                    heapq.heappush(queue, (length, order, end, tuple(walked)))
    return None


def free_run(curves: TipCurves, piece: Segment, tool: list[ToolLoop], keep: RegionIndex, stock: RegionIndex, tolerance: float) -> list[Segment]:
    """The beginning of a straight or curved move where the tool may stand: it penetrates no part and its edges that are not cutting stay out of the stock."""
    return _free([piece], tool, keep, tolerance, curves, RegionCurves(tool, stock))
