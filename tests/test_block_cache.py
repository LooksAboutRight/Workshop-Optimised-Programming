"""The block cache (`PlanCache` in wop/core/program_model/plan_cache.py): a block with the same inputs and the same material before it is taken from the last plan,
and a plan made with the cache is the same as one made without it."""

import unittest
from dataclasses import replace
from pathlib import Path

from wop.core.program_model.plan_cache import PlanCache
from wop.core.program_model.program import plan_program
from wop.core.files.project_io import project_from_json
from wop.core.verify import verify_plan

ROOT = Path(__file__).resolve().parent.parent


def reference():
    return project_from_json((ROOT / "examples" / "reference.wop.json").read_text(encoding="utf-8")).program


def with_block(program, index, **changes):
    blocks = list(program.blocks)
    blocks[index] = replace(blocks[index], **changes)
    return replace(program, blocks=tuple(blocks))


class BlockCacheTests(unittest.TestCase):
    def assertSamePlan(self, cached, fresh):
        self.assertEqual(cached.operations, fresh.operations)
        self.assertEqual(cached.messages, fresh.messages)
        self.assertEqual([b.program_index for b in cached.blocks], [b.program_index for b in fresh.blocks])
        for a, b in zip(cached.blocks, fresh.blocks):
            self.assertAlmostEqual(a.residual_after.area, b.residual_after.area, places=9)

    def test_the_same_program_again_takes_every_block_from_the_cache(self):
        program, cache = reference(), PlanCache()
        first = plan_program(program, cache=cache)
        self.assertEqual(cache.hits, 0)
        again = plan_program(program, cache=cache)
        self.assertEqual(cache.hits, len(program.blocks))
        self.assertSamePlan(again, first)

    def test_a_changed_block_and_the_blocks_after_it_are_planned_again(self):
        program, cache = reference(), PlanCache()
        plan_program(program, cache=cache)
        last = len(program.blocks) - 1
        changed = with_block(program, last, name="changed")
        hits = cache.hits
        cached = plan_program(changed, cache=cache)
        self.assertEqual(cache.hits - hits, last)  # every block but the last
        self.assertSamePlan(cached, plan_program(changed))
        hits = cache.hits
        first_changed = with_block(changed, 1, name="changed too")
        plan_program(first_changed, cache=cache)
        self.assertEqual(cache.hits - hits, 1)  # only the block before it

    def test_a_selection_and_the_whole_program_share_the_cache(self):
        program, cache = reference(), PlanCache()
        for selection, unticked_done in ((None, True), ((2,), True), ((2,), False), (None, True)):
            with self.subTest(selection=selection, unticked_done=unticked_done):
                self.assertSamePlan(
                    plan_program(program, selection=selection, unticked_done=unticked_done, cache=cache),
                    plan_program(program, selection=selection, unticked_done=unticked_done),
                )

    def test_a_thicker_bar_plans_everything_again(self):
        program, cache = reference(), PlanCache()
        plan_program(program, cache=cache)
        hits = cache.hits
        thicker = replace(program, raw_part=replace(program.raw_part, outer_diameter_mm=program.raw_part.outer_diameter_mm + 2))
        self.assertSamePlan(plan_program(thicker, cache=cache), plan_program(thicker))
        self.assertEqual(cache.hits, hits)

    def test_the_cache_keeps_no_more_than_its_size(self):
        program, cache = reference(), PlanCache(size=2)
        plan_program(program, cache=cache)
        hits = cache.hits
        plan_program(program, cache=cache)
        self.assertEqual(cache.hits - hits, 0)  # the first blocks were pushed out by the later ones



class CheckCacheTests(unittest.TestCase):
    """The check of a block is kept like its plan: the same findings as a check without the cache."""

    def collision_demo(self):
        return project_from_json((ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json").read_text(encoding="utf-8")).program

    def test_the_findings_are_the_same_and_an_unchanged_block_is_not_checked_again(self):
        program, cache = self.collision_demo(), PlanCache()
        plan = plan_program(program, cache=cache)
        fresh = verify_plan(program, plan)
        self.assertTrue(fresh)  # the demo has collisions
        self.assertEqual(verify_plan(program, plan, cache=cache), fresh)
        self.assertEqual(cache.recalled["check"], 0)
        self.assertEqual(verify_plan(program, plan_program(program, cache=cache), cache=cache), fresh)
        self.assertEqual(cache.recalled["check"], len(plan.blocks))

    def test_after_a_change_the_changed_block_and_the_later_ones_are_checked_again(self):
        program, cache = reference(), PlanCache()
        verify_plan(program, plan_program(program, cache=cache), cache=cache)
        changed = with_block(program, len(program.blocks) - 1, name="changed")
        hits = cache.recalled["check"]
        plan = plan_program(changed, cache=cache)
        self.assertEqual(verify_plan(changed, plan, cache=cache), verify_plan(changed, plan))
        self.assertEqual(cache.recalled["check"] - hits, len(program.blocks) - 1)


if __name__ == "__main__":
    unittest.main()
