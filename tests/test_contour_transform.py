import unittest

from wop.core.contour import (
    ArcCenterStep,
    ArcRadiusStep,
    ContourDefinition,
    LineStep,
    NamedPoint,
    chamfer,
    fillet,
)
from wop.core.contour_solver import solve_contour
from wop.core.contour_transform import mirrored_x, mirrored_z, rotated_90, shifted
from wop.core.geometry import ArcDirection, Point

TOLERANCE = 1e-6

PART = ContourDefinition(
    Point(8, 0),
    (
        LineStep(Point(8, -10), fillet(1)),
        LineStep(Point(12, -10), chamfer(1)),
        LineStep(Point(12, -20)),
        ArcRadiusStep(Point(16, -24), 4, ArcDirection.CCW),
        LineStep(Point(16, -30)),
    ),
    points=(NamedPoint("tip", 8, 0),),
)
CLOSED = ContourDefinition(
    Point(0, 0),
    (
        LineStep(Point(0, 10)),
        ArcCenterStep(Point(5, 15), Point(5, 10), ArcDirection.CW),
        LineStep(Point(10, 15)),
        LineStep(Point(10, 0)),
    ),
    closed=True,
)


def samples(segments, where, count=5):
    """Points along the segments, each mapped by `where`, rounded: a set that does not depend on the direction."""
    result = set()
    for segment in segments:
        for step in range(count + 1):
            point = where(segment.point_at(step / count))
            result.add((round(point.x, 5) + 0.0, round(point.z, 5) + 0.0))
    return result


def same_shape(test, definition, moved, where):
    test.assertEqual(samples(solve_contour(moved), lambda p: p), samples(solve_contour(definition), where))


class TransformTests(unittest.TestCase):
    def test_shift_moves_everything(self):
        moved = shifted(PART, 3, -2)
        same_shape(self, PART, moved, lambda p: Point(p.x + 3, p.z - 2))
        self.assertEqual((moved.points[0].x, moved.points[0].z), (11, -2))

    def test_mirror_x_gives_the_mirrored_picture(self):
        for shape in (PART, CLOSED):
            same_shape(self, shape, mirrored_x(shape), lambda p: Point(-p.x, p.z))

    def test_mirror_z_gives_the_mirrored_picture_and_an_open_contour_still_starts_at_its_highest_z(self):
        for shape in (PART, CLOSED):
            same_shape(self, shape, mirrored_z(shape), lambda p: Point(p.x, -p.z))
        segments = solve_contour(mirrored_z(PART))
        self.assertAlmostEqual(segments[0].start.z, 30)
        self.assertAlmostEqual(segments[-1].end.z, 0)

    def test_rotate_turns_a_quarter_counter_clockwise(self):
        for shape in (PART, CLOSED):
            same_shape(self, shape, rotated_90(shape), lambda p: Point(p.z, -p.x))
        self.assertEqual(rotated_90(CLOSED).start, Point(0, 0))
        up = rotated_90(ContourDefinition(Point(0, 0), (LineStep(Point(0, 10)),)))  # along +Z goes to +X
        self.assertAlmostEqual(up.steps[0].end.x, 10)
        self.assertAlmostEqual(up.steps[0].end.z, 0)

    def test_four_turns_and_double_mirrors_give_the_shape_back(self):
        turned = CLOSED
        for _ in range(4):
            turned = rotated_90(turned)
        same_shape(self, CLOSED, turned, lambda p: p)
        same_shape(self, PART, mirrored_x(mirrored_x(PART)), lambda p: p)
        same_shape(self, PART, mirrored_z(mirrored_z(PART)), lambda p: p)
        self.assertEqual(mirrored_z(mirrored_z(PART)).start, PART.start)

    def test_a_full_circle_stays_a_full_circle(self):
        circle = ContourDefinition(
            Point(5, 0), (ArcCenterStep(Point(5, 0), Point(5, 3), ArcDirection.CCW),), closed=True)
        turned = rotated_90(circle)
        self.assertTrue(turned.steps[0].end.is_close(turned.start))
        self.assertEqual(turned.steps[0].center, Point(3, -5))  # the centre (5, 3) goes to (3, -5)

    def test_named_points_go_with_the_shape(self):
        mirrored = mirrored_z(PART)
        self.assertEqual((mirrored.points[0].x, mirrored.points[0].z), (8, 0))
        turned = rotated_90(PART)
        self.assertEqual((turned.points[0].x, turned.points[0].z), (0, -8))


class FullCircleOnTheAxisTests(unittest.TestCase):
    def test_a_circle_that_starts_level_with_its_centre_stays_a_full_circle(self):
        circle = ContourDefinition(Point(5, 0), (ArcCenterStep(Point(5, 0), Point(0, 0), ArcDirection.CCW),), closed=True)
        for how in (mirrored_x, mirrored_z, rotated_90):
            (arc,) = solve_contour(how(circle))
            self.assertTrue(arc.is_full_circle)


if __name__ == "__main__":
    unittest.main()
