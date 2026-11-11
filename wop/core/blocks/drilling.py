"""Drilling block (requirement B3): a hole on the spindle axis.

The tool stands on the axis and feeds towards the chuck from the clearance in front of the material
to depth_z_mm (an absolute Z, normally negative), stays there for the dwell time and rapids out to the
safe Z. The hole starts at the front face of the material. Modes: drilling (one stroke); peck drilling
(pecks, after each one the drill goes back only to where that peck began); peck drilling with full
retract (back to the start every time). After a retract the drill rapids in to a little above the last
depth. The depth is measured either to where the hole has its full diameter (the point of the drill goes
deeper, the hole bottom is a cone) or to the tip of the drill. Where an earlier drill has made a hole
already, the drill rapids through it to the clearance above the first material and feeds from there. The hole radius is the radius of the drill (the largest radius of
its cutter pieces). The tool is checked along the way; if it cannot get to the full depth the hole
stays shorter and the rest is reported.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    DRILL_AIR_SKIP_MIN_MM,
    EXAMPLE_DRILL_DEPTH_MM,
    EXAMPLE_DRILL_DWELL_S,
    EXAMPLE_DRILL_FEED_MM_PER_REV,
    EXAMPLE_DRILL_MODE,
    EXAMPLE_DRILL_PECK_MM,
    EXAMPLE_DRILL_TO_FULL_DIAMETER,
    GEOMETRY_TOLERANCE_MM,
    MAX_PASS_LEVELS,
)
from ..geometry import LineSegment, Point, Segment
from ..program_model.operations import BlockBegin, BlockEnd, DrillMode, DrillOperation, Rapid, SpindleSetting
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .sweep import Sweeper
from .uncut import report_uncut


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class DrillingBlock(Block):
    type_name = "drilling"

    depth_z_mm: float  # absolute Z (normally negative): where the hole has its full diameter, or the drill tip
    depth_to_full_diameter: bool = True  # True: the point of the drill goes deeper; False: the tip reaches the depth
    feed_mm_per_rev: float
    drill_mode: DrillMode = DrillMode.DRILL
    peck_depth_mm: float | None = None  # used by the two peck modes
    dwell_s: float = 0  # at the bottom of the hole

    def form_fields(self) -> tuple[str, ...]:
        """The order of the form (the free comment is not shown)."""
        return (
            "name", "drill_mode", "tool_number", "spindle", "feed_mm_per_rev", "depth_z_mm", "depth_to_full_diameter",
            "peck_depth_mm", "dwell_s", "coolant",
        )

    def form_disabled(self) -> frozenset[str]:
        return frozenset({"peck_depth_mm"}) if self.drill_mode is DrillMode.DRILL else frozenset()

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "DrillingBlock":
        mode = next((m for m in DrillMode if m.value == EXAMPLE_DRILL_MODE), DrillMode.PECK)
        return cls(
            block_id=block_id, name="Drill", tool_number=tool_number, spindle=spindle,
            depth_z_mm=-EXAMPLE_DRILL_DEPTH_MM, depth_to_full_diameter=EXAMPLE_DRILL_TO_FULL_DIAMETER == "yes",
            feed_mm_per_rev=EXAMPLE_DRILL_FEED_MM_PER_REV, drill_mode=mode,
            peck_depth_mm=None if mode is DrillMode.DRILL else EXAMPLE_DRILL_PECK_MM, dwell_s=EXAMPLE_DRILL_DWELL_S,
        )

    def __post_init__(self) -> None:
        if self.drill_mode is not DrillMode.DRILL and self.peck_depth_mm is None:  # switched to a peck mode with no peck depth: the preset
            object.__setattr__(self, "peck_depth_mm", EXAMPLE_DRILL_PECK_MM)
        if self.feed_mm_per_rev <= 0:
            raise BlockError("feed must be greater than zero")
        if self.peck_depth_mm is not None and self.peck_depth_mm <= 0:
            raise BlockError("the peck depth must be greater than zero")
        if self.dwell_s < 0:
            raise BlockError("the dwell time must not be negative")

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        """The hole: its wall and the cone of the point."""
        bounds = context.residual.bounds
        points = [p for seg in context.tool.shape.cutter_segments for p in (seg.start, seg.end)]
        radius = max(p.x for p in points)
        if bounds is None or radius <= GEOMETRY_TOLERANCE_MM:
            return ()
        point_height = min(p.z for p in points if p.x >= radius - GEOMETRY_TOLERANCE_MM)
        if self.depth_to_full_diameter:
            end_z, tip_z = self.depth_z_mm, self.depth_z_mm - point_height
        else:
            tip_z, end_z = self.depth_z_mm, self.depth_z_mm + point_height
        if end_z >= bounds.max_z - GEOMETRY_TOLERANCE_MM:
            return ()
        return (
            LineSegment(Point(radius, bounds.max_z), Point(radius, end_z)),
            LineSegment(Point(radius, end_z), Point(0, tip_z)),
        )

    def generate(self, context: BlockContext) -> BlockResult:
        """The drilling moves of the hole, or a note when there is no material left or the tool cannot drill."""
        header = BlockBegin(0, self.block_id, self.type_name, self.name)
        footer = BlockEnd(self.block_id)
        residual = context.residual
        bounds = residual.bounds
        nothing = BlockResult((header, footer), Region.empty())
        if bounds is None:
            return BlockResult(nothing.operations, nothing.removed, ("drilling: no material left",))
        points = [p for seg in context.tool.shape.cutter_segments for p in (seg.start, seg.end)]
        radius = max(p.x for p in points)
        if radius <= GEOMETRY_TOLERANCE_MM:
            raise BlockError("the tool has no radius, it cannot drill")
        point_height = min(p.z for p in points if p.x >= radius - GEOMETRY_TOLERANCE_MM)
        start_z = bounds.max_z  # the hole starts at the front face of the material
        if self.depth_to_full_diameter:
            end_z = self.depth_z_mm
            tip_z = end_z - point_height
        else:
            tip_z = self.depth_z_mm
            end_z = tip_z + point_height
        if end_z >= start_z - GEOMETRY_TOLERANCE_MM:
            return BlockResult(nothing.operations, nothing.removed, ("drilling: the depth is not behind the front face",))
        hole = Region.from_points(
            [Point(0, tip_z), Point(radius, end_z), Point(radius, start_z), Point(0, start_z)]
        )
        planned = residual.intersection(hole)
        if planned.is_empty:
            return BlockResult(nothing.operations, nothing.removed, ("drilling: nothing to remove",))

        clearance = context.safety.clearance_mm
        safe_radius = context.safety.safe_radius_mm
        retract_z = start_z + clearance
        safe_z = max(context.safety.safe_z_mm, retract_z)
        sweeper = Sweeper(context, residual.difference(planned))
        air_z = max(sweeper.air_line(Point(0, retract_z), Point(0, tip_z)).z + clearance, tip_z)  # a hole is there already
        reached, collision = sweeper.follow_line(Point(0, retract_z), Point(0, tip_z))  # as asked: always to the depth
        notes = () if collision is None else (
            "drilling: the tool collides on the way down; it is drilled as asked, see the problem list",
        )
        way_in = [Rapid(Point(0, safe_z))]  # the block starts at the safe point: first X to the axis, then Z down
        if safe_z - retract_z > GEOMETRY_TOLERANCE_MM:
            way_in.append(Rapid(Point(0, retract_z)))
        air = air_z if air_z < retract_z - DRILL_AIR_SKIP_MIN_MM else None
        end_z = reached[-1].z
        if self.drill_mode is not DrillMode.DRILL and self.peck_depth_mm is not None and (start_z - end_z) / self.peck_depth_mm > MAX_PASS_LEVELS:
            raise BlockError(
                f"a hole of {start_z - end_z:g} mm drilled in pecks of {self.peck_depth_mm:g} mm would need more than {MAX_PASS_LEVELS} pecks: check the peck depth"
            )
        stroke = [DrillOperation(  # the pecks of the form: the post may write a drilling cycle
            retract_z, end_z, self.feed_mm_per_rev, self.peck_depth_mm, self.drill_mode, self.dwell_s, exit_z=safe_z, entry_z=start_z, air_z=air,
        )]
        operations = (header, *way_in, *stroke, Rapid(Point(safe_radius, safe_z)), footer)
        removed, messages = report_uncut(self.name or self.type_name, planned, sweeper.current)
        return BlockResult(operations, removed, (*notes, *messages))
