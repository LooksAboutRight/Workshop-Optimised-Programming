import unittest

from tests.helpers import assert_chain_is_continuous
from wop.core.contour import ArcCenterStep, ArcRadiusStep, ContourError, LineStep
from wop.core.contour_solver import build_contour
from wop.core.dxf_contour import DxfArc, DxfAxes, DxfDrawing, DxfLine, contour_from_drawing
from wop.core.geometry import ArcSegment, Point


def drawing(*entities, notes=()):
    return DxfDrawing(tuple(entities), tuple(notes))


def line(a, b):
    return DxfLine(a, b)


# A stepped shaft in a drawing with the axis horizontal: drawing x = Z, drawing y = radius.
SHAFT = [line((-10, 5), (0, 5)), line((-10, 5), (-10, 8)), line((-30, 8), (-10, 8))]


class DxfContourTests(unittest.TestCase):
    def test_unordered_lines_become_one_chain_from_the_highest_z(self):
        result = contour_from_drawing(drawing(*SHAFT))
        self.assertEqual(result.definition.start, Point(5, 0))
        self.assertEqual([s.end for s in result.definition.steps], [Point(5, -10), Point(8, -10), Point(8, -30)])
        self.assertTrue(all(isinstance(s, LineStep) for s in result.definition.steps))
        self.assertEqual(result.messages, ())

    def test_a_chain_drawn_the_other_way_round_is_turned(self):
        flipped = [line(b, a) for a, b in ((l.start, l.end) for l in SHAFT)]
        result = contour_from_drawing(drawing(*reversed(flipped)))
        self.assertEqual(result.definition.start, Point(5, 0))
        self.assertTrue(any("turned round" in m for m in result.messages))

    def test_a_vertical_drawing_swaps_the_axes(self):
        vertical = [line((a[1], a[0]), (b[1], b[0])) for a, b in ((l.start, l.end) for l in SHAFT)]
        result = contour_from_drawing(drawing(*vertical), DxfAxes.VERTICAL)
        self.assertEqual(result.definition.start, Point(5, 0))
        self.assertEqual(result.definition.steps[-1].end, Point(8, -30))

    def test_a_drawing_below_the_axis_is_mirrored(self):
        below = [line((a[0], -a[1]), (b[0], -b[1])) for a, b in ((l.start, l.end) for l in SHAFT)]
        result = contour_from_drawing(drawing(*below))
        self.assertEqual(result.definition.start, Point(5, 0))
        self.assertTrue(any("mirrored" in m for m in result.messages))

    def test_a_rounded_corner_keeps_its_shape(self):
        # radius 5 arc, centre (-5, 5), from 90 to 180 degrees: the outer corner of a shoulder
        entities = [
            line((0, 10), (-5, 10)), DxfArc((-5, 5), 5, 90, 180), line((-10, 5), (-10, 0.5)),
        ]
        result = contour_from_drawing(drawing(*entities))
        self.assertIsInstance(result.definition.steps[1], ArcCenterStep)
        contour = build_contour("c", "round", result.definition)
        assert_chain_is_continuous(self, contour.segments)
        arc = contour.segments[1]
        self.assertIsInstance(arc, ArcSegment)
        middle = arc.point_at(0.5)
        self.assertAlmostEqual(middle.x, 5 + 5 * 0.70710678, places=4)
        self.assertAlmostEqual(middle.z, -5 - 5 * 0.70710678, places=4)

    def test_a_concave_arc_has_the_other_direction(self):
        # centre (-5, 10) radius 5 from 180 to 270 degrees: the inner corner of a shoulder
        entities = [line((0, 5), (-5, 5)), DxfArc((-5, 10), 5, 270, 360), line((0, 10), (0, 12))]
        # arc 270..360 starts at (-5, 5) and ends at (0, 10): drawn from z=-5 towards z=0
        result = contour_from_drawing(drawing(*entities))
        contour = build_contour("c", "hollow", result.definition)
        assert_chain_is_continuous(self, contour.segments)
        self.assertEqual(sum(isinstance(s, ArcSegment) for s in contour.segments), 1)
        middle = [s for s in contour.segments if isinstance(s, ArcSegment)][0].point_at(0.5)
        self.assertAlmostEqual(middle.x, 10 - 5 * 0.70710678, places=4)

    def test_a_closed_half_section_loses_its_axis_line(self):
        box = [
            line((0, 0), (-20, 0)), line((-20, 0), (-20, 6)), line((-20, 6), (0, 6)), line((0, 6), (0, 0)),
        ]
        result = contour_from_drawing(drawing(*box))
        self.assertTrue(any("on the spindle axis" in m for m in result.messages))
        self.assertEqual(len(result.definition.steps), 3)

    def test_a_closed_loop_without_axis_line_is_refused(self):
        loop = [line((0, 3), (-20, 3)), line((-20, 3), (-20, 6)), line((-20, 6), (0, 6)), line((0, 6), (0, 3))]
        with self.assertRaises(ContourError) as raised:
            contour_from_drawing(drawing(*loop))
        self.assertIn("closed", str(raised.exception))

    def test_a_branch_is_refused(self):
        with self.assertRaises(ContourError):
            contour_from_drawing(drawing(*SHAFT, line((-10, 5), (-10, 2))))

    def test_small_gaps_are_closed_and_reported(self):
        gap = [line((-10, 5), (0, 5)), line((-10.05, 5), (-10.05, 8))]
        result = contour_from_drawing(drawing(*gap))
        self.assertTrue(any("gap" in m for m in result.messages))
        build_contour("c", "gap", result.definition)

    def test_a_gap_between_two_arcs_still_gives_a_valid_contour(self):
        entities = [
            line((0, 10), (-5, 10)), DxfArc((-5, 5), 5, 90, 150),
            DxfArc((-5.05, 5.0), 5, 150.2, 180), line((-10.05, 5), (-10.05, 1)),
        ]
        result = contour_from_drawing(drawing(*entities))
        self.assertTrue(any(isinstance(s, ArcRadiusStep) for s in result.definition.steps))
        build_contour("c", "arcs", result.definition)

    def test_other_chains_are_reported(self):
        result = contour_from_drawing(drawing(*SHAFT, line((-50, 20), (-60, 20))))
        self.assertTrue(any("separate chains" in m for m in result.messages))

    def test_notes_of_the_reader_are_passed_on(self):
        result = contour_from_drawing(drawing(*SHAFT, notes=("ignored: 2 TEXT",)))
        self.assertEqual(result.messages[0], "ignored: 2 TEXT")

    def test_an_empty_drawing_is_refused(self):
        with self.assertRaises(ContourError):
            contour_from_drawing(drawing())


if __name__ == "__main__":
    unittest.main()
