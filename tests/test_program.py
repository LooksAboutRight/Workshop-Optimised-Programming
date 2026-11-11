import unittest
from dataclasses import dataclass, replace

from tests.helpers import simple_tool
from wop.core.program_model.operations import (
    BlockBegin,
    BlockEnd,
    CoolantMode,
    Rapid,
    SetCoolant,
    SetSpindle,
    SpindleMode,
    SpindleSetting,
    StopSpindle,
    ToolChange,
)
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (importing registers the built-in types)
from wop.core.blocks.base import Block, BlockContext, BlockError, BlockRegistry, BlockResult, Safety
from wop.core.blocks.facing import FacingBlock
from wop.core.blocks.turning import TurningBlock, TurningSide
from wop.core.program_model.program import Program, plan_program
from wop.core.geometry.region import Region

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
CSS = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 150, 3000)


def program(*blocks, tools=None):
    return Program(
        raw_part=RawPart("steel", 30, 60),
        tools=tools or (simple_tool(1), simple_tool(2)),
        safety=Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1),
        blocks=tuple(blocks),
    )


def facing(block_id="f", tool=1, spindle=RPM, coolant=CoolantMode.NONE, target=-1):
    return FacingBlock(
        block_id=block_id, tool_number=tool, spindle=spindle, coolant=coolant,
        target_z_mm=target, feed_mm_per_rev=0.2, depth_of_cut_mm=1,
    )


def turning(block_id="t", tool=1, spindle=RPM, coolant=CoolantMode.NONE):
    return TurningBlock(
        block_id=block_id, tool_number=tool, spindle=spindle, coolant=coolant,
        side=TurningSide.OUTSIDE, target_radius_mm=10, end_z_mm=-30,
        feed_mm_per_rev=0.25, depth_of_cut_mm=2,
    )


def kinds(operations, wanted):
    return [op for op in operations if isinstance(op, wanted)]


class PlanTests(unittest.TestCase):
    def test_a_finishing_speed_inside_a_block_is_known_to_the_next_block(self):
        fast = replace(turning("a"), finish_spindle_value=2000)
        plan = plan_program(program(fast, turning("b")))
        second = [op for op in plan.blocks[1].operations if isinstance(op, SetSpindle)]
        self.assertEqual([op.setting.value for op in second], [RPM.value])  # back to the normal speed


    def test_blocks_keep_their_order_and_get_their_index(self):
        plan = plan_program(program(facing("a"), turning("b")))
        begins = kinds(plan.operations, BlockBegin)
        self.assertEqual([(b.index, b.block_id) for b in begins], [(0, "a"), (1, "b")])
        self.assertEqual(len(kinds(plan.operations, BlockEnd)), 2)

    def test_residual_follows_the_blocks(self):
        plan = plan_program(program(facing("a"), turning("b")))
        first, second = plan.blocks
        self.assertAlmostEqual(first.residual_after.area, plan.stock.area - first.result.removed.area)
        self.assertAlmostEqual(second.residual_before.area, first.residual_after.area)
        self.assertAlmostEqual(plan.final_residual.area, second.residual_after.area)

    def test_second_block_only_cuts_what_is_left(self):
        # The same facing twice: the second one finds nothing to cut.
        plan = plan_program(program(facing("a"), facing("b")))
        self.assertTrue(plan.blocks[1].result.removed.is_empty)
        self.assertEqual(len(plan.messages), 1)

    def test_tool_change_only_when_the_tool_changes(self):
        plan = plan_program(program(facing("a", tool=1), turning("b", tool=1), turning("c", tool=2)))
        changes = [op.tool_number for op in kinds(plan.operations, ToolChange)]
        self.assertEqual(changes, [1, 2])

    def test_every_tool_change_is_preceded_by_a_retract_to_the_safe_position(self):
        plan = plan_program(program(facing("a", tool=1), turning("b", tool=2)))
        operations = plan.operations
        for index, operation in enumerate(operations):
            if isinstance(operation, ToolChange):
                previous = [op for op in operations[:index] if isinstance(op, Rapid)][-1]
                self.assertEqual((previous.end.x, previous.end.z), (25, 10))

    def test_spindle_and_coolant_are_set_when_they_change(self):
        plan = plan_program(
            program(
                facing("a", spindle=CSS, coolant=CoolantMode.FLOOD),
                turning("b", spindle=CSS, coolant=CoolantMode.FLOOD),
                turning("c", spindle=RPM, coolant=CoolantMode.MIST),
            )
        )
        spindles = [op.setting for op in kinds(plan.operations, SetSpindle)]
        coolants = [op.mode for op in kinds(plan.operations, SetCoolant)]
        self.assertEqual(spindles, [CSS, RPM])
        self.assertEqual(coolants, [CoolantMode.FLOOD, CoolantMode.MIST, CoolantMode.NONE])

    def test_program_ends_at_the_safe_position_with_spindle_stopped(self):
        plan = plan_program(program(facing("a")))
        self.assertIsInstance(plan.closing[-1], StopSpindle)
        last_rapid = kinds(plan.closing, Rapid)[-1]
        self.assertEqual((last_rapid.end.x, last_rapid.end.z), (25, 10))

    def test_the_tool_change_position_is_used_for_tool_changes_and_the_end_the_safe_position_between_blocks(self):
        base = program(facing("a", tool=1), turning("b", tool=1), turning("c", tool=2))
        separate = replace(base, safety=Safety(25, 10, 1, change_radius_mm=60, change_z_mm=30))
        plan = plan_program(separate)
        ops = plan.operations
        for index, operation in enumerate(ops):
            if isinstance(operation, ToolChange):
                previous = [op for op in ops[:index] if isinstance(op, Rapid)][-1]
                self.assertEqual((previous.end.x, previous.end.z), (60, 30))
        safe_stops = [op for op in kinds(ops, Rapid) if (op.end.x, op.end.z) == (25, 10)]
        self.assertTrue(safe_stops)  # between the blocks of tool 1 the tool waits at the safe position
        last_rapid = kinds(plan.closing, Rapid)[-1]
        self.assertEqual((last_rapid.end.x, last_rapid.end.z), (60, 30))

    def test_unknown_tool_leaves_the_block_out_with_the_reason(self):
        plan = plan_program(program(facing("a", tool=9)))
        self.assertEqual(plan.blocks, ())
        self.assertIn("T9", plan.left_out[0].reason)
        self.assertTrue(any("is left out" in message for message in plan.messages))

    def test_a_block_that_fails_does_not_stop_the_others(self):
        plan = plan_program(program(facing("a"), facing("b", tool=9), facing("c")))
        self.assertEqual([p.block.block_id for p in plan.blocks], ["a", "c"])
        self.assertEqual([left.program_index for left in plan.left_out], [1])

    def test_a_block_whose_calculation_fails_is_left_out_with_the_reason(self):
        class Broken(FacingBlock):
            def generate(self, context):
                return 1 / 0

        broken = Broken(**{name: getattr(facing("b"), name) for name in facing("b").__dataclass_fields__})
        plan = plan_program(program(facing("a"), broken, facing("c")))
        self.assertEqual([p.block.block_id for p in plan.blocks], ["a", "c"])
        self.assertIn("ZeroDivisionError", plan.left_out[0].reason)

    def test_empty_program(self):
        plan = plan_program(program())
        self.assertEqual(plan.operations, [])
        self.assertAlmostEqual(plan.final_residual.area, plan.stock.area)


class RegistryTests(unittest.TestCase):
    """Requirement B10: a new block type is one file and needs no other change."""

    def test_built_in_types_are_registered(self):
        self.assertEqual(BLOCK_TYPES.names(), [
            "facing", "turning", "drilling", "threading", "grooving", "turning_contour",
            "machine_function", "custom_path"])
        self.assertIn("facing", BLOCK_TYPES.names())
        self.assertIn("turning", BLOCK_TYPES.names())
        self.assertIs(BLOCK_TYPES.get("facing"), FacingBlock)

    def test_a_new_block_type_needs_only_its_own_class(self):
        registry = BlockRegistry()

        @registry.register
        @dataclass(frozen=True, kw_only=True)
        class DummyBlock(Block):
            type_name = "dummy"

            def generate(self, context: "BlockContext") -> "BlockResult":
                return BlockResult((BlockBegin(0, self.block_id, self.type_name, ""),), Region.empty())

        self.assertEqual(registry.names(), ["dummy"])
        block = DummyBlock(block_id="d", tool_number=1, spindle=RPM)
        plan = plan_program(program(block))
        self.assertEqual(kinds(plan.operations, BlockBegin)[0].type_name, "dummy")

    def test_unknown_and_duplicate_names_are_rejected(self):
        with self.assertRaises(BlockError):
            BLOCK_TYPES.get("teleport")
        with self.assertRaises(BlockError):
            BLOCK_TYPES.register(FacingBlock)


if __name__ == "__main__":
    unittest.main()
