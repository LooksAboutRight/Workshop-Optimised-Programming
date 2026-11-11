"""Tool shape model (requirement: tools are defined with the contour editor).

A tool is one closed outline made of lines and arcs. Each piece is tagged as
CUTTER (may touch material) or HOLDER (must never touch material). The outline
is stored with the tool tip at the origin (0, 0) of the tool; positioning it
on the machine is done by the reach and collision checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from ..constants import GEOMETRY_TOLERANCE_MM, THREAD_FLANK_HALF_ANGLE_DEG
from ..contour import NamedPoint
from ..geometry import Segment


class ToolError(ValueError):
    """The tool data is not usable."""


class ToolSegmentRole(Enum):
    CUTTER = "cutter"
    HOLDER = "holder"


@dataclass(frozen=True)
class ToolSegment:
    segment: Segment
    role: ToolSegmentRole


@dataclass(frozen=True)
class ToolShape:
    """Closed outline, in order, each piece starting where the last ended."""

    pieces: tuple[ToolSegment, ...]

    def __post_init__(self) -> None:
        if not self.pieces:
            raise ToolError("a tool shape needs at least one segment")
        for index, (first, second) in enumerate(zip(self.pieces, self.pieces[1:])):
            if not first.segment.end.is_close(second.segment.start, GEOMETRY_TOLERANCE_MM):
                raise ToolError(f"tool shape is not connected after segment {index}")
        if not self.pieces[-1].segment.end.is_close(
            self.pieces[0].segment.start, GEOMETRY_TOLERANCE_MM
        ):
            raise ToolError("tool shape is not closed")

    @property
    def segments(self) -> list[Segment]:
        return [piece.segment for piece in self.pieces]

    @property
    def cutter_segments(self) -> list[Segment]:
        return [p.segment for p in self.pieces if p.role is ToolSegmentRole.CUTTER]

    @property
    def holder_segments(self) -> list[Segment]:
        return [p.segment for p in self.pieces if p.role is ToolSegmentRole.HOLDER]


class ToolMaterial(Enum):
    """What the cutting part is made of (requirement T10); later used to suggest cutting data (T11)."""

    HSS = "HSS"
    CARBIDE = "carbide"
    COATED_CARBIDE = "coated carbide"
    CERMET = "cermet"
    CERAMIC = "ceramic"


def nose_radius_of(shape: ToolShape) -> float:
    """The smallest radius of an arc on the cutting edge (the nose radius); 0 when the cutting edge has no arc."""
    from ..geometry import ArcSegment

    radii = [s.center.distance_to(s.start) for s in shape.cutter_segments if isinstance(s, ArcSegment)]
    return min(radii) if radii else 0


def flank_half_angle_deg(shape: ToolShape) -> float:
    """The half angle of the cutting flanks of a threading tool, measured from the radial direction (X).

    Taken from the straight cutting edges that are neither radial nor axial; the larger one counts when the two differ,
    so that the run-out of the tool beyond the thread ends is never underestimated. A shape without such an edge
    (a drawn tool that is not a V) gets the standard 60 degree thread value.
    """
    from ..geometry import LineSegment

    angles = []
    for segment in shape.cutter_segments:
        if isinstance(segment, LineSegment):
            dx, dz = abs(segment.end.x - segment.start.x), abs(segment.end.z - segment.start.z)
            if dx > GEOMETRY_TOLERANCE_MM and dz > GEOMETRY_TOLERANCE_MM:
                angles.append(math.degrees(math.atan2(dz, dx)))
    return max(angles) if angles else THREAD_FLANK_HALF_ANGLE_DEG


def flank_angles_by_side(shape: ToolShape, tip_z: float = 0) -> tuple[float, float]:
    """The angles from the radial direction (X) of the cutting flanks of a threading tool on the smaller-Z side and on the
    larger-Z side of `tip_z` (the reference point of the tool: 0 for a tool that has its tip at the origin).

    A flank that runs straight along X has the angle 0. A side without a flank (a drawn tool that is not a V) gets the
    standard 60 degree thread value. Where a side has several, the larger angle counts (the run-out is never underestimated).
    """
    from ..geometry import LineSegment

    found: dict[bool, list[float]] = {False: [], True: []}  # larger-Z side?
    for segment in shape.cutter_segments:
        if isinstance(segment, LineSegment):
            dx, dz = abs(segment.end.x - segment.start.x), abs(segment.end.z - segment.start.z)
            if dx > GEOMETRY_TOLERANCE_MM:
                found[(segment.start.z + segment.end.z) / 2 > tip_z + GEOMETRY_TOLERANCE_MM].append(math.degrees(math.atan2(dz, dx)))
    low, high = (max(found[side]) if found[side] else THREAD_FLANK_HALF_ANGLE_DEG for side in (False, True))
    return low, high


def flank_reach_by_side(shape: ToolShape, depth: float, tip_z: float = 0) -> tuple[float, float]:
    """How far the cutting flanks of a threading tool reach to the smaller-Z side and to the larger-Z side of `tip_z` when
    the tip is `depth` below the thread crest: the flank lines taken to that height above the tip. A rounded tip is
    narrower at the tip than a sharp V and reaches a little further out higher up, which this includes (a sharp V gives
    depth times the tangent of the flank angle). A side without a flank gets the value of the standard 60 degree thread."""
    from ..geometry import LineSegment

    found: dict[bool, list[float]] = {False: [], True: []}  # larger-Z side?
    for segment in shape.cutter_segments:
        if isinstance(segment, LineSegment):
            start_u, end_u = abs(segment.start.x), abs(segment.end.x)
            if abs(end_u - start_u) > GEOMETRY_TOLERANCE_MM:
                z = segment.start.z + (depth - start_u) / (end_u - start_u) * (segment.end.z - segment.start.z)
                found[(segment.start.z + segment.end.z) / 2 > tip_z + GEOMETRY_TOLERANCE_MM].append(abs(z - tip_z))
    standard = depth * math.tan(math.radians(THREAD_FLANK_HALF_ANGLE_DEG))
    low, high = (max(found[side]) if found[side] else standard for side in (False, True))
    return low, high


@dataclass(frozen=True)
class Tool:
    number: int
    name: str
    shape: ToolShape
    material: ToolMaterial = ToolMaterial.CARBIDE
    kind: str = ""  # the tool type that made it (tool_types); empty for a tool that was drawn or loaded as a shape only
    definition: dict | None = field(default=None, hash=False)  # the entries of that type's form, as plain data
    points: tuple[NamedPoint, ...] = ()  # named points of the tool (reference point, tip ...), in the tool's coordinates
    offset_number: int | None = None  # the tool offset the post calls after a tool change (G43 H..); None: the tool number
    sketch: dict | None = field(default=None, hash=False, compare=False)  # the sketch the shape was drawn in (plain data), for editing again
    origin_library: str = ""  # the tool library this tool was copied from (T19); empty: made in the project
    origin_name: str = ""  # ... and the name it had there

    @property
    def nose_radius_mm(self) -> float:
        """The nose radius of the cutting edge: its smallest arc (0 for a sharp tool)."""
        return nose_radius_of(self.shape)
