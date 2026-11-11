"""Thread designations: the parser, the profile rules, and what the threading block does with them."""

import unittest
from dataclasses import replace

from wop.core.blocks.base import BlockError
from wop.core.blocks.threading import ThreadingBlock
from wop.core.blocks.turning_common import TurningSide
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.thread_designation import METRIC, TRAPEZOIDAL, UNIFIED, ThreadDesignationError, parse_designation

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 800)


def thread_block(**overrides):
    values = dict(
        block_id="t1", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE,
        crest_radius_mm=15, pitch_mm=1.5, start_z_mm=0, end_z_mm=-15,
    )
    values.update(overrides)
    return ThreadingBlock(**values)


class ParserTests(unittest.TestCase):
    def test_metric_with_and_without_pitch(self):
        self.assertEqual((parse_designation("M8x1").pitch_mm, parse_designation("M8").pitch_mm), (1, 1.25))
        self.assertEqual(parse_designation("m10 x 1,5").designation, "M10x1.5")
        odd = parse_designation("M17.3x0.73")
        self.assertEqual((odd.family, odd.major_diameter_mm, odd.pitch_mm), (METRIC, 17.3, 0.73))

    def test_a_metric_size_without_a_standard_pitch_asks_for_one(self):
        with self.assertRaisesRegex(ThreadDesignationError, "write the pitch"):
            parse_designation("M17.3")

    def test_trapezoidal_and_unified(self):
        tr = parse_designation("Tr40x7")
        self.assertEqual((tr.family, tr.major_diameter_mm, tr.pitch_mm), (TRAPEZOIDAL, 40, 7))
        for text, diameter, tpi in (("1/4-20 UNC", 6.35, 20), ("1/4 UNF", 6.35, 28), ("#10-24", 4.826, 24), ("#10", 4.826, 24),
                                    ("1 1/8-7", 28.575, 7), ("0.5-13", 12.7, 13)):
            with self.subTest(text=text):
                spec = parse_designation(text)
                self.assertEqual(spec.family, UNIFIED)
                self.assertAlmostEqual(spec.major_diameter_mm, diameter, places=3)
                self.assertAlmostEqual(spec.pitch_mm, 25.4 / tpi, places=4)

    def test_nonsense_is_refused_with_a_hint(self):
        for text in ("", "X", "M8x9", "M0", "1/4-0", "#1.5", "Tr40"):
            with self.subTest(text=text), self.assertRaises(ThreadDesignationError):
                parse_designation(text)


class ProfileTests(unittest.TestCase):
    def test_the_standard_metric_diameters(self):
        for text, minor_bolt, bore in (("M8x1.25", 6.466, 6.647), ("M8x1", 6.773, 6.917), ("M10x1.5", 8.160, 8.376), ("M20x2.5", 16.933, 17.294)):
            with self.subTest(text=text):
                spec = parse_designation(text)
                self.assertAlmostEqual(spec.values_for(True).minor_diameter_mm, minor_bolt, places=2)
                self.assertAlmostEqual(spec.values_for(False).minor_diameter_mm, bore, places=2)

    def test_outside_is_turned_to_the_major_diameter_inside_is_bored_to_the_minor(self):
        spec = parse_designation("M8x1")
        outside, inside = spec.values_for(True), spec.values_for(False)
        self.assertAlmostEqual(outside.crest_radius_mm, 4)
        self.assertAlmostEqual(outside.depth_mm, 0.6134)
        self.assertAlmostEqual(inside.crest_radius_mm, 6.9174 / 2, places=3)
        self.assertAlmostEqual(inside.depth_mm, 0.5413)
        self.assertAlmostEqual(outside.pitch_diameter_mm, 7.3505, places=3)
        self.assertEqual(outside.compound_angle_deg, 29.5)

    def test_trapezoidal_follows_the_iso_2904_rules(self):
        spec = parse_designation("Tr40x7")  # pitch 7: clearance 0.5, flank height 4
        out, inside = spec.values_for(True), spec.values_for(False)
        self.assertAlmostEqual(out.depth_mm, 4)
        self.assertAlmostEqual(out.minor_diameter_mm, 32)
        self.assertAlmostEqual(inside.minor_diameter_mm, 33)
        self.assertAlmostEqual(inside.depth_mm, 4)
        self.assertAlmostEqual(out.pitch_diameter_mm, 36.5)
        self.assertEqual(out.compound_angle_deg, 14.5)
        self.assertAlmostEqual(parse_designation("Tr20x4").values_for(True).depth_mm, 2.25)

    def test_the_fit_allowances_move_the_crest_and_keep_the_root(self):
        from unittest import mock

        import wop.core.thread_designation as module

        with mock.patch.object(module, "THREAD_EXTERNAL_CREST_ALLOWANCE_MM", 0.2):
            spec = parse_designation("M8x1")
            out = spec.values_for(True)
            self.assertAlmostEqual(out.crest_radius_mm, 3.9)
            self.assertAlmostEqual(out.crest_radius_mm - out.depth_mm, 4 - 0.6134)  # the root radius is unchanged


class BlockTests(unittest.TestCase):
    def test_a_new_designation_fills_the_numbers(self):
        edited = replace(thread_block(), designation="M8x1").with_derived_fields(thread_block())
        self.assertEqual(edited.designation, "M8x1")
        self.assertEqual((edited.pitch_mm, edited.crest_radius_mm), (1, 4))
        self.assertAlmostEqual(edited.thread_depth_mm, 0.6134)
        self.assertEqual((edited.start_z_mm, edited.end_z_mm, edited.spindle, edited.first_cut_depth_mm), (0, -15, SPINDLE, 0.3))

    def test_changing_the_side_recomputes_the_numbers_of_the_designation(self):
        outside = replace(thread_block(), designation="M8x1").with_derived_fields(thread_block())
        inside = replace(outside, side=TurningSide.INSIDE).with_derived_fields(outside)
        self.assertAlmostEqual(inside.crest_radius_mm * 2, 6.9174, places=3)
        self.assertAlmostEqual(inside.thread_depth_mm, 0.5413)

    def test_editing_a_derived_number_by_hand_clears_the_designation(self):
        outside = replace(thread_block(), designation="M8x1").with_derived_fields(thread_block())
        for change in ({"pitch_mm": 1.25}, {"crest_radius_mm": 3.9}, {"thread_depth_mm": 0.7}):
            with self.subTest(change=change):
                custom = replace(outside, **change).with_derived_fields(outside)
                self.assertEqual(custom.designation, "")
                self.assertEqual(getattr(custom, next(iter(change))), next(iter(change.values())))

    def test_other_edits_keep_the_designation_and_the_numbers(self):
        outside = replace(thread_block(), designation="M8x1").with_derived_fields(thread_block())
        for change in ({"end_z_mm": -20}, {"first_cut_depth_mm": 0.2}, {"compound_angle_deg": 28.0}, {"tool_number": 2}):
            with self.subTest(change=change):
                kept = replace(outside, **change).with_derived_fields(outside)
                self.assertEqual(kept.designation, "M8x1")
                self.assertEqual(kept.pitch_mm, 1)

    def test_a_bad_designation_is_refused_and_an_empty_one_changes_nothing(self):
        with self.assertRaises(BlockError):
            thread_block(designation="M8x9")
        block = thread_block()
        self.assertIs(block.with_derived_fields(None), block)

    def test_old_blocks_without_a_designation_are_as_before(self):
        self.assertEqual(thread_block().designation, "")


class PlanTests(unittest.TestCase):
    def _plan(self, block, tool, diameter):
        from tests.test_blocks_threading import program
        from wop.core.program_model.program import plan_program
        from wop.core.program_model.raw_part import RawPart

        return plan_program(program(block, tool, RawPart("steel", diameter, 60)))

    def test_the_messages_name_the_diameters_and_warn_about_a_wrong_tool(self):
        from wop.core.tooling.tool_presets import thread_tool

        block = replace(thread_block(), designation="M8x1").with_derived_fields(thread_block())
        plan = self._plan(replace(block, crest_radius_mm=4, end_z_mm=-8), thread_tool(1, "thread"), 8)
        text = " ".join(plan.messages)
        self.assertIn("M8x1 outside: major diameter 8.000", text)
        self.assertNotIn("flank angle of the tool", text)
        tr = replace(thread_block(), designation="Tr20x4").with_derived_fields(thread_block())
        plan = self._plan(replace(tr, end_z_mm=-8), thread_tool(1, "thread"), 20)
        self.assertIn("flank angle of the tool (60 degrees between the flanks) differs from that of Tr20x4 (30 degrees", " ".join(plan.messages))


class ModelTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel

        self.model = AppModel()
        self.model.auto_check = False
        self.index = self.model.add_block("threading")

    def test_typing_a_designation_in_the_form_fills_the_block(self):
        block = self.model.blocks[self.index]
        self.model.replace_block(self.index, replace(block, designation="M8x1"))
        done = self.model.blocks[self.index]
        self.assertEqual((done.pitch_mm, done.crest_radius_mm), (1, 4))
        self.model.replace_block(self.index, replace(done, pitch_mm=1.25))  # by hand: a custom thread
        self.assertEqual(self.model.blocks[self.index].designation, "")
        self.assertEqual(self.model.blocks[self.index].pitch_mm, 1.25)
        self.model.undo()
        self.assertEqual(self.model.blocks[self.index].designation, "M8x1")

    def test_a_bad_designation_is_refused_with_a_message(self):
        from wop.ui.app_model import ModelError

        with self.assertRaises((ModelError, BlockError)):
            self.model.replace_block(self.index, replace(self.model.blocks[self.index], designation="M8x9"))

    def test_the_form_has_the_designation_field_after_the_side(self):
        from wop.ui.block_forms import form_for

        names = [spec.path[-1] if isinstance(spec.path, tuple) else spec.path for spec in form_for(self.model.blocks[self.index])]
        self.assertEqual(names[:3], ["name", "side", "designation"])


if __name__ == "__main__":
    unittest.main()
