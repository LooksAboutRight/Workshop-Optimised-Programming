"""A tool that reaches past the spindle axis is also tested against the far side of the round part."""

import unittest

from tests.helpers import simple_tool
from wop.core.geometry import Point

SAFE_BAR_X = 9
HOLE_RADIUS_MM = 10
SMALL_HOLE_RADIUS_MM = 4


class FarSideTests(unittest.TestCase):
    def check(self, hole_radius, tip_x, tool):
        from wop.core.reach import CollisionContext, CollisionKind, check_prepared, prepare_tool
        from wop.core.geometry.region import Region
        material = Region.rectangle(hole_radius, -50, 20, 0)
        context = CollisionContext(Region.empty(), material)
        return {c.kind for c in check_prepared(prepare_tool(tool), Point(tip_x, -10), context)}, CollisionKind

    def test_an_outside_tool_never_gets_a_far_side(self):
        from wop.core.reach import prepare_tool
        self.assertIsNone(prepare_tool(simple_tool(1)).mirror)

    def test_a_boring_bar_in_a_wide_bore_is_free(self):
        kinds, _ = self.check(HOLE_RADIUS_MM, SAFE_BAR_X, simple_tool(1, side=-1))
        self.assertEqual(kinds, set())

    def test_a_boring_bar_in_a_small_bore_runs_into_the_far_wall(self):
        # the tip is at 3 mm, the bar reaches to -5 mm, the wall of the far side is at -4 mm
        kinds, kind = self.check(SMALL_HOLE_RADIUS_MM, 3, simple_tool(1, side=-1))
        self.assertIn(kind.HOLDER_IN_MATERIAL, kinds)

    def test_the_same_bar_further_to_the_near_wall_is_free(self):
        kinds, _ = self.check(SMALL_HOLE_RADIUS_MM + 5, SMALL_HOLE_RADIUS_MM + 5 - 1, simple_tool(1, side=-1))
        self.assertEqual(kinds, set())

    def test_a_finished_part_on_the_far_side_is_not_cut_into(self):
        from wop.core.reach import CollisionContext, CollisionKind, check_prepared, prepare_tool
        from wop.core.geometry.region import Region
        part = Region.rectangle(SMALL_HOLE_RADIUS_MM, -50, 20, 0)
        context = CollisionContext(part, part)
        kinds = {c.kind for c in check_prepared(prepare_tool(simple_tool(1, side=-1)), Point(3, -10), context)}
        self.assertIn(CollisionKind.GOUGE, kinds)


if __name__ == "__main__":
    unittest.main()
