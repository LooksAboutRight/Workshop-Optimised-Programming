import unittest
from dataclasses import replace

from tests.post_helpers import limited_post, shipped_post
from wop.core.program_model.units import XInputMode
from wop.post.base import Feature

from tests.reference_program import REFERENCE_SETTINGS, reference_program
from wop.core.program_model.program import plan_program
from wop.post.generate import RemedyKind, find_issues, generate_gcode


def reference_plan():
    return plan_program(reference_program())


class ReferenceProgramTests(unittest.TestCase):
    def test_reference_program_is_complete_without_issues(self):
        result = generate_gcode(reference_plan(), shipped_post(), REFERENCE_SETTINGS)
        self.assertTrue(result.complete)
        self.assertEqual(result.issues, ())


class ProgramOutputTests(unittest.TestCase):
    def setUp(self):
        self.plan = reference_plan()
        self.lines = generate_gcode(self.plan, shipped_post(), REFERENCE_SETTINGS).text.splitlines()

    def test_blocks_appear_in_order(self):
        markers = [line for line in self.lines if line.startswith("(Block ")]
        self.assertEqual(len(markers), 4)
        self.assertEqual([m.split(":")[0] for m in markers], [f"(Block {n}" for n in range(1, 5)])

    def test_every_tool_change_follows_a_move_to_the_safe_position(self):
        for index, line in enumerate(self.lines):
            if line.endswith("M6"):
                before = [earlier for earlier in self.lines[:index] if not earlier.startswith("(")]  # skip the block markers
                self.assertTrue(before[-3].endswith("X60 Z10"), before[-3])  # to the safe position (G0 is not repeated) ...
                self.assertEqual(before[-2:], ["M9", "M5"])  # ... then coolant and spindle off

    def test_spindle_modes_and_coolant_codes_appear(self):
        for expected in ("G96 D3000 S150 M3", "G97 S1200 M3", "M8", "M7", "M9"):
            self.assertIn(expected, self.lines)

    def test_diameter_mode_is_stated_and_used_once_for_the_whole_program(self):
        self.assertIn("G18 G21 G90 G40 G95 G7", self.lines)
        self.assertNotIn("G8", [word for line in self.lines for word in line.split()])
        radius_lines = generate_gcode(
            self.plan, shipped_post(), replace(REFERENCE_SETTINGS, x_mode=XInputMode.RADIUS)
        ).text.splitlines()
        self.assertIn("X21 Z-0.8", radius_lines)  # the same move as "X42" in diameter mode
        self.assertIn("X42 Z-0.8", self.lines)

    def test_program_ends_with_spindle_stop_and_program_end(self):
        self.assertEqual(self.lines[-3:], ["M5", "M9", "M30"])

    def test_no_move_repeats_the_position_it_is_already_at(self):
        for first, second in zip(self.lines, self.lines[1:]):
            if first.startswith("G0 X") and " Z" in first:
                self.assertNotEqual(first, second)


class RemedyTests(unittest.TestCase):
    """Requirements O2, O4, O11."""

    def setUp(self):
        self.plan = reference_plan()

    def test_missing_constant_surface_speed_names_feature_and_block_and_proposes_fixed_rpm(self):
        post = limited_post({Feature.CONSTANT_SURFACE_SPEED})
        issues = [i for i in find_issues(self.plan, post.info, REFERENCE_SETTINGS) if i.remedy is RemedyKind.FIXED_RPM]
        self.assertEqual([i.block_index for i in issues], [0, 3])
        self.assertIn("block 1", issues[0].message)
        self.assertIn("constant surface speed", issues[0].message)
        self.assertIn("RPM", issues[0].remedy_text)

    def test_accepting_the_remedy_gives_fixed_rpm_and_lists_it_in_the_header(self):
        post = limited_post({Feature.CONSTANT_SURFACE_SPEED})
        accepted = {(0, RemedyKind.FIXED_RPM), (3, RemedyKind.FIXED_RPM)}
        result = generate_gcode(self.plan, post, REFERENCE_SETTINGS, accepted)
        self.assertTrue(result.complete)
        self.assertNotIn("G96", result.text)
        header = "\n".join(result.text.splitlines()[:8])
        self.assertIn("remedy, block 1", header)
        # 150 m/min at the 40 mm outside diameter is 1193.7 RPM
        self.assertIn("G97 S1193.7 M3", result.text)

    def test_refusing_leaves_the_block_out_and_marks_the_result_incomplete(self):
        post = limited_post({Feature.CONSTANT_SURFACE_SPEED})
        result = generate_gcode(self.plan, post, REFERENCE_SETTINGS)
        self.assertFalse(result.complete)
        self.assertEqual(result.skipped_blocks, (0, 3))
        self.assertIn("INCOMPLETE - DO NOT RUN", result.text)
        self.assertIn("(block 1 NOT OUTPUT", result.text)
        self.assertNotIn("T2 M6", result.text)  # block 4 is not there

    def test_the_program_itself_is_not_changed_by_a_remedy(self):
        post = limited_post({Feature.CONSTANT_SURFACE_SPEED})
        before = reference_program()
        generate_gcode(self.plan, post, REFERENCE_SETTINGS, {(0, RemedyKind.FIXED_RPM)})
        self.assertEqual(reference_program(), before)

    def test_missing_coolant_can_be_left_out(self):
        post = limited_post({Feature.COOLANT_MIST})
        result = generate_gcode(self.plan, post, REFERENCE_SETTINGS, {(1, RemedyKind.OMIT_COOLANT)})
        self.assertTrue(result.complete)
        self.assertNotIn("M7", result.text)
        self.assertIn("coolant mist not supported: switch by hand", result.text)

    def test_missing_arcs_become_short_lines(self):
        post = limited_post({Feature.ARCS})
        accepted = {(1, RemedyKind.ARCS_AS_LINES), (3, RemedyKind.ARCS_AS_LINES)}
        result = generate_gcode(self.plan, post, REFERENCE_SETTINGS, accepted)
        self.assertTrue(result.complete)
        self.assertNotIn("G2 ", result.text)
        self.assertNotIn("G3 ", result.text)
        self.assertGreater(len(result.text.splitlines()), len(generate_gcode(self.plan, shipped_post(), REFERENCE_SETTINGS).text.splitlines()))

    def test_missing_diameter_mode_switches_the_whole_program_to_radius_values(self):
        post = limited_post({Feature.DIAMETER_MODE})
        result = generate_gcode(self.plan, post, REFERENCE_SETTINGS, {(None, RemedyKind.RADIUS_MODE)})
        self.assertTrue(result.complete)
        self.assertIn("G8", result.text)
        self.assertIn("X21 Z-0.8" + chr(10) + "G1 X20 F0.2", result.text)  # G0 and the Z word of the second move are not repeated

    def test_missing_tool_change_has_no_remedy_and_blocks_output(self):
        post = limited_post({Feature.TOOL_CHANGE})
        issues = find_issues(self.plan, post.info, REFERENCE_SETTINGS)
        self.assertTrue(all(i.remedy is None for i in issues if "tool change" in i.message))
        self.assertFalse(generate_gcode(self.plan, post, REFERENCE_SETTINGS).complete)

    def test_the_same_block_for_linuxcnc_needs_no_question(self):
        self.assertEqual(find_issues(self.plan, shipped_post().info, REFERENCE_SETTINGS), [])

    def test_without_accepting_anything_the_text_still_comes_and_says_what_was_left_out(self):
        result = generate_gcode(self.plan, limited_post({Feature.CONSTANT_SURFACE_SPEED}), REFERENCE_SETTINGS)
        self.assertTrue(result.text.strip())
        self.assertEqual(result.complete, not result.skipped_blocks)


class PostReuseTests(unittest.TestCase):
    def test_one_postprocessor_object_gives_the_same_text_every_time(self):
        # Regression: the second run left out feed words that the first run had already written.
        post = shipped_post()
        first = generate_gcode(reference_plan(), post, REFERENCE_SETTINGS).text
        second = generate_gcode(reference_plan(), post, REFERENCE_SETTINGS).text
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
