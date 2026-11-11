import math
import unittest

from tests import reference_data
from tests.helpers import assert_chain_is_continuous, assert_segments_close, distance_to_line
from wop.core.contour import (
    ArcCenterStep,
    ArcRadiusStep,
    ContourDefinition,
    ContourError,
    LineStep,
    chamfer,
    fillet,
)
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point, segments_to_polyline, signed_area
from wop.core.contour_solver import build_contour, solve_contour

ORIGIN = Point(0, 0)


def definition(start, *steps):
    return ContourDefinition(start, tuple(steps))


class FilletTests(unittest.TestCase):
    def test_right_angle_fillet(self):
        segments = solve_contour(
            definition(Point(0, 0), LineStep(Point(10, 0), fillet(2)), LineStep(Point(10, -10)))
        )
        first, arc, last = segments
        self.assertTrue(first.start.is_close(Point(0, 0)) and first.end.is_close(Point(8, 0)))
        self.assertTrue(arc.start.is_close(Point(8, 0)) and arc.end.is_close(Point(10, -2)))
        self.assertTrue(arc.center.is_close(Point(8, -2)))
        self.assertIs(arc.direction, ArcDirection.CW)
        self.assertAlmostEqual(arc.radius, 2)
        self.assertTrue(last.start.is_close(Point(10, -2)) and last.end.is_close(Point(10, -10)))

    def test_left_turn_gives_a_counter_clockwise_arc(self):
        segments = solve_contour(
            definition(Point(0, 0), LineStep(Point(10, 0), fillet(2)), LineStep(Point(10, 10)))
        )
        self.assertIs(segments[1].direction, ArcDirection.CCW)
        self.assertTrue(segments[1].center.is_close(Point(8, 2)))

    def test_fillet_is_tangent_to_both_lines_at_any_angle(self):
        a, vertex, b = Point(0, 0), Point(10, 0), Point(20, -8)
        segments = solve_contour(definition(a, LineStep(vertex, fillet(3)), LineStep(b)))
        first, arc, last = segments
        self.assertAlmostEqual(arc.radius, 3)
        self.assertAlmostEqual(distance_to_line(arc.center, a, vertex), 3)
        self.assertAlmostEqual(distance_to_line(arc.center, vertex, b), 3)
        self.assertAlmostEqual(distance_to_line(arc.start, a, vertex), 0)
        self.assertAlmostEqual(distance_to_line(arc.end, vertex, b), 0)
        self.assertTrue(first.end.is_close(arc.start))
        self.assertTrue(arc.end.is_close(last.start))

    def test_both_input_styles_give_the_same_contour(self):
        """Requirement C2: intersection point + radius equals start/end + radius."""
        a, vertex, b = Point(0, 0), Point(10, 0), Point(20, -8)
        by_corner = solve_contour(definition(a, LineStep(vertex, fillet(3)), LineStep(b)))
        arc = by_corner[1]
        by_endpoints = solve_contour(
            definition(
                a,
                LineStep(arc.start),
                ArcRadiusStep(arc.end, 3, arc.direction),
                LineStep(b),
            )
        )
        assert_segments_close(self, by_corner, by_endpoints)

    def test_rounded_end_matches_the_reference_profile(self):
        segments = solve_contour(
            definition(
                Point(0, 0),
                LineStep(Point(10, 0), fillet(3)),
                LineStep(Point(10, -20)),
                LineStep(Point(0, -20)),
                LineStep(Point(0, 0)),
            )
        )
        assert_segments_close(self, reference_data.rounded_end_profile(), segments)

    def test_two_corners_on_one_short_line_drop_the_zero_length_remainder(self):
        segments = solve_contour(
            definition(
                Point(0, 0),
                LineStep(Point(10, 0), fillet(2)),
                LineStep(Point(10, -4), fillet(2)),
                LineStep(Point(0, -4)),
            )
        )
        self.assertEqual(len(segments), 4)
        self.assertIsInstance(segments[1], ArcSegment)
        self.assertIsInstance(segments[2], ArcSegment)
        assert_chain_is_continuous(self, segments)


class ChamferTests(unittest.TestCase):
    def test_chamfer_on_a_right_angle(self):
        segments = solve_contour(
            definition(Point(0, 0), LineStep(Point(10, 0), chamfer(2)), LineStep(Point(10, -10)))
        )
        connector = segments[1]
        self.assertIsInstance(connector, LineSegment)
        self.assertTrue(connector.start.is_close(Point(8, 0)))
        self.assertTrue(connector.end.is_close(Point(10, -2)))
        self.assertAlmostEqual(connector.length, 2 * math.sqrt(2))


class ArcStepTests(unittest.TestCase):
    def test_arc_by_end_and_radius(self):
        segments = solve_contour(definition(Point(10, 0), ArcRadiusStep(Point(0, 10), 10, ArcDirection.CCW)))
        self.assertTrue(segments[0].center.is_close(ORIGIN))

    def test_large_arc_flag(self):
        segments = solve_contour(
            definition(Point(10, 0), ArcRadiusStep(Point(0, 10), 10, ArcDirection.CCW, large_arc=True))
        )
        self.assertAlmostEqual(segments[0].sweep, 3 * math.pi / 2)

    def test_arc_by_end_and_center(self):
        segments = solve_contour(
            definition(Point(10, 0), ArcCenterStep(Point(0, 10), ORIGIN, ArcDirection.CCW))
        )
        self.assertAlmostEqual(segments[0].sweep, math.pi / 2)

    def test_full_circle_by_center(self):
        segments = solve_contour(
            definition(Point(10, 0), ArcCenterStep(Point(10, 0), ORIGIN, ArcDirection.CCW))
        )
        self.assertTrue(segments[0].is_full_circle)


class ErrorTests(unittest.TestCase):
    def assert_error(self, contour_definition, step_index):
        with self.assertRaises(ContourError) as context:
            solve_contour(contour_definition)
        self.assertEqual(context.exception.index, step_index)
        return str(context.exception)

    def test_no_steps(self):
        with self.assertRaises(ContourError):
            solve_contour(ContourDefinition(ORIGIN, ()))

    def test_radius_too_small_for_the_distance(self):
        message = self.assert_error(
            definition(ORIGIN, ArcRadiusStep(Point(30, 0), 10, ArcDirection.CCW)), 0
        )
        self.assertIn("step 1", message)

    def test_center_not_equidistant(self):
        self.assert_error(
            definition(Point(10, 0), ArcCenterStep(Point(0, 11), ORIGIN, ArcDirection.CCW)), 0
        )

    def test_corner_too_large_for_the_lines(self):
        # the error points at the step that carries the corner (step 1, index 0),
        # because that is the value the user has to change
        message = self.assert_error(
            definition(ORIGIN, LineStep(Point(10, 0), fillet(20)), LineStep(Point(10, -10))), 0
        )
        self.assertIn("too large", message)

    def test_corner_on_the_last_step(self):
        self.assert_error(definition(ORIGIN, LineStep(Point(10, 0), fillet(2))), 0)

    def test_corner_next_to_an_arc(self):
        self.assert_error(
            definition(
                ORIGIN,
                LineStep(Point(10, 0), fillet(2)),
                ArcRadiusStep(Point(20, -10), 10, ArcDirection.CW),
            ),
            0,
        )

    def test_collinear_lines_have_no_corner(self):
        self.assert_error(
            definition(ORIGIN, LineStep(Point(10, 0), fillet(2)), LineStep(Point(20, 0))), 0
        )

    def test_fold_back_has_no_corner(self):
        self.assert_error(
            definition(ORIGIN, LineStep(Point(10, 0), fillet(2)), LineStep(Point(5, 0))), 0
        )

    def test_zero_length_line_and_zero_corner_size(self):
        self.assert_error(definition(ORIGIN, LineStep(ORIGIN)), 0)
        self.assert_error(
            definition(ORIGIN, LineStep(Point(10, 0), fillet(0)), LineStep(Point(10, -10))), 0
        )


class BuildContourTests(unittest.TestCase):
    def test_stepped_shaft_from_a_definition(self):
        contour = build_contour(
            "c1",
            "shaft",
            definition(
                Point(0, 0),
                LineStep(Point(10, 0)),
                LineStep(Point(10, -20)),
                LineStep(Point(15, -20)),
                LineStep(Point(15, -50)),
                LineStep(Point(0, -50)),
                LineStep(Point(0, 0)),
            ),
        )
        self.assertTrue(contour.is_closed)
        self.assertEqual(contour.contour_id, "c1")
        self.assertIsNotNone(contour.definition)
        points = segments_to_polyline(list(contour.segments))
        self.assertAlmostEqual(abs(signed_area(points)), reference_data.STEPPED_SHAFT_AREA_MM2)

    def test_open_contour_is_not_closed(self):
        contour = build_contour("c2", "open", definition(ORIGIN, LineStep(Point(5, 0))))
        self.assertFalse(contour.is_closed)


if __name__ == "__main__":
    unittest.main()
