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
    GROOVE_EDGE_RELIEF_MM,
    GROOVE_EDGE_SIZE_MM,
    GROOVE_EDGE_SKIN_MM,
    GROOVE_FINISH_STOP_BLADE_FRACTION,
    GROOVE_FINISH_STOP_MIN_MM,
    GROOVE_ONE_SIDED_CUT_MM,
    GROOVE_ONE_SIDED_CUT_PERCENT,
    GROOVE_ONE_SIDED_MODE,
    PERCENT_OF_WHOLE,
)
from ..geometry import LineSegment, Point, Segment
from ..geometry.chains import reversed_segment
from ..program_model.operations import BlockBegin, BlockEnd, SetSpindle, SpindleSetting, finishing_spindle
from ..reach import prepare_tool
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .groove_edges import EdgeKind, edge_moves, edge_pieces, edge_region
from .groove_path import GroovePath
from .groove_style import EDGE_HIGH, EdgeCut, GrooveInput, GrooveStyleError, GROOVING, check_plunges
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
    left_edge_kind: EdgeKind = EdgeKind.NONE  # the edge of the wall nearer the chuck (the lower Z, the left in the picture) ...
    left_edge_mm: float = GROOVE_EDGE_SIZE_MM  # ... a chamfer or a fillet of this size
    right_edge_kind: EdgeKind = EdgeKind.NONE  # the edge of the wall nearer the face (the right): the part of a cut-off
    right_edge_mm: float = GROOVE_EDGE_SIZE_MM
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
            "right_edge_kind", "right_edge_mm", "left_edge_kind", "left_edge_mm", "peck_depth_mm", "peck_mode", "one_sided_mode", "one_sided_cut_value", "finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev",
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
        return {"start_z_mm": "Groove Z (front edge)", "bottom_radius_mm": "Final X radius",
                "right_edge_kind": "Right edge (face side)", "right_edge_mm": "size", "left_edge_kind": "Left edge (chuck side)", "left_edge_mm": "size",
                "one_sided_mode": "One-sided cut in", "one_sided_cut_value": "Max one-sided cut"}  # short: a long label squeezes the form

    def form_units(self) -> dict[str, str]:
        """The one-sided cut is a length or a percentage, as the mode says (a length follows the unit of the window)."""
        return {"one_sided_cut_value": "%" if self.one_sided_mode is OneSidedMode.PERCENT else "mm"}

    def form_same_line(self) -> frozenset[str]:
        return frozenset({"finish_feed_mm_per_rev", "finish_spindle_value", "right_edge_mm", "left_edge_mm"})  # next to the "Finishing" checkbox, next to the kind of an edge

    def form_disabled(self) -> frozenset[str]:
        off: set[str] = set()
        if self.right_edge_kind is EdgeKind.NONE:
            off.add("right_edge_mm")
        if self.left_edge_kind is EdgeKind.NONE:
            off.add("left_edge_mm")
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
        for label, kind, size in (("right", self.right_edge_kind, self.right_edge_mm), ("left", self.left_edge_kind, self.left_edge_mm)):
            if kind is not EdgeKind.NONE and size <= 0:
                raise BlockError(f"the size of the {label} edge must be greater than zero")
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
        sign = 1 if self.side is TurningSide.OUTSIDE else -1
        right = edge_pieces(self.right_edge_kind, self.right_edge_mm, True, surface, z_high, sign)
        left = edge_pieces(self.left_edge_kind, self.left_edge_mm, False, surface, z_low, sign)
        top = right[-1].end if right else Point(surface, z_high)  # where the wall starts under its edge
        low = left[-1].end if left else Point(surface, z_low)
        walls = [Point(self.bottom_radius_mm, z_high), Point(self.bottom_radius_mm, z_low), low]
        corners = [top, *walls]
        return (*right, *(LineSegment(a, b) for a, b in zip(corners, corners[1:])), *(reversed_segment(piece) for piece in reversed(left)))

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
        edges = self._edge_regions(place)
        for edge_region_ in edges:
            planned = planned.union(residual.intersection(edge_region_))  # the part the edges take off is cut too

        allowance = self.finish_allowance_mm
        finishing = self.finish_pass and allowance > 0
        rough_bottom = self.bottom_radius_mm + place.sign * allowance
        self._check_allowance(place, rough_bottom)
        self._check_edges(place)
        groove = self._groove_input(place, rough_bottom, finishing)
        open_for_the_tool = planned
        if groove.relief_low_z is not None and groove.relief_low_z < place.z_low - GEOMETRY_TOLERANCE_MM:
            # the first plunges of a cut-off with an edge reach a little past the wall nearer the chuck, so that the wall of the part keeps its skin
            open_for_the_tool = planned.union(residual.intersection(Region.rectangle(near, groove.relief_low_z, far, place.z_low)))
        sweeper = Sweeper(context, residual.difference(open_for_the_tool))
        path = self._path(context, bounds, place, sweeper)
        plunges = self._plunges(groove)

        feed = self.feed_mm_per_rev
        finish_feed = self.finish_feed_mm_per_rev or feed
        finishing_started = False
        part_off = False  # a groove that goes to the axis has cut the part off
        part_edge_late = False
        for step in plunges:
            edge = step.side if isinstance(step, EdgeCut) else step.edge
            if edge == EDGE_HIGH and part_off:
                part_edge_late = True  # the edge of the part is cut after the part came off
            if isinstance(step, EdgeCut):
                path.edge_cut(self._edge_moves(edge, step.size_mm, place), place.shift - (place.blade if edge == EDGE_HIGH else 0), finish_feed)
                continue
            if step.finishing and not finishing_started:
                finishing_started = True
                if path.started and self.finish_spindle_value is not None:
                    path.operations.append(SetSpindle(finishing_spindle(self.spindle, self.finish_spindle_value)))  # often faster
            if edge is not None:  # the corner cuts the edge and goes on down the wall in the same move
                path.edge_cut(self._edge_moves(edge, None, place), place.shift - (place.blade if edge == EDGE_HIGH else 0), finish_feed, step.radius, self.peck_depth_mm)
            else:
                path.plunge(step.z, step.radius, finish_feed if step.finishing else feed, None if step.finishing else self.peck_depth_mm)
            if groove.through and abs(step.radius - self.bottom_radius_mm) <= GEOMETRY_TOLERANCE_MM:
                part_off = True
            if step.sweep_to is not None:
                path.pass_along(step, finish_feed)
        path.leave()
        path.operations.append(self._footer())

        wanted = planned
        if allowance > 0 and not finishing and place.z_high - place.z_low > 2 * allowance:  # the allowance stays on the part
            low_x, high_x = sorted((rough_bottom, place.outer))
            wanted = residual.intersection(Region.rectangle(low_x, place.z_low + allowance, high_x, place.z_high - allowance))
        for edge_region_ in edges:
            wanted = wanted.union(residual.intersection(edge_region_))
        removed, messages = report_uncut(self.name or self.type_name, wanted, sweeper.current)
        if any(point is not None for point in path.collisions):
            messages.insert(0, "grooving: the tool collides while cutting the groove; it is cut as asked, see the problem list")
        if part_edge_late:
            messages.insert(0, "grooving: the groove goes to the axis, so the part is off before its (right) edge is cut; use the style 'Edges before full depth'")
        if place.solid:
            messages.insert(0, "grooving inside starts in solid material (there is no bore): drill and bore first unless the tool can cut at the centre")
        return BlockResult(tuple(path.operations), removed, tuple(messages))

    def _edge_moves(self, side: str, size_mm: float | None, place: "_Place"):
        """How the corner of the blade cuts an edge: all of it, or the part of this size (one of the first passes of a large edge)."""
        high = side == EDGE_HIGH
        kind, size = (self.right_edge_kind, self.right_edge_mm) if high else (self.left_edge_kind, self.left_edge_mm)
        return edge_moves(kind, size_mm or size, high, place.surface, place.z_high if high else place.z_low, place.sign, place.clearance)

    def _edge_regions(self, place: "_Place") -> list[Region]:
        """The material the chamfers or fillets take off the part (none for an edge that is off)."""
        regions = [
            edge_region(self.right_edge_kind, self.right_edge_mm, True, place.surface, place.z_high, place.sign),
            edge_region(self.left_edge_kind, self.left_edge_mm, False, place.surface, place.z_low, place.sign),
        ]
        return [region for region in regions if not region.is_empty]

    def _check_edges(self, place: "_Place") -> None:
        depth = place.sign * (place.surface - self.bottom_radius_mm)
        for label, kind, size in (("right", self.right_edge_kind, self.right_edge_mm), ("left", self.left_edge_kind, self.left_edge_mm)):
            if kind is not EdgeKind.NONE and size >= depth - GEOMETRY_TOLERANCE_MM:
                raise BlockError(f"the {label} edge ({size:g} mm) is as large as the groove is deep ({depth:g} mm) or larger")

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
        # a wall with an edge keeps a thin skin when the roughing is done, so that the edge and the wall are cut in one move
        skin_low = allowance if allowance > 0 or self.left_edge_kind is EdgeKind.NONE else GROOVE_EDGE_SKIN_MM
        skin_high = allowance if allowance > 0 or self.right_edge_kind is EdgeKind.NONE else GROOVE_EDGE_SKIN_MM
        rough_low, rough_high = place.z_low + skin_low, place.z_high - skin_high
        relief_low = relief_high = None
        if rough_high - rough_low < blade:  # narrow groove: the blade fills it, inside the walls
            if self.right_edge_kind is not EdgeKind.NONE:
                relief_high, relief_low = rough_high, rough_high - blade  # the first plunges reach a little past the wall nearer the chuck: the wall of the part keeps its skin
            rough_low = min(rough_low, place.z_high - blade)
            rough_high = rough_low + blade
        edges = [size for kind, size in ((self.right_edge_kind, self.right_edge_mm), (self.left_edge_kind, self.left_edge_mm)) if kind is not EdgeKind.NONE]
        relief = place.surface - place.sign * (max(edges) + GROOVE_EDGE_RELIEF_MM) if edges else None
        if relief is not None and place.sign * (relief - rough_bottom) <= GEOMETRY_TOLERANCE_MM:
            relief = None  # the groove is not deeper than the edge needs: no relief step
        return GrooveInput(
            blade_mm=blade, wall_low_z=place.z_low, wall_high_z=place.z_high, rough_low_z=rough_low, rough_high_z=rough_high,
            surface_radius=place.surface, rough_bottom_radius=rough_bottom, final_radius=self.bottom_radius_mm,
            one_sided_mm=self.one_sided_mm(blade), peck_depth_mm=self.peck_depth_mm, finishing=finishing,
            finish_stop_early_mm=max(GROOVE_FINISH_STOP_MIN_MM, GROOVE_FINISH_STOP_BLADE_FRACTION * blade),
            edge_high_mm=self.right_edge_mm if self.right_edge_kind is not EdgeKind.NONE else 0,
            edge_low_mm=self.left_edge_mm if self.left_edge_kind is not EdgeKind.NONE else 0,
            relief_radius=relief, relief_low_z=relief_low, relief_high_z=relief_high,
            through=place.sign > 0 and self.bottom_radius_mm <= GEOMETRY_TOLERANCE_MM,
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
