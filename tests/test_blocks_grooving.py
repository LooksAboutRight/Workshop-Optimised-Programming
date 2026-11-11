import unittest

from wop.core.program_model.operations import LinearMove, Rapid, SetSpindle, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, BlockError, Safety
from wop.core.blocks.grooving import GroovePeckMode, GroovingBlock, OneSidedMode, default_one_sided_value
from wop.core.blocks.turning_common import TurningSide
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region
from wop.core.tooling.tool_presets import groove_tool

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 800)
AREA_TOLERANCE = 0.05


def block(**overrides):
    values = dict(
        block_id="g1", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE,
        start_z_mm=-10, width_mm=4, bottom_radius_mm=12, feed_mm_per_rev=0.05,
    )
    values.update(overrides)
    return GroovingBlock(**values)


def context(raw_part=None, tool=None, residual=None):
    raw_part = raw_part or RawPart("steel", 30, 60)
    safety = Safety(safe_radius_mm=25, safe_z_mm=10, clearance_mm=1)
    return BlockContext(
        raw_part, tool or groove_tool(1, "groove 3"), residual or stock_region(raw_part), safety
    )


class GroovingPositionTests(unittest.TestCase):
    def test_a_groove_in_front_of_the_face_says_that_z_is_absolute(self):
        result = block(start_z_mm=25).generate(context())
        self.assertTrue(any("not in the material" in m and "absolute" in m for m in result.messages))


class GroovePlungeOrderTests(unittest.TestCase):
    def _path(self, **overrides):
        values = dict(start_z_mm=-5, width_mm=14, bottom_radius_mm=12, feed_mm_per_rev=0.05)
        values.update(overrides)
        return block(**values).generate(context()).operations

    def test_a_wide_groove_is_roughed_front_first_then_towards_the_chuck(self):
        feeds = list(dict.fromkeys(op.end.z for op in self._path() if isinstance(op, LinearMove)))  # one per plunge
        self.assertEqual(feeds[1], -5 - 3)  # the second plunge is the one at the front wall
        self.assertEqual(feeds[2:], sorted(feeds[2:], reverse=True))  # then steps towards the chuck
        self.assertEqual(feeds[-1], -19)
        self.assertTrue(all(a - b <= 1 + 1e-9 for a, b in zip(feeds[2:], feeds[3:])))  # steps of the one-sided cut

    def test_the_finishing_passes_stop_early_and_overlap_by_one_blade(self):
        path = self._path(finish_allowance_mm=0.2, finish_pass=True, finish_feed_mm_per_rev=0.02)
        finish = [op for op in path if isinstance(op, LinearMove) and op.feed_mm_per_rev == 0.02]
        # plunge at the front wall, pass to 1.5 in front of the other wall, plunge at the other wall, same pass back
        self.assertEqual([round(op.end.z, 3) for op in finish], [-8, -17.5, -19, -17.5])
        self.assertEqual([round(op.end.x, 3) for op in finish], [12, 12, 12, 12])

    def test_a_groove_to_the_axis_is_allowed(self):
        block(bottom_radius_mm=0)


class GroovingValidationTests(unittest.TestCase):
    def test_bad_values_are_refused(self):
        for overrides in (
            dict(width_mm=0), dict(bottom_radius_mm=-1), dict(feed_mm_per_rev=0),
            dict(peck_depth_mm=0), dict(finish_allowance_mm=-1), dict(finish_feed_mm_per_rev=0),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(BlockError):
                    block(**overrides)


class GroovingTests(unittest.TestCase):
    def test_a_groove_as_wide_as_the_blade_is_cut_out(self):
        result = block(width_mm=3).generate(context())
        self.assertEqual(result.messages, ())
        expected = Region.rectangle(12, -13, 15, -10)
        self.assertAlmostEqual(result.removed.area, expected.area, delta=AREA_TOLERANCE)
        self.assertTrue(result.removed.intersection(expected).area > expected.area - AREA_TOLERANCE)

    def test_a_wider_groove_needs_several_plunges(self):
        result = block(width_mm=8).generate(context())
        self.assertEqual(result.messages, ())
        self.assertAlmostEqual(result.removed.area, 8 * 3, delta=AREA_TOLERANCE)
        plunges = [
            op for op in result.operations
            if isinstance(op, LinearMove) and abs(op.end.x - 12) < 1e-6
        ]
        self.assertGreaterEqual(len(plunges), 3)

    def test_pecking_splits_the_plunge(self):
        plain = block(width_mm=3).generate(context())
        pecked = block(width_mm=3, peck_depth_mm=1).generate(context())
        feeds = lambda r: [op for op in r.operations if isinstance(op, LinearMove)]
        self.assertEqual(len(feeds(plain)), 1)
        self.assertEqual(len(feeds(pecked)), 3)

    def test_a_finishing_allowance_still_reaches_the_final_size(self):
        result = block(width_mm=6, finish_allowance_mm=0.2, finish_pass=True).generate(context())
        self.assertEqual(result.messages, ())
        self.assertAlmostEqual(result.removed.area, 6 * 3, delta=AREA_TOLERANCE)

    def test_a_tool_wider_than_the_groove_leaves_it_uncut(self):
        wide_tool = groove_tool(1, "groove 6", blade_width_mm=6)
        result = block(width_mm=4).generate(context(tool=wide_tool))
        self.assertTrue(result.messages)

    def test_a_too_short_blade_leaves_the_bottom_uncut(self):
        short_tool = groove_tool(1, "short", reach_mm=1)
        result = block(bottom_radius_mm=10).generate(context(tool=short_tool))
        self.assertTrue(result.messages)

    def test_an_inside_groove_in_a_bore(self):
        raw_part = RawPart("steel", 100, 60)  # the bore must be wide enough for the 30 mm long tool body
        bore = Region.rectangle(0, -60, 40, 0)
        residual = stock_region(raw_part).difference(bore)
        tool = groove_tool(1, "inner groove", body_towards_larger_x=False)
        result = block(side=TurningSide.INSIDE, bottom_radius_mm=43, width_mm=3).generate(
            context(raw_part, tool, residual)
        )
        self.assertEqual(result.messages, ())
        self.assertAlmostEqual(result.removed.area, 3 * 3, delta=AREA_TOLERANCE)

    def test_a_bottom_above_the_surface_removes_nothing(self):
        result = block(bottom_radius_mm=20).generate(context())
        self.assertTrue(result.messages)
        self.assertTrue(result.removed.is_empty)

    def test_the_allowance_stays_when_there_is_no_finishing_pass(self):
        result = block(width_mm=6, finish_allowance_mm=0.4).generate(context())
        self.assertEqual(result.messages, ())
        self.assertAlmostEqual(result.removed.area, (6 - 0.8) * (3 - 0.4), delta=AREA_TOLERANCE * 2)

    def test_the_example_block_generates(self):
        example = GroovingBlock.example("g1", 1, SPINDLE)
        result = example.generate(context())
        self.assertEqual(result.messages, ())


def moves_of(result):
    return [op for op in result.operations if hasattr(op, "end")]


class GroovingPathTests(unittest.TestCase):
    def test_an_outside_block_starts_with_a_z_move_at_the_safe_radius_and_ends_at_the_safe_point(self):
        moves = moves_of(block(width_mm=3).generate(context()))
        self.assertEqual((moves[0].end.x, moves[0].end.z), (25, -13))  # the first plunge position
        self.assertEqual((moves[1].end.x, moves[1].end.z), (16, -13))  # X to the clear radius, nothing else
        self.assertEqual((moves[-1].end.x, moves[-1].end.z), (25, 10))

    def test_an_inside_block_starts_like_a_drill_and_ends_at_the_safe_point(self):
        raw_part = RawPart("steel", 100, 60)  # the bore must be wide enough for the 30 mm long tool body
        residual = stock_region(raw_part).difference(Region.rectangle(0, -60, 40, 0))
        tool = groove_tool(1, "inner groove", body_towards_larger_x=False)
        result = block(side=TurningSide.INSIDE, bottom_radius_mm=43, width_mm=3).generate(context(raw_part, tool, residual))
        moves = moves_of(result)
        for move, wanted in ((moves[0], (39, 10)), (moves[1], (39, -13)), (moves[-1], (25, 10))):  # clear radius at the safe Z, down the bore, out
            self.assertAlmostEqual(move.end.x, wanted[0], places=9)
            self.assertAlmostEqual(move.end.z, wanted[1], places=9)

    def test_the_tool_retracts_to_the_surface_of_the_place_it_works_not_to_the_largest_radius(self):
        raw_part = RawPart("steel", 30, 90)
        turned_down = stock_region(raw_part).difference(Region.rectangle(10, -90, 15, -30))
        result = block(start_z_mm=-60, bottom_radius_mm=8, width_mm=3).generate(context(raw_part, None, turned_down))
        self.assertEqual(result.messages, ())
        plunge_start = [m for m in moves_of(result) if isinstance(m, Rapid) and m.end.x < 25][0]
        self.assertEqual(plunge_start.end.x, 11)  # radius 10 plus the clearance (not 15 + 1)

    def test_a_second_groove_rapids_through_the_air_of_the_first(self):
        first = block(width_mm=3, bottom_radius_mm=13).generate(context())
        residual = stock_region(RawPart("steel", 30, 60)).difference(first.removed)
        second = block(width_mm=3, bottom_radius_mm=11).generate(context(residual=residual))
        self.assertEqual(second.messages, ())
        moves = moves_of(second)
        feed = [i for i, m in enumerate(moves) if isinstance(m, LinearMove)][0]
        self.assertAlmostEqual(moves[feed - 1].end.x, 14, delta=0.2)  # in to the clearance above the first groove's bottom (13 + 1)
        self.assertAlmostEqual(moves[feed].end.x, 11)

    def test_the_two_peck_modes(self):
        def path(mode):
            result = block(width_mm=3, peck_depth_mm=1, peck_mode=mode).generate(context())
            return [(m.end.x, "F" if isinstance(m, LinearMove) else "R") for m in moves_of(result)][2:-1]
        self.assertEqual(path(GroovePeckMode.CHIP_BREAK), [
            (14, "F"), (14.5, "R"), (14, "R"), (13, "F"), (13.5, "R"), (13, "R"), (12, "F"), (16, "R")])
        self.assertEqual(path(GroovePeckMode.FULL_RETRACT), [
            (14, "F"), (16, "R"), (14.25, "R"), (13, "F"), (16, "R"), (13.25, "R"), (12, "F"), (16, "R")])

    def test_the_form_order_labels_and_greyed_out_fields(self):
        from wop.ui.block_forms import form_for
        specs = form_for(block())
        names = list(dict.fromkeys(spec.path[0] for spec in specs))  # the spindle has several fields
        self.assertEqual(names[:6], ["name", "style", "side", "tool_number", "spindle", "feed_mm_per_rev"])
        self.assertEqual(names[-1], "coolant")
        self.assertLess(names.index("peck_depth_mm"), names.index("finish_allowance_mm"))
        self.assertEqual(next(s for s in specs if s.path[0] == "start_z_mm").label, "Groove Z (front edge)")
        self.assertEqual(next(s for s in specs if s.path[0] == "bottom_radius_mm").label, "Final X radius")
        off = {spec.path[0] for spec in specs if not spec.enabled}
        self.assertEqual(off, {"peck_mode", "finish_feed_mm_per_rev", "finish_spindle_value"})
        on = {spec.path[0] for spec in form_for(block(peck_depth_mm=1, finish_pass=True)) if not spec.enabled}
        self.assertEqual(on, set())

    def test_the_finishing_speed_is_set_before_the_finishing_plunges(self):
        result = block(width_mm=6, finish_allowance_mm=0.2, finish_pass=True, finish_spindle_value=1200).generate(context())
        changes = [i for i, op in enumerate(result.operations) if isinstance(op, SetSpindle)]
        self.assertEqual(len(changes), 1)
        self.assertEqual(result.operations[changes[0]].setting.value, 1200)
        self.assertTrue(all(not isinstance(op, LinearMove) or op.feed_mm_per_rev == 0.05 for op in result.operations[:changes[0]]))

    def test_an_old_project_block_with_an_allowance_gets_the_finishing_pass(self):
        from wop.core.blocks import BLOCK_TYPES  # noqa: F401
        from wop.core.files.project_io import _block_from_data
        parameters = {"block_id": "g", "tool_number": 1, "spindle": {"mode": "CONSTANT_RPM", "value": 800, "rpm_limit": None},
                      "side": "OUTSIDE", "start_z_mm": -10, "width_mm": 4, "bottom_radius_mm": 12, "feed_mm_per_rev": 0.05,
                      "finish_allowance_mm": 0.2}
        self.assertTrue(_block_from_data({"type": "grooving", "parameters": parameters}).finish_pass)
        parameters["finish_allowance_mm"] = 0
        self.assertFalse(_block_from_data({"type": "grooving", "parameters": parameters}).finish_pass)


if __name__ == "__main__":
    unittest.main()


class OneSidedModeTests(unittest.TestCase):
    def _plunges(self, **overrides):
        values = dict(start_z_mm=-5, width_mm=14, bottom_radius_mm=12, feed_mm_per_rev=0.05)
        values.update(overrides)
        path = block(**values).generate(context()).operations
        return list(dict.fromkeys(op.end.z for op in path if isinstance(op, LinearMove)))

    def test_a_percentage_of_the_blade_gives_the_same_plunges_as_the_same_mm(self):
        blade = 3  # the preset groove tool "groove 3"
        in_mm = self._plunges(one_sided_mode=OneSidedMode.MM, one_sided_cut_value=blade * 0.5)
        in_percent = self._plunges(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=50)
        self.assertEqual(in_mm, in_percent)

    def test_the_percentage_changes_the_step_with_the_blade(self):
        small = self._plunges(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=20)
        large = self._plunges(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=80)
        self.assertGreater(len(small), len(large))

    def test_the_mm_of_the_block(self):
        self.assertEqual(block(one_sided_mode=OneSidedMode.MM, one_sided_cut_value=1.5).one_sided_mm(3), 1.5)
        self.assertEqual(block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=25).one_sided_mm(4), 1)

    def test_a_percentage_above_a_whole_blade_is_refused(self):
        with self.assertRaises(BlockError):
            block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=150)
        block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=100)
        with self.assertRaises(BlockError):
            block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=0)

    def test_switching_the_mode_gives_the_default_of_the_new_mode(self):
        from dataclasses import replace

        before = block(one_sided_mode=OneSidedMode.MM, one_sided_cut_value=2.5)
        after = replace(before, one_sided_mode=OneSidedMode.PERCENT).with_derived_fields(before)
        self.assertEqual(after.one_sided_cut_value, default_one_sided_value(OneSidedMode.PERCENT))
        again = replace(after, one_sided_mode=OneSidedMode.MM).with_derived_fields(after)
        self.assertEqual(again.one_sided_cut_value, default_one_sided_value(OneSidedMode.MM))

    def test_an_edit_of_the_value_alone_is_kept(self):
        from dataclasses import replace

        before = block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=50)
        self.assertEqual(replace(before, one_sided_cut_value=30).with_derived_fields(before).one_sided_cut_value, 30)

    def test_reset_to_default_of_the_value_follows_the_mode_of_the_block(self):
        current = block(one_sided_mode=OneSidedMode.PERCENT, one_sided_cut_value=30)
        example = GroovingBlock.example("g1", 1, SPINDLE)
        self.assertEqual(current.example_with_default("one_sided_cut_value", example).one_sided_cut_value, default_one_sided_value(OneSidedMode.PERCENT))
        self.assertIs(current.example_with_default("one_sided_mode", example), example)

    def test_the_form_shows_a_dropdown_and_one_value_with_the_unit_of_the_mode(self):
        from wop.ui.block_forms import FieldKind, form_for

        for mode, unit in ((OneSidedMode.MM, "mm"), (OneSidedMode.PERCENT, "%")):
            specs = {spec.path[0]: spec for spec in form_for(block(one_sided_mode=mode, one_sided_cut_value=1))}
            self.assertIs(specs["one_sided_mode"].kind, FieldKind.CHOICE)
            self.assertEqual([c.value for c in specs["one_sided_mode"].choices], list(OneSidedMode))
            self.assertIn(f"({unit})", specs["one_sided_cut_value"].label)
