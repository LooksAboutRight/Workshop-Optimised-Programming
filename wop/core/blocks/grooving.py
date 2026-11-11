"""Grooving block (requirement B3): a rectangular groove cut with plunges.

OUTSIDE cuts a groove into the outer surface, INSIDE into the wall of a bore.
The groove lies between start_z_mm (the edge nearer the face, the higher Z) and
start_z_mm - width_mm, down to bottom_radius_mm. The tool plunges at positions
spaced by the blade width (with overlap); with a finishing pass (and an allowance)
the walls and the bottom are taken with a last plunge on each side and a pass along
the bottom. The tool is checked at every position; what it cannot reach stays uncut
and is reported.

Paths: the tool retracts to the clear radius after every plunge (one rapid). The clear
radius is the surface of the part where the tool works plus the clearance, not the
largest radius of the whole part. Where an earlier cut has made a groove already, the
tool rapids through the air to the clearance above the first material. Pecking: the tool
backs out a little (chip breaking) or all the way (full retract) after every peck. An
outside block starts with a Z move at the safe radius; an inside block like a drill:
X to the clear radius at the safe Z, then straight down. The block ends with one rapid
to the safe point (when that line is not free, out along the bore or out to the safe
radius first).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ..constants import (
    EXAMPLE_FEED_MM_PER_REV,
    EXAMPLE_GROOVE_BOTTOM_RADIUS_MM,
    EXAMPLE_GROOVE_START_Z_MM,
    EXAMPLE_GROOVE_WIDTH_MM,
    GEOMETRY_TOLERANCE_MM,
    GROOVE_FINISH_STOP_BLADE_FRACTION,
    GROOVE_FINISH_STOP_MIN_MM,
    GROOVE_ONE_SIDED_CUT_MM,
    GROOVE_ONE_SIDED_CUT_PERCENT,
    GROOVE_ONE_SIDED_MODE,
    PERCENT_OF_WHOLE,
)
from ..geometry import LineSegment, Point, Segment
from ..program_model.operations import BlockBegin, BlockEnd, SetSpindle, SpindleSetting, finishing_spindle
from ..reach import prepare_tool
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .groove_path import GroovePath
from .groove_style import GrooveInput, GrooveStyleError, GROOVING, check_plunges
from .styles import DEFAULT_STYLE_KEY, STYLES, StyleError
from .sweep import Sweeper
from .turning_common import TurningSide
from .uncut import report_uncut


class GroovePeckMode(Enum):
    CHIP_BREAK = "chip breaking (small retract)"
    FULL_RETRACT = "full retract"


class OneSidedMode(Enum):
    """How the most the blade may cut wide with air on one side is given: in mm, or as a part of the blade width."""

    MM = "mm"
    PERCENT = "% of blade width"


def default_one_sided_mode() -> OneSidedMode:
    return OneSidedMode[GROOVE_ONE_SIDED_MODE.upper()]  # the name of the preference: "mm" or "percent"


def default_one_sided_value(mode: OneSidedMode) -> float:
    return GROOVE_ONE_SIDED_CUT_PERCENT if mode is OneSidedMode.PERCENT else GROOVE_ONE_SIDED_CUT_MM


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class GroovingBlock(Block):
    type_name = "grooving"

    side: TurningSide
    start_z_mm: float  # groove edge nearer the face (higher Z)
    width_mm: float
    bottom_radius_mm: float
    feed_mm_per_rev: float
    peck_depth_mm: float | None = None  # None: one plunge to the bottom
    peck_mode: GroovePeckMode = GroovePeckMode.CHIP_BREAK  # what the tool does between two pecks
    one_sided_mode: OneSidedMode = default_one_sided_mode()  # how the next field is given
    one_sided_cut_value: float = default_one_sided_value(default_one_sided_mode())  # most the blade may cut wide with air on one side: mm or % of the blade width
    finish_allowance_mm: float = 0  # what the roughing leaves on the walls and the bottom
    finish_pass: bool = False  # True (and an allowance): the finishing plunges and the pass along the bottom
    finish_feed_mm_per_rev: float | None = None  # None: the normal feed
    finish_spindle_value: float | None = None  # rpm or m/min as for the spindle; None: as for roughing
    style: str = DEFAULT_STYLE_KEY  # the key of the style that decides the order and depth of the plunges (`groove_style.py`)

    def form_fields(self) -> tuple[str, ...]:
        """The order of the form (the free comment is not shown)."""
        return (
            "name", "style", "side", "tool_number", "spindle", "feed_mm_per_rev", "start_z_mm", "width_mm", "bottom_radius_mm",
            "peck_depth_mm", "peck_mode", "one_sided_mode", "one_sided_cut_value", "finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev",
            "finish_spindle_value", "coolant",
        )

    def field_choices(self) -> dict[str, list[tuple[str, str]]]:
        """The style dropdown: the styles of grooving; the style of the block even when this program does not know it."""
        styles = [(info.key, info.label) for info in STYLES.styles_for(GROOVING)]
        if self.style not in [key for key, _label in styles]:
            styles.append((self.style, f"{self.style} (not available)"))
        return {"style": styles}

    def form_preview(self) -> dict[str, str]:
        return {"style": GROOVING}  # hovering a style in the dropdown shows its path on the sample grooves

    def form_notes(self) -> dict[str, str]:
        known = {info.key: info for info in STYLES.styles_for(GROOVING)}
        return {"style": known[self.style].hint if self.style in known else "This style is not available in this program: choose another one."}

    def form_labels(self) -> dict[str, str]:
        unit = "%" if self.one_sided_mode is OneSidedMode.PERCENT else "mm"
        return {"start_z_mm": "Groove Z (front edge)", "bottom_radius_mm": "Final X radius",
                "one_sided_mode": "One-sided cut in", "one_sided_cut_value": f"Max one-sided cut ({unit})"}  # short: a long label squeezes the form

    def form_same_line(self) -> frozenset[str]:
        return frozenset({"finish_feed_mm_per_rev", "finish_spindle_value"})  # next to the "Finishing" checkbox

    def form_disabled(self) -> frozenset[str]:
        off: set[str] = set()
        if self.peck_depth_mm is None:
            off.add("peck_mode")
        if not self.finish_pass:
            off |= {"finish_feed_mm_per_rev", "finish_spindle_value"}
        return frozenset(off)

    def one_sided_mm(self, blade_mm: float) -> float:
        """The most the blade may cut wide with air on one side, in mm, for a blade of this width."""
        if self.one_sided_mode is OneSidedMode.PERCENT:
            return blade_mm * self.one_sided_cut_value / PERCENT_OF_WHOLE
        return self.one_sided_cut_value

    def with_derived_fields(self, previous: Block | None) -> "GroovingBlock":
        """Another mode: the value takes the default of that mode (a number in mm is not a number in percent)."""
        if isinstance(previous, GroovingBlock) and previous.one_sided_mode is not self.one_sided_mode:
            return replace(self, one_sided_cut_value=default_one_sided_value(self.one_sided_mode))
        return self

    def example_with_default(self, name: str, example: Block) -> Block:
        """Reset to default of the value gives the default of the mode the block is in now."""
        if name == "one_sided_cut_value":
            return replace(example, one_sided_mode=self.one_sided_mode, one_sided_cut_value=default_one_sided_value(self.one_sided_mode))
        return example

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "GroovingBlock":
        return cls(
            block_id=block_id, name="Groove", tool_number=tool_number, spindle=spindle,
            side=TurningSide.OUTSIDE, start_z_mm=EXAMPLE_GROOVE_START_Z_MM,
            width_mm=EXAMPLE_GROOVE_WIDTH_MM, bottom_radius_mm=EXAMPLE_GROOVE_BOTTOM_RADIUS_MM,
            feed_mm_per_rev=EXAMPLE_FEED_MM_PER_REV,
        )

    def __post_init__(self) -> None:
        if self.width_mm <= 0:
            raise BlockError("the groove width must be greater than zero")
        if self.bottom_radius_mm < 0:
            raise BlockError("the final radius must not be negative")
        if self.one_sided_cut_value <= 0:
            raise BlockError("the one-sided cut must be greater than zero")
        if self.one_sided_mode is OneSidedMode.PERCENT and self.one_sided_cut_value > PERCENT_OF_WHOLE:
            raise BlockError(f"the one-sided cut is at most {PERCENT_OF_WHOLE} % of the blade width")
        if self.feed_mm_per_rev <= 0:
            raise BlockError("feed must be greater than zero")
        if self.peck_depth_mm is not None and self.peck_depth_mm <= 0:
            raise BlockError("the peck depth must be greater than zero")
        if self.finish_allowance_mm < 0:
            raise BlockError("finishing allowance must not be negative")
        if self.finish_feed_mm_per_rev is not None and self.finish_feed_mm_per_rev <= 0:
            raise BlockError("finishing feed must be greater than zero")
        if self.finish_spindle_value is not None and self.finish_spindle_value <= 0:
            raise BlockError("the finishing spindle speed must be greater than zero")

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        """The groove: both walls and the bottom, from the surface of the part."""
        bounds = context.residual.bounds
        if bounds is None:
            return ()
        surface = bounds.max_x if self.side is TurningSide.OUTSIDE else bounds.min_x
        z_high, z_low = self.start_z_mm, self.start_z_mm - self.width_mm
        corners = [Point(surface, z_high), Point(self.bottom_radius_mm, z_high), Point(self.bottom_radius_mm, z_low), Point(surface, z_low)]
        return tuple(LineSegment(a, b) for a, b in zip(corners, corners[1:]))

    # --- helpers --------------------------------------------------------------------

    def _blade(self, context: BlockContext) -> tuple[float, float]:
        """Width of the cutting edge across Z (the Z extent of the tool's cutter pieces) and how far the left side of the
        blade (the smaller Z) lies from the reference point of the tool: 0 when the tool is touched off at the left corner,
        the blade width at the right corner."""
        points = [p for seg in context.tool.shape.cutter_segments for p in (seg.start, seg.end)]
        low, high = min(p.z for p in points), max(p.z for p in points)
        if high - low <= GEOMETRY_TOLERANCE_MM:
            raise BlockError("the tool has no cutting edge across Z, it cannot make a groove")
        return high - low, -low

    # --- generation --------------------------------------------------------------------

    def generate(self, context: BlockContext) -> BlockResult:
        """The groove plunge by plunge: the checks, the plunges of the style, the way out and the report of what stays uncut."""
        residual = context.residual
        bounds = residual.bounds
        if bounds is None:
            return self._nothing("grooving: no material left")
        if self._outside_the_material(bounds):
            return self._nothing(self._not_in_material_note(bounds))
        place = self._place(context, bounds)
        if place.sign * (place.surface - self.bottom_radius_mm) <= GEOMETRY_TOLERANCE_MM:
            return self._nothing("grooving: the final radius is not below the surface (outside) or beyond the bore (inside)")
        near, far = sorted((self.bottom_radius_mm, place.outer))
        planned = residual.intersection(Region.rectangle(near, place.z_low, far, place.z_high))
        if planned.is_empty:
            return self._nothing("grooving: nothing to remove")

        allowance = self.finish_allowance_mm
        finishing = self.finish_pass and allowance > 0
        rough_bottom = self.bottom_radius_mm + place.sign * allowance
        self._check_allowance(place, rough_bottom)
        sweeper = Sweeper(context, residual.difference(planned))
        path = self._path(context, bounds, place, sweeper)
        plunges = self._plunges(self._groove_input(place, rough_bottom, finishing))

        feed = self.feed_mm_per_rev
        finish_feed = self.finish_feed_mm_per_rev or feed
        finishing_started = False
        for step in plunges:
            if step.finishing and not finishing_started:
                finishing_started = True
                if path.started and self.finish_spindle_value is not None:
                    path.operations.append(SetSpindle(finishing_spindle(self.spindle, self.finish_spindle_value)))  # often faster
            path.plunge(step.z, step.radius, finish_feed if step.finishing else feed, None if step.finishing else self.peck_depth_mm)
            if step.sweep_to is not None:
                path.pass_along(step, finish_feed)
        path.leave()
        path.operations.append(self._footer())

        wanted = planned
        if allowance > 0 and not finishing and place.z_high - place.z_low > 2 * allowance:  # the allowance stays on the part
            low_x, high_x = sorted((rough_bottom, place.outer))
            wanted = residual.intersection(Region.rectangle(low_x, place.z_low + allowance, high_x, place.z_high - allowance))
        removed, messages = report_uncut(self.name or self.type_name, wanted, sweeper.current)
        if any(point is not None for point in path.collisions):
            messages.insert(0, "grooving: the tool collides while cutting the groove; it is cut as asked, see the problem list")
        if place.solid:
            messages.insert(0, "grooving inside starts in solid material (there is no bore): drill and bore first unless the tool can cut at the centre")
        return BlockResult(tuple(path.operations), removed, tuple(messages))

    def _header(self) -> BlockBegin:
        return BlockBegin(0, self.block_id, self.type_name, self.name)

    def _footer(self) -> BlockEnd:
        return BlockEnd(self.block_id)

    def _nothing(self, note: str) -> BlockResult:
        """A block that moves nothing and says why."""
        return BlockResult((self._header(), self._footer()), Region.empty(), (note,))

    def _outside_the_material(self, bounds) -> bool:
        return self.start_z_mm - self.width_mm >= bounds.max_z - GEOMETRY_TOLERANCE_MM or self.start_z_mm <= bounds.min_z + GEOMETRY_TOLERANCE_MM

    def _not_in_material_note(self, bounds) -> str:
        return (
            f"grooving: the groove (Z {self.start_z_mm - self.width_mm:g} to {self.start_z_mm:g}) is not in the material "
            f"(Z {bounds.min_z:g} to {bounds.max_z:g}); Z is absolute, behind the front face it is negative"
        )

    def _place(self, context: BlockContext, bounds) -> "_Place":
        """Where the blade works: the side, the blade, the surface within reach of the tool body and the radius it starts from."""
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        clearance = context.safety.clearance_mm
        blade, shift = self._blade(context)  # the planning is for the left side of the blade; `shift` leads to the reference point
        z_high = self.start_z_mm
        z_low = self.start_z_mm - self.width_mm
        # The surface where the tool works: the highest (inside: lowest) radius within reach of the tool body
        # while it stands at the plunge positions, not the largest radius of the whole part.
        body = prepare_tool(context.tool).body.bounds
        reach = context.residual.intersection(Region.rectangle(
            bounds.min_x - clearance, z_low + shift + body.min_z, bounds.max_x + clearance, max(z_high - blade, z_low) + shift + body.max_z,
        )).bounds or bounds
        surface = reach.max_x if sign > 0 else reach.min_x
        return _Place(
            sign=sign, clearance=clearance, blade=blade, shift=shift, z_high=z_high, z_low=z_low, surface=surface,
            outer=max(surface + sign * clearance, 0),  # no clearance below the axis in solid material
            solid=sign < 0 and surface <= GEOMETRY_TOLERANCE_MM,  # inside, but no bore: the tool starts in solid material
        )

    def _check_allowance(self, place: "_Place", rough_bottom: float) -> None:
        allowance = self.finish_allowance_mm
        if 2 * allowance >= self.width_mm - GEOMETRY_TOLERANCE_MM and allowance > 0:
            raise BlockError(f"the finishing allowance ({allowance:g} mm on each wall) is half the groove width ({self.width_mm:g} mm) or more")
        if place.sign * (place.surface - rough_bottom) <= GEOMETRY_TOLERANCE_MM:
            raise BlockError(f"the finishing allowance ({allowance:g} mm) is as deep as the groove or deeper")

    def _path(self, context: BlockContext, bounds, place: "_Place", sweeper: Sweeper) -> GroovePath:
        """The mover of the blade: the clear radii and the safe point."""
        safety = context.safety
        z_front = max(bounds.max_z + place.clearance, place.z_high + place.clearance)
        z_safe = max(safety.safe_z_mm, z_front)
        whole_surface = bounds.max_x if place.sign > 0 else bounds.min_x
        return GroovePath(
            sweeper, [self._header()], sign=place.sign, shift=place.shift, surface=place.surface, clearance=place.clearance,
            clear_x=place.outer, whole_clear_x=whole_surface + place.sign * place.clearance,  # clear of the whole part (the way along a bore)
            z_front=z_front, safe_radius=safety.safe_radius_mm, safe_point=Point(safety.safe_radius_mm, z_safe),
            start_z=place.z_high, full_retract=self.peck_mode is GroovePeckMode.FULL_RETRACT,
        )

    def _groove_input(self, place: "_Place", rough_bottom: float, finishing: bool) -> GrooveInput:
        """What a style needs to decide the order and depth of the plunges."""
        allowance = self.finish_allowance_mm
        blade = place.blade
        rough_low, rough_high = place.z_low + allowance, place.z_high - allowance
        if rough_high - rough_low < blade:  # narrow groove: the blade fills it
            rough_high = max(rough_high, rough_low + blade)
        return GrooveInput(
            blade_mm=blade, wall_low_z=place.z_low, wall_high_z=place.z_high, rough_low_z=rough_low, rough_high_z=rough_high,
            surface_radius=place.surface, rough_bottom_radius=rough_bottom, final_radius=self.bottom_radius_mm,
            one_sided_mm=self.one_sided_mm(blade), peck_depth_mm=self.peck_depth_mm, finishing=finishing,
            finish_stop_early_mm=max(GROOVE_FINISH_STOP_MIN_MM, GROOVE_FINISH_STOP_BLADE_FRACTION * blade),
        )

    def _plunges(self, groove: GrooveInput) -> list:
        """The plunges of the style of the block, checked."""
        try:
            plunges = STYLES.get(GROOVING, self.style).function(groove)
            check_plunges(groove, plunges, self.style)
        except StyleError:
            raise BlockError(f"the style {self.style!r} is not available in this program: choose another style") from None
        except GrooveStyleError as error:
            raise BlockError(str(error)) from error
        except BlockError:
            raise
        except Exception as error:  # noqa: BLE001 - a style file is somebody else's code
            raise BlockError(f"the style {self.style!r} stopped with {type(error).__name__}: {error}") from error
        return plunges


@dataclass(frozen=True)
class _Place:
    """Where a grooving block works (worked out once from the part and the tool)."""

    sign: int  # 1 outside, -1 inside
    clearance: float
    blade: float  # the width of the cutting edge across Z
    shift: float  # from the left side of the blade to the reference point of the tool
    z_high: float  # the groove edge nearer the face
    z_low: float
    surface: float  # the radius within reach of the tool where it starts to cut
    outer: float  # the clear radius: the surface plus the clearance
    solid: bool  # inside, but no bore
