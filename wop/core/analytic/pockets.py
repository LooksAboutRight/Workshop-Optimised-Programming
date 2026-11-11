"""Which lines are in pockets, and the lines of a pocket.

A stretch of a line has two ends. An end is OPEN when just beyond it is not material (the air in front of the part, or at the
side of the stock), and a WALL when just beyond it is material that stays (the part and its allowance). A stretch with a wall at
both ends cannot be entered along itself: it is a pocket line, entered from above, and then the tool goes down in steps of the
plunge depth of cut. So a pocket does not keep the lines of the normal depth of cut: it gets its own lines, spaced by the plunge
depth of cut, from the height where it becomes reachable (the level of the open line above it) down to its bottom.

Pockets are found by linking pocket stretches of neighbouring levels that overlap along the line.
"""

from __future__ import annotations

from ..passes import levels
from ..constants import CHAIN_SNAP_MM, WANTED_LEVEL_SHIFT_MM, WANTED_SPAN_MIN_MM
from ..geometry import Point
from ..geometry.chains import INSIDE, Loop, locate
from .wanted_lines import LineKind, WantedLine, spans

PROBE_MM = 2 * CHAIN_SNAP_MM  # how far beyond the end of a stretch the material is looked at (more than the snap distance)

Member = tuple[int, int]  # (level index, index of the stretch on that level)


def _point(level: float, along: float, axis: int) -> Point:
    return Point(level, along) if axis == 0 else Point(along, level)


def end_is_open(stock: list[Loop], level: float, along: float, axis: int, chuck_z: float | None = None) -> bool:
    """True when the material just beyond the end of a stretch (at `along`, outwards) is not part of the stock. The chuck is a
    wall too: along Z, nothing beyond the clamping plane `chuck_z` is open air."""
    if chuck_z is not None and axis == 0 and along <= chuck_z:
        return False
    return locate(_point(level, along, axis), stock, CHAIN_SNAP_MM)[0] != INSIDE


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return min(a[1], b[1]) - max(a[0], b[0])


def _groups(closed: list[Member], by_level: list[list[tuple[float, float]]]) -> list[list[Member]]:
    """The pocket stretches linked into pockets: stretches of neighbouring levels that overlap along the line belong together."""
    parent = {member: member for member in closed}

    def find(member: Member) -> Member:
        while parent[member] != member:
            parent[member] = parent[parent[member]]
            member = parent[member]
        return member

    known = set(closed)
    for level, index in closed:
        for other in range(len(by_level[level + 1]) if level + 1 < len(by_level) else 0):
            if (level + 1, other) in known and _overlap(by_level[level][index], by_level[level + 1][other]) > WANTED_SPAN_MIN_MM:
                parent[find((level + 1, other))] = find((level, index))
    groups: dict[Member, list[Member]] = {}
    for member in closed:
        groups.setdefault(find(member), []).append(member)
    return sorted((sorted(members) for members in groups.values()), key=lambda members: members[0])


def make_lines(
    loops: list[Loop], stock: list[Loop], positions: list[float], critical: list[float], surface: float, axis: int,
    free_side: int, plunge_depth: float, chuck_z: float | None = None,
) -> list[WantedLine]:
    """The wanted lines: the normal lines with open ends, and for every pocket the lines of the plunge depth of cut.

    `positions` are the normal levels from the free side towards the part, `critical` the levels that must get a line of their
    own (flat walls), `surface` where the material begins (the level above the first), `free_side` +1 if the free air is towards
    larger coordinates of the level axis, `chuck_z` the clamping plane (a wall)."""

    shift = free_side * WANTED_LEVEL_SHIFT_MM
    by_level = [spans(loops, level + shift, axis) for level in positions]
    ends: dict[Member, tuple[bool, bool]] = {}
    for number, level in enumerate(positions):
        for index, (low, high) in enumerate(by_level[number]):
            ends[(number, index)] = (end_is_open(stock, level, high + PROBE_MM, axis, chuck_z), end_is_open(stock, level, low - PROBE_MM, axis, chuck_z))
    closed = [member for member, (open_high, open_low) in ends.items() if not open_high and not open_low]
    lines: list[WantedLine] = []
    for number, level in enumerate(positions):
        for index, (low, high) in enumerate(by_level[number]):
            if (number, index) in ends and (number, index) not in closed:
                open_high, open_low = ends[(number, index)]
                lines.append(_line(number, level, low, high, axis, LineKind.OPEN, open_high, open_low))
    for pocket, members in enumerate(_groups(closed, by_level)):
        first, last = members[0][0], members[-1][0]
        contact = positions[first - 1] if first > 0 else surface
        bottom = positions[last]
        between = [c for c in critical if free_side * (contact - c) > 0 and free_side * (c - bottom) > 0]
        radii = levels(contact, bottom, between, plunge_depth)
        for layer, level in enumerate(radii):
            reach = next((k for k in range(first, last + 1) if free_side * (positions[k] - level) <= 0), last)  # the normal level at or below this one
            support = [by_level[reach][index] for (k, index) in members if k == reach]
            for low, high in spans(loops, level + shift, axis):
                if any(_overlap((low, high), s) > WANTED_SPAN_MIN_MM for s in support) and not (
                    end_is_open(stock, level, high + PROBE_MM, axis, chuck_z) or end_is_open(stock, level, low - PROBE_MM, axis, chuck_z)
                ):  # a stretch open to the front is reached by the normal lines
                    lines.append(_line(-1, level, low, high, axis, LineKind.POCKET, False, False, pocket, layer))
    return lines


def _line(number: int, level: float, low: float, high: float, axis: int, kind: LineKind, open_high: bool, open_low: bool,
          pocket: int = -1, layer: int = -1) -> WantedLine:
    return WantedLine(number, _point(level, high, axis), _point(level, low, axis), kind, open_high, open_low, pocket, layer)
