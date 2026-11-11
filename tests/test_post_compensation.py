"""Cutter compensation in the engine: the moves of a compensated finishing pass carry the nominal contour, and a post with
cutter_compensation = yes writes it with G41 / G42 / G40 (invented codes Q41, Q42, Q40 in the test post)."""

import unittest
from pathlib import Path

from wop.core.geometry import ArcDirection, Point
from wop.core.program_model.operation_text import describe_operation
from wop.core.program_model.operations import ArcMove, CompensationSide, LinearMove, MoveRole, Rapid
from wop.core.program_model.units import XInputMode
from wop.post.base import PostError, PostSettings
from wop.post.engine import TemplatePost
from wop.post.post_definition import PostFileError, parse_post

FOLDER = Path(__file__).resolve().parent / "data" / "posts"
TEXT = (FOLDER / "fake_comp.post.ini").read_text(encoding="utf-8")
RADIUS = PostSettings(XInputMode.RADIUS)

# Outside turning towards the chuck: the tool path is the contour moved 0.4 up, the lead-in comes from the front.
LEAD_IN = LinearMove(Point(10.4, 0), 0.2, Point(10, 0), MoveRole.LEAD_IN, CompensationSide.RIGHT)
CYLINDER = LinearMove(Point(10.4, -20), 0.2, Point(10, -20))
JOIN = ArcMove(Point(10, -20.4), Point(10, -20), ArcDirection.CW, 0.2, role=MoveRole.JOIN)  # round the corner at (10, -20)
FACE = LinearMove(Point(5, -20.4), 0.2, Point(5, -20))
LEAD_OUT = LinearMove(Point(3, -20.4), 0.2, role=MoveRole.LEAD_OUT)


def post(compensation=True, text=TEXT):
    text = text.replace("cutter_compensation = yes", f"cutter_compensation = {'yes' if compensation else 'no'}")
    instance = TemplatePost(parse_post(text, "comp"))
    instance.header(RADIUS, [])
    return instance


def write(instance, *moves):
    lines = []
    position = Point(12, 3)
    for move in moves:
        if isinstance(move, ArcMove):
            lines += instance.arc(move, position.x, position.z)
        elif isinstance(move, Rapid):
            lines += instance.rapid(move)
        else:
            lines += instance.linear(move)
        position = move.end
    return lines


class WritingTests(unittest.TestCase):
    def test_with_compensation_the_contour_is_written_and_the_codes_stand_on_lead_in_and_lead_out(self):
        lines = write(post(True), Rapid(Point(12, 3)), LEAD_IN, CYLINDER, FACE, LEAD_OUT)
        self.assertEqual(lines, ["Q0 X12 Z3", "Q42 Q1 X10 Z0", "Q1 X10 Z-20", "Q1 X5 Z-20", "Q40 Q1 X3 Z-20.4"])

    def test_the_other_side_is_the_other_code(self):
        left = LinearMove(Point(10.4, 0), 0.2, Point(10, 0), MoveRole.LEAD_IN, CompensationSide.LEFT)
        self.assertEqual(write(post(True), left), ["Q41 Q1 X10 Z0"])

    def test_without_compensation_the_tool_path_is_written_and_there_are_no_codes(self):
        lines = write(post(False), Rapid(Point(12, 3)), LEAD_IN, CYLINDER, FACE, LEAD_OUT)
        self.assertEqual(lines, ["Q0 X12 Z3", "Q1 X10.4 Z0", "Q1 X10.4 Z-20", "Q1 X5 Z-20.4", "Q1 X3 Z-20.4"])

    def test_a_join_arc_is_left_out_with_compensation_and_written_without(self):
        with_comp = write(post(True), CYLINDER, JOIN, FACE)
        without = write(post(False), CYLINDER, JOIN, FACE)
        self.assertEqual(len(with_comp), 2)
        self.assertEqual(len(without), 3)
        self.assertEqual(without[1], "Q3 X10 Z-20.4 I-0.4 K0 R0.4")

    def test_a_move_without_a_contour_point_is_written_as_it_is_with_compensation(self):
        plain = LinearMove(Point(5, 5), 0.2)
        self.assertEqual(write(post(True), plain), ["Q1 X5 Z5"])

    def test_the_options_choose_the_point_whatever_the_post_does(self):
        text = TEXT.replace("[feed]\n[<comp code> ]<code feed> X<X> Z<Z>", "[feed]\nC<X contour> <Z contour> P<X path> <Z path>")
        for compensation in (True, False):
            with self.subTest(compensation=compensation):
                self.assertEqual(write(post(compensation, text), CYLINDER), ["C10 -20 P10.4 -20"])
        self.assertEqual(write(post(False, text), LEAD_OUT), ["C3 -20.4 P3 -20.4"])  # no contour point: the tool path point

    def test_contour_and_path_together_are_refused(self):
        with self.assertRaises(PostFileError):
            post(True, TEXT.replace("X<X> Z<Z>\n\n[arc", "X<X contour path> Z<Z>\n\n[arc"))

    def test_changed_compares_with_the_last_point_of_the_same_kind(self):
        text = TEXT.replace("[feed]\n[<comp code> ]<code feed> X<X> Z<Z>", "[feed]\n[X<X changed>] [Z<Z changed>]")
        instance = post(True, text)
        first = LinearMove(Point(10.4, -5), 0.2, Point(10, -5))
        second = LinearMove(Point(10.4, -20), 0.2, Point(10, -20))
        self.assertEqual(write(instance, first, second), ["X10 Z-5", "Z-20"])

    def test_a_post_that_writes_the_contour_but_has_no_codes_is_an_error_not_a_wrong_path(self):
        text = TEXT.replace("comp_left = Q41\ncomp_right = Q42\ncomp_off = Q40\n", "")
        with self.assertRaises(PostError) as caught:
            write(post(True, text), LEAD_IN)
        self.assertIn("no comp_right", str(caught.exception))
        with self.assertRaises(PostError) as caught:
            write(post(True, text), LEAD_OUT)
        self.assertIn("no comp_off", str(caught.exception))
        self.assertEqual(write(post(False, text), LEAD_IN), ["Q1 X10.4 Z0"])  # a post without compensation does not need them

    def test_a_post_whose_feed_template_does_not_write_the_code_is_an_error_too(self):
        text = TEXT.replace("[<comp code> ]<code feed>", "<code feed>")
        with self.assertRaises(PostError) as caught:
            write(post(True, text), LEAD_IN)
        self.assertIn("put <comp code> into the template", str(caught.exception))
        write(post(True, text), CYLINDER)  # a plain contour move needs no code

    def test_the_arc_of_the_contour_has_its_own_centre_start_and_radius(self):
        # tool path arc: centre (12, -20), radius 2.4 round a convex arc of radius 2; the contour arc is concentric
        tool_arc = ArcMove(Point(12, -22.4), Point(12, -20), ArcDirection.CW, 0.2,
                           contour_end=Point(12, -22), contour_center=Point(12, -20))
        instance = post(True)
        write(instance, LinearMove(Point(14.4, -20), 0.2, Point(14, -20)))
        lines = instance.arc(tool_arc, 14.4, -20)
        self.assertEqual(lines, ["Q3 X12 Z-22 I-2 K0 R2"])  # from the contour start (14, -20): the centre is 2 away, not 2.4
        plain = post(False)
        write(plain, LinearMove(Point(14.4, -20), 0.2, Point(14, -20)))
        self.assertEqual(plain.arc(tool_arc, 14.4, -20), ["Q3 X12 Z-22.4 I-2.4 K0 R2.4"])

    def test_the_text_of_the_operation_list_shows_the_role_and_the_contour(self):
        self.assertEqual(describe_operation(LEAD_IN), "FEED     X10.4 Z0  feed 0.2  [lead in, tool right, contour X10 Z0]")
        self.assertEqual(describe_operation(CYLINDER), "FEED     X10.4 Z-20  feed 0.2  [contour X10 Z-20]")
        self.assertEqual(describe_operation(LinearMove(Point(1, 2), 0.2)), "FEED     X1 Z2  feed 0.2")


class RemedyTests(unittest.TestCase):
    def test_arcs_as_lines_keep_the_contour_point_of_every_chord(self):
        from wop.post.generate import RemedyKind, _rewrite

        arc = ArcMove(Point(12, -22.4), Point(12, -20), ArcDirection.CW, 0.2, Point(12, -22), Point(12, -20), MoveRole.JOIN)
        before = LinearMove(Point(14.4, -20), 0.2, Point(14, -20))
        result = _rewrite(None, 0, (before, arc), {(0, RemedyKind.ARCS_AS_LINES)})
        chords = result[1:]
        self.assertTrue(len(chords) > 1)
        self.assertTrue(all(isinstance(c, LinearMove) and c.role is MoveRole.JOIN and c.contour_end is not None for c in chords))
        self.assertTrue(chords[-1].end.is_close(Point(12, -22.4)) and chords[-1].contour_end.is_close(Point(12, -22)))
        for chord in chords:  # the contour chord stays 0.4 closer to the centre of the arc
            self.assertAlmostEqual(chord.end.distance_to(Point(12, -20)) - chord.contour_end.distance_to(Point(12, -20)), 0.4, delta=0.01)


if __name__ == "__main__":
    unittest.main()
