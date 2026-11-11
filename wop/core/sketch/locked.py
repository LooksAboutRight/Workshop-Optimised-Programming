"""Locked things in a sketch: points, construction lines and arcs that the program supplies (the safe point, the part before a block).
The user can pick them and dimension to them, but not move, change or delete them.

A target hands over the list of what is locked, each with a key that stays the same from one opening of the editor to the next.
A key may have the form `group/name`: the things of one group (the outline of the part) belong together. `sync_locked` brings
the sketch in line with the lists. A dimension or relation that the new positions no longer allow is removed, and so is every
relation that touches a group whose pieces are not the same as before (a part that changed shape cannot be trusted to mean the
same pieces), and the notes say which, so the sketch is never left broken.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import ArcDirection
from .constants import POINT_TOLERANCE
from .model import Sketch
from .relations import relation_for
from .solver import solve


@dataclass(frozen=True)
class LockedPoint:
    key: str
    x: float
    z: float


@dataclass(frozen=True)
class LockedLine:
    key: str
    start: str  # the keys of two locked points
    end: str


@dataclass(frozen=True)
class LockedArc:
    key: str
    centre: str  # the keys of three locked points
    start: str
    end: str
    direction: ArcDirection = ArcDirection.CCW


def group_of(key: str) -> str:
    """The part of a key before the first '/' ('' for a key without one)."""
    return key.split("/", 1)[0] if "/" in key else ""


def sync_locked(
    sketch: Sketch, points: tuple[LockedPoint, ...], lines: tuple[LockedLine, ...], arcs: tuple[LockedArc, ...] = (),
) -> list[str]:
    """Make the locked things of the sketch what the lists say. Returns notes for the user (empty: nothing was lost)."""
    before = dict(sketch.constraints)
    notes = _forget_changed_groups(sketch, points, lines, arcs)
    wanted_lines = {line.key for line in lines}
    for key in [k for k in sketch.locked_lines if k not in wanted_lines]:
        sketch.lines.pop(sketch.locked_lines.pop(key), None)
    wanted_arcs = {arc.key for arc in arcs}
    for key in [k for k in sketch.locked_arcs if k not in wanted_arcs]:
        sketch.arcs.pop(sketch.locked_arcs.pop(key), None)
    wanted_points = {point.key for point in points}
    for key in [k for k in sketch.locked_points if k not in wanted_points]:
        del sketch.locked_points[key]  # a point that a normal piece uses stays as an ordinary point
    for point in points:
        point_id = sketch.locked_points.get(point.key)
        if point_id is None or point_id not in sketch.points:
            sketch.locked_points[point.key] = sketch.add_point(point.x, point.z)
        else:
            sketch.move_point(point_id, point.x, point.z)
    for line in lines:
        start, end = sketch.locked_points[line.start], sketch.locked_points[line.end]
        line_id = sketch.locked_lines.get(line.key)
        if line_id is not None and line_id in sketch.lines:
            sketch.update_piece(line_id, start=start, end=end, construction=True)
        else:
            sketch.locked_lines[line.key] = sketch.add_line(start, end, construction=True)
    for arc in arcs:
        centre, start, end = (sketch.locked_points[key] for key in (arc.centre, arc.start, arc.end))
        arc_id = sketch.locked_arcs.get(arc.key)
        if arc_id is not None and arc_id in sketch.arcs:
            sketch.update_piece(arc_id, centre=centre, start=start, end=end, direction=arc.direction, construction=True)
        else:
            sketch.locked_arcs[arc.key] = sketch.add_arc(centre, start, end, arc.direction, construction=True)
    sketch.drop_unused_points()  # also forgets the relations of what is gone
    gone = [_note(before[i]) for i in before if i not in sketch.constraints]
    notes += [text for text in gone if text not in notes]
    if not solve(sketch).converged:
        notes += _drop_until_solved(sketch)
    return notes


def _signature(lines: tuple[LockedLine, ...], arcs: tuple[LockedArc, ...]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Per group: which pieces it has, in order (a piece that was a line and is an arc now is another piece)."""
    found: dict[str, list[tuple[str, str]]] = {}
    for kind, items in (("line", lines), ("arc", arcs)):
        for item in items:
            if group_of(item.key):
                found.setdefault(group_of(item.key), []).append((kind, item.key))
    return {group: tuple(pieces) for group, pieces in found.items()}


def _forget_changed_groups(sketch: Sketch, points: tuple[LockedPoint, ...], lines: tuple[LockedLine, ...], arcs: tuple[LockedArc, ...]) -> list[str]:
    """Remove every relation that touches a group whose pieces are not what they were. Remembers the groups for next time."""
    now = _signature(lines, arcs)
    notes: list[str] = []
    for group, old in sketch.locked_groups.items():
        if now.get(group) == old:
            continue
        ids = {i for key, i in sketch.locked_points.items() if group_of(key) == group}
        dropped = [c for c in sketch.constraints.values() if ids & set(sketch.constraint_points(c))]
        for constraint in dropped:
            del sketch.constraints[constraint.constraint_id]
        if dropped:
            notes.append(f"{len(dropped)} dimensions or relations to the {group} were removed: its shape changed")
    sketch.locked_groups = now
    return notes


def _note(constraint) -> str:
    return f"{relation_for(constraint.kind).label} removed: what it referred to is gone or moved"


def _drop_until_solved(sketch: Sketch) -> list[str]:
    """Remove the relations and dimensions that touch a locked point, the newest first, until the sketch solves again."""
    locked = set(sketch.locked_points.values())
    notes: list[str] = []
    for constraint_id in sorted(sketch.constraints, reverse=True):
        constraint = sketch.constraints[constraint_id]
        if not locked & set(sketch.constraint_points(constraint)):
            continue
        sketch.remove_constraint(constraint_id)
        notes.append(_note(constraint))
        if solve(sketch).converged:
            break
    return notes


def locked_changed(before: Sketch, after: Sketch) -> bool:
    """Did a change move, alter or delete something that is locked?"""
    for key, point_id in before.locked_points.items():
        if after.locked_points.get(key) != point_id or point_id not in after.points:
            return True
        if before.points[point_id].position.distance_to(after.points[point_id].position) > POINT_TOLERANCE:
            return True
    for key, line_id in before.locked_lines.items():
        if after.locked_lines.get(key) != line_id or after.lines.get(line_id) != before.lines.get(line_id):
            return True
    for key, arc_id in before.locked_arcs.items():
        if after.locked_arcs.get(key) != arc_id or after.arcs.get(arc_id) != before.arcs.get(arc_id):
            return True
    return False
