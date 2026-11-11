"""Small demo programs (an outside turning, a tube, a contour, a wrong tool) for the tests of the SVG picture (`tests/test_svg_preview.py`)."""

from __future__ import annotations

from wop.core.blocks.base import Safety
from wop.core.blocks.facing import FacingBlock
from wop.core.blocks.turning import PassDirection, TurningBlock, TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.contour import ContourDefinition, LineStep, chamfer, fillet
from wop.core.contour_solver import build_contour
from wop.core.geometry import LineSegment, Point
from wop.core.program_model.operations import CoolantMode, SpindleMode, SpindleSetting
from wop.core.program_model.program import Program
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool import Tool, ToolSegment, ToolSegmentRole, ToolShape

CUTTER = ToolSegmentRole.CUTTER
HOLDER = ToolSegmentRole.HOLDER


def block_shape(side: int) -> ToolShape:
    """Square tool, tip at the origin. side 1: body at larger X (outside tool), -1: smaller X."""
    corners = [Point(0, 0), Point(8 * side, 0), Point(8 * side, 12), Point(0, 12), Point(0, 0)]
    roles = [CUTTER, HOLDER, HOLDER, CUTTER]
    return ToolShape(
        tuple(ToolSegment(LineSegment(a, b), r) for (a, b), r in zip(zip(corners, corners[1:]), roles))
    )


SPINDLE = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 150, rpm_limit=3000)


def outside_program() -> Program:
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=(Tool(1, "outside tool", block_shape(1)),),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=(
            FacingBlock(
                block_id="b1", name="face", tool_number=1, spindle=SPINDLE,
                coolant=CoolantMode.FLOOD, target_z_mm=-1, feed_mm_per_rev=0.2,
                depth_of_cut_mm=1, finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.1,
            ),
            TurningBlock(
                block_id="b2", name="journal", tool_number=1, spindle=SPINDLE,
                coolant=CoolantMode.FLOOD, side=TurningSide.OUTSIDE, target_radius_mm=10,
                end_z_mm=-30, feed_mm_per_rev=0.25, depth_of_cut_mm=2,
                start_corner=chamfer(1), shoulder_corner=fillet(1.5),
                finish_allowance_mm=0.3, finish_feed_mm_per_rev=0.1,
            ),
            TurningBlock(
                block_id="b3", name="second step, transverse", tool_number=1, spindle=SPINDLE,
                side=TurningSide.OUTSIDE, target_radius_mm=13, end_z_mm=-45,
                feed_mm_per_rev=0.2, depth_of_cut_mm=3, pass_direction=PassDirection.ALONG_X,
                finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.1,
            ),
        ),
    )


def tube_program() -> Program:
    return Program(
        raw_part=RawPart("steel", 40, 50, inner_diameter_mm=14),
        tools=(
            Tool(1, "outside tool", block_shape(1)),
            Tool(2, "boring bar", block_shape(-1)),
        ),
        safety=Safety(safe_radius_mm=30, safe_z_mm=10, clearance_mm=1),
        blocks=(
            FacingBlock(
                block_id="t1", name="face", tool_number=1, spindle=SPINDLE,
                target_z_mm=-1, feed_mm_per_rev=0.2, depth_of_cut_mm=1,
            ),
            TurningBlock(
                block_id="t2", name="bore", tool_number=2, spindle=SPINDLE,
                side=TurningSide.INSIDE, target_radius_mm=10, end_z_mm=-25,
                feed_mm_per_rev=0.15, depth_of_cut_mm=1, shoulder_corner=fillet(1),
                start_corner=chamfer(0.5), finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.08,
            ),
        ),
    )


def contour_program() -> Program:
    """Contour form: a step, a taper and a groove this tool is too wide for (stays uncut)."""
    points = [(8, 0), (8, -12), (12, -12), (14, -20), (10, -22), (10, -26), (14, -26), (14, -40)]
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    contour = build_contour("demo", "demo contour", ContourDefinition(Point(*points[0]), steps))
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=(Tool(1, "outside tool", block_shape(1)),),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        contours=(contour,),
        blocks=(
            ContourTurningBlock(
                block_id="k1", name="contour", tool_number=1, spindle=SPINDLE,
                contour_id=contour.contour_id, side=TurningSide.OUTSIDE, feed_mm_per_rev=0.25,
                depth_of_cut_mm=2, finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.1,
            ),
        ),
    )


def wrong_tool_program() -> Program:
    """On purpose wrong: a boring bar used for an outside cut. The viewer must show crosses."""
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=(Tool(2, "boring bar", block_shape(-1)),),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=(
            TurningBlock(
                block_id="w1", name="outside cut with the wrong tool", tool_number=2,
                spindle=SPINDLE, side=TurningSide.OUTSIDE, target_radius_mm=10,
                end_z_mm=-30, feed_mm_per_rev=0.25, depth_of_cut_mm=2,
            ),
        ),
    )
