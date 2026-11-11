"""The cut list of a roughing block: the cuts in the order they are made (`Cut`) and the whole result (`RoughingCuts`)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..geometry import Point, Segment
from ..geometry.chains import Loop
from .wanted_lines import WantedLine


class CutKind(Enum):
    LINE = "line"  # a stretch of a wanted line
    DIP = "dip"  # the pass along the contour under a line with no line below it


@dataclass(frozen=True)
class Cut:
    """One cut of the list. The tool is at `start` when it begins to cut (the side the cut comes from: the front, for a line along Z) and at
    `end` when the stretch is cut; `ride` is the way on from `end` along the contour (empty at an open end). A dip pass has `start == end`
    and all its moves in `ride`."""
    start: Point
    end: Point
    ride: tuple[Segment, ...]
    source: WantedLine  # the wanted line it belongs to (`source.open_high` tells whether a wall stands at the start)
    kind: CutKind = CutKind.LINE
    joined: bool = False  # begins where the cut before ended (over a bump): no entry of its own
    entry: tuple[Segment, ...] = ()  # the way in to `start`, feed moves: from a clearance away in the air, along the contour at a wall, to `start`
    retreat: tuple[Segment, ...] = ()  # feed moves before the rapid: back along the path of the cut before (the tool is in a notch it cannot rapid out of), and the rise out of the clearance (X12)
    rapid: tuple[Segment, ...] = ()  # the rapid moves from where the cut before ended (or the retreat) to where the way in begins (none for the first cut and a joined one)
    plunged: bool = False  # the way in goes straight into the material (no way in from the air): at the plunge feed


@dataclass(frozen=True)
class RoughingCuts:
    cuts: tuple[Cut, ...]  # in the order they are made
    tools: tuple[tuple[Point, ...], ...]  # the outline of the planning tool at the ends of the first and the last stretch
    removed: tuple[Loop, ...]  # the material the cut removes
    residual: tuple[Loop, ...]  # the material after it
    fast_lines: int = 0  # lines whose ends were found from the two ends only
    scanned_lines: int = 0  # lines that needed the contact search
    failed_lines: int = 0  # lines whose removal could not be worked out (the boolean met a coincidence it could not decide): not cut here
    unreachable_lines: int = 0  # stretches the tool cannot be brought to (no way in from the air), and the ones under them: left in the material
    unconnected_cuts: int = 0  # cuts with no free rapid from the end of the cut before to the start of the way in (they have no rapid)
    leave_retreat: tuple[Segment, ...] = ()  # the end of the block: feed moves back along the path of the last cut ...
    leave_rapid: tuple[Segment, ...] = ()  # ... and the rapid to the safe point
    material: tuple[Loop, ...] = ()  # the material when the block begins (what the replay of `replay.py` starts from)
    keep: tuple[Loop, ...] = ()  # the part and its allowance (what no tool may enter)
    wanted: tuple[Loop, ...] = ()  # the region the roughing is to remove (`WantedPlan.removal`)
    clearance: float = 0.0  # the room a rapid keeps from the material (X12)
    both_sides: bool = False  # the material holds both sides of the axis (an inside block): a cut takes the same on the other side
