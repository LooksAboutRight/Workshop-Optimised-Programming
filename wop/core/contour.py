"""Contour data model: what the user enters and what the solver returns.

A ContourDefinition is a chain: a start point and a list of steps. Every step
ends at a point (requirement C2):

- Corner style: a corner between two straight lines is given by the
  theoretical intersection point plus a fillet radius or a chamfer size.
- Arc style: an arc is given by its end point plus radius (or center).

The solver (contour_solver.py) turns a definition into exact segments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .geometry import ArcDirection, Point, Segment


class ContourError(ValueError):
    """The contour input or geometry cannot be used; `index` points at the element."""

    def __init__(self, message: str, index: int | None = None) -> None:
        super().__init__(message)
        self.index = index


class CornerKind(Enum):
    NONE = "none"
    FILLET = "fillet"
    CHAMFER = "chamfer"


@dataclass(frozen=True)
class Corner:
    """Treatment of the vertex at the end of a line step.

    size_mm is the fillet radius, or the chamfer length measured along each line.
    """

    kind: CornerKind = CornerKind.NONE
    size_mm: float = 0


SHARP_CORNER = Corner()


def fillet(radius_mm: float) -> Corner:
    return Corner(CornerKind.FILLET, radius_mm)


def chamfer(size_mm: float) -> Corner:
    return Corner(CornerKind.CHAMFER, size_mm)


NO_CONTOUR = ""  # the contour field of a block that has none yet (C10)

@dataclass(frozen=True)
class LineStep:
    """Straight line to `end`. `corner` applies at `end`, between this line and the next."""

    end: Point
    corner: Corner = SHARP_CORNER
    cutting: bool = False  # a cutting edge of a tool shape (may touch the material); not used by part contours


@dataclass(frozen=True)
class ArcRadiusStep:
    """Arc to `end` with a known radius; large_arc picks the arc over half a circle."""

    end: Point
    radius_mm: float
    direction: ArcDirection
    large_arc: bool = False
    cutting: bool = False


@dataclass(frozen=True)
class ArcCenterStep:
    """Arc to `end` around a known center (also used for a full circle)."""

    end: Point
    center: Point
    direction: ArcDirection
    cutting: bool = False


Step = LineStep | ArcRadiusStep | ArcCenterStep


@dataclass(frozen=True)
class NamedPoint:
    """A point with a name next to the lines and arcs (a tool's reference point, tip and so on)."""

    name: str
    x: float = 0
    z: float = 0

    @property
    def position(self) -> Point:
        return Point(self.x, self.z)


@dataclass(frozen=True)
class ContourDefinition:
    """`closed`: the shape ends where it starts; a straight line is added from the last point to the start if needed.

    `points` are named points that belong to the shape (they are not part of the chain).
    """

    start: Point
    steps: tuple[Step, ...]
    closed: bool = False
    points: tuple[NamedPoint, ...] = ()


@dataclass(frozen=True)
class Contour:
    """A named contour with its solved geometry.

    `definition` is kept so the editor can change it later; it is None for
    contours that come from a DXF file.
    """

    contour_id: str
    name: str
    segments: tuple[Segment, ...]
    definition: ContourDefinition | None = None
    error: str = ""  # why the definition does not solve (requirement C10); the segments are empty then
    cutting: tuple[bool, ...] = ()  # per segment: is it a cutting edge (tool shapes); empty = none is
    points: tuple[NamedPoint, ...] = ()
    sketch: dict | None = field(default=None, hash=False)  # the sketch it was made from (plain data), so it can be edited again

    @property
    def is_valid(self) -> bool:
        return not self.error and bool(self.segments)

    @property
    def is_closed(self) -> bool:
        return bool(self.segments) and self.segments[-1].end.is_close(self.segments[0].start)
