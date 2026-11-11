import unittest

from wop.core.program_model.operations import LinearMove, SetSpindle
from wop.core.program_model.raw_part import RawPart

from tests.test_blocks_turning import FINISH_FEED, ROUGH_FEED, SAFETY, SPINDLE, context_for, make_block, moves_with_feed
from wop.core.blocks.base import BlockContext, BlockError
from tests.helpers import simple_tool



def block(**overrides):
    return make_block(finish_feed_mm_per_rev=FINISH_FEED, **overrides)  # the finishing pass has its own feed


class TurningRetractTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def test_the_block_ends_with_one_rapid_to_the_safe_point(self):
        ops = block().generate(self.context).operations
        last = ops[-2]  # the last operation is the end marker
        self.assertEqual((last.end.x, last.end.z), (SAFETY.safe_radius_mm, SAFETY.safe_z_mm))

class TurningFinishPassTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def test_form_order_and_finishing_feed_greyed_out(self):
        block = make_block(finish_pass=False)
        fields = block.form_fields()
        self.assertEqual(fields[0], "name")
        self.assertEqual(fields[-1], "coolant")
        self.assertLess(fields.index("finish_allowance_mm"), fields.index("finish_pass"))
        self.assertIn("finish_feed_mm_per_rev", block.form_disabled())
        self.assertNotIn("finish_feed_mm_per_rev", make_block(finish_pass=True).form_disabled())

    def test_without_a_finishing_pass_nothing_is_cut_with_the_finishing_feed(self):
        block = make_block(finish_allowance_mm=0.3, finish_feed_mm_per_rev=FINISH_FEED, finish_pass=False)
        result = block.generate(self.context)
        self.assertEqual(moves_with_feed(result, FINISH_FEED), [])
        self.assertTrue(moves_with_feed(result, ROUGH_FEED))

    def test_the_allowance_stays_when_there_is_no_finishing_pass(self):
        done = make_block(finish_allowance_mm=0.3, finish_pass=True).generate(self.context)
        kept = make_block(finish_allowance_mm=0.3, finish_pass=False).generate(self.context)
        self.assertLess(kept.removed.area, done.removed.area - 1)

    def test_the_finishing_pass_is_on_by_default(self):
        self.assertTrue(make_block().finish_pass)


class TurningFinishingSpindleTests(unittest.TestCase):
    def setUp(self):
        self.context = context_for(RawPart("steel", 30, 60))

    def spindle_changes(self, **overrides):
        ops = block(**overrides).generate(self.context).operations
        return [(i, op) for i, op in enumerate(ops) if isinstance(op, SetSpindle)], ops

    def test_a_finishing_speed_is_set_right_before_the_finishing_pass(self):
        changes, ops = self.spindle_changes(finish_spindle_value=2000)
        self.assertEqual(len(changes), 1)
        index, change = changes[0]
        self.assertEqual((change.setting.mode, change.setting.value), (SPINDLE.mode, 2000))
        later = [op for op in ops[index:] if isinstance(op, LinearMove)]
        self.assertTrue(all(op.feed_mm_per_rev == FINISH_FEED for op in later))
        earlier = [op for op in ops[:index] if isinstance(op, LinearMove)]
        self.assertTrue(earlier and all(op.feed_mm_per_rev == ROUGH_FEED for op in earlier))

    def test_no_change_without_a_value_or_with_the_same_value(self):
        self.assertEqual(self.spindle_changes()[0], [])
        self.assertEqual(self.spindle_changes(finish_spindle_value=SPINDLE.value)[0], [])

    def test_no_change_when_there_is_no_finishing_pass(self):
        self.assertEqual(self.spindle_changes(finish_spindle_value=2000, finish_pass=False)[0], [])

    def test_the_finishing_speed_must_be_positive(self):
        with self.assertRaises(BlockError):
            block(finish_spindle_value=0)

    def test_the_finishing_speed_is_greyed_out_with_the_finishing_pass(self):
        self.assertIn("finish_spindle_value", make_block(finish_pass=False).form_disabled())
        self.assertNotIn("finish_spindle_value", make_block().form_disabled())


class TurningFinishingThroughAirTests(unittest.TestCase):
    def test_the_finishing_pass_only_feeds_where_there_is_material(self):
        raw = RawPart("steel", 30, 60)
        first = block(target_radius_mm=8, end_z_mm=-20).generate(context_for(raw))
        residual = context_for(raw).residual.difference(first.removed)
        context = BlockContext(raw, simple_tool(1), residual, SAFETY)
        result = block(target_radius_mm=10, end_z_mm=-30, finish_allowance_mm=0.3).generate(context)
        finishing = moves_with_feed(result, FINISH_FEED)
        self.assertTrue(finishing)
        # Down to Z-20 the part is already smaller than the outline: no cutting feed there.
        self.assertTrue(all(move.end.z <= -20 + 0.5 for move in finishing))


if __name__ == "__main__":
    unittest.main()
