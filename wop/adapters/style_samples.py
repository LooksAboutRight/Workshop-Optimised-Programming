"""Small example blocks a style is tried on when it is loaded, and drawn on for its picture.

Every block type with styles has a few samples that differ in what makes styles differ (narrow and wide, outside and inside). A style
must work on all of them. A sample is made by a function: the key of a style in, the block and what it is planned in out.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from ..core.blocks.base import Block, BlockContext, Safety
from ..core.blocks.grooving import GroovingBlock
from ..core.blocks.turning_contour import ContourTurningBlock
from ..core.blocks.turning_common import TurningSide
from ..core.contour import Contour, ContourDefinition, LineStep
from ..core.contour_solver import solve_contour
from ..core.geometry import Point
from ..core.program_model.operations import SpindleMode, SpindleSetting
from ..core.program_model.program import Program
from ..core.program_model.raw_part import RawPart
from ..core.program_model.stock import stock_region
from ..core.tooling.tool_presets import groove_tool
from ..core.tooling.tool_reference import with_tip_at_origin
from ..core.tool_types import TOOL_TYPES, make_tool

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 800)
SAFETY = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)
BORE_DIAMETER_MM = 80  # the inside sample: a bore the 30 mm long tool body fits in
PICTURE_PADDING = 0.3  # of the longer side of the part to show, added on every side
PICTURE_PADDING_MM = 2  # and this much more


@dataclass(frozen=True)
class StyleSample:
    name: str  # what the user reads under the picture: "outside, wide groove"
    build: Callable[[str], tuple[Block, BlockContext]]  # style key -> the block with that style and what it is planned in
    program: Callable[[str], Program]  # style key -> the same block as a program (for the picture)
    focus: tuple[Point, Point]  # two corners (X radius, Z) of the part the picture shows
    rapids: bool = False  # the picture shows the rapid moves too (a style that changes the routes)
    verify: bool = False  # the check of the style also runs the collision check on this sample


def _groove(name: str, side: TurningSide, **values) -> StyleSample:
    inside = side is TurningSide.INSIDE
    raw_part = RawPart("steel", 100, 60, inner_diameter_mm=BORE_DIAMETER_MM) if inside else RawPart("steel", 30, 60)
    tool = groove_tool(1, "sample", body_towards_larger_x=not inside)

    def block_of(style: str) -> Block:
        return GroovingBlock(block_id="sample", tool_number=1, spindle=SPINDLE, side=side, feed_mm_per_rev=0.05, style=style, **values)

    def build(style: str) -> tuple[Block, BlockContext]:
        return block_of(style), BlockContext(raw_part, tool, stock_region(raw_part), SAFETY)

    def program(style: str) -> Program:
        return Program(raw_part=raw_part, tools=(tool,), safety=SAFETY, blocks=(block_of(style),))

    surface = BORE_DIAMETER_MM / 2 if inside else raw_part.outer_diameter_mm / 2
    z_high = values["start_z_mm"]
    focus = (Point(min(surface, values["bottom_radius_mm"]), z_high - values["width_mm"]), Point(max(surface, values["bottom_radius_mm"]), z_high))
    return StyleSample(name, build, program, focus)


def _contour(name: str, points: tuple[tuple[float, float], ...]) -> StyleSample:
    raw_part = RawPart("steel", 40, 60)
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    definition = ContourDefinition(Point(*points[0]), steps)
    shape = Contour("sample", name, tuple(solve_contour(definition)), definition)
    wide_back = replace(  # a right-hand ISO holder with a V insert: the back of the tool leaves room beside a wall (50 degrees)
        TOOL_TYPES.get("holder").default(), insert_code="VNMG 160404", holder_code="PVLNR 2020 M16", shape="V", section="2020",
        insert_size="16", corner_radius="04",
    )
    tool = make_tool("holder", 1, wide_back)
    safety = Safety(safe_radius_mm=30, safe_z_mm=10, clearance_mm=1)

    def block_of(style: str) -> Block:
        return ContourTurningBlock(
            block_id="sample", tool_number=1, spindle=SPINDLE, contour_id="sample", side=TurningSide.OUTSIDE,
            feed_mm_per_rev=0.25, depth_of_cut_mm=1.5, finish_pass=False, style=style,
        )

    def build(style: str) -> tuple[Block, BlockContext]:
        return block_of(style), BlockContext(raw_part, with_tip_at_origin(tool), stock_region(raw_part), safety, contours=(shape,))

    def program(style: str) -> Program:
        return Program(raw_part=raw_part, tools=(tool,), safety=safety, blocks=(block_of(style),), contours=(shape,))

    focus = (Point(0, min(z for _x, z in points)), Point(raw_part.outer_diameter_mm / 2, max(z for _x, z in points)))
    return StyleSample(name, build, program, focus, rapids=True, verify=True)


SAMPLES = {
    "grooving": (
        _groove("outside, narrow groove", TurningSide.OUTSIDE, start_z_mm=-10, width_mm=4, bottom_radius_mm=12),
        _groove(
            "outside, wide groove, finishing", TurningSide.OUTSIDE, start_z_mm=-5, width_mm=14, bottom_radius_mm=12,
            finish_allowance_mm=0.2, finish_pass=True, finish_feed_mm_per_rev=0.02,
        ),
        _groove("outside, deep groove, pecking", TurningSide.OUTSIDE, start_z_mm=-5, width_mm=12, bottom_radius_mm=8, peck_depth_mm=2),
        _groove("inside, wide groove", TurningSide.INSIDE, start_z_mm=-10, width_mm=8, bottom_radius_mm=43),
    ),
    "turning_contour": (
        _contour("stepped shaft, no pocket", ((8, 0), (8, -10), (12, -10), (12, -25), (14, -25), (14, -40))),
        _contour("a pocket with sloping walls", ((14, 0), (14, -10), (10, -18), (10, -24), (14, -30), (14, -40))),
        _contour("a long pocket with a ramp", ((14, 0), (14, -10), (10, -21), (10, -27), (14, -27), (14, -40))),
        _contour("two pockets behind crests", ((10, 0), (10, -5), (14, -8), (14, -11), (9, -17), (9, -21), (14, -25), (14, -28), (9, -34), (9, -38))),
    ),
}


def samples_for(block_type: str) -> tuple[StyleSample, ...]:
    return SAMPLES.get(block_type, ())
