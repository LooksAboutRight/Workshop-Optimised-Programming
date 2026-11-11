"""The reference program (requirement O5): uses every block type and setting once.

It is posted with the LinuxCNC post in the tests of the generator.
"""

from __future__ import annotations

from tests.helpers import simple_tool
from wop.core.blocks.base import Safety
from wop.core.blocks.facing import FacingBlock
from wop.core.blocks.turning import PassDirection, TurningBlock, TurningSide
from wop.core.contour import chamfer, fillet
from wop.core.program_model.operations import CoolantMode, SpindleMode, SpindleSetting
from wop.core.program_model.program import Program
from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings

CSS = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 150, rpm_limit=3000)
RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1200)


def reference_program() -> Program:
    return Program(
        raw_part=RawPart("Mild steel", 40, 50, inner_diameter_mm=14),
        tools=(simple_tool(1, side=1), simple_tool(2, side=-1)),
        safety=Safety(safe_radius_mm=30, safe_z_mm=10, clearance_mm=1),
        blocks=(
            FacingBlock(
                block_id="r1", name="face", tool_number=1, spindle=CSS, coolant=CoolantMode.FLOOD,
                target_z_mm=-1, feed_mm_per_rev=0.2, depth_of_cut_mm=1,
                finish_allowance_mm=0.2, finish_pass=True, finish_feed_mm_per_rev=0.1,
            ),
            TurningBlock(
                block_id="r2", name="outside, along Z", tool_number=1, spindle=RPM,
                coolant=CoolantMode.MIST, side=TurningSide.OUTSIDE, target_radius_mm=17,
                end_z_mm=-30, feed_mm_per_rev=0.25, depth_of_cut_mm=1.5,
                start_corner=chamfer(1), shoulder_corner=fillet(1.5),
                finish_allowance_mm=0.3, finish_feed_mm_per_rev=0.1,
            ),
            TurningBlock(
                block_id="r3", name="outside, along X", tool_number=1, spindle=RPM,
                side=TurningSide.OUTSIDE, target_radius_mm=18.5, end_z_mm=-42,
                feed_mm_per_rev=0.2, depth_of_cut_mm=1, pass_direction=PassDirection.ALONG_X,
            ),
            TurningBlock(
                block_id="r4", name="bore", tool_number=2, spindle=CSS, coolant=CoolantMode.FLOOD,
                side=TurningSide.INSIDE, target_radius_mm=10, end_z_mm=-25,
                feed_mm_per_rev=0.15, depth_of_cut_mm=1, start_corner=chamfer(0.5),
                shoulder_corner=fillet(1), finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.08,
            ),
        ),
    )


REFERENCE_SETTINGS = PostSettings(XInputMode.DIAMETER)
