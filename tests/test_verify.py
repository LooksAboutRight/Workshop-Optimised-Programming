import unittest
from dataclasses import dataclass, replace

from tests.helpers import simple_tool
from wop.core.geometry import Point
from wop.core.program_model.operations import (
    BlockBegin,
    BlockEnd,
    CoolantMode,
    Rapid,
    SpindleMode,
    SpindleSetting,
)
from wop.core.program_model.raw_part import RawPart

from tests.reference_program import reference_program
from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (importing registers the built-in types)
from wop.core.blocks.base import Block, BlockContext, BlockRegistry, BlockResult, Safety
from wop.core.blocks.turning import PassDirection, TurningBlock, TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.contour import ContourDefinition, LineStep, fillet
from wop.core.contour_solver import build_contour
from wop.core.program_model.program import Program, plan_program
from wop.core.geometry.region import Region
from wop.core.verify import FindingKind, verify_plan

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)


def turning_block(tool: int, radius: float = 10):
    return TurningBlock(
        block_id="t", tool_number=tool, spindle=RPM, coolant=CoolantMode.NONE,
        side=TurningSide.OUTSIDE, target_radius_mm=radius, end_z_mm=-30,
        feed_mm_per_rev=0.25, depth_of_cut_mm=2,
    )


def program_with_findings():
    """A contour with a groove that the tool is too wide for: the finishing follows it as drawn and the checks report it."""
    points = [(10, 0), (10, -10), (6, -10), (6, -14), (10, -14), (10, -30)]
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    contour = build_contour("c", "groove", ContourDefinition(Point(*points[0]), steps))
    block = ContourTurningBlock(
        block_id="c", tool_number=1, spindle=RPM, contour_id=contour.contour_id, side=TurningSide.OUTSIDE,
        feed_mm_per_rev=0.25, depth_of_cut_mm=2, finish_allowance_mm=0.2,
    )
    return replace(program(block), contours=(contour,))


def program(*blocks):
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=(simple_tool(1, side=1), simple_tool(2, side=-1)),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=tuple(blocks),
    )


class VerifyTests(unittest.TestCase):
    def test_the_reference_program_has_no_findings(self):
        reference = reference_program()
        self.assertEqual(verify_plan(reference, plan_program(reference)), [])

    def test_roughing_stays_out_of_a_fillet_in_the_shoulder_corner(self):
        # Regression: the roughing passes used to end in a square corner inside the fillet.
        for allowance in (0, 0.3):
            for direction in PassDirection:
                with self.subTest(allowance=allowance, direction=direction):
                    block = TurningBlock(
                        block_id="f", tool_number=1, spindle=RPM, side=TurningSide.OUTSIDE,
                        target_radius_mm=10, end_z_mm=-30, feed_mm_per_rev=0.25,
                        depth_of_cut_mm=2, shoulder_corner=fillet(1.5), pass_direction=direction,
                        finish_allowance_mm=allowance, finish_feed_mm_per_rev=0.1,
                    )
                    prog = program(block)
                    self.assertEqual(verify_plan(prog, plan_program(prog)), [])

    def test_a_grooving_block_has_no_findings(self):
        from wop.core.blocks.grooving import GroovingBlock
        from wop.core.tooling.tool_presets import groove_tool

        for width, allowance in ((3, 0), (8, 0), (8, 0.2)):
            with self.subTest(width=width, allowance=allowance):
                block = GroovingBlock(
                    block_id="g", tool_number=3, spindle=RPM, side=TurningSide.OUTSIDE,
                    start_z_mm=-10, width_mm=width, bottom_radius_mm=12, feed_mm_per_rev=0.05,
                    peck_depth_mm=1, finish_allowance_mm=allowance,
                )
                prog = replace(program(block), tools=(groove_tool(3, "groove"),))
                self.assertEqual(verify_plan(prog, plan_program(prog)), [])

    def test_contour_turning_with_an_unreachable_groove_is_written_as_drawn_and_the_checks_report_it(self):
        # The finishing follows the groove as drawn: the tool is too wide for it, and the problem list says so.
        points = [(10, 0), (10, -10), (6, -10), (6, -14), (10, -14), (10, -30)]
        steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
        contour = build_contour("c", "groove", ContourDefinition(Point(*points[0]), steps))
        block = ContourTurningBlock(
            block_id="c", tool_number=1, spindle=RPM, contour_id=contour.contour_id, side=TurningSide.OUTSIDE,
            feed_mm_per_rev=0.25, depth_of_cut_mm=2, finish_allowance_mm=0.2,
        )
        prog = replace(program(block), contours=(contour,))
        findings = verify_plan(prog, plan_program(prog))
        self.assertTrue(any(f.kind is FindingKind.GOUGE for f in findings))

    def test_a_tool_with_its_body_towards_the_axis_on_an_outside_cut_works_on_the_far_side(self):
        # Tool 2 has its body towards the axis: on an outside cut it stands below the axis (an upside-down tool) and cuts the far side.
        prog = program(turning_block(tool=2))
        plan = plan_program(prog)
        self.assertLess(min(op.end.x for op in plan.operations if hasattr(op, "end")), 0)  # the moves are below the axis
        self.assertEqual(verify_plan(prog, plan), [])

    def test_a_finding_says_where_and_what_to_do(self):
        prog = program_with_findings()
        finding = verify_plan(prog, plan_program(prog))[0]
        self.assertEqual(finding.block_index, 0)
        self.assertIn("block 1", finding.message)
        self.assertTrue(finding.remedy)
        self.assertIsInstance(finding.position, Point)

    def test_each_kind_is_reported_once_per_move(self):
        prog = program_with_findings()
        findings = verify_plan(prog, plan_program(prog))
        keys = [(f.operation_index, f.kind) for f in findings]
        self.assertEqual(len(keys), len(set(keys)))

    def test_a_rapid_move_into_the_material_is_found(self):
        registry = BlockRegistry()

        @registry.register
        @dataclass(frozen=True, kw_only=True)
        class DiveBlock(Block):
            type_name = "dive"

            def generate(self, context: "BlockContext") -> "BlockResult":
                operations = (
                    BlockBegin(0, self.block_id, self.type_name, ""),
                    Rapid(Point(5, -20)),
                    BlockEnd(self.block_id),
                )
                return BlockResult(operations, Region.empty())

        prog = program(DiveBlock(block_id="d", tool_number=1, spindle=RPM))
        kinds = [f.kind for f in verify_plan(prog, plan_program(prog))]
        self.assertIn(FindingKind.RAPID_IN_MATERIAL, kinds)


if __name__ == "__main__":
    unittest.main()
