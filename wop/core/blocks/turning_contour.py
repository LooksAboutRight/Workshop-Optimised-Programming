"""Turning block, contour form (requirements X7, X8).

Roughs and finishes along a contour: any chain of lines and arcs that starts at
the highest Z and ends at the lowest Z. OUTSIDE removes the material outside the
contour, INSIDE the material inside it (a bore). The tool is checked at every
position. Areas it cannot reach stay uncut and are reported with a remedy.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..geometry.chains import ChainError, Loop, box_of, loop_area, loops_box, region_of_loops
from ..analytic.cut_operations import FinishingJob, cut_operations, finishing_pass
from ..analytic.cut_list import RoughingCuts
from ..analytic.roughing_cuts import RoughingJob, left_standing, roughing_cuts
from ..analytic.material import chains_of_region, is_uncut, stock_chains
from ..analytic.mirror import MIRROR_X, MIRROR_Z
from ..analytic.nose_follow import largest_following_radius, misses
from ..analytic.wanted_lines import LineDirection, removal_ring
from ..analytic.wanted_plan import WantedJob, wanted_plan
from ..constants import (
    CHAIN_SNAP_MM,
    CUT_JITTER_MM,
    EXAMPLE_DEPTH_OF_CUT_MM,
    EXAMPLE_FEED_MM_PER_REV,
    EXAMPLE_FINISH_ALLOWANCE_MM,
    EXAMPLE_FINISH_FEED_MM_PER_REV,
    EXAMPLE_MIN_FREE_ANGLE_DEG,
    GEOMETRY_TOLERANCE_MM,
    RIGHT_ANGLE_DEG,
)
from ..geometry import LineSegment, Point, Segment, segments_to_polyline
from ..program_model.operations import BlockBegin, BlockEnd, Rapid, SetSpindle, SpindleSetting, finishing_spindle
from ..geometry.region import Region
from ..tooling.tool_back_angle import back_direction
from ..tooling.tool_reference import nose_circle
from .base import BLOCK_TYPES, NO_CONTOUR, Block, BlockContext, BlockError, BlockResult
from .rough_style import ROUGHING, RoughStyleError, style_sequence
from .styles import DEFAULT_STYLE_KEY, STYLES, StyleError
from .turning_common import PassDirection, TurningSide, inside_stock_radius, nose_radius_presets, with_solid_note
from ..analytic.far_side import works_on_far_side
from .turning_job import merge_straight_rapids


@dataclass(frozen=True)
class PlanInputs:
    """What the analytic planner needs from the form and the material of a contour block."""
    path: list[Segment]  # the contour, with the last wall run on to the material
    stock: list[Loop]  # the material as loops (inside: both sides of the axis)
    cleaned: Callable[[], list[Loop]] | None  # the loops of the material opened and simplified, tried when the exact ones fail; None: exact
    outside: bool
    direction: LineDirection
    outer: float  # the radius beyond the material and the contour where the area to remove is closed
    start_z: float  # the front of the block's material
    stock_radius: float  # the radius of the material the block starts from (inside: the hole; 0: a solid bar)


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class ContourTurningBlock(Block):
    type_name = "turning_contour"

    contour_id: str
    side: TurningSide
    feed_mm_per_rev: float
    depth_of_cut_mm: float
    pass_direction: PassDirection = PassDirection.ALONG_Z
    finish_allowance_mm: float = 0
    finish_pass: bool = True  # False: only roughing; what the allowance leaves stays for a later block
    cutter_compensation: bool = False  # the finishing pass is a compensated contour: lead-in, lead-out and the contour points for a post with G41 / G42
    finish_feed_mm_per_rev: float | None = None
    finish_spindle_value: float | None = None  # rpm or m/min as for the spindle; None: as for roughing
    plunge_feed_mm_per_rev: float | None = None  # roughing moves against the direction of the lines; None: the normal feed
    plunge_depth_of_cut_mm: float | None = None  # deepest one plunge into a pocket goes; None: the depth of cut
    min_free_angle_deg: float = EXAMPLE_MIN_FREE_ANGLE_DEG  # angle that must stay free between the back of the tool and the wall behind a pocket
    style: str = DEFAULT_STYLE_KEY  # the key of the style that decides the order of the roughing lines and the routes (`rough_style.py`)

    @classmethod
    def example(
        cls, block_id: str, tool_number: int, spindle: SpindleSetting
    ) -> "ContourTurningBlock":
        # A new block has no contour (C10); the user picks one.
        return cls(
            block_id=block_id, name="Turning along a contour", tool_number=tool_number,
            spindle=spindle, contour_id=NO_CONTOUR, side=TurningSide.OUTSIDE,
            feed_mm_per_rev=EXAMPLE_FEED_MM_PER_REV, depth_of_cut_mm=EXAMPLE_DEPTH_OF_CUT_MM,
            finish_allowance_mm=EXAMPLE_FINISH_ALLOWANCE_MM,
            finish_feed_mm_per_rev=EXAMPLE_FINISH_FEED_MM_PER_REV,
            plunge_feed_mm_per_rev=EXAMPLE_FEED_MM_PER_REV / 2, plunge_depth_of_cut_mm=EXAMPLE_DEPTH_OF_CUT_MM / 2,
            finish_spindle_value=spindle.value,
        )

    tool_default_fields = ("depth_of_cut_mm", "finish_allowance_mm")

    def with_tool_defaults(self, tool) -> "ContourTurningBlock":
        return nose_radius_presets(self, tool)

    def works_on_far_side(self, tool) -> bool:
        return works_on_far_side(tool, self.side is TurningSide.INSIDE)

    def form_fields(self) -> tuple[str, ...]:
        """The contour comes right after the name, then what and where, then the cutting data."""
        return (
            "name", "style", "contour_id", "side", "pass_direction", "tool_number", "spindle", "feed_mm_per_rev",
            "depth_of_cut_mm", "finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev", "finish_spindle_value", "cutter_compensation",
            "plunge_feed_mm_per_rev", "plunge_depth_of_cut_mm", "min_free_angle_deg", "coolant",
        )

    def field_choices(self) -> dict[str, list[tuple[str, str]]]:
        """The style dropdown: the styles of turning contour; the style of the block even when this program does not know it."""
        styles = [(info.key, info.label) for info in STYLES.styles_for(ROUGHING)]
        if self.style not in [key for key, _label in styles]:
            styles.append((self.style, f"{self.style} (not available)"))
        return {"style": styles}

    def form_preview(self) -> dict[str, str]:
        return {"style": ROUGHING}  # hovering a style in the dropdown shows its path on the sample parts

    def form_notes(self) -> dict[str, str]:
        known = {info.key: info for info in STYLES.styles_for(ROUGHING)}
        return {"style": known[self.style].hint if self.style in known else "This style is not available in this program: choose another one."}

    def follower_values(self) -> dict[str, object]:
        """The plunge feed and the plunge depth of cut are half of the feed and the depth of cut, the finishing speed is
        the roughing speed, until the user types a value of his own."""
        return {
            "plunge_feed_mm_per_rev": self.feed_mm_per_rev / 2,
            "plunge_depth_of_cut_mm": self.depth_of_cut_mm / 2,
            "finish_spindle_value": self.spindle.value,
        }

    def form_same_line(self) -> frozenset[str]:
        return frozenset({"finish_feed_mm_per_rev", "finish_spindle_value"})  # next to the "Finishing pass" checkbox

    def form_disabled(self) -> frozenset[str]:
        return frozenset() if self.finish_pass else frozenset({"finish_feed_mm_per_rev", "finish_spindle_value", "cutter_compensation"})

    def form_labels(self) -> dict[str, str]:
        return {
            "finish_allowance_mm": "Finishing allowance",
            "finish_feed_mm_per_rev": "Finishing feed",
            "plunge_feed_mm_per_rev": "Plunge feed",
            "plunge_depth_of_cut_mm": "Plunge depth of cut",
            "min_free_angle_deg": "Back clearance",
        }

    def __post_init__(self) -> None:
        if self.feed_mm_per_rev <= 0 or self.depth_of_cut_mm <= 0:
            raise BlockError("feed and depth of cut must be greater than zero")
        if self.finish_allowance_mm < 0:
            raise BlockError("finishing allowance must not be negative")
        if self.finish_feed_mm_per_rev is not None and self.finish_feed_mm_per_rev <= 0:
            raise BlockError("finishing feed must be greater than zero")
        if self.finish_spindle_value is not None and self.finish_spindle_value <= 0:
            raise BlockError("the finishing spindle speed must be greater than zero")
        if self.plunge_feed_mm_per_rev is not None and self.plunge_feed_mm_per_rev <= 0:
            raise BlockError("the plunge feed must be greater than zero")
        if self.plunge_depth_of_cut_mm is not None and self.plunge_depth_of_cut_mm <= 0:
            raise BlockError("the plunge depth of cut must be greater than zero")
        if not 0 <= self.min_free_angle_deg < RIGHT_ANGLE_DEG:
            raise BlockError("the free angle must be at least 0 and less than 90 degrees")

    @property
    def contour_ids(self) -> tuple[str, ...]:
        return (self.contour_id,)

    def _check_contour(self, segments) -> None:
        if not segments:
            raise BlockError("the contour is empty")
        points = segments_to_polyline(list(segments))
        highest = max(point.z for point in points)
        lowest = min(point.z for point in points)
        tol = GEOMETRY_TOLERANCE_MM
        if segments[0].start.z < highest - tol or segments[-1].end.z > lowest + tol:
            raise BlockError("the contour must start at its highest Z and end at its lowest Z")
        if highest - lowest <= tol:
            across = max(point.x for point in points) - min(point.x for point in points)
            if self.pass_direction is not PassDirection.ALONG_X or across <= tol:  # a face alone is cut across X (the facing block)
                raise BlockError("the contour needs a length along Z")

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        try:
            return tuple(context.contour(self.contour_id).segments)
        except BlockError:
            return ()

    def _analytic_inputs(self, context: BlockContext) -> PlanInputs | None:
        """What the analytic planner (`wop/core/analytic`) needs from the form and the material, or None when there is no material."""
        residual = context.residual
        bounds = residual.bounds
        if bounds is None:
            return None
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        contour = context.contour(self.contour_id)
        self._check_contour(contour.segments)
        stock_radius = bounds.max_x if sign > 0 else inside_stock_radius(residual, contour.segments[-1].end.z, contour.segments[0].start.z)
        path = list(contour.segments)
        end = path[-1].end
        if sign * (stock_radius - end.x) > GEOMETRY_TOLERANCE_MM:
            path.append(LineSegment(end, Point(stock_radius, end.z)))  # the last wall runs on to the material
        start_z = max(path[0].start.z, bounds.max_z if context.front_z is None else context.front_z)
        outer = stock_radius + sign * context.safety.clearance_mm
        reaching = max(box_of(s)[2] for s in path) if sign > 0 else min(box_of(s)[0] for s in path)  # exact: an arc counts with its extreme points
        outer = max(outer, reaching + context.safety.clearance_mm) if sign > 0 else min(outer, reaching - context.safety.clearance_mm)
        direction = LineDirection.ALONG_Z if self.pass_direction is PassDirection.ALONG_Z else LineDirection.ALONG_X
        if sign < 0:  # inside: the far side of the bar too (x < 0), the tool must keep off the other wall of the bore
            whole = residual.union(residual.mirrored())
            stock, cleaned = chains_of_region(whole), lambda: chains_of_region(whole, True)
        elif is_uncut(residual, context.raw_part):
            stock, cleaned = stock_chains(context.raw_part), None  # a bar nobody has cut: exact
        else:  # what earlier blocks left: the loops of the residual (`analytic.material`)
            stock, cleaned = chains_of_region(residual), lambda: chains_of_region(residual, True)
        return PlanInputs(path, stock, cleaned, sign > 0, direction, outer, start_z, stock_radius)

    def wanted_plan(self, context: BlockContext):
        inputs = self._analytic_inputs(context)
        if inputs is None:
            return None
        raw = context.raw_part
        job = WantedJob(
            path=inputs.path, outside=True, direction=inputs.direction, allowance=self.finish_allowance_mm, depth_of_cut=self.depth_of_cut_mm,
            plunge_depth=self.plunge_depth_of_cut_mm, outer=inputs.outer, start_z=inputs.start_z, chuck_z=raw.clamp_z_mm,
            grid_from=(raw.outer_radius_mm, raw.front_z_mm),
        )
        if inputs.outside:
            return wanted_plan(inputs.stock, job, inputs.cleaned)
        cleaned = inputs.cleaned  # inside: planned mirrored in X as an outside block, the levels from the bore of the raw bar
        mirrored = replace(job, path=MIRROR_X.path(inputs.path), outer=-inputs.outer, grid_from=(-raw.inner_radius_mm, raw.front_z_mm))
        return MIRROR_X.plan(wanted_plan(MIRROR_X.loops(inputs.stock), mirrored, (lambda: MIRROR_X.loops(cleaned())) if cleaned is not None else None))

    def roughing_cuts(self, context: BlockContext, run_on: float = 0.0):
        """The wanted plan shortened for the tool, ridden up and cut (`analytic.roughing_cuts`).
        `run_on`: a line whose low end is open (it runs out of the material, towards the axis across X) goes on that far (the overtravel of
        the facing block, past the centre)."""
        inputs = self._analytic_inputs(context)
        plan = self.wanted_plan(context)
        if inputs is None or plan is None:
            return None
        path, outside = inputs.path, inputs.outside
        bounds = context.residual.bounds
        clearance = context.safety.clearance_mm
        begin, finish = self._block_ends(context, inputs.start_z)
        job = RoughingJob(
            path=path, tool=context.tool, outside=outside, allowance=self.finish_allowance_mm, clearance_deg=self.min_free_angle_deg,
            outer=inputs.outer,
            inner=min(bounds.min_x, path[0].start.x) - clearance if outside else max(bounds.max_x, max(box_of(s)[2] for s in path)) + clearance,
            far_z=context.raw_part.clamp_z_mm - clearance, clearance=clearance, begin=begin, finish=finish,
            across=inputs.direction is LineDirection.ALONG_X, run_on=run_on, sequence=self._roughing_sequence(),
        )
        try:
            return roughing_cuts(plan, inputs.stock, job)
        except ChainError:  # the loops of an earlier block's material have needles along their border: try the cleaned ones
            if inputs.cleaned is None:
                raise
            return roughing_cuts(plan, inputs.cleaned(), job)

    def _roughing_sequence(self):
        """The order of the lines of the roughing style (`rough_style.style_sequence`); None for the standard style (level by level)."""
        style = STYLES.get(ROUGHING, self.style)
        return None if style.key == DEFAULT_STYLE_KEY else (lambda lines: style_sequence(lines, style.function, style.key))

    @staticmethod
    def _block_ends(context: BlockContext, start_z: float) -> tuple[Point, Point]:
        """Where the block begins (the safe radius, at the front plane: in front of all the material, also when the block's own material
        begins further back, `BlockContext.front_z`) and where it ends (the safe point), as the old planner has them."""
        safety, bounds = context.safety, context.residual.bounds
        approach = max(start_z, bounds.max_z) + safety.clearance_mm
        return Point(safety.safe_radius_mm, approach), Point(safety.safe_radius_mm, max(safety.safe_z_mm, bounds.max_z + safety.clearance_mm, approach))

    def _analytic_finishing(self, context: BlockContext, inputs: PlanInputs, material: list, start: Point) -> tuple[tuple, tuple[str, ...]]:
        """The finishing pass of the analytic planner (`cut_operations.finishing_pass`), from `start` (where the roughing ended) to the safe
        point, and the note when the nose cannot follow the contour (`nose_follow.py`)."""
        path, outside, outer = inputs.path, inputs.outside, inputs.outer
        _begin, finish = self._block_ends(context, inputs.start_z)
        feed = self.finish_feed_mm_per_rev or self.feed_mm_per_rev
        job = FinishingJob(path, context.tool, outside, self.cutter_compensation, feed, context.safety.clearance_mm, outer)
        if outside and back_direction(context.tool) < 0:  # a left-hand tool finishes from the chuck side towards the front: planned mirrored
            flip = MIRROR_Z
            mirrored = replace(job, path=flip.path(path), tool=flip.tool(context.tool))
            operations = [flip.operation(move) for move in finishing_pass(mirrored, flip.loops(material), flip.point(start), flip.point(finish))]
        else:
            operations = finishing_pass(job, material, start, finish)
        spindle = finishing_spindle(self.spindle, self.finish_spindle_value)
        if spindle is not None:
            operations = [SetSpindle(spindle), *operations]
        radius, _centre = nose_circle(context.tool)
        missed = misses(path, outside, radius)
        notes = []
        if missed:
            largest = math.floor(largest_following_radius(path, outside, radius) * 100) / 100  # down to hundredths: "or smaller" stays true
            zs = [point.z for point in missed]
            notes.append(
                f"{self.name or self.type_name}: the nose of the tool (radius {radius:.2f} mm) cannot follow the contour between Z {max(zs):.2f} "
                f"and Z {min(zs):.2f}: the finishing pass needs a nose radius of {largest:.2f} mm or smaller"
                + (" (the controller may refuse the compensated pass there)" if self.cutter_compensation else "")
            )
        return tuple(operations), tuple(notes)

    def _analytic_roughing(self, context: BlockContext, run_on: float = 0.0) -> tuple[tuple, tuple[str, ...], RoughingCuts | None]:
        """The roughing moves of the analytic planner (from the first rapid to the safe point), the notes and the cut list (what it leaves for
        the finishing pass and the next block), or ((), (), None) when there is no line to rough (only the finishing allowance stands, or
        less). A line with no way in is not cut (a note)."""
        name = self.name or self.type_name
        try:
            first = self.roughing_cuts(context, run_on=run_on)
        except ChainError:
            raise BlockError(f"{name}: the planner cannot read the material of this block (its border has a feature too small for it)") from None
        except RoughStyleError as error:
            raise BlockError(str(error)) from error
        if first is None:
            return (), (), None
        standing = left_standing(first, context.tool.nose_radius_mm, CHAIN_SNAP_MM)
        if standing is None:
            raise BlockError(f"{name}: the planner cannot work out what the roughing of this block leaves standing")
        notes = []
        if first.failed_lines:  # the boolean met a feature it cannot decide: the line is not cut, its material stays
            notes.append(f"{name}: {first.failed_lines} roughing line(s) could not be worked out and are not cut; that material stays for another block")
        if first.unconnected_cuts:
            notes.append(
                f"{name}: {first.unconnected_cuts} time(s) no free way was found between two cuts: the tool goes out beyond the stock and back in "
                f"there; the check shows whether that way is free"
            )
        if first.unreachable_lines:  # the planning rule: a line the tool cannot get to is not cut, its material stays (the note below says how much)
            notes.append(f"{name}: {first.unreachable_lines} roughing line(s) are not cut: the tool has no free way in to them (or they lie under one)")
        if standing:
            _x0, z_low, _x1, z_high = loops_box(standing)
            notes.append(
                f"{name}: {sum(abs(loop_area(loop)) for loop in standing):.2f} mm2 of the material to rough between Z {z_high:.2f} and Z {z_low:.2f} is not "
                f"cut: the tool cannot reach it; it stays for another tool or block"
            )
        rough = tuple(cut_operations(first, self.feed_mm_per_rev, self.plunge_feed_mm_per_rev or self.feed_mm_per_rev))
        return rough, tuple(notes), first

    def generate(self, context: BlockContext, run_on: float = 0.0) -> BlockResult:
        """The moves of the block (the analytic planner): to the start point, the roughing, the finishing pass, at the safe point. `run_on`:
        see `roughing_cuts`."""
        ends = (BlockBegin(0, self.block_id, self.type_name, self.name), BlockEnd(self.block_id))
        residual = context.residual
        inputs = self._analytic_inputs(context)
        if inputs is None:
            return BlockResult(ends, Region.empty(), ("turning: no material left",))
        ring = removal_ring(inputs.path, inputs.outside, 0.0, inputs.outer, inputs.start_z)
        whole = residual.intersection(Region.from_segments(ring))  # all the material between the stock and the contour
        if whole.is_empty:
            return BlockResult(ends, Region.empty(), ("turning: nothing to remove",))
        try:
            STYLES.get(ROUGHING, self.style)
        except StyleError:
            raise BlockError(f"the style {self.style!r} is not available in this program: choose another style") from None
        rough, notes, first = self._analytic_roughing(context, run_on)
        begin, _finish = self._block_ends(context, inputs.start_z)
        operations = [ends[0], *([Rapid(begin)] if inputs.outside else []), *rough]  # inside: the first rapid goes straight over the bore
        removed = self._taken(residual, first, whole) if first is not None else Region.empty()
        if self.finish_pass:
            material = list(first.residual) if first is not None else inputs.stock
            finishing, finish_notes = self._analytic_finishing(context, inputs, material, rough[-1].end if rough else begin)
            operations += finishing
            notes = (*notes, *finish_notes)
            removed = removed.union(whole)  # the finishing pass follows the contour: it takes what the roughing could not reach (the note stays)
        result = BlockResult(tuple(merge_straight_rapids([*operations, ends[1]])), removed, notes, residual.difference(whole))
        return result if inputs.outside else with_solid_note(result, inputs.stock_radius)

    @staticmethod
    def _taken(residual: Region, first: RoughingCuts, whole: Region) -> Region:
        """What the roughing took: the material minus what it left. Outside `whole` (the area between the stock and the contour) only what
        is thicker than the shifts of a retried cut (`CUT_JITTER_MM`): a retried cut shaves a hair off the part, that is no removal."""
        taken = residual.difference(region_of_loops(first.residual))
        beyond = taken.difference(whole)
        if beyond.is_empty:
            return taken
        hair = max(math.hypot(dx, dz) for dx, dz in CUT_JITTER_MM)
        return taken.intersection(whole).union(beyond.offset(-hair).offset(hair))
