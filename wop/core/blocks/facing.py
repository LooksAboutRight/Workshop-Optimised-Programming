"""Facing block (requirement X5): take the face down to a flat surface.

Outside in, the face is planned as a contour across X by the contour block (`_as_contour`): the face line at the target from past the centre
(or the bore of a tube) by the overtravel out to the stock, the lines across X of the analytic planner on the material that stands, running
on past the centre by the overtravel. The finishing pass is the block's own (`_finishing`): across X a tool cuts outside in only (its
side towards larger X may be its holder), and the contour block would finish along the face from the centre out. Its way there and away
keeps the clearance from the material (X12). Centre out (`_centre_out`) is passes of its own, made the same way as the finishing pass: turned 90 degrees, the planner would see every outside tool cut with its body in front (it has the wrong hand), so the contour block cannot plan it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ..constants import (
    EXAMPLE_DEPTH_OF_CUT_MM,
    EXAMPLE_FEED_MM_PER_REV,
    FACING_OVERTRAVEL_NOSE_FACTOR,
    GEOMETRY_TOLERANCE_MM,
)
from ..geometry import LineSegment, Point, Segment
from ..program_model.operations import BlockBegin, BlockEnd, LinearMove, Rapid, SetSpindle, SpindleSetting, finishing_spindle
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from ..passes import pass_levels


class FacingDirection(Enum):
    OUTSIDE_IN = "outside in"
    CENTER_OUT = "centre out"


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class FacingBlock(Block):
    type_name = "facing"

    target_z_mm: float  # the finished face
    feed_mm_per_rev: float
    depth_of_cut_mm: float
    direction: FacingDirection = FacingDirection.OUTSIDE_IN
    finish_allowance_mm: float = 0  # what the roughing passes leave on the face
    finish_pass: bool = False  # True: this block also cuts the finishing pass at the target, with the finishing feed
    finish_feed_mm_per_rev: float | None = None  # None: the normal feed
    finish_spindle_value: float | None = None  # rpm or m/min as for the spindle; None: as for roughing
    overtravel_mm: float = 0  # how far the tool runs past the centre (or the bore of a tube); preset: twice the nose radius
    tool_default_fields = ("overtravel_mm",)

    def form_fields(self) -> tuple[str, ...]:
        """The order of the form (the fields the user sees; the free comment is not one of them)."""
        return (
            "name", "direction", "tool_number", "spindle", "target_z_mm", "feed_mm_per_rev", "depth_of_cut_mm",
            "overtravel_mm", "finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev", "finish_spindle_value", "coolant",
        )

    def form_same_line(self) -> frozenset[str]:
        return frozenset({"finish_feed_mm_per_rev", "finish_spindle_value"})  # next to the "Finishing" checkbox

    def form_disabled(self) -> frozenset[str]:
        return frozenset() if self.finish_pass else frozenset({"finish_feed_mm_per_rev", "finish_spindle_value"})

    def with_tool_defaults(self, tool) -> "FacingBlock":
        return replace(self, overtravel_mm=FACING_OVERTRAVEL_NOSE_FACTOR * tool.nose_radius_mm)

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "FacingBlock":
        return cls(
            block_id=block_id, name="Facing", tool_number=tool_number, spindle=spindle,
            target_z_mm=-1, feed_mm_per_rev=EXAMPLE_FEED_MM_PER_REV,
            depth_of_cut_mm=EXAMPLE_DEPTH_OF_CUT_MM,
        )

    def __post_init__(self) -> None:
        if self.feed_mm_per_rev <= 0 or self.depth_of_cut_mm <= 0:
            raise BlockError("feed and depth of cut must be greater than zero")
        if self.overtravel_mm < 0:
            raise BlockError("the overtravel must not be negative")
        if self.finish_allowance_mm < 0:
            raise BlockError("finishing allowance must not be negative")
        if self.finish_feed_mm_per_rev is not None and self.finish_feed_mm_per_rev <= 0:
            raise BlockError("finishing feed must be greater than zero")
        if self.finish_spindle_value is not None and self.finish_spindle_value <= 0:
            raise BlockError("the finishing spindle speed must be greater than zero")

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        bounds = context.residual.bounds
        if bounds is None:
            return ()
        return (LineSegment(Point(bounds.min_x, self.target_z_mm), Point(bounds.max_x, self.target_z_mm)),)

    def _as_contour(self, context: BlockContext) -> BlockResult:
        """The block planned as a contour block across X on its face line (see the module text). The moves keep the name and the type of
        this block."""
        from ..contour import Contour
        from .turning_common import PassDirection, TurningSide
        from .turning_contour import ContourTurningBlock  # late: the contour block is a neighbour

        bounds = context.residual.bounds
        face = LineSegment(Point(bounds.min_x - self.overtravel_mm, self.target_z_mm), Point(bounds.max_x, self.target_z_mm))
        contour = Contour(contour_id=f"{self.block_id}:face", name=self.name, segments=(face,))
        twin = ContourTurningBlock(
            block_id=self.block_id, tool_number=self.tool_number, spindle=self.spindle, coolant=self.coolant, name=self.name,
            contour_id=contour.contour_id, side=TurningSide.OUTSIDE, feed_mm_per_rev=self.feed_mm_per_rev, depth_of_cut_mm=self.depth_of_cut_mm,
            pass_direction=PassDirection.ALONG_X, finish_allowance_mm=self.finish_allowance_mm, finish_pass=False,
        )
        result = twin.generate(replace(context, contours=(*context.contours, contour)), run_on=self.overtravel_mm)
        operations = [replace(operation, type_name=self.type_name) if isinstance(operation, BlockBegin) else operation for operation in result.operations]
        removed = result.removed
        if self.finish_pass:
            end = len(operations) - 1  # before the block end, and instead of the rapid away of the roughing: the finishing goes away itself
            if end > 0 and isinstance(operations[end - 1], Rapid):
                end -= 1
            operations[end:] = [*self._finishing(context, context.residual.difference(result.removed), operations[:end]), operations[-1]]
            removed = context.residual.intersection(Region.rectangle(bounds.min_x, self.target_z_mm, bounds.max_x, bounds.max_z))
        return replace(result, operations=tuple(operations), removed=removed)

    def _finishing(self, context: BlockContext, after_roughing: Region, operations: list) -> list:
        """The finishing pass at the target, outside in at the finishing feed (and speed), past the centre by the overtravel (`_passes`)."""
        bounds = context.residual.bounds
        here = next((operation.end for operation in reversed(operations) if getattr(operation, "end", None) is not None), None)
        feed = self.finish_feed_mm_per_rev or self.feed_mm_per_rev
        fast = finishing_spindle(self.spindle, self.finish_spindle_value)
        start, end = bounds.max_x + context.safety.clearance_mm, bounds.min_x - self.overtravel_mm
        return self._passes(context, after_roughing, here, [(self.target_z_mm, feed, fast)], start, end)

    def _passes(self, context: BlockContext, standing: Region, here: Point | None, passes: list, start_x: float, end_x: float) -> list:
        """The passes (Z, feed, a spindle setting or None) from `start_x` across to `end_x`, then away to the safe point. The way to each
        pass and away from the last one are the rapids of the analytic planner (`rapids.clear_way`: a clearance from the material that
        stands then, the last stretch at feed, X12); the material is cut by each pass (`removal.cut`). Where no clear way is found (the body of
        the tool cannot stand beside the material there), the way is the old one over the top (`_over_the_top`); the checker reports the tool
        in the material."""
        from ..geometry.chains import ChainError
        from ..analytic.rapids import clear_way
        from ..analytic.material import chains_of_region
        from ..geometry.removal import cut
        from ..analytic.tool_outline import tool_loops
        from ..constants import CHAIN_SNAP_MM

        clearance = context.safety.clearance_mm
        tool = tool_loops(context.tool)
        material = chains_of_region(standing) if not standing.is_empty else []
        above = context.residual.bounds.max_z + clearance
        moves: list = []
        z, feed = passes[-1][0], passes[-1][1]
        for z, feed, setting in passes:
            if setting is not None:
                moves.append(SetSpindle(setting))
            start, end = Point(start_x, z), Point(end_x, z)
            way = clear_way(here, start, tool, material, clearance) if here is not None else None
            moves += _way_moves(way, feed) if way is not None else [*_over_the_top(here, above, clearance, feed), Rapid(Point(start_x, above)), LinearMove(start, feed)]
            moves.append(LinearMove(end, feed))
            try:
                material = cut(material, tool, [LineSegment(start, end)], CHAIN_SNAP_MM)[0] if material else []
            except ChainError:
                pass  # the material stays as it was: the ways keep their distance from more than stands
            here = end
        finish = Point(context.safety.safe_radius_mm, max(context.safety.safe_z_mm, z + clearance))
        way = clear_way(here, finish, tool, material, clearance)
        return moves + (_way_moves(way, feed) if way is not None else [*_over_the_top(here, above, clearance, feed), Rapid(finish)])

    def _centre_out(self, context: BlockContext, header: BlockBegin, footer: BlockEnd) -> BlockResult:
        """Centre out: the passes from past the centre by the overtravel out beside the part (`_passes`). The levels are laid out from the
        front of the raw bar, as for the contour block, so a second block gets the same levels."""
        residual = context.residual
        bounds = residual.bounds
        z_top = bounds.max_z
        rough_end = min(self.target_z_mm + self.finish_allowance_mm, z_top)
        levels = [z for z in pass_levels(max(context.raw_part.front_z_mm, z_top), rough_end, self.depth_of_cut_mm) if z < z_top - GEOMETRY_TOLERANCE_MM]
        passes = [(z, self.feed_mm_per_rev, None) for z in levels]
        if self.finish_pass:
            fast = finishing_spindle(self.spindle, self.finish_spindle_value)
            passes.append((self.target_z_mm, self.finish_feed_mm_per_rev or self.feed_mm_per_rev, fast))
        final_z = passes[-1][0] if passes else z_top  # an allowance that is not finished stays on the face
        removed = residual.intersection(Region.rectangle(bounds.min_x, final_z, bounds.max_x, bounds.max_z))
        if not passes:
            return BlockResult((header, footer), Region.empty(), ("facing: the allowance is all that stands above the target, nothing to cut",))
        clearance = context.safety.clearance_mm
        x_in = bounds.min_x - self.overtravel_mm  # past the centre, so the nose radius leaves no pip
        here = Point(context.safety.safe_radius_mm, z_top + clearance)  # where the contour block starts too (outside in)
        moves = self._passes(context, residual, here, passes, x_in, bounds.max_x + clearance)
        return BlockResult((header, Rapid(here), *moves, footer), removed)

    def generate(self, context: BlockContext) -> BlockResult:
        """The moves of the block: outside in as a contour across X (`_as_contour`), centre out by passes of its own (`_centre_out`)."""
        header = BlockBegin(0, self.block_id, self.type_name, self.name)
        footer = BlockEnd(self.block_id)
        bounds = context.residual.bounds
        if bounds is None or self.target_z_mm >= bounds.max_z - GEOMETRY_TOLERANCE_MM:
            note = "facing: there is no material above the target, nothing to cut"
            return BlockResult((header, footer), Region.empty(), (note,))

        if self.overtravel_mm > bounds.max_x:
            raise BlockError(f"the overtravel ({self.overtravel_mm:g} mm) is more than the radius of the part ({bounds.max_x:g} mm)")
        return self._as_contour(context) if self.direction is FacingDirection.OUTSIDE_IN else self._centre_out(context, header, footer)


def _over_the_top(here: Point | None, above: float, clearance: float, feed: float) -> list:
    """Up from `here` to `above` (a clearance over the top of the material): the first clearance at feed (X12), the rest a rapid.
    Nothing when the tool is nowhere yet (the roughing made no move: an allowance as big as the whole face)."""
    if here is None or here.z >= above - GEOMETRY_TOLERANCE_MM:
        return []
    rise = Point(here.x, min(here.z + clearance, above))
    return [LinearMove(rise, feed), *([Rapid(Point(here.x, above))] if rise.z < above - GEOMETRY_TOLERANCE_MM else [])]


def _way_moves(way, feed: float) -> list:
    """The moves of a way of `rapids.clear_way` (feed moves, rapids, feed moves)."""
    lift, rapid, down = way
    return [*(LinearMove(piece.end, feed) for piece in lift), *(Rapid(piece.end) for piece in rapid), *(LinearMove(piece.end, feed) for piece in down)]
