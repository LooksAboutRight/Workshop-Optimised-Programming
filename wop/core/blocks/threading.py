"""Threading block (requirement B3): a straight 60 degree thread along Z, outside or inside.

The block gives the crest radius (the outer radius of an outside thread, the inner
radius of an inside thread, so the radius the material has been turned or bored
to), the pitch and the Z range (start and end, both absolute). The thread depth
defaults to the ISO metric value. The other values are those of the G76 cycle:
first cut depth (J), degression (R), compound angle (Q), spring passes (H) and
the tapered entry or exit (E, L). A thread is cut at a fixed spindle speed, so the
spindle of this block is only an RPM (a constant surface speed is turned into the
RPM at the crest). The cutting is one thread operation (X4); the postprocessor maps it
to the controller's cycle. The material must already be at the crest radius over the
thread length: the block does not turn it, and says so if there is more material.
The thread is not drawn as a V profile: the removed area is the whole band of the
thread depth, widened at both ends by what the tool flanks cut, so later blocks and the
collision check see the envelope of the thread.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..constants import (
    EXAMPLE_THREAD_CREST_RADIUS_MM,
    EXAMPLE_THREAD_LENGTH_MM,
    EXAMPLE_THREAD_PITCH_MM,
    EXAMPLE_THREAD_START_Z_MM,
    GEOMETRY_TOLERANCE_MM,
    MM_PER_M,
    THREAD_COMPOUND_ANGLE_DEG,
    THREAD_COMPOUND_ANGLE_LIMIT_DEG,
    THREAD_DEGRESSION_CONSTANT_AREA,
    THREAD_DEPTH_FACTOR_EXTERNAL,
    THREAD_DEPTH_FACTOR_INTERNAL,
    THREAD_FIRST_CUT_MM,
    THREAD_FLANK_MISMATCH_DEG,
    THREAD_CREST_TOLERANCE_MM,
    THREAD_LEAD_IN_PITCHES,
    THREAD_SPRING_PASSES,
)
from ..geometry import LineSegment, Point, Segment
from ..lathe.machine import Capability
from ..program_model.operations import (
    BlockBegin,
    BlockEnd,
    Rapid,
    SpindleMode,
    SpindleSetting,
    ThreadOperation,
    ThreadTaper,
)
from ..geometry.region import Region
from ..thread_designation import ThreadDesignationError, parse_designation
from ..tooling.tool import flank_angles_by_side, flank_reach_by_side
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .sweep import Sweeper
from .turning_common import TurningSide


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class ThreadingBlock(Block):
    type_name = "threading"
    required_capabilities = frozenset({Capability.SPINDLE_SYNC})

    side: TurningSide
    designation: str = ""  # M8x1, Tr40x7, 1/4-20 UNC ...: fills pitch, crest radius, depth and compound angle (see with_derived_fields)
    crest_radius_mm: float
    pitch_mm: float
    start_z_mm: float  # the thread starts here (higher Z)
    end_z_mm: float  # the thread ends here (lower Z), absolute; the form can show it as a length
    thread_depth_mm: float | None = None  # None: ISO metric from the pitch (G76 K)
    first_cut_depth_mm: float = THREAD_FIRST_CUT_MM  # G76 J
    degression: float = THREAD_DEGRESSION_CONSTANT_AREA  # G76 R: 1 same depth, 2 same area, more: decreasing area
    compound_angle_deg: float = THREAD_COMPOUND_ANGLE_DEG  # G76 Q
    spring_passes: int = THREAD_SPRING_PASSES  # G76 H
    taper: ThreadTaper = ThreadTaper.NONE  # G76 L
    taper_distance_mm: float = 0.0  # G76 E: used with a taper

    def form_fields(self) -> tuple[str, ...]:
        """The order of the form (the free comment is not shown)."""
        return (
            "name", "side", "designation", "tool_number", "spindle", "crest_radius_mm", "pitch_mm", "start_z_mm", "end_z_mm",
            "thread_depth_mm", "first_cut_depth_mm", "degression", "compound_angle_deg", "spring_passes",
            "taper", "taper_distance_mm", "coolant",
        )

    def form_headings(self) -> dict[str, str]:
        return {"crest_radius_mm": "Thread", "thread_depth_mm": "Passes (G76 J, K, R, Q, H)", "taper": "Run-in and run-out (G76 L, E)"}

    def form_labels(self) -> dict[str, str]:
        return {
            "spindle.value": "Spindle RPM", "designation": "Thread (M8x1, Tr40x7, 1/4-20 UNC)", "crest_radius_mm": "Crest X radius", "pitch_mm": "Pitch",
            "start_z_mm": "Start Z (front)", "end_z_mm": "End Z", "thread_depth_mm": "Thread depth",
            "first_cut_depth_mm": "First cut depth", "degression": "Degression", "compound_angle_deg": "Compound angle",
            "spring_passes": "Spring passes", "taper": "Tapered at", "taper_distance_mm": "Taper length",
        }

    def form_hidden(self) -> frozenset[str]:
        return frozenset({"spindle.mode", "spindle.rpm_limit"})  # a thread is cut at a fixed RPM

    def form_relative_ends(self) -> dict[str, tuple[str, str]]:
        return {"end_z_mm": ("start_z_mm", "Length")}  # end field -> (start field, label when shown as a length)

    def form_disabled(self) -> frozenset[str]:
        return frozenset({"taper_distance_mm"}) if self.taper is ThreadTaper.NONE else frozenset()

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "ThreadingBlock":
        return cls(
            block_id=block_id, name="Thread", tool_number=tool_number, spindle=spindle,
            side=TurningSide.OUTSIDE, crest_radius_mm=EXAMPLE_THREAD_CREST_RADIUS_MM,
            pitch_mm=EXAMPLE_THREAD_PITCH_MM, start_z_mm=EXAMPLE_THREAD_START_Z_MM,
            end_z_mm=EXAMPLE_THREAD_START_Z_MM - EXAMPLE_THREAD_LENGTH_MM,
        )

    def __post_init__(self) -> None:
        if self.designation.strip():
            try:
                parse_designation(self.designation)
            except ThreadDesignationError as error:
                raise BlockError(str(error)) from error
        if self.crest_radius_mm <= 0:
            raise BlockError("the crest radius must be greater than zero")
        if self.pitch_mm <= 0:
            raise BlockError("the pitch must be greater than zero")
        if self.end_z_mm >= self.start_z_mm - GEOMETRY_TOLERANCE_MM:
            raise BlockError("the thread must end behind its start (a lower Z)")
        if self.thread_depth_mm is not None and self.thread_depth_mm <= 0:
            raise BlockError("the thread depth must be greater than zero")
        if self.first_cut_depth_mm <= 0:
            raise BlockError("the first cut depth must be greater than zero")
        if self.spring_passes < 0:
            raise BlockError("the number of spring passes must not be negative")
        if self.degression < 1:
            raise BlockError("the degression must be 1 or more")
        if not 0 <= self.compound_angle_deg < THREAD_COMPOUND_ANGLE_LIMIT_DEG:
            raise BlockError(f"the compound angle must be from 0 to below {THREAD_COMPOUND_ANGLE_LIMIT_DEG} degrees")
        if self.taper_distance_mm < 0:
            raise BlockError("the taper length must not be negative")
        setting = self.spindle  # a thread is cut at a fixed RPM: a surface speed becomes the RPM at the crest
        if setting.mode is not SpindleMode.CONSTANT_RPM or setting.rpm_limit is not None:
            rpm = setting.value
            if setting.mode is SpindleMode.CONSTANT_SURFACE_SPEED:
                rpm = setting.value * MM_PER_M / (math.pi * 2 * self.crest_radius_mm)
            object.__setattr__(self, "spindle", replace(setting, mode=SpindleMode.CONSTANT_RPM, value=rpm, rpm_limit=None))

    @property
    def length_mm(self) -> float:
        return self.start_z_mm - self.end_z_mm

    def with_derived_fields(self, previous: Block | None) -> "ThreadingBlock":
        """A designation fills pitch, crest radius, depth and compound angle when it or the side changes.

        Editing pitch, crest radius or depth by hand makes the thread a custom one: the designation is cleared. The block
        keeps the numbers; the G-code never depends on the designation.
        """
        if not self.designation.strip():
            return self
        spec = parse_designation(self.designation)
        same_thread = isinstance(previous, ThreadingBlock) and previous.designation == self.designation and previous.side is self.side
        if same_thread and (
            previous.pitch_mm != self.pitch_mm or previous.crest_radius_mm != self.crest_radius_mm
            or previous.thread_depth_mm != self.thread_depth_mm
        ):
            return replace(self, designation="")
        if same_thread:
            return self
        values = spec.values_for(self.side is TurningSide.OUTSIDE)
        return replace(
            self, designation=spec.designation, pitch_mm=values.pitch_mm, crest_radius_mm=values.crest_radius_mm,
            thread_depth_mm=values.depth_mm, compound_angle_deg=values.compound_angle_deg,
        )

    def _designation_messages(self, tool_shape) -> tuple[str, ...]:
        if not self.designation.strip():
            return ()
        spec = parse_designation(self.designation)
        values = spec.values_for(self.side is TurningSide.OUTSIDE)
        messages = [values.summary(spec.designation, self.side is TurningSide.OUTSIDE)]
        flanks = flank_angles_by_side(tool_shape)
        wanted = values.flank_half_angle_deg
        if any(abs(flank - wanted) > THREAD_FLANK_MISMATCH_DEG for flank in flanks):
            if abs(flanks[0] - flanks[1]) <= THREAD_FLANK_MISMATCH_DEG:  # a symmetric tool: one angle is enough
                messages.append(
                    f"threading: the flank angle of the tool ({2 * flanks[0]:g} degrees between the flanks) differs from that of "
                    f"{spec.designation} ({2 * wanted:g} degrees): use a threading tool with the right profile"
                )
            else:
                messages.append(
                    f"threading: the flank angles of the tool ({flanks[0]:g} and {flanks[1]:g} degrees from the radial direction) differ from "
                    f"those of {spec.designation} ({wanted:g} each): use a threading tool with the right profile"
                )
        return tuple(messages)

    def depth(self) -> float:
        if self.thread_depth_mm is not None:
            return self.thread_depth_mm
        factor = (
            THREAD_DEPTH_FACTOR_EXTERNAL if self.side is TurningSide.OUTSIDE
            else THREAD_DEPTH_FACTOR_INTERNAL
        )
        return factor * self.pitch_mm

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        """The crest and the root of the thread along its length."""
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        root = self.crest_radius_mm - sign * self.depth()
        return (
            LineSegment(Point(self.crest_radius_mm, self.start_z_mm), Point(self.crest_radius_mm, self.end_z_mm)),
            LineSegment(Point(root, self.start_z_mm), Point(root, self.end_z_mm)),
        )

    def generate(self, context: BlockContext) -> BlockResult:
        """The thread as one thread cycle: the checks of the band and of the crest, the way to the start and out again; a note instead when nothing can be cut."""
        header = BlockBegin(0, self.block_id, self.type_name, self.name)
        footer = BlockEnd(self.block_id)
        nothing = BlockResult((header, footer), Region.empty())

        def refuse(text: str) -> BlockResult:
            return BlockResult(nothing.operations, nothing.removed, (f"threading: {text}",))

        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        depth = self.depth()
        root = self.crest_radius_mm - sign * depth
        if root <= GEOMETRY_TOLERANCE_MM:
            return refuse("the thread is deeper than the radius")
        z_start = self.start_z_mm
        z_end = self.end_z_mm
        flank_low, flank_high = flank_reach_by_side(context.tool.shape, depth)  # what the flanks cut beyond the ends
        near, far = sorted((self.crest_radius_mm, root))
        band = Region.rectangle(near, z_end, far, z_start)
        residual = context.residual
        planned = residual.intersection(band)
        if planned.is_empty:
            bounds = residual.bounds
            if bounds is not None and (z_start <= bounds.min_z or z_end >= bounds.max_z):
                return refuse(
                    f"the thread (Z {z_end:g} to {z_start:g}) is not in the material (Z {bounds.min_z:g} to {bounds.max_z:g}); "
                    "Z is absolute, behind the front face it is negative"
                )
            return refuse("there is no material in the thread band")
        # the material that must be turned or bored to the crest radius first
        above_near, above_far = (
            (self.crest_radius_mm + THREAD_CREST_TOLERANCE_MM, residual.bounds.max_x + 1)
            if sign > 0 else (0.0, self.crest_radius_mm - THREAD_CREST_TOLERANCE_MM)
        )
        if not residual.intersection(Region.rectangle(above_near, z_end, above_far, z_start)).is_empty:
            return refuse(f"there is material beyond the crest radius, turn or bore the thread diameter first (to diameter {2 * self.crest_radius_mm:.3f})")
        # the tool flanks run out a little beyond both ends of the thread
        margin_band = Region.rectangle(near, z_end - flank_low, far, z_start + flank_high)
        sweeper = Sweeper(context, residual.difference(margin_band))
        clearance = context.safety.clearance_mm
        start_x = self.crest_radius_mm + sign * clearance
        lead_in = THREAD_LEAD_IN_PITCHES * self.pitch_mm
        start_point_z = z_start + lead_in
        reached = sweeper.cut_line(Point(start_x, start_point_z), Point(root, start_point_z))
        deep_end = sweeper.cut_line(Point(root, start_point_z), Point(root, z_end))
        reach_notes: tuple[str, ...] = ()
        if len(reached) < 2 or len(deep_end) < 2 or abs(deep_end[-1].z - z_end) > GEOMETRY_TOLERANCE_MM:
            # as drawn: the thread is written anyway, the checks report where the tool collides
            reach_notes = ("threading: the tool collides on the way to the thread (holder or point); the thread is written as asked, see the problem list",)
        safe_radius = context.safety.safe_radius_mm
        taper, taper_distance = self.taper, self.taper_distance_mm  # a taper that cannot be cut is left out, with a finding
        notes: list[str] = []
        if taper is not ThreadTaper.NONE and taper_distance <= 0:
            notes.append(f"threading: a tapered {taper.value} is selected but no taper length is given; the thread is cut without a taper")
        elif taper is not ThreadTaper.NONE and taper_distance > self.length_mm / 2 + GEOMETRY_TOLERANCE_MM:
            notes.append("threading: the taper length is more than half the thread length; the thread is cut without a taper")
        else:
            notes = []
        if notes:
            taper, taper_distance = ThreadTaper.NONE, 0.0
        operation = ThreadOperation(
            start_x=start_x, start_z=start_point_z, end_z=z_end, pitch_mm=self.pitch_mm,
            peak_offset_mm=self.crest_radius_mm - start_x,
            first_cut_mm=min(self.first_cut_depth_mm, depth), depth_mm=depth,
            degression=self.degression,
            compound_angle_deg=self.compound_angle_deg, spring_passes=self.spring_passes,
            taper_distance_mm=taper_distance, taper=taper,
        )
        operation.pass_depths()  # raises ValueError when the passes would be absurdly many (first cut, degression, spring passes)
        bounds = residual.bounds
        z_front = max(bounds.max_z + clearance, start_point_z)
        z_safe = max(context.safety.safe_z_mm, z_front)
        safe_point = Point(safe_radius, z_safe)
        here = Point(start_x, start_point_z)  # the cycle begins and ends here
        if sign > 0:
            approach = [Rapid(Point(safe_radius, start_point_z)), Rapid(here)]
        elif sweeper.line_is_free(Point(start_x, z_safe), here):  # like a drill: X first, then straight down
            approach = [Rapid(Point(start_x, z_safe))] if z_safe - start_point_z <= GEOMETRY_TOLERANCE_MM else [
                Rapid(Point(start_x, z_safe)), Rapid(here),
            ]
        else:
            approach = [Rapid(Point(safe_radius, z_front)), Rapid(Point(start_x, z_front)), Rapid(here)]
        if sweeper.line_is_free(here, safe_point):  # one rapid to the safe point
            leave = [Rapid(safe_point)]
        elif sign > 0:
            leave = [Rapid(Point(safe_radius, start_point_z)), Rapid(safe_point)]
        else:
            up = Point(start_x, z_front)
            if sweeper.line_is_free(here, up) and sweeper.line_is_free(up, safe_point):
                leave = [Rapid(up), Rapid(safe_point)]
            else:
                leave = [Rapid(up), Rapid(Point(safe_radius, z_front)), Rapid(safe_point)]
        operations = (header, *approach, operation, *leave, footer)
        removed = residual.intersection(margin_band)
        return BlockResult(operations, removed, (*reach_notes, *notes, *self._designation_messages(context.tool.shape)))
