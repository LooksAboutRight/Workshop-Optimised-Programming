"""Check the generated moves of a planned program (requirements X3, R5).

Every move is followed in small steps. Cutting moves remove material as the
tool passes (the tool body counts as cutting), so the holder of a later pass
may be where an earlier pass cut. Rapid moves must not run through material.
What must never be cut is the material that stays after the block.
Hand-written blocks are not checked: their moves are not known.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from typing import Callable
from enum import Enum

import math

import numpy as np

from .constants import (
    COLLISION_PENETRATION_TOLERANCE_MM, GEOMETRY_TOLERANCE_MM, HOLDER_BAND_MM, HOLDER_NORMAL_PROBE_MM, PATH_CHECK_STEP_MM, RAPID_SKIP_MARGIN_MM, RAPID_SKIP_UNLIMITED,
    SHRUNK_NEAR_MARGIN_FACTOR, SWEEP_CONTACT_SEARCH_STEPS, SWEEP_MIN_LENGTH_MM,
    WORKHOLDING_NOTE_TOLERANCE_MM,
)
from .analytic.far_side import turned_operations, turned_point, turned_tool
from .geometry import ArcSegment, LineSegment, Point, Segment
from .program_model.operations import ArcMove, LinearMove, Rapid, SetSpindle, SpindleSetting, StopSpindle, plain_moves, spindle_after
from .program_model.plan_cache import PlanCache
from .program_model.program import Program, ProgramPlan, stop_if_asked
from .reach import (
    CollisionContext, axis_gap, check_prepared, far_side_tip, jaws_region, placed_shrunk, prepare_tool, program_jaws,
    sample_segments,
)
from .geometry.chains import loops_of_region
from .geometry.contacts import free_all_along
from .geometry.penetration import RegionIndex
from .geometry.tool_edges import ToolEdge
from .geometry.region import Region


class FindingKind(Enum):
    """Names of the first three match CollisionKind. Value: (what happens, a remedy)."""

    GOUGE = (
        "cuts into the finished part",
        "use a tool with a narrower body or more clearance, or change the block",
    )
    HOLDER_IN_MATERIAL = (
        "holder runs into the material",
        "use a tool with a smaller holder, or shorten the cut",
    )
    JAWS = ("touches the jaws", "shorten the cut or let the part stick out further")
    RAPID_IN_MATERIAL = (
        "rapid move through material",
        "check the safe positions and the approach of the block",
    )
    CLAMP_PLANE = (
        "goes behind the clamping plane of the Setup",
        "the part is held there: shorten the cut, or change the clamping position in the Setup",
    )
    SPINDLE_OFF = (
        "cutting move with the spindle stopped",
        "start the spindle before the block (a spindle stop machine function may be in the way)",
    )

    @property
    def text(self) -> str:
        return self.value[0]

    @property
    def remedy(self) -> str:
        return self.value[1]


@dataclass(frozen=True)
class Finding:
    block_index: int
    operation_index: int
    position: Point  # tool tip where it happens (x = radius)
    kind: FindingKind
    message: str
    remedy: str
    move_number: int = 0  # 1-based among the moves of the block: the number the stepper shows next to the step (`StepFrame.move_number`)





def _finding_text(block_plan, move_number: int, what: str, place: Point) -> str:
    """The text of a finding: the block and the move as the stepper shows them, then what happens and where."""
    return f"block {block_plan.number} ({block_plan.block.type_name}), move {move_number}: {what} (radius {place.x:.2f}, Z {place.z:.2f})"


def move_points(start: Point | None, operation) -> list[Point]:
    if start is None:
        return [operation.end]
    segment: Segment
    if isinstance(operation, ArcMove):
        segment = ArcSegment(start, operation.end, operation.center, operation.direction)
    else:
        segment = LineSegment(start, operation.end)
    return sample_segments([segment], PATH_CHECK_STEP_MM)


class _HolderEdges:
    """The straight edges of the holder pieces of a tool and the direction each one faces (out of the tool)."""

    def __init__(self, tool) -> None:
        starts, ends, normals = [], [], []
        for outline in tool.holder_outlines:
            for a, b in zip(outline, outline[1:]):
                length = a.distance_to(b)
                if length <= 0:
                    continue
                nx, nz = (b.z - a.z) / length, (a.x - b.x) / length
                middle = Point((a.x + b.x) / 2, (a.z + b.z) / 2)
                if tool.body.contains_point(Point(middle.x + nx * HOLDER_NORMAL_PROBE_MM, middle.z + nz * HOLDER_NORMAL_PROBE_MM)):
                    nx, nz = -nx, -nz  # that side is inside the tool: the edge faces the other way
                starts.append((a.x, a.z))
                ends.append((b.x, b.z))
                normals.append((nx, nz))
        self.starts = np.array(starts).reshape(-1, 2)
        self.ends = np.array(ends).reshape(-1, 2)
        self.normals = np.array(normals).reshape(-1, 2)

    def facing(self, vx: float, vz: float) -> np.ndarray:
        """The edges that face the direction of the move: only they can meet material the tool has not passed yet."""
        return self.normals @ np.array((vx, vz)) > 0


@dataclass(frozen=True)
class _Contact:
    """A collision that the swept area of a straight move proves: what kind, with what, and the tool that sweeps."""

    kind: FindingKind
    obstacle: Region  # shrunk, as the step check compares it
    tool: object  # the PreparedTool (or its mirror) that touches it
    shift: tuple  # (vx, vz, ox, oz): the move as this tool sees it and where it starts


def _sweep_verdict(
    prepared, edges: tuple, start: Point, end: Point, rapid: bool, protected_shrunk: Region, jaws_shrunk: Region | None,
    current: Region, clamp_z: float,
) -> tuple[list[_Contact], bool]:
    """What the area swept by the tool on the straight move from `start` to `end` says.

    Returns the collisions it proves (the finished part, the jaws, and for a rapid move the material: a swept area that
    meets them means the tool is there at some place of the move, whatever the step) and whether the step check has to
    look at the move anyway: the holder edges (cutting move) come near the material, or the move goes behind the clamping
    plane. Nothing proved and no doubt: the move is clean. Everything is compared the way the step check compares it, so
    a clean move never hides a collision that the step check would find."""
    dx, dz = end.x - start.x, end.z - start.z
    doubt = not rapid and min(start.z, end.z) < clamp_z - WORKHOLDING_NOTE_TOLERANCE_MM  # the step check says where
    tools = [(prepared, edges[0], dx, dz, start.x, start.z)]
    if prepared.mirror is not None:  # a tool that can reach past the axis: its far side is the mirrored tool
        tools.append((prepared.mirror, edges[1], -dx, dz, -start.x, start.z))
    proved: list[_Contact] = []
    for tool, holder, vx, vz, ox, oz in tools:
        body = tool.body.shrunk_for_collision().swept(vx, vz).translated(ox, oz)
        if body.is_empty:
            continue
        material = _shrunk_near(current, body)
        shift = (vx, vz, ox, oz)
        if body.overlaps(protected_shrunk):
            proved.append(_Contact(FindingKind.GOUGE, protected_shrunk, tool, shift))
        if jaws_shrunk is not None and body.overlaps(jaws_shrunk):
            proved.append(_Contact(FindingKind.JAWS, jaws_shrunk, tool, shift))
        if rapid:
            if body.overlaps(material):
                proved.append(_Contact(FindingKind.RAPID_IN_MATERIAL, material, tool, shift))
        elif not doubt:
            # The holder at the start of the move, and afterwards only the holder edges that face the way of the move: an
            # edge that faces back is where the tool body has been already (it has cut the material there).
            front = holder.facing(vx, vz)
            at_start = Region.swept_edges(holder.starts, holder.ends, 0, 0, HOLDER_BAND_MM).translated(ox, oz)
            ahead = Region.swept_edges(holder.starts[front], holder.ends[front], vx, vz, HOLDER_BAND_MM).translated(ox, oz)
            doubt = at_start.overlaps(material) or ahead.overlaps(material)
    return proved, doubt


class _Material:
    """The material while the check follows a block, with the cuts of the last moves not yet taken out of it (`cut`): the quick test
    may use the material as it was (`as_tested`, a little more than there is: what is free of it is free); `now` takes the cuts out
    when a test needs the material exactly, all of them at once (joined first: they are small, the material is large)."""

    def __init__(self, start: Region) -> None:
        self.as_tested = start
        self._pending: list[Region] = []

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def cut(self, area: Region) -> None:
        self._pending.append(area)

    def now(self) -> Region:
        if self._pending:
            taken = self._pending[0]
            for area in self._pending[1:]:
                taken = taken.union(area)
            self.as_tested, self._pending = self.as_tested.difference(taken), []
        return self.as_tested

    def set(self, material: Region) -> None:
        """The material after a move that was followed in steps (worked out from `now`)."""
        self.as_tested, self._pending = material, []


class _ExactTests:
    """What the quick test of a straight move needs, made once per block: the tool (and the mirrored tool on the far side of the axis)
    as loops of edges, its holder as flat loops (each piece there and back: only the edge itself is tested), and the finished part and
    the jaws as chain indexes (`analytic.penetration`)."""

    def __init__(self, prepared, protected: Region, jaws: Region | None) -> None:
        self.tools = [(prepared, _edge_loops(prepared.body), _holder_loops(prepared))]
        if prepared.mirror is not None:
            self.tools.append((prepared.mirror, _edge_loops(prepared.mirror.body), _holder_loops(prepared.mirror)))
        self.protected = RegionIndex(loops_of_region(protected)) if not protected.is_empty else None
        self.jaws = RegionIndex(loops_of_region(jaws)) if jaws is not None and not jaws.is_empty else None


def _edge_loops(region: Region) -> list[tuple[ToolEdge, ...]]:
    return [tuple(ToolEdge(piece, False) for piece in loop) for loop in loops_of_region(region)]


def _holder_loops(prepared) -> list[tuple[ToolEdge, ...]]:
    """Every holder outline as one flat loop, there and back: it has no inside, so only its edges are tested."""
    loops = []
    for outline in prepared.holder_outlines:
        there = [LineSegment(a, b) for a, b in zip(outline, outline[1:]) if a.distance_to(b) > 0]
        if there:
            back = [LineSegment(piece.end, piece.start) for piece in reversed(there)]
            loops.append(tuple(ToolEdge(piece, False) for piece in there + back))
    return loops


def _clearly_free(tests: _ExactTests, start: Point, end: Point, rapid: bool, material: Region, clamp_z: float) -> bool:
    """True when the straight move is free beyond doubt, tested exactly along the whole move with the contact events of the analytic
    planner (`contacts.free_all_along`), with half the collision tolerance (a case near the limit goes to the swept-area test): the tool
    body keeps out of the finished part and the jaws, on a rapid the whole tool keeps out of the material, on a cutting move the holder
    does, and the move stays in front of the clamping plane. Then the swept-area test (`_sweep_verdict`) is not needed; it is a few
    times slower (booleans of the whole material for every move)."""
    if not rapid and min(start.z, end.z) < clamp_z - WORKHOLDING_NOTE_TOLERANCE_MM:
        return False
    length = start.distance_to(end)
    tolerance = COLLISION_PENETRATION_TOLERANCE_MM / 2
    stock = RegionIndex(loops_of_region(material)) if not material.is_empty else None
    for tool, body, holder in tests.tools:
        sign = -1 if tool is not tests.tools[0][0] else 1  # the mirrored tool stands and moves mirrored in X
        here = Point(sign * start.x, start.z)
        vector = (sign * (end.x - start.x) / length, (end.z - start.z) / length)
        for obstacle in (tests.protected, tests.jaws):
            if obstacle is not None and not free_all_along(body, obstacle, here, vector, length, tolerance):
                return False
        if stock is not None:
            moving = body if rapid else holder
            if moving and not free_all_along(moving, stock, here, vector, length, tolerance):
                return False
    return True


def _shrunk_near(region: Region, near: Region) -> Region:
    """`region.shrunk_for_collision()`, only where `near` can reach it: the region is clipped to the box of `near` grown by a few
    tolerances first. The clip border shrinks too, but it lies further from `near` than any shrinking reaches, so every overlap with
    `near` is the same; the material changes with every cut, and shrinking all of it for each move costs most of the check."""
    box = near.bounds
    if box is None or region.is_empty:
        return Region.empty()
    margin = SHRUNK_NEAR_MARGIN_FACTOR * COLLISION_PENETRATION_TOLERANCE_MM
    return region.intersection(Region.rectangle(box.min_x - margin, box.min_z - margin, box.max_x + margin, box.max_z + margin)).shrunk_for_collision()


def _sweep_is_clean(*arguments) -> bool:
    """True when the swept area proves no collision and leaves no doubt (see `_sweep_verdict`)."""
    proved, doubt = _sweep_verdict(*arguments)
    return not proved and not doubt


def _first_contact(contact: _Contact, start: Point, end: Point) -> Point:
    """Where on the move the tool first touches what the swept area met (found by halving: no step size)."""
    tool, (vx, vz, ox, oz) = contact.tool, contact.shift
    body = tool.body.shrunk_for_collision()

    def meets(fraction: float) -> bool:
        return body.swept(vx * fraction, vz * fraction).translated(ox, oz).overlaps(contact.obstacle)

    low, high = 0.0, 1.0  # the whole move meets it; the start does not need to (else the contact is at the start)
    if meets(0.0):
        return start
    for _ in range(SWEEP_CONTACT_SEARCH_STEPS):
        middle = (low + high) / 2
        if meets(middle):
            high = middle
        else:
            low = middle
    return Point(start.x + (end.x - start.x) * high, start.z + (end.z - start.z) * high)


def verify_plan(
    program: Program,
    plan: ProgramPlan,
    jaws_outline: list[Segment] | None = None,
    cache: PlanCache | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[Finding]:
    """Every finding of the plan. A straight move is first looked at as a whole (the area the tool sweeps), and followed in steps only
    where it may touch something; an arc is followed in steps. `cache`: the findings of a block whose moves, material, tool and start are the same as in an
    earlier check are taken from there (`plan_cache.py`). `should_stop`: asked before every block (`program.stop_if_asked`)."""
    findings: list[Finding] = []
    clamp_z = program.raw_part.clamp_z_mm
    if jaws_outline:
        jaws = jaws_region(program.raw_part, jaws_outline)
    else:
        jaws, _problem = program_jaws(program.raw_part, program.workholding)
    jaws_key = (program.raw_part, program.workholding, tuple(jaws_outline or ()))
    position: Point | None = None
    spindle: SpindleSetting | None = None  # stopped at the start
    spindle_known = True  # not after a hand-written block: its text may start or stop the spindle
    for block_index, block_plan in enumerate(plan.blocks):
        stop_if_asked(should_stop)
        tool = program.equipped_tool(block_plan.block.tool_number)
        state = (position, spindle, spindle_known)
        key = ("check", block_plan.operations, block_plan.program_index, block_plan.block.type_name, tool, jaws_key, clamp_z, state)
        known = None if cache is None else cache.recall(key, block_plan)
        far = block_plan.block.works_on_far_side(tool)  # the part is round: the far side is checked as its mirror image on the near side
        if known is None:
            if far:
                turned = replace(block_plan, operations=turned_operations(block_plan.operations))
                known = _check_block(block_index, turned, prepare_tool(turned_tool(tool)), jaws, clamp_z, turned_point(position), spindle, spindle_known)
            else:
                known = _check_block(block_index, block_plan, prepare_tool(tool), jaws, clamp_z, *state)
            if cache is not None:
                cache.remember(key, block_plan, known)
        block_findings, position, spindle, spindle_known = known
        if far:
            position = turned_point(position)  # back to where the machine is
        findings += [replace(finding, block_index=block_index) for finding in block_findings]
    return findings


def _finding(block_plan, block_index: int, operation_index: int, move_number: int, kind: FindingKind, place: Point) -> Finding:
    return Finding(block_index, operation_index, place, kind, _finding_text(block_plan, move_number, kind.text, place), kind.remedy, move_number)


def _straight_length(position: Point | None, operation) -> float | None:
    """The length of a straight move (a rapid or a line); None for an arc, or when the tool is nowhere yet."""
    if position is None or not isinstance(operation, (Rapid, LinearMove)):
        return None
    return position.distance_to(operation.end)


def _swept_by(prepared, position: Point, end: Point) -> Region:
    """What the body of the tool covers on a straight move from `position` to `end`."""
    return prepared.body.swept(end.x - position.x, end.z - position.z).translated(position.x, position.z)


def _whole_move_verdict(
    prepared, edges, exact, material: _Material, position: Point | None, operation, length: float | None, rapid: bool,
    protected_shrunk: Region, jaws_shrunk: Region | None, clamp_z: float,
) -> tuple[bool, list[_Contact]]:
    """The tests of a straight move as a whole: (settled, contacts). Settled: the move is clean, the step check is not needed.
    Otherwise the contacts that the swept area proved (the step check still follows the move)."""
    if length is None:
        return False, []
    # The quick exact test first, for a straight move of any length. Free of the material as it was a few cuts ago is free of the
    # material now (it only gets less); only when that is not clear the cuts are taken out of it and the test is made again.
    if length > GEOMETRY_TOLERANCE_MM and (
        _clearly_free(exact, position, operation.end, rapid, material.as_tested, clamp_z)
        or (material.has_pending and _clearly_free(exact, position, operation.end, rapid, material.now(), clamp_z))
    ):
        return True, []
    if length <= SWEEP_MIN_LENGTH_MM:  # too short for the swept-area test
        return False, []
    contacts, doubt = _sweep_verdict(prepared, edges, position, operation.end, rapid, protected_shrunk, jaws_shrunk, material.now(), clamp_z)
    return not contacts and not doubt, contacts


def _obstacles(protected: Region, current: Region, jaws: Region | None) -> Region:
    """What a rapid has to keep clear of, as the tests compare it (made once per move)."""
    obstacles = protected.shrunk_for_collision().union(current.shrunk_for_collision())
    return obstacles if jaws is None else obstacles.union(jaws.shrunk_for_collision())


def _steps_to_skip(prepared, point: Point, body: Region, far_body: Region | None, obstacles: Region) -> int:
    """How many of the next points of a rapid cannot touch anything, because the tool is far from everything: the next points are at
    most one step further along, so with `gap` free that many cannot touch."""
    gap = body.distance_to(obstacles) - RAPID_SKIP_MARGIN_MM
    if far_body is None:  # not across the axis yet: how far until it is
        gap = min(gap, axis_gap(prepared, point) - RAPID_SKIP_MARGIN_MM)
    else:
        gap = min(gap, far_body.distance_to(obstacles) - RAPID_SKIP_MARGIN_MM)
    if gap <= 0:
        return 0
    return RAPID_SKIP_UNLIMITED if math.isinf(gap) else int(gap / PATH_CHECK_STEP_MM)


def _kinds_at(prepared, point: Point, rapid: bool, context: CollisionContext, body: Region, far_body: Region | None) -> list[FindingKind]:
    """What is wrong with the tool standing at `point` (`body`: the tool there, `far_body`: its far side, when it reaches past the axis)."""
    kinds = [FindingKind[c.kind.name] for c in check_prepared(prepared, point, context, body, holder=not rapid)]
    if rapid:
        material = context.residual.shrunk_for_collision()
        if body.overlaps(material) or (far_body is not None and far_body.overlaps(material)):
            kinds.append(FindingKind.RAPID_IN_MATERIAL)
    return kinds


def _check_block(
    block_index: int, block_plan, prepared, jaws: Region | None, clamp_z: float,
    position: Point | None, spindle: SpindleSetting | None, spindle_known: bool,
) -> tuple[tuple[Finding, ...], Point | None, SpindleSetting | None, bool]:
    """The findings of one block, from the position and the spindle state at its start; and that state at its end."""
    findings: list[Finding] = []
    found = partial(_finding, block_plan, block_index)  # (operation_index, move_number, kind, place)
    protected = block_plan.result.protected
    if protected is None:
        protected = block_plan.residual_before.difference(block_plan.result.removed)
    material = _Material(block_plan.residual_before)
    protected_shrunk = protected.shrunk_for_collision()
    jaws_shrunk = None if jaws is None else jaws.shrunk_for_collision()
    edges = (_HolderEdges(prepared), None if prepared.mirror is None else _HolderEdges(prepared.mirror))
    exact = _ExactTests(prepared, protected, jaws)
    expanded = [
        (index, move)
        for index, original in enumerate(block_plan.operations)
        for move in plain_moves(original)
    ]
    move_number = 0
    for operation_index, operation in expanded:
        if not isinstance(operation, (Rapid, LinearMove, ArcMove)):
            if isinstance(operation, (SetSpindle, StopSpindle)):
                spindle, spindle_known = spindle_after(spindle, operation), True
            continue
        move_number += 1
        rapid = isinstance(operation, Rapid)
        reported: set[FindingKind] = set()
        behind: Point | None = None  # the first point of a cutting move behind the clamping plane
        if not rapid and spindle_known and spindle is None:
            reported.add(FindingKind.SPINDLE_OFF)
            findings.append(found(operation_index, move_number, FindingKind.SPINDLE_OFF, operation.end))
        length = _straight_length(position, operation)
        settled, contacts = _whole_move_verdict(
            prepared, edges, exact, material, position, operation, length, rapid, protected_shrunk, jaws_shrunk, clamp_z,
        )
        if settled:
            if not rapid:  # the tool cuts what it passes: the whole area between the start and the end
                material.cut(_swept_by(prepared, position, operation.end))
            position = operation.end
            continue
        current = material.now()
        current_before = current
        skip = 0  # rapid moves: positions that cannot touch anything, because the tool is far from everything
        obstacles: Region | None = None
        for point in move_points(position, operation):
            if not rapid and point.z < clamp_z - WORKHOLDING_NOTE_TOLERANCE_MM:
                behind = behind or point
            if skip > 0:
                skip -= 1
                continue
            context = CollisionContext(protected, current, jaws)  # `current` changes as the tool cuts
            body = placed_shrunk(prepared, point)
            far_tip = far_side_tip(prepared, point)  # only a tool that reaches past the axis has a far side
            far_body = None if far_tip is None else placed_shrunk(prepared.mirror, far_tip)
            kinds = _kinds_at(prepared, point, rapid, context, body, far_body)
            if rapid and not kinds:
                if obstacles is None:
                    obstacles = _obstacles(protected, current, jaws)
                skip = _steps_to_skip(prepared, point, body, far_body, obstacles)
            for kind in kinds:
                if kind not in reported:
                    reported.add(kind)
                    findings.append(found(operation_index, move_number, kind, point))
            if not rapid:
                # The tool cuts what it passes, so later positions see it removed.
                current = current.difference(prepared.body.translated(point.x, point.z))
        for contact in contacts:  # what the swept area proved and the steps did not see (a thin obstacle between two steps)
            if contact.kind not in reported:
                reported.add(contact.kind)
                findings.append(found(operation_index, move_number, contact.kind, _first_contact(contact, position, operation.end)))
        if not rapid and length is not None and length > SWEEP_MIN_LENGTH_MM:  # the exact area replaces what the steps cut (they leave little teeth)
            current = current_before.difference(_swept_by(prepared, position, operation.end))
        material.set(current)
        if behind is not None and FindingKind.JAWS not in reported:  # the jaws finding already says it
            findings.append(found(operation_index, move_number, FindingKind.CLAMP_PLANE, behind))
        position = operation.end
    return tuple(findings), position, spindle, spindle_known
