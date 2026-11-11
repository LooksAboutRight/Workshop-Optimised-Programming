"""The styles of the turning contour block: in which order the roughing lines are cut.

The block works out the roughing lines (the layers of the open part and of the pockets behind walls) and cuts every line with all its
rules: the way over a bump, the ramp or diagonal entry to a pocket, the back clearance of the tool, no plunge through uncut stock. A style does
NOT make moves. It is asked about every line the block finds, in the order the block finds them (level by level, from the front), and says:
- when to cut it: now, or (a pocket line only) after all the open lines, and in what order the late lines are cut.
The way between the lines is the planner's (over the material at one clearance, X12).

A style is a function `plan(line) -> Cut`. The block keeps everything else: what is cut, the finishing pass, the checks of the tool. The
styles are part of the program (the user's decision, 2026-10-25: no style files): "standard" and "pockets last".
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM
from .styles import STYLES, StyleInfo

ROUGHING = "turning_contour"  # the block type these styles belong to
OPEN, POCKET = "open", "pocket"  # the kinds of a roughing line


@dataclass(frozen=True)
class RoughLine:
    """One roughing line the block has found. Lengths in mm, Z absolute (behind the front face it is negative), X a radius."""

    level: int  # 0 for the first (highest) level, then 1, 2 ...
    radius: float  # the X radius of the line (of the layer)
    z_high: float  # where the line starts: the end nearer the face
    z_low: float  # where it ends: the end nearer the chuck
    kind: str  # "open": reached from the front; "pocket": starts behind a wall (a crest) and is entered from above
    pocket: int  # for a pocket line: the number of its pocket (0, 1 ... in the order the pockets are found, front first); else -1
    layer: int  # for a pocket line: 0 for the first layer of its pocket, then 1, 2 ...; else -1


@dataclass(frozen=True)
class Cut:
    """What a style says about one roughing line.

    `later` True (a pocket line only): the line is not cut now but after all the open lines. A pocket whose first line is cut later has all its
    lines cut later (the block does that). `order`: the lines that are cut later go in the order of this key (a tuple of numbers; lines
    with the same key in the order they were found); the layers of one pocket must stay in their order. (The routes are always over the material at one
    clearance, X12.)
    """

    later: bool = False
    order: tuple[float, ...] = ()


class RoughStyleError(ValueError):
    pass


def checked_cut(line: RoughLine, cut: object, style: str) -> Cut:
    """The contract of a roughing style for one line. Raises RoughStyleError with the reason."""
    where = f"style {style!r}, {line.kind} line at radius {line.radius:g}, Z {line.z_high:g} to {line.z_low:g}"
    if not isinstance(cut, Cut):
        raise RoughStyleError(f"{where}: plan must return a Cut")
    if cut.later and line.kind != POCKET:
        raise RoughStyleError(f"{where}: only a pocket line can be cut later")
    if not all(isinstance(part, (int, float)) for part in cut.order):
        raise RoughStyleError(f"{where}: order must be a tuple of numbers")
    return cut


def style_sequence(lines: list, function, key: str) -> tuple[list[int], set[int]]:
    """The order in which a style has the analytic planner cut its lines (`analytic.wanted_lines.WantedLine`, sorted level by level from the
    front): the numbers of the lines cut now, in their order, then the ones the style keeps for later in the order of their `Cut.order` (a
    pocket whose first line is kept for later is kept for later as a whole; the layers of a pocket must stay in their order). Returns (that
    order, the numbers kept for later). The numbers the style sees are those of the planner (an inside block or a left-hand tool is planned
    mirrored). A style that stops or answers wrongly is a RoughStyleError."""
    levels = sorted({round(line.high.x / GEOMETRY_TOLERANCE_MM) for line in lines}, reverse=True)
    rank = {value: index for index, value in enumerate(levels)}
    now: list[int] = []
    later: list[tuple[tuple[float, ...], int, int, object]] = []
    held: set[int] = set()  # the pockets kept for later
    for number, line in enumerate(lines):
        rough = RoughLine(rank[round(line.high.x / GEOMETRY_TOLERANCE_MM)], line.high.x, line.high.z, line.low.z, line.kind.value, line.pocket, line.layer)
        try:
            answer = function(rough)
        except Exception as error:  # noqa: BLE001 - whatever goes wrong in a style is a reason for the block, not a crash
            raise RoughStyleError(f"style {key!r} stopped with {type(error).__name__}: {error}") from error
        cut = checked_cut(rough, answer, key)
        if cut.later or (rough.kind == POCKET and line.pocket in held):
            held.add(line.pocket)
            later.append((cut.order or (line.pocket, line.layer), len(later), number, line))
        else:
            now.append(number)
    later.sort(key=lambda entry: (entry[0], entry[1]))
    last_layer: dict[int, int] = {}
    for _order, _found, _number, line in later:
        if line.pocket in last_layer and line.layer < last_layer[line.pocket]:
            raise RoughStyleError(f"style {key!r}: the layers of a pocket must be cut in their order (layer {line.layer} after layer {last_layer[line.pocket]})")
        last_layer[line.pocket] = line.layer
    return now + [number for _order, _found, number, _line in later], {number for _order, _found, number, _line in later}


def standard_plan(line: RoughLine) -> Cut:
    """The standard style: every line when it is found."""
    return Cut()


def pockets_last_plan(line: RoughLine) -> Cut:
    """All the open lines first, then every pocket by itself, layer by layer, front pocket first."""
    if line.kind == POCKET:
        return Cut(later=True, order=(line.pocket, line.layer))
    return Cut()


STYLES.register(ROUGHING, StyleInfo(
    "standard", "Standard",
    "Every roughing line is cut when it is found, level by level from the front, pockets and open lines taken together.", standard_plan,
))
STYLES.register(ROUGHING, StyleInfo(
    "pockets_last", "Pockets last",
    "Cuts all open lines first, then each pocket by itself, layer by layer, front pocket first.", pockets_last_plan,
))
