"""The post engine with invented posts (`tests/data/posts/fake_*.post.ini`, codes like Q7 and ZZ that no controller has).

The expected text is written by hand. A failure means the engine changed, not that a real controller is wrong.
"""

import unittest
from datetime import datetime
from pathlib import Path

from wop.core.geometry import ArcDirection, Point
from wop.core.program_model.operations import (
    ArcMove,
    BlockBegin,
    CoolantMode,
    DrillMode,
    DrillOperation,
    LinearMove,
    MachineFunction,
    MachineFunctionKind,
    Rapid,
    RapidAxes,
    SpindleMode,
    SpindleSetting,
    ThreadOperation,
    ThreadTaper,
)
from wop.core.program_model.units import XInputMode
from tests.post_helpers import ALL_FEATURES
from wop.post.base import Feature, PostError, PostSettings
from wop.post.context import BlockInfo, PostContext, ToolInfo
from wop.post.engine import TemplatePost
from wop.post.post_definition import PostFileError, parse_post

FOLDER = Path(__file__).resolve().parent / "data" / "posts"
RADIUS = PostSettings(XInputMode.RADIUS)
DIAMETER = PostSettings(XInputMode.DIAMETER)


def definition(name, fallback=None, **replace):
    text = (FOLDER / f"{name}.post.ini").read_text(encoding="utf-8")
    for old, new in replace.items():
        assert old.replace("__", " ") in text, old
        text = text.replace(old.replace("__", " "), new)
    return parse_post(text, name, fallback)


def post(name, settings=RADIUS, context=None, **replace):
    instance = TemplatePost(definition(name, **replace), context)
    instance.header(settings, [])
    return instance


def inline(*sections, fallback=None):
    """A post from the text of some sections, for one small test."""
    head = "[post]\nname = Inline\nformat_version = 1\n\n"
    return parse_post(head + "\n\n".join(sections) + "\n", "inline", fallback)


class MotionTests(unittest.TestCase):
    def test_header_setup_and_the_explicit_blank_line(self):
        instance = TemplatePost(definition("fake_motion"), PostContext(project_title="Part A"))
        self.assertEqual(instance.header(RADIUS, []), ["%", "", "PROGRAM Part A", "Q8 ZZ"])
        self.assertEqual(TemplatePost(definition("fake_motion")).header(DIAMETER, []), ["%", "", "PROGRAM", "Q7 ZZ"])

    def test_a_rapid_writes_only_what_changed(self):
        instance = post("fake_motion")
        self.assertEqual(instance.rapid(Rapid(Point(10, -5))), ["Q0 X10 Z-5"])
        self.assertEqual(instance.rapid(Rapid(Point(10, -8))), ["Z-8"])  # the code is modal, X did not change
        self.assertEqual(instance.rapid(Rapid(Point(10, -8))), [])  # nothing changed: no line at all, no blank line
        self.assertEqual(instance.rapid(Rapid(Point(12, -8))), ["X12"])

    def test_a_rapid_of_one_axis_leaves_the_other_out(self):
        instance = post("fake_motion")
        self.assertEqual(instance.rapid_axes(RapidAxes(x=10)), ["Q0 X10"])
        self.assertEqual(instance.rapid_axes(RapidAxes(z=-3)), ["Z-3"])
        self.assertEqual(instance.rapid(Rapid(Point(10, -3))), [])  # the position is known from the moves of one axis

    def test_the_modal_group_is_shared_by_rapid_and_feed(self):
        instance = post("fake_motion")
        instance.rapid(Rapid(Point(10, 0)))
        self.assertEqual(instance.linear(LinearMove(Point(10, -4), 0.2)), ["L100 Q1 X10 Z-4 F0.2"])
        self.assertEqual(instance.linear(LinearMove(Point(12, -4), 0.2)), ["L105 X12 Z-4"])  # same code, same feed
        self.assertEqual(instance.linear(LinearMove(Point(12, -6), 0.1)), ["L110 X12 Z-6 F0.1"])
        self.assertEqual(instance.rapid(Rapid(Point(12, -8))), ["Q0 Z-8"])  # back to the group of the rapid

    def test_x_is_written_as_a_diameter_in_diameter_mode(self):
        instance = post("fake_motion", DIAMETER)
        self.assertEqual(instance.rapid(Rapid(Point(10, -5))), ["Q0 X20 Z-5"])

    def test_decimals_come_from_the_post(self):
        instance = post("fake_motion")
        self.assertEqual(instance.rapid(Rapid(Point(10.12345, -5.006))), ["Q0 X10.12 Z-5.01"])

    def test_a_new_run_has_no_memory(self):
        first = post("fake_motion")
        first.rapid(Rapid(Point(10, -5)))
        second = first.fresh()
        second.header(RADIUS, [])
        self.assertEqual(second.rapid(Rapid(Point(10, -5))), ["Q0 X10 Z-5"])

    def test_arcs(self):
        instance = post("fake_motion")
        quarter = ArcMove(Point(12, -2), Point(10, -2), ArcDirection.CCW, 0.2)
        self.assertEqual(instance.arc(quarter, 10, 0), ["Q2 X12 Z-2 I0 K-2 F0.2"])
        # more than half a circle: R is negative; the same arc the other way round is a quarter circle
        instance = post("fake_motion")
        self.assertEqual(instance.arc(ArcMove(Point(10, -1), Point(10, 0), ArcDirection.CCW, 0.2), 11, 0)[0], "Q2 X10 Z-1 I-1 K0 F0.2")
        self.assertEqual(instance.arc(ArcMove(Point(10, -1), Point(10, 0), ArcDirection.CW, 0.2), 11, 0), ["Q3 X10 Z-1 R1"])

    def test_the_radius_of_a_big_arc_is_negative(self):
        instance = post("fake_motion")
        # a full 270 degrees; the direction that is the long way round writes a negative radius
        lines = [
            instance.arc(ArcMove(Point(10, -1), Point(10, 0), direction, 0.2), 11, 0) for direction in (ArcDirection.CCW, ArcDirection.CW)
        ]
        self.assertEqual(lines[1], ["Q3 X10 Z-1 R1"])
        radius_template = definition("fake_motion", **{"I<I> K<K>": "R<R>"})
        long_way = TemplatePost(radius_template)
        long_way.header(RADIUS, [])
        self.assertEqual(long_way.arc(ArcMove(Point(10, -1), Point(10, 0), ArcDirection.CCW, 0.2), 11, 0), ["Q2 X10 Z-1 R-1 F0.2"])

    def test_a_comment_keeps_to_the_characters_of_the_post(self):
        instance = post("fake_motion")
        self.assertEqual(instance.comment("note (a) (b)"), [";note <a> <b>"])


class OptionsOfTokensTests(unittest.TestCase):
    def test_incremental_and_absolute(self):
        instance = TemplatePost(inline(
            "[rapid]\nX<X incremental> Z<Z incremental> / <X absolute> <Z>",
        ))
        instance.header(RADIUS, [])
        with self.assertRaises(PostError):  # no position yet
            instance.rapid(Rapid(Point(10, -5)))
        instance.state.x, instance.state.z = 4.0, 1.0
        self.assertEqual(instance.rapid(Rapid(Point(10, -5))), ["X6 Z-6 / 10 -5"])

    def test_diameter_and_radius_can_be_chosen_per_token(self):
        instance = TemplatePost(inline("[rapid]\n<X diameter> <X radius> <X>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid(Rapid(Point(10, 0))), ["20 10 10"])
        instance.header(DIAMETER, [])
        self.assertEqual(instance.rapid(Rapid(Point(10, 0))), ["20 10 20"])

    def test_prefix_and_suffix_are_left_out_with_an_empty_value(self):
        instance = TemplatePost(inline('[rapid]\n<X prefix=X> <Z prefix="Z=" suffix=mm>'))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(z=-2)), ["Z=-2mm"])

    def test_i_and_k_can_be_absolute_and_a_diameter(self):
        arc = ArcMove(Point(12, -2), Point(10, -2), ArcDirection.CCW, 0.2)
        instance = TemplatePost(inline("[arc_ccw]\n<I> <K> <I absolute> <K absolute> <I diameter>"))
        instance.header(DIAMETER, [])
        self.assertEqual(instance.arc(arc, 10, 0), ["0 -2 10 -2 0"])

    def test_zeros_and_point_options(self):
        instance = TemplatePost(inline("[rapid]\n<X zeros> <X point> <Z decimals=1 zeros>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid(Rapid(Point(10, -5))), ["10.000 10. -5.0"])

    def test_the_numbers_of_the_post_settings(self):
        text = "[settings]\npoint = yes\ndecimals = 4"
        instance = TemplatePost(inline(text, "[rapid]\n<X> <Z>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid(Rapid(Point(10, -5.25))), ["10. -5.25"])

    def test_upper_case(self):
        instance = TemplatePost(inline("[comment]\n<comment text upper>"))
        self.assertEqual(instance.comment("abc"), ["ABC"])

    def test_empty_tokens_and_optional_parts(self):
        instance = TemplatePost(inline(
            "[rapid]\nA [B<X>] C[ D<Z>]\n[ E<X> ] [ F<Z> ]\n<X> <Z>\n<text></text>\nstay [text]",
        ))
        instance.header(RADIUS, [])
        self.assertEqual(
            instance.rapid_axes(RapidAxes(x=1)),
            ["A B1 C", "E1", "1", "", "stay text"],
        )  # the line with only the empty <Z> in [ F<Z> ] part: " E1 " keeps only E1; the explicit blank stays
        self.assertEqual(instance.rapid_axes(RapidAxes()), ["A C", "", "stay text"])  # empty values: the lines made of them go

    def test_spaces_are_tidied_but_text_tags_keep_theirs(self):
        instance = TemplatePost(inline("[rapid]\n  a    b  [<X>]   c  \n<text>  x  y  </text>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes()), ["a b c", "  x  y  "])


class NumbersAndMemoryTests(unittest.TestCase):
    def test_line_numbers(self):
        instance = TemplatePost(inline(
            "[settings]\nline_number_prefix = N\nline_number_start = 10\nline_number_step = 10",
            "[rapid]\n<N next> A <N>\n<N next> B",
        ))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["N10 A N10", "N20 B"])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["N30 A N30", "N40 B"])

    def test_the_last_line_number_is_empty_before_the_first(self):
        instance = TemplatePost(inline("[rapid]\nA[ <N>]"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["A"])

    def test_a_token_with_memory_leaves_out_what_was_written(self):
        instance = TemplatePost(inline("[spindle_rpm]\n[S<S changed>]\nalways"))
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)), ["S1000", "always"])
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)), ["always"])
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1500)), ["S1500", "always"])

    def test_modal_groups_of_codes(self):
        instance = TemplatePost(inline(
            "[codes]\na = G1\nb = G2\nc = M3\nd = M4\n[modal_groups]\nmotion = G1 G2\nspindle = M3 M4",
            "[rapid]\n<code a changed>\n<code b changed>\n<code c changed>\n<code d>",
        ))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["G1", "G2", "M3", "M4"])  # a, then b replaces it in the group
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["G1", "G2", "M3", "M4"])  # d replaced c in its group, so c is news again
        # the last codes written were b and d: asking for them again is empty
        again = TemplatePost(inline("[codes]\nb = G2\n[modal_groups]\nmotion = G2", "[rapid]\n<code b changed>|<code b changed>"))
        again.header(RADIUS, [])
        self.assertEqual(again.rapid_axes(RapidAxes(x=1)), ["G2|"])

    def test_a_code_of_a_group_that_is_not_modal_is_always_written(self):
        instance = TemplatePost(inline("[codes]\ndwell = G4\n[modal_groups]\nnon_modal = G4", "[rapid]\n<code dwell changed>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["G4"])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["G4"])

    def test_two_codes_of_one_group_in_one_line_are_refused(self):
        with self.assertRaises(PostFileError) as caught:
            TemplatePost(inline("[codes]\na = G1\nb = G2\n[modal_groups]\nmotion = G1 G2", "[rapid]\n<code a> <code b>"))
        self.assertIn("same modal group (motion)", str(caught.exception))
        TemplatePost(inline("[codes]\na = G1\nb = G2\n[modal_groups]\nmotion = G1 G2", "[rapid]\n<code a>\n<code b>"))  # two lines are fine
        TemplatePost(inline("[codes]\na = G1\n[modal_groups]\nmotion = G1", "[rapid]\n<code a> <code a changed>"))  # the same code twice is fine
        TemplatePost(inline("[codes]\na = G1\nb = G2", "[rapid]\n<code a> <code b>"))  # no groups: each code is its own group

    def test_changed_does_not_care_how_a_code_is_spelled(self):
        instance = TemplatePost(inline("[codes]\nfeed = G01\n[modal_groups]\nmotion = G0 G1", "[feed]\n<code feed changed> X<X>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.linear(LinearMove(Point(10, -5), 0.2)), ["G01 X10"])  # written the way the table has it
        self.assertEqual(instance.linear(LinearMove(Point(10, -6), 0.2)), ["X10"])

    def test_the_code_table_takes_the_group_from_the_modal_groups_and_not_from_the_line(self):
        instance = TemplatePost(inline("[codes]\na = G10 L2\nb = G99\n[modal_groups]\nnon_modal = G10\nmine = G98 G99", "[rapid]\n<code a>"))
        codes = instance.definition.codes
        self.assertEqual((codes["a"].group, codes["a"].modal), ("non_modal", False))  # compared by the first word
        self.assertEqual((codes["b"].group, codes["b"].modal), ("mine", True))
        with self.assertRaises(PostFileError) as caught:
            TemplatePost(inline("[codes]\na = G1 | motion", "[rapid]\n<code a>"))
        self.assertIn("[modal_groups]", str(caught.exception))

    def test_a_code_without_a_group_is_its_own_group(self):
        instance = TemplatePost(inline("[codes]\nstop = M0", "[rapid]\n<code stop changed>"))
        instance.header(RADIUS, [])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), ["M0"])
        self.assertEqual(instance.rapid_axes(RapidAxes(x=1)), [])

    def test_feed_per_minute_needs_the_spindle_speed(self):
        instance = post("fake_machine")
        with self.assertRaises(PostError) as caught:
            instance.linear(LinearMove(Point(10, -5), 0.2))
        self.assertIn("spindle", str(caught.exception))
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1200))
        self.assertEqual(instance.linear(LinearMove(Point(10, -5), 0.2)), ["G1 X10 Z-5 F240"])
        instance.stop_spindle()
        with self.assertRaises(PostError):
            instance.linear(LinearMove(Point(10, -5), 0.2))


CONTEXT = PostContext(
    project_title="Shaft", machine_name="Lathe", now=datetime(2026, 10, 17, 14, 30),
    tools={1: ToolInfo(1, "Rough", offset_number=1, nose_radius_mm=0.8), 2: ToolInfo(2, "Finish", offset_number=2)},
    blocks=(BlockInfo(1, "Face", "facing", 1), BlockInfo(2, "Turn", "turning", 2), BlockInfo(3, "Cut", "grooving", 1)),
    tool_sequence=(1, 2, 1), path_length_mm=1234.56, estimated_time_min=7.5,
)


class ProgramKnowledgeTests(unittest.TestCase):
    def test_header_with_the_run_summary_the_tool_list_and_the_notes(self):
        instance = TemplatePost(definition("fake_program"), CONTEXT)
        self.assertEqual(instance.header(RADIUS, ["check it", "second"]), [
            "FILE Shaft on Lathe by Fake program",
            "2026/10/17 14-30 2026-10-17",
            "2 tools, 3 blocks, 1234.6 mm, 7.5 min",
            "TOOL 1 Rough R0.8",
            "TOOL 2 Finish",
            "NOTE check it",
            "NOTE second",
        ])

    def test_blocks_know_their_neighbours(self):
        instance = TemplatePost(definition("fake_program"), CONTEXT)
        self.assertEqual(instance.block_begin(BlockBegin(0, "b1", "facing", "Face")), ["BLOCK 1/3 Face next Turn"])
        self.assertEqual(instance.block_begin(BlockBegin(1, "b2", "turning", "Turn")), ["BLOCK 2/3 Turn next Cut was Face"])
        self.assertEqual(instance.block_begin(BlockBegin(2, "b3", "grooving", "Cut")), ["BLOCK 3/3 Cut was Turn"])

    def test_tool_changes_look_back_and_ahead(self):
        instance = TemplatePost(definition("fake_program"), CONTEXT)
        self.assertEqual(instance.tool_change(1), ["T2 preload", "Q6 T1 O1 from first 1 last 1"])
        self.assertEqual(instance.tool_change(2), ["T1 preload", "Q6 T2 O2 from 1 first 1 last 1"])
        self.assertEqual(instance.tool_change(1), ["Q6 T1 O1 from 2 first 1 last 1"])  # no next tool: the preload line is gone

    def test_without_a_context_the_tokens_are_empty_and_nothing_breaks(self):
        instance = TemplatePost(definition("fake_program"))
        self.assertEqual(instance.tool_change(3), ["Q6 T3 O3 from first last"])
        self.assertEqual(instance.block_begin(BlockBegin(0, "b", "facing", "Face")), ["BLOCK 1/0 Face"])

    def test_a_tool_that_does_not_fit_the_sequence_has_no_neighbours(self):
        instance = TemplatePost(definition("fake_program"), CONTEXT)
        self.assertEqual(instance.tool_change(2), ["Q6 T2 O2 from first 1 last 1"])  # the program starts with tool 1

    def test_the_clock_is_an_input(self):
        later = PostContext(now=datetime(2030, 1, 2, 3, 4))
        instance = TemplatePost(definition("fake_program"), later)
        self.assertEqual(instance.header(RADIUS, [])[1], "2030/01/02 03-04 2030-01-02")


class MachineTests(unittest.TestCase):
    def test_spindle_coolant_and_stops(self):
        instance = post("fake_machine")
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120, 3000)), ["Q96 LIM3000 SPEED120"])
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120)), ["Q96 SPEED120"])
        self.assertEqual(instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1200)), ["Q97 SPEED1200"])
        self.assertEqual(instance.stop_spindle(), ["Q5"])
        self.assertEqual([instance.set_coolant(mode) for mode in CoolantMode], [["Q9"], ["Q8"], ["Q8 MIST"]])

    def test_machine_functions(self):
        instance = post("fake_machine")
        self.assertEqual(instance.machine_function(MachineFunction(MachineFunctionKind.PROGRAM_STOP), RADIUS), ["PSTOP"])
        self.assertEqual(instance.machine_function(MachineFunction(MachineFunctionKind.OPTIONAL_STOP), RADIUS), ["OSTOP"])
        self.assertEqual(instance.machine_function(MachineFunction(MachineFunctionKind.DWELL, 1.5), RADIUS), ["WAIT 1.5"])

    def thread(self, **changes):
        values = dict(
            start_x=11, start_z=2, end_z=-20, pitch_mm=1.5, peak_offset_mm=-1, first_cut_mm=0.2, depth_mm=0.92, degression=1,
            compound_angle_deg=29.5, spring_passes=2,
        )
        return ThreadOperation(**{**values, **changes})

    def test_a_thread_in_two_blocks(self):
        instance = post("fake_machine")
        self.assertEqual(instance.thread(self.thread()), ["T1 P020030", "T2 X9.08 Z-20 P920 Q200"])

    def test_a_thread_root_is_a_diameter_in_diameter_mode(self):
        instance = post("fake_machine", DIAMETER)
        self.assertEqual(instance.thread(self.thread())[1], "T2 X18.16 Z-20 P920 Q200")

    def test_a_taper_adds_its_words_and_without_one_they_are_gone(self):
        instance = post("fake_machine")
        tapered = self.thread(taper=ThreadTaper.BOTH, taper_distance_mm=3)
        self.assertEqual(instance.thread(tapered)[1], "T2 X9.08 Z-20 P920 Q200 E3 L3")
        self.assertEqual(instance.thread(self.thread(taper=ThreadTaper.EXIT))[1], "T2 X9.08 Z-20 P920 Q200")  # no distance

    def test_an_inside_thread_root_lies_outside_the_crest(self):
        instance = post("fake_machine")
        inside = self.thread(start_x=9, peak_offset_mm=1)  # crest at 10, root deeper into the material: larger radius
        self.assertIn("X10.92", instance.thread(inside)[1])

    def test_a_thread_in_a_single_block_and_as_plain_passes(self):
        cycle = post("fake_machine", **{"threading_style__=__two_block": "threading_style = cycle"})
        self.assertEqual(cycle.thread(self.thread()), ["CYCLE P1.5 Z-20"])
        passes = post("fake_machine", **{"threading_style__=__two_block": "threading_style = passes"})
        with self.assertRaises(PostError):  # the passes are feed moves per minute: the spindle speed must be known
            passes.thread(self.thread())
        passes.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 100))
        lines = passes.thread(self.thread())
        self.assertEqual(lines[0], "PASSES")
        self.assertTrue(lines[1].startswith("G0 X"))
        self.assertIn("G1 X", lines[2])
        self.assertTrue(lines[2].endswith("F150"))

    def test_a_drill_cycle_and_its_optional_words(self):
        instance = post("fake_machine")
        pecking = DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1, peck_depth_mm=3, mode=DrillMode.PECK, dwell_s=0.5)
        self.assertEqual(instance.drill(pecking, RADIUS), ["DRILL Z-10 R2 Q3 P0.5 F0.1 peck drilling"])
        plain = DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1)
        self.assertEqual(instance.drill(plain, RADIUS), ["DRILL Z-10 R2 F0.1 drilling"])

    def test_a_drill_written_as_plain_moves_when_the_post_has_no_cycle(self):
        instance = post("fake_machine", **{"drilling_style__=__cycle": "drilling_style = expanded"})
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1000))
        lines = instance.drill(DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1), RADIUS)
        self.assertEqual(lines, ["G1 X0 Z-10 F100", "G0 X0 Z2"])  # in at the feed per minute, out at rapid


class FilesTests(unittest.TestCase):
    def error(self, text, **kwargs):
        with self.assertRaises(PostFileError) as caught:
            parse_post("[post]\nname = x\nformat_version = 1\n" + text, "x", **kwargs)
        return caught.exception

    def test_an_unknown_token_is_reported_with_the_place(self):
        error = self.error("\n[rapid]\nG0\nX<Y>\n")
        self.assertEqual((error.section, error.line, error.position), ("rapid", 7, 1))
        self.assertIn("unknown token <Y>", str(error))
        self.assertIn("[rapid] line 7, column 2", str(error))

    def test_a_token_in_the_wrong_concept(self):
        error = self.error("\n[rapid]\n<S>\n")
        self.assertIn("not allowed in [rapid]", error.message)
        self.assertIn("spindle_css", error.message)

    def test_an_unknown_option_lists_the_known_ones(self):
        error = self.error("\n[rapid]\n<X zeroes>\n")
        self.assertIn("zeroes", error.message)
        self.assertIn("zeros", error.message)

    def test_a_code_must_be_in_the_table(self):
        error = self.error("\n[rapid]\n<code g0>\n")
        self.assertIn("'g0'", error.message)

    def test_a_token_of_several_lines_stands_alone(self):
        error = self.error("\n[header]\nA <list tools>\n")
        self.assertIn("must stand alone", error.message)

    def test_a_template_that_cannot_be_read(self):
        self.assertIn("not closed", self.error("\n[rapid]\nG0 [X<X>\n").message)

    def test_sections_settings_and_the_version(self):
        self.assertIn("unknown section", self.error("\n[ragid]\nG0\n").message)
        self.assertIn("twice", self.error("\n[rapid]\nG0\n[rapid]\nG1\n").message)
        self.assertIn("unknown setting", self.error("\n[settings]\nflavour = nice\n").message)
        self.assertIn("whole number", self.error("\n[settings]\ndecimals = x\n").message)
        self.assertIn("yes or no", self.error("\n[settings]\nzeros = maybe\n").message)
        self.assertIn("threading_style", self.error("\n[settings]\nthreading_style = loop\n").message)
        self.assertIn("[supports] is gone", self.error("\n[supports]\nall\n").message)
        with self.assertRaises(PostFileError):
            parse_post("[post]\nname = x\n", "x")
        with self.assertRaises(PostFileError):
            parse_post("[post]\nname = x\nformat_version = 2\n", "x")

    def test_what_a_post_supports_follows_from_its_codes_templates_and_settings(self):
        base = "[post]\nname = x\nformat_version = 1\n"
        self.assertEqual(parse_post(base, "x").features, frozenset({Feature.THREAD_CYCLE}))  # a thread can always be written
        text = base + "[codes]\narc_ccw = G2\narc_cw = G3\ndwell = G4\ncoolant_flood = M8\n[settings]\nx_diameters = yes\n[tool_change]\nT<tool number>\n"
        expected = {Feature.THREAD_CYCLE, Feature.ARCS, Feature.DWELL, Feature.COOLANT_FLOOD, Feature.DIAMETER_MODE, Feature.TOOL_CHANGE}
        self.assertEqual(parse_post(text, "x").features, frozenset(expected))
        self.assertEqual(parse_post(text, "x").info.supported, frozenset(expected))
        self.assertNotIn(Feature.ARCS, parse_post(text.replace("arc_cw = G3\n", ""), "x").features)  # both directions are needed
        default = parse_post(base + "[tool_change]\nM0\n", "default")
        mine = parse_post(base, "mine", default)
        self.assertEqual(mine.features, frozenset({Feature.THREAD_CYCLE, Feature.TOOL_CHANGE}))  # the default post has it
        every = base + ALL_FEATURES + "[tool_change]\nT\n"
        self.assertEqual(parse_post(every, "x").features, frozenset(Feature))

    def test_a_concept_the_post_does_not_have_comes_from_the_default_post(self):
        default = inline("[coolant_off]\ndefault off")
        mine = inline("[coolant_flood]\nmy flood", fallback=default)
        instance = TemplatePost(mine)
        self.assertEqual(instance.set_coolant(CoolantMode.FLOOD), ["my flood"])
        self.assertEqual(instance.set_coolant(CoolantMode.NONE), ["default off"])

    def test_a_missing_concept_is_an_error_that_names_it(self):
        instance = TemplatePost(inline("[coolant_flood]\nx"))
        with self.assertRaises(PostError) as caught:
            instance.set_coolant(CoolantMode.MIST)
        self.assertIn("[coolant_mist]", str(caught.exception))

    def test_a_missing_value_names_the_block_and_the_concept(self):
        instance = TemplatePost(inline("[rapid]\n<X incremental>"))
        instance.block_begin(BlockBegin(2, "b", "turning", "Turn"))
        with self.assertRaises(PostError) as caught:
            instance.rapid(Rapid(Point(1, 1)))
        self.assertIn("block 3 (turning) [rapid]", str(caught.exception))

    def test_comment_replace_is_read_as_old_arrow_new_pairs(self):
        from wop.post.post_definition import replace_pairs

        self.assertEqual(replace_pairs("( -> [, ) -> ]"), (("(", "["), (")", "]")))
        self.assertEqual(replace_pairs(""), ())
        for bad in ("(", "-> x", "( [ ) ]"):
            with self.assertRaises(ValueError):
                replace_pairs(bad)
        self.assertIn("written like", self.error("\n[settings]\ncomment_replace = ([)]\n").message)

    def test_the_line_ending_is_a_setting(self):
        self.assertEqual(inline("[settings]\nline_ending = crlf").settings.newline, "\r\n")
        self.assertEqual(inline().settings.newline, "\n")

    def test_the_text_of_every_section_is_kept_for_the_editor(self):
        self.assertEqual(definition("fake_motion").sources["rapid"], ("<code rapid changed> [X<X changed>] [Z<Z changed>]",))


if __name__ == "__main__":
    unittest.main()
