"""Turning block, simple form (requirement X6): cylinder with a shoulder, or a taper (a cone) with a shoulder.

OUTSIDE turns a cylinder of the target radius with a shoulder at end_z; the
material outside the radius is removed. INSIDE bores to the target radius
with a flat bottom at end_z; the material inside the radius is removed.
Roughing passes run along Z or along X, then one finishing pass follows the
finished outline, including the optional corner treatments. The outline begins
at the Start Z (with auto: where the material of the block begins, worked out
at every plan), so the start corner lies on that edge; the stock in front of
it is not the block's (`BlockContext.front_z`). The outline is
planned as a contour by the contour block (`_as_contour`), the same as a drawn
contour: the analytic planner, outside and inside, along Z and across X.

The taper is its included angle: 0 is a cylinder, a positive angle makes the radius larger towards the chuck. The target radius is the
radius at Z 0 (the form value alone sets the cone, whatever earlier blocks cut).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..constants import (
    EXAMPLE_DEPTH_OF_CUT_MM,
    EXAMPLE_FEED_MM_PER_REV,
    EXAMPLE_FINISH_ALLOWANCE_MM,
    EXAMPLE_FINISH_FEED_MM_PER_REV,
    EXAMPLE_TARGET_RADIUS_MM,
    EXAMPLE_TURNING_LENGTH_MM,
    GEOMETRY_TOLERANCE_MM,
    STRAIGHT_ANGLE_DEG,
    TURNING_TAPER_DEG,
)
from ..contour import SHARP_CORNER, Contour, ContourDefinition, ContourError, Corner, LineStep
from ..contour_solver import solve_contour
from ..geometry import Point, Segment
from ..program_model.operations import BlockBegin, BlockEnd, SpindleSetting
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .turning_common import PassDirection, TurningSide, inside_stock_radius, nose_radius_presets
from ..analytic.far_side import works_on_far_side


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class TurningBlock(Block):
    type_name = "turning"

    side: TurningSide
    target_radius_mm: float
    end_z_mm: float  # shoulder / bottom position (towards the chuck)
    start_z_mm: float = 0.0  # not an input: the form shows here the start edge of the outline the plan worked out (`material_start`, `shown_values`)
    taper_deg: float = TURNING_TAPER_DEG  # included angle; 0: a cylinder, positive: larger towards the chuck (the target radius is at Z 0)
    feed_mm_per_rev: float
    depth_of_cut_mm: float
    pass_direction: PassDirection = PassDirection.ALONG_Z
    start_corner: Corner = SHARP_CORNER
    shoulder_corner: Corner = SHARP_CORNER
    finish_allowance_mm: float = 0
    finish_pass: bool = True  # False: only roughing; what the allowance leaves stays for a later block
    cutter_compensation: bool = False  # the finishing pass is a compensated contour: lead-in, lead-out and the contour points for a post with G41 / G42
    finish_feed_mm_per_rev: float | None = None
    finish_spindle_value: float | None = None  # rpm or m/min as for the spindle; None: as for roughing

    tool_default_fields = ("depth_of_cut_mm", "finish_allowance_mm")

    def with_tool_defaults(self, tool) -> "TurningBlock":
        return nose_radius_presets(self, tool)

    def works_on_far_side(self, tool) -> bool:
        return works_on_far_side(tool, self.side is TurningSide.INSIDE)

    def form_fields(self) -> tuple[str, ...]:
        """The order of the form (the free comment is not shown)."""
        return (
            "name", "side", "pass_direction", "tool_number", "spindle", "target_radius_mm", "start_z_mm", "end_z_mm", "taper_deg",
            "feed_mm_per_rev", "depth_of_cut_mm", "finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev", "finish_spindle_value", "cutter_compensation",
            "start_corner", "shoulder_corner", "coolant",
        )

    def form_same_line(self) -> frozenset[str]:
        return frozenset({"finish_feed_mm_per_rev", "finish_spindle_value"})  # next to "Finishing pass"

    def form_labels(self) -> dict[str, str]:
        return {"start_z_mm": "Start Z"}

    def form_disabled(self) -> frozenset[str]:
        off = {"start_z_mm"}  # the block works it out: it begins where its material begins
        if not self.finish_pass:
            off |= {"finish_feed_mm_per_rev", "finish_spindle_value", "cutter_compensation"}
        return frozenset(off)

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "TurningBlock":
        return cls(
            block_id=block_id, name="Turning", tool_number=tool_number, spindle=spindle,
            side=TurningSide.OUTSIDE, target_radius_mm=EXAMPLE_TARGET_RADIUS_MM,
            end_z_mm=-EXAMPLE_TURNING_LENGTH_MM, feed_mm_per_rev=EXAMPLE_FEED_MM_PER_REV,
            depth_of_cut_mm=EXAMPLE_DEPTH_OF_CUT_MM,
            finish_allowance_mm=EXAMPLE_FINISH_ALLOWANCE_MM,
            finish_feed_mm_per_rev=EXAMPLE_FINISH_FEED_MM_PER_REV,
        )

    def __post_init__(self) -> None:
        if self.target_radius_mm <= 0:
            raise BlockError("target radius must be greater than zero")
        if not -STRAIGHT_ANGLE_DEG < self.taper_deg < STRAIGHT_ANGLE_DEG:
            raise BlockError(f"the taper (its included angle) must lie between -{STRAIGHT_ANGLE_DEG:g} and {STRAIGHT_ANGLE_DEG:g} degrees")
        if self.feed_mm_per_rev <= 0 or self.depth_of_cut_mm <= 0:
            raise BlockError("feed and depth of cut must be greater than zero")
        if self.finish_allowance_mm < 0:
            raise BlockError("finishing allowance must not be negative")
        if self.finish_feed_mm_per_rev is not None and self.finish_feed_mm_per_rev <= 0:
            raise BlockError("finishing feed must be greater than zero")
        if self.finish_spindle_value is not None and self.finish_spindle_value <= 0:
            raise BlockError("the finishing spindle speed must be greater than zero")

    # --- outline ------------------------------------------------------------

    def radius_at(self, z: float) -> float:
        """The finished radius at `z`: the target radius at Z 0, larger towards the chuck by a positive taper."""
        return self.target_radius_mm - z * math.tan(math.radians(self.taper_deg) / 2)

    def _outline(self, stock_radius: float, clearance: float, sign: int, start_z: float) -> list[Segment]:
        """Segments of the finished outline. The first one is the face line, which is not cut."""
        front, back = self.radius_at(start_z), self.radius_at(self.end_z_mm)
        if min(front, back) <= GEOMETRY_TOLERANCE_MM:
            raise BlockError(f"turning outline: the taper reaches the axis (radius {front:g} mm at the front, {back:g} mm at the end)")
        face_start = front - sign * (self.start_corner.size_mm + clearance)
        steps = [LineStep(Point(front, start_z), self.start_corner), LineStep(Point(back, self.end_z_mm), self.shoulder_corner), LineStep(Point(stock_radius, self.end_z_mm))]
        if sign * (stock_radius - back) <= GEOMETRY_TOLERANCE_MM:  # the cone leaves the stock before the end: there is no shoulder to cut
            steps = steps[:1] + [LineStep(Point(back, self.end_z_mm))]
        definition = ContourDefinition(Point(max(face_start, 0), start_z), tuple(steps))
        try:
            return solve_contour(definition)
        except ContourError as error:
            raise BlockError(f"turning outline: {error}") from error

    def material_start(self, residual: Region, sign: int, max_z: float) -> float | None:
        """The highest Z where material stands beyond the finished outline (outside it, or inside it for a bore), between the front and the
        end Z: where the material of this block begins. None when no material stands beyond it."""
        bounds = residual.bounds
        if bounds is None or self.end_z_mm >= max_z - GEOMETRY_TOLERANCE_MM:
            return None
        far = max(bounds.max_x, self.radius_at(max_z), self.radius_at(self.end_z_mm)) + 1 if sign > 0 else 0.0  # beyond the material and the cone, or the axis
        cone = Region.from_points([
            Point(self.radius_at(max_z), max_z), Point(self.radius_at(self.end_z_mm), self.end_z_mm), Point(far, self.end_z_mm), Point(far, max_z),
        ])
        beyond = residual.intersection(cone)
        if beyond.area <= GEOMETRY_TOLERANCE_MM:
            return None
        return beyond.bounds.max_z

    def start_z(self, residual: Region, sign: int) -> float | None:
        """The start edge of the outline: where the material of the block begins (None: none stands beyond the outline)."""
        bounds = residual.bounds
        return None if bounds is None else self.material_start(residual, sign, bounds.max_z)

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        """The finished outline from the form values: the start corner, the target, the shoulder with its corner, without the face line."""
        bounds = context.residual.bounds
        if bounds is None:
            return ()
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        stock_radius = bounds.max_x if sign > 0 else inside_stock_radius(context.residual, self.end_z_mm, bounds.max_z)
        start_z = self.start_z(context.residual, sign)
        try:
            return tuple(self._outline(stock_radius, context.safety.clearance_mm, sign, bounds.max_z if start_z is None else start_z)[1:])
        except BlockError:
            return ()

    # --- generation -----------------------------------------------------------

    def _as_contour(self, path: list[Segment], context: BlockContext, front_z: float | None = None) -> BlockResult:
        """The block planned as a contour block on its outline (the target radius, the shoulder with its corners, up to the stock): the
        roughing of the analytic planner. The moves keep the name and the type of this block. `front_z`: where the material of the block
        begins (its start edge): the stock in front of it is not the block's (it would be removed down to where the outline begins)."""
        from .turning_contour import ContourTurningBlock  # late: the contour block is a neighbour

        contour = Contour(contour_id=f"{self.block_id}:outline", name=self.name, segments=tuple(path))
        twin = ContourTurningBlock(
            block_id=self.block_id, tool_number=self.tool_number, spindle=self.spindle, coolant=self.coolant, name=self.name,
            contour_id=contour.contour_id, side=self.side, feed_mm_per_rev=self.feed_mm_per_rev, depth_of_cut_mm=self.depth_of_cut_mm,
            pass_direction=self.pass_direction, finish_allowance_mm=self.finish_allowance_mm, finish_pass=self.finish_pass,
            cutter_compensation=self.cutter_compensation, finish_feed_mm_per_rev=self.finish_feed_mm_per_rev,
            finish_spindle_value=self.finish_spindle_value,
        )
        result = twin.generate(replace(context, contours=(*context.contours, contour), front_z=front_z))
        operations = tuple(
            replace(operation, type_name=self.type_name) if isinstance(operation, BlockBegin) else operation for operation in result.operations
        )
        return replace(result, operations=operations)

    def _from_start(self, context: BlockContext, stock_radius: float, sign: int, empty: BlockResult) -> BlockResult:
        """The block planned as a contour block on its outline from the start edge (`start_z`), with the notes about the start."""
        residual = context.residual
        begins = self.start_z(residual, sign)
        name = self.name or self.type_name
        if begins is None:
            return BlockResult(empty.operations, empty.removed, ("turning: the material is already at or beyond the target radius",))
        notes = [f"{name}: Start Z: {begins:.2f}, the edge of the material"]
        result = self._as_contour(self._outline(stock_radius, context.safety.clearance_mm, sign, begins)[1:], context, begins)  # the face line is not cut
        return replace(result, messages=(*notes, *result.messages), shown_values=(("start_z_mm", begins),))  # the greyed field shows it

    def generate(self, context: BlockContext) -> BlockResult:
        """The moves of the block: planned as a contour block on its outline from the start edge (`_from_start`)."""
        residual = context.residual
        bounds = residual.bounds
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        empty = BlockResult((BlockBegin(0, self.block_id, self.type_name, self.name),
                             BlockEnd(self.block_id)), Region.empty())
        if bounds is None:
            return BlockResult(empty.operations, empty.removed, ("turning: no material left",))
        stock_radius = bounds.max_x if sign > 0 else inside_stock_radius(residual, self.end_z_mm, bounds.max_z)
        nearest = min(sign * self.radius_at(bounds.max_z), sign * self.radius_at(self.end_z_mm)) * sign  # the finished radius nearest the stock
        if sign * (stock_radius - nearest) <= GEOMETRY_TOLERANCE_MM:
            note = "turning: the material is already at or beyond the target radius"
            return BlockResult(empty.operations, empty.removed, (note,))

        start_z = bounds.max_z  # the cut starts at the front face of the material
        if self.end_z_mm >= start_z - GEOMETRY_TOLERANCE_MM:
            note = "turning: the end position is not behind the front face of the material"
            return BlockResult(empty.operations, empty.removed, (note,))
        return self._from_start(context, stock_radius, sign, empty)
