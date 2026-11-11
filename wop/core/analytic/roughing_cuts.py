"""The roughing of a block, end to end: the lines of the wanted plan (step A) shortened to where the planning tool may stand (step B,
`reach.py`), each cut on the material the lines before left (`removal.py`: what the tool sweeps), with the ride up the contour at a wall,
the way over a bump, the passes under the lowest lines (`dips.py`), the way in to every cut and the rapids between them (X12). A neutral
tool cuts like a right-hand one: from the front towards the chuck. Every case is reflected into the one the planner knows by the frame
(`frame.py`): inside, a left-hand tool, lines across X.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..constants import CHAIN_SNAP_MM, CUT_END_SNAP_MM, CUT_JITTER_MM, DIP_MIN_AREA_MM2, GEOMETRY_TOLERANCE_MM, MIDPOINT_FRACTION, WANTED_SPAN_MIN_MM
from ..geometry import ArcSegment, LineSegment, Point, Segment, segments_to_polyline
from ..nose_compensation import reference_path
from ..geometry.intersect import point_of
from ..geometry.distance import distance_to_segment
from ..tooling.tool import Tool
from ..geometry.chains import ChainError, Loop, boxes_meet, loop_area, loops_box, reversed_segment
from ..geometry.contacts import free_intervals
from .cut_limits import column_top, goes_into, holder_stop, taken_on_both_sides
from . import mirror
from .dips import follow_dip, uncovered
from ..geometry.penetration import RegionIndex
from .reach import end_intervals, keep_loops, ride_over, ride_up
from ..geometry.removal import cut
from .tip_walk import TipCurves, free_run, way_out
from ..geometry.tidy import steady_intersection
from ..geometry.tool_edges import placed, translated_segment
from .tool_outline import planning_loops, tool_loops
from .wanted_lines import WantedLine, WantedPlan
from .cut_list import Cut, CutKind, RoughingCuts
from .frame import Frame
from .rapids import RapidTool, connect_cuts, leg_free


@dataclass(frozen=True)
class RoughingJob:
    """What the roughing of a block needs besides the wanted plan and the material, in the real coordinates."""
    path: list[Segment]  # the contour, from the front to the chuck, with its last wall run on to the material
    tool: Tool  # its tip at its origin
    outside: bool
    allowance: float  # the finishing allowance
    clearance_deg: float  # the free angle the back of the tool keeps from the part (the block's 'Back clearance')
    outer: float  # beyond the material and the contour on the free side (outside: a larger radius; inside: towards the axis)
    inner: float  # beyond the part on the other side (outside: below the part; inside: beyond the wall of the bore)
    far_z: float  # beyond the chuck end of the bar
    clearance: float  # the project's clearance (X12)
    begin: Point | None = None  # where the block starts: the first cut is reached from there; None: no first move
    finish: Point | None = None  # where the block ends (the safe point); None: no last move
    across: bool = False  # the lines of the plan run across X
    run_on: float = 0.0  # a line whose low end is open (it runs out of the material) goes on that far into the air (past the centre)
    sequence: Callable | None = None  # the order of the roughing style (`rough_style.style_sequence`); None: level by level from the front


def roughing_cuts(plan: WantedPlan, stock: list[Loop], job: RoughingJob) -> RoughingCuts | None:
    """The lines of the plan cut on the material `stock`; None when there is nothing to do. Every case is planned in the one case the planner
    knows, through the frame (`frame.py`): reflected in, planned, reflected back. The part and its allowance and the path of the tool
    reference are made after the side step (inside: mirrored in X), where X is the radius and the chuck and the axis are where they belong."""
    frame = Frame.of(job.outside, job.across, job.tool)
    side = frame.side
    plan, stock, path, tool = _through(side, "plan", plan), _through(side, "loops", stock), _through(side, "path", job.path), _through(side, "tool", job.tool)
    begin, finish = Frame.point_through(side, job.begin), Frame.point_through(side, job.finish)
    outer, inner = (job.outer, job.inner) if job.outside else (-job.outer, -job.inner)  # inside, mirrored: the bore side is the outside one
    keep_ring = keep_loops(path, True, job.allowance, outer, inner, job.far_z)
    if frame.both_sides:
        keep_ring += mirror.MIRROR_X.loops(keep_ring)  # the part turned over the axis: the far side of a bore
    curve = [segment for _index, segment in reference_path(path, tool, True, job.allowance)]
    work = frame.work
    found = _roughing_cuts(
        _through(work, "plan", plan), _through(work, "loops", stock), _through(work, "loops", keep_ring), _through(work, "path", curve),
        _through(work, "tool", tool), Frame.point_through(work, begin), Frame.point_through(work, finish), job, frame,
    )
    return frame.back(found) if found is not None else None


@dataclass(frozen=True)
class _Planner:
    """What the steps of the cut share, in the one case of the frame."""
    curves: TipCurves  # where the tip of the planning tool touches the part
    planning: list  # the planning tool: the real one with its back edge turned by the free angle
    real: list  # the real tool
    keep: RegionIndex  # the part and its allowance
    tolerance: float
    clearance: float
    frame: Frame


def _through(flips, kind: str, value):
    """`value` reflected by every flip in turn (`kind`: the method of `mirror.Flip` for its type)."""
    for flip in flips:
        value = getattr(flip, kind)(value)
    return value


def _roughing_cuts(
    plan: WantedPlan, stock: list[Loop], keep_ring: list[Loop], curve: list[Segment], tool: Tool, begin: Point | None, finish: Point | None,
    job: RoughingJob, frame: Frame,
) -> RoughingCuts | None:
    """`roughing_cuts` in the one case the planner knows, with the part and its allowance (`keep_ring`) and the path of the tool reference along
    the contour (`curve`) already made, all in the one case of the frame (`frame` only says where the axis and the free sides are)."""
    if not plan.lines:
        return None
    run = _Roughing(plan, stock, keep_ring, curve, tool, job, frame)
    run.cut_the_lines()
    run.cut_the_dips()
    run.cut_the_left_out_again()
    run.snapshot_the_dips()
    return run.result(begin, finish)


def _end_on_ride(end: Point, ride: list[Segment], level: float) -> tuple[Point, list[Segment]]:
    """The end of a line and its ride up, made to meet: the ride may begin a few thousandths from where the wanted stretch ended."""
    if not ride or not GEOMETRY_TOLERANCE_MM < end.distance_to(ride[0].start) <= CUT_END_SNAP_MM:
        return end, ride
    end = Point(level, ride[0].start.z)  # the line ends where the tool touches the part
    if isinstance(ride[0], LineSegment):  # ... and stays on its level: the ride begins there (a G-code line that is level stays level)
        return end, [LineSegment(end, ride[0].end), *ride[1:]]
    arc = ride[0]  # an arc must begin on its circle: where the circle touches the level (its lowest point), the arc begins there
    bottom = Point(level, arc.center.z)
    if abs(arc.center.x - arc.radius - level) <= GEOMETRY_TOLERANCE_MM and bottom.distance_to(arc.start) <= CUT_END_SNAP_MM:
        return bottom, [ArcSegment(bottom, arc.end, arc.center, arc.direction), *ride[1:]]
    return arc.start, ride  # the line ends where the arc begins


class _Roughing:
    """The roughing of one block while it is made: the lines in the order they are cut, the material as the cuts leave it, the cuts so far.
    The steps are methods and are called in this order: `cut_the_lines`, `cut_the_dips`, `cut_the_left_out_again`, `snapshot_the_dips`, `result`."""

    def __init__(self, plan: WantedPlan, stock: list[Loop], keep_ring: list[Loop], curve: list[Segment], tool: Tool, job: RoughingJob, frame: Frame) -> None:
        self.plan, self.stock, self.keep_ring, self.job = plan, stock, keep_ring, job
        self.axis, self.beside = frame.axis, frame.column_beside_part
        self.tolerance = CHAIN_SNAP_MM
        self.planning, self.real = planning_loops(tool, 1, job.clearance_deg), tool_loops(tool)
        self.keep = RegionIndex(keep_ring)
        self.curves = TipCurves(self.planning, [segment for loop in keep_ring for segment in loop])
        self.planner = _Planner(self.curves, self.planning, self.real, self.keep, self.tolerance, job.clearance, frame)
        self.frame = frame
        self.stats = {"fast": 0, "scan": 0, "failed": 0, "unreachable": 0}
        self.cuts: list[Cut] = []
        self.snapshots: dict[int, list[Loop]] = {}
        self.material, self.removed = stock, []
        # from the free side towards the part, the front first (levels that differ only by rounding are one level)
        self.ordered = sorted(plan.lines, key=lambda l: (-round(l.high.x / GEOMETRY_TOLERANCE_MM), -l.high.z))
        # where the tool may stand, for every line
        self.planned = [end_intervals(self.planning, self.keep, curve, l.high.x, l.low.z, l.high.z, self.tolerance) for l in self.ordered]
        for _intervals, fast in self.planned:
            self.stats["fast" if fast else "scan"] += 1
        keys = [(number, k) for number, (intervals, _fast) in enumerate(self.planned) for k in range(len(intervals))]
        # the stretches with no line under them (of the whole plan)
        self.gaps = dict(zip(keys, uncovered([(self.ordered[n].high.x, *self.planned[n][0][k]) for n, k in keys], self.tolerance)))
        self.done: set[int] = set()
        self.after: dict[tuple[int, int], int] = {}  # where in the list the cuts of a line end, and the top of the material above it
        self.tops: dict[tuple[int, int], float] = {}
        self.shadows: list[tuple[float, float, float]] = []  # (level, low, high) of the stretches left in the material: nothing under them is cut
        # the order of the roughing style
        self.order, self.later = (list(range(len(self.ordered))), set()) if job.sequence is None else job.sequence(self.ordered)
        self.skipped: list[tuple[int, int]] = []  # the stretches not cut: tried once more when the passes are made (the material in front of them may be gone)

    def _leave_out(self, number: int, k: int, level: float, low: float, high: float, retry: bool) -> None:
        """The stretch stays in the material (and nothing under it is cut); at the first try it is tried once more later."""
        self.shadows.append((level, low, high))
        if not retry:
            self.stats["unreachable"] += 1
            self.skipped.append((number, k))

    def _way_in(self, line: WantedLine, start: Point) -> tuple[list[Segment], bool] | None:
        """The way in to the start of a cut and whether it is a plunge into the material; None: no way from the air to the start."""
        planner, material = self.planner, self.material
        # along a sloping wall: the wedge in front of the start is cut on the way
        way_in = _wall_entry(planner, self.ordered, material, line, start, self.axis, self.beside) if not line.open_high else None
        if way_in is None:
            way_in = _entry(planner, RegionIndex(material), start, not line.open_high)
        plunged = way_in is None or goes_into(way_in, self.real, material, self.tolerance)
        if way_in is None:  # at a wall, or where material stands all round (a solid bar inside): straight in at feed, if the tool cuts there
            way_in = _plunge(planner, material, start)
        return None if way_in is None else (way_in, plunged)

    def cut_stretch(self, number: int, k: int, retry: bool) -> None:
        """The stretch `k` of the line `number` cut on the material as it stands; `retry`: the second try, after the passes."""
        line = self.ordered[number]
        level = line.high.x
        tolerance = self.tolerance
        low, high = self.planned[number][0][k]
        if line.open_low and self.job.run_on > GEOMETRY_TOLERANCE_MM and abs(low - line.low.z) <= CUT_END_SNAP_MM:
            low -= self.job.run_on  # out of the material at an open end: on into the air (past the centre)
        start, end = Point(level, high), Point(level, low)
        if any(above > level + tolerance and low < s_high and high > s_low for above, s_low, s_high in self.shadows):
            self._leave_out(number, k, level, low, high, retry)  # under a stretch that stays: cut, it would take both layers at once (deeper than the depth of cut)
            return
        # the top of the material to rough in the column at the end of the line; an open end runs out into the air, so the column is looked at
        # on the air side (a line that ends exactly on a bore wall must not see the wall as material above its end)
        top = column_top(self.material, level, low - 4 * tolerance if line.open_low else low, self.axis, tolerance, self.keep_ring, self.beside)
        # at a wall (or where the tool stopped on the contour) it rides up
        ride = [] if line.open_low else ride_up(self.curves, end, top, 1, self.planning, self.keep, tolerance, (0.0, -1.0))
        end, ride = _end_on_ride(end, ride, level)
        end, ride = holder_stop(start, end, ride, self.real, self.material, tolerance, self.axis, self.beside)
        if not ride and end.distance_to(start) <= WANTED_SPAN_MIN_MM:  # the holder meets material at once: the line stays in the material
            self._leave_out(number, k, level, low, high, retry)
            return
        entry = self._way_in(line, start)
        if entry is None:
            self._leave_out(number, k, level, low, high, retry)
            return
        way_in, plunged = entry
        moves, entries, cut_keys = [LineSegment(start, end), *ride], [Cut(start, end, tuple(ride), line, entry=tuple(way_in), plunged=plunged)], [(number, k)]
        joinable = self.done if number in self.later else self.done | self.later  # a line kept for later is not pulled into a cut made now
        behind = _behind_a_bump(self.ordered, self.planned, joinable, ride, top, self.material, self.planner)
        if behind is not None:  # a bump lower than the line above: over it and on along the same level
            over, other, arrival, low2, ride2 = behind
            self.done.add(other)
            cut_keys.append((other, 0))
            entries[0] = Cut(start, end, (*ride, *over), line, entry=tuple(way_in), plunged=plunged)
            entries.append(Cut(arrival, Point(arrival.x, low2), tuple(ride2), self.ordered[other], joined=True))
            moves += [*over, LineSegment(arrival, Point(arrival.x, low2)), *ride2]
        try:
            after_cut, taken = _cut_with_entry(self.material, self.real, way_in, moves, tolerance)
            after_cut = taken_on_both_sides(after_cut, taken, self.axis, tolerance)
        except ChainError:
            self.stats["failed"] += 1  # the border of the material has a feature at the scale of the tolerance: this line is left out
            self.shadows.append((level, low, high))
            return
        self.material = after_cut
        if behind is None and sum(abs(loop_area(loop)) for loop in taken) < DIP_MIN_AREA_MM2:
            return  # it would take next to nothing (a cusp the lines before left, a sliver of the material handed on): not made
        if retry:
            self.stats["unreachable"] -= 1  # it was counted at the first try
        self.removed += taken
        self.cuts.extend(entries)
        for listed in entries:
            self.snapshots[id(listed)] = self.material  # the material after the cut: what the rapid to the next cut has to keep clear of
        for key in cut_keys:
            self.after[key], self.tops[key] = len(self.cuts), top

    def cut_the_lines(self) -> None:
        """Every stretch of every line, in the order of the style."""
        for number in self.order:
            if number in self.done:
                continue
            self.done.add(number)
            for k in range(len(self.planned[number][0])):
                self.cut_stretch(number, k, False)

    def cut_the_dips(self) -> None:
        """The material left under the lines with no line below: along the contour, down and up again, on what the lines left."""
        tolerance = self.tolerance
        passes = []
        for key, stretches in self.gaps.items():
            for _low, gap_high in stretches:
                level = self.ordered[key[0]].high.x
                start = Point(level, gap_high)
                dip = follow_dip(self.curves, start, level, self.tops[key], self.planning, self.keep, tolerance) if key in self.tops else []
                dip = holder_stop(start, start, dip, self.real, self.material, tolerance, self.axis)[1] if dip else dip
                try:
                    left, dipped = cut(self.material, self.real, dip, tolerance) if dip else (self.material, [])
                except ChainError:
                    self.stats["failed"] += 1
                    continue
                if sum(abs(loop_area(loop)) for loop in dipped) >= DIP_MIN_AREA_MM2:
                    self.material, self.removed = taken_on_both_sides(left, dipped, self.axis, tolerance), self.removed + dipped
                    passes.append((self.after[key], Cut(start, start, tuple(dip), self.ordered[key[0]], CutKind.DIP)))
        for place, _number, dip_cut in sorted(_placed_passes(passes, self.cuts, self.real), key=lambda entry: (-entry[0], -entry[1])):
            self.cuts.insert(place, dip_cut)

    def cut_the_left_out_again(self) -> None:
        """The stretches left out are tried once more, on the material the lines and the passes left, in their order."""
        self.shadows.clear()
        for number, k in sorted(self.skipped, key=lambda entry: (-self.ordered[entry[0]].high.x, -self.planned[entry[0]][0][entry[1]][1])):
            self.cut_stretch(number, k, True)

    def snapshot_the_dips(self) -> None:
        """The material at the start of every pass (a little more than there will be: the rapids are tested on the safe side)."""
        for index, listed in enumerate(self.cuts):
            if listed.kind is CutKind.DIP:
                before = self.snapshots[id(self.cuts[index - 1])]
                try:
                    self.snapshots[id(listed)] = cut(before, self.real, list(listed.ride), self.tolerance)[0]
                except ChainError:
                    self.snapshots[id(listed)] = before

    def result(self, begin: Point | None, finish: Point | None) -> RoughingCuts:
        """The cuts joined by rapids, the tool at the first and the last place, and the counts."""
        job, stats = self.job, self.stats
        cuts, leave_retreat, leave_rapid, unconnected = connect_cuts(
            self.cuts, self.snapshots, RapidTool.of(self.real, job.clearance, self.frame.free), self.stock, begin, finish,
        )
        tools = []
        for index in sorted({0, len(cuts) - 1}) if cuts else []:
            for position in (cuts[index].start, cuts[index].end):
                tools.append(tuple(p for loop in placed(self.planning, position) for edge in loop for p in segments_to_polyline([edge.segment])))
        return RoughingCuts(
            tuple(cuts), tuple(tools), tuple(self.removed), tuple(self.material), stats["fast"], stats["scan"], stats["failed"], stats["unreachable"],
            unconnected, tuple(leave_retreat), tuple(leave_rapid), tuple(self.stock), tuple(self.keep_ring), tuple(self.plan.removal), job.clearance,
        )


def left_standing(first: RoughingCuts, nose_radius: float, tolerance: float) -> list[Loop] | None:
    """The pieces of the material to rough that the cut left standing (the tool cannot reach them). Left out: the ones smaller than
    `DIP_MIN_AREA_MM2`, and the ones that lie wholly within the nose radius of the part and its allowance (the fillet a nose leaves in an inner
    corner: the finishing pass takes it). None when the boolean cannot work it out (tried as `removal.cut` does: a smaller tolerance, the
    smallest shifts)."""
    try:
        pieces = steady_intersection(list(first.residual), list(first.wanted), tolerance)
    except ChainError:
        return None
    border = [segment for loop in first.keep for segment in loop]

    def beyond_the_nose(loop: Loop) -> bool:
        places = [point for segment in loop for point in (segment.start, point_of(segment, MIDPOINT_FRACTION))]
        return any(min(distance_to_segment(place, piece) for piece in border) > nose_radius + tolerance for place in places)

    return [loop for loop in pieces if abs(loop_area(loop)) >= DIP_MIN_AREA_MM2 and beyond_the_nose(loop)]


def _area(listed: Cut, reach: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """The box of every place of the tool on the moves of a cut (its way in, the line and the ride)."""
    pieces = [*listed.entry, LineSegment(listed.start, listed.end), *listed.ride]
    x0, z0, x1, z1 = loops_box([pieces])
    return x0 + reach[0], z0 + reach[1], x1 + reach[2], z1 + reach[3]


def _placed_passes(passes: list[tuple[int, Cut]], cuts: list[Cut], real: list) -> list[tuple[int, int, Cut]]:
    """Where every pass goes in the list: behind its line, but also behind every later cut that works where the pass works, and behind the
    passes planned before it there: the passes are planned on the material all the lines left (and the passes before them), so on the machine
    they must come after those cuts, or they would go into material a lower line takes later, deeper than the depth of cut. The boxes are
    on the safe side (a pass may go a little later than needed). Returns (place, number in the planning order, pass)."""
    reach = loops_box([[edge.segment for edge in loop] for loop in real])
    areas = [_area(listed, reach) for listed in cuts]
    placed: list[tuple[int, int, Cut]] = []
    for number, (place, dip_cut) in enumerate(passes):
        area = _area(dip_cut, reach)
        place = max([place, *(index + 1 for index, other in enumerate(areas) if index >= place and boxes_meet(area, other, 0.0))])
        place = max([place, *(earlier for earlier, _n, before in placed if boxes_meet(area, _area(before, reach), 0.0))])
        placed.append((place, number, dip_cut))
    return placed


def _behind_a_bump(
    ordered: list[WantedLine], planned: list, done: set[int], ride: list[Segment], goal: float, material: list[Loop], planner: _Planner,
):
    """When the ride up of a line stops on the top of a bump that is lower than `goal` (the line above), the tool goes over it and down. Some
    other line lies behind the bump at the radius of this line at most, so the next lines of the list are tried in order: the first one the way
    down reaches (at its radius, within its stretch) is pulled out of the list and cut with this one, from where the tool arrives: one cut, one
    line used up, at most one depth of cut deeper. Returns the way over, the number of that line, where the tool arrives, the end of its cut and
    its ride up; None when there is no such line."""
    curves, planning, keep, tolerance, frame = planner.curves, planner.planning, planner.keep, planner.tolerance, planner.frame
    if not ride:
        return None
    level = ride[0].start.x
    for number, other in enumerate(ordered):
        if number in done or other.high.x > level + GEOMETRY_TOLERANCE_MM:
            continue
        if other.high.x < level - (goal - level) - GEOMETRY_TOLERANCE_MM:
            break  # deeper than one depth of cut: the lines are sorted, none further on is nearer
        over = ride_over(curves, ride, other.high.x, goal, planning, keep, tolerance)
        if not over:
            continue
        arrival = over[-1].end
        if other.low.z + WANTED_SPAN_MIN_MM < arrival.z <= other.high.z + tolerance:
            intervals = planned[number][0]  # the stretch as for any line: it begins where the tool arrives
            if len(intervals) == 1 and abs(intervals[0][1] - arrival.z) <= CUT_END_SNAP_MM:
                low = intervals[0][0]
                top = column_top(material, other.high.x, low, frame.axis, tolerance, keep.loops, frame.column_beside_part)
                follow = [] if other.open_low else ride_up(curves, Point(other.high.x, low), top, 1, planning, keep, tolerance, (0.0, -1.0))
                return over, number, arrival, low, follow
    return None


def _cut_with_entry(material: list[Loop], real: list, way_in: list[Segment], moves: list[Segment], tolerance: float) -> tuple[list[Loop], list[Loop]]:
    """The material after the way in and the moves of the line, and what was taken. The way in is cut with the line as one path; when the
    boolean cannot decide that (the end of the way in lies exactly on the start of the line), the line is cut first and the way in on its own,
    moved by the smallest shift of the cut."""
    try:
        return cut(material, real, [*way_in, *moves], tolerance)
    except ChainError:
        if not way_in:
            raise
    after_line, taken = cut(material, real, moves, tolerance)
    after_entry, early = cut(after_line, real, _jittered(way_in), tolerance)
    return after_entry, [*early, *taken]


def _jittered(path: list[Segment]) -> list[Segment]:
    """The path moved by the smallest shift of the cut (`CUT_JITTER_MM`, far below the roughing accuracy): the way in ends where the line begins,
    with the same tool outline, and the boolean cannot always decide two borders that lie exactly on each other."""
    dx, dz = CUT_JITTER_MM[0]
    return [translated_segment(piece, dx, dz) for piece in path]


def _plunge(planner: _Planner, material: list[Loop], start: Point) -> list[Segment] | None:
    """A straight plunge down to the start of a cut at a wall, when the way out along the contour finds none: the tool comes down from one
    clearance above the first place where it is clear of the material, along X, at feed. `way_out` tests every place against the material
    as it stands before the way in, so a tool whose side does not cut and runs flush along the wall of the groove the plunge cuts (a flat
    side face, a left-hand tool on a full bar) finds no way there. Here the plunge is tested as the replay tests a feed move: no edge in the
    part, and no edge in the material that is left after the plunge has cut (`removal.cut`). None when that fails."""
    planning, real, keep, clearance, tolerance = planner.planning, planner.real, planner.keep, planner.clearance, planner.tolerance
    stock = RegionIndex(material)
    length = (loops_box(material)[2] if material else start.x) + clearance - start.x
    if length <= GEOMETRY_TOLERANCE_MM:
        return None
    clear = [low for low, _high in free_intervals(planning, stock, start, (1.0, 0.0), length, tolerance, 0.0) if low > GEOMETRY_TOLERANCE_MM]
    if not clear:
        return None
    top = Point(start.x + clear[0], start.z)
    above = Point(top.x + clearance, top.z)
    try:
        after = RegionIndex(cut(material, real, [LineSegment(top, start)], tolerance)[0])
    except ChainError:
        return None
    if not (leg_free(above, start, planning, keep, CUT_END_SNAP_MM) and leg_free(top, start, real, after, tolerance)):
        return None
    return [LineSegment(above, top), LineSegment(top, start)]


def _wall_entry(
    planner: _Planner, ordered: list[WantedLine], material: list[Loop], line: WantedLine, start: Point, axis, beside: bool,
) -> list[Segment] | None:
    """The way in to a line that starts at a wall, along the wall: the mirror image of the ride up at the end of a line. The tool stands at
    the start on the contour and rides up along it to the top of the material in front of the start (the line above has cut everything
    higher), so a wall that falls away is cut on the way in, the wedge between it and the line above and the sawtooth between two lines, then
    on the usual way in from the top. None where it makes no difference (a wall straight across the line, the old way in is the same), where
    the material above the start is higher than the line above (it should not be: that line is cut first), or where no ride leads up."""
    curves, planning, keep, tolerance = planner.curves, planner.planning, planner.keep, planner.tolerance
    level = start.x
    above = [other.high.x for other in ordered if other.high.x > level + tolerance]
    if not above:
        return None
    top = column_top(material, level, start.z - 4 * tolerance, axis, tolerance, keep.loops, beside)  # at the start, a little behind the wall
    if top <= level + tolerance or top > min(above) + tolerance:
        return None
    ride = ride_up(curves, start, top, 1, planning, keep, tolerance, (0.0, 1.0))
    if not ride or all(isinstance(piece, LineSegment) and abs(piece.end.z - start.z) <= CUT_END_SNAP_MM for piece in ride):
        return None
    top_way = _entry(planner, RegionIndex(material), ride[-1].end, True)
    if top_way is None:
        return None
    return [*top_way, *(reversed_segment(piece) for piece in reversed(ride))]


def _entry(
    planner: _Planner, stock: RegionIndex, start: Point, wall: bool,
) -> list[Segment] | None:
    """The way in to the start of a cut, as feed moves in the order the tool goes. It is found backwards from the start: the tool leaves the
    stock along the contour (`way_out`; nothing to do where the start is already in the air), then goes one clearance on, orthogonal to the line
    when a wall stands at the start (up, out of the pocket), along the line otherwise. None when no way out leads from the start."""
    curves, planning, keep, clearance, tolerance = planner.curves, planner.planning, planner.keep, planner.clearance, planner.tolerance
    away = (1.0, 0.0) if wall else (0.0, 1.0)
    out = way_out(curves, start, planning, keep, stock, tolerance, (0.0, 1.0), away=away)
    if out is None:
        return None
    here = out[-1].end if out else start
    leg = LineSegment(here, Point(here.x + away[0] * clearance, here.z + away[1] * clearance))
    backwards = [*out, *free_run(curves, leg, planning, keep, stock, tolerance)] if clearance > GEOMETRY_TOLERANCE_MM else out
    return [reversed_segment(piece) for piece in reversed(backwards)]
