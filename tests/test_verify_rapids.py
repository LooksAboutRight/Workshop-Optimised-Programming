"""The verification must not report the diagonal rapids of facing and turning  (the finishing pass through air is covered in test_turning_retract)."""

import unittest

from tests.helpers import simple_tool
from wop.core.program_model.operations import CoolantMode, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (importing registers the built-in types)
from wop.core.blocks.base import Safety
from wop.core.blocks.facing import FacingBlock, FacingDirection
from wop.core.blocks.turning import PassDirection, TurningBlock, TurningSide
from wop.core.program_model.program import Program, plan_program
from wop.core.verify import FindingKind, verify_plan

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
FEED = 0.25


def program(*blocks):
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=(simple_tool(1, side=1),),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=tuple(blocks),
    )


def kinds(prog):
    return {finding.kind for finding in verify_plan(prog, plan_program(prog))}


class DiagonalRapidTests(unittest.TestCase):
    def test_facing_in_both_directions_has_no_rapid_finding(self):
        for direction in FacingDirection:
            with self.subTest(direction=direction):
                block = FacingBlock(
                    block_id="f", tool_number=1, spindle=RPM, coolant=CoolantMode.NONE, target_z_mm=-3,
                    feed_mm_per_rev=FEED, depth_of_cut_mm=1, direction=direction,
                )
                self.assertNotIn(FindingKind.RAPID_IN_MATERIAL, kinds(program(block)))

    def test_turning_outside_along_z_and_x_has_no_rapid_finding(self):
        for direction in PassDirection:
            with self.subTest(direction=direction):
                block = TurningBlock(
                    block_id="t", tool_number=1, spindle=RPM, coolant=CoolantMode.NONE, side=TurningSide.OUTSIDE,
                    target_radius_mm=10, end_z_mm=-30, feed_mm_per_rev=FEED, depth_of_cut_mm=2,
                    pass_direction=direction,
                )
                self.assertNotIn(FindingKind.RAPID_IN_MATERIAL, kinds(program(block)))
