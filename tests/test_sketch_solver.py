import math
import unittest

from wop.core.geometry import ArcDirection, Point
from wop.core.sketch.constants import ORIGIN
from wop.core.sketch.model import Sketch, SketchError
from wop.core.sketch.solver import analyse, solve


def _rectangle(width: float = 10, height: float = 6) -> tuple[Sketch, list[int], list[int]]:
    """Corners a, b, c, d going round; sides ab, bc, cd, da (drawn a little crooked on purpose)."""
    sketch = Sketch()
    a = sketch.add_point(0, 0)
    b = sketch.add_point(0.3, width)
    c = sketch.add_point(height, width - 0.2)
    d = sketch.add_point(height - 0.1, 0.2)
    points = [a, b, c, d]
    lines = [sketch.add_line(points[i], points[(i + 1) % 4]) for i in range(4)]
    return sketch, points, lines


class RelationTests(unittest.TestCase):
    def test_horizontal_and_vertical_square_up_a_rectangle(self):
        sketch, (a, b, c, d), _ = _rectangle()
        sketch.add_constraint("horizontal", (a, b))
        sketch.add_constraint("horizontal", (d, c))
        sketch.add_constraint("vertical", (b, c))
        sketch.add_constraint("vertical", (a, d))
        result = solve(sketch)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(sketch.point(a).x, sketch.point(b).x)
        self.assertAlmostEqual(sketch.point(b).z, sketch.point(c).z)

    def test_dimensions_drive_the_geometry(self):
        sketch, (a, b, c, d), (ab, bc, cd, da) = _rectangle()
        for pair in ((a, b), (d, c)):
            sketch.add_constraint("horizontal", pair)
        for pair in ((b, c), (a, d)):
            sketch.add_constraint("vertical", pair)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("length", (ab,), (25,))
        height = sketch.add_constraint("length", (bc,), (8,))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(c).z, 25)
        self.assertAlmostEqual(sketch.point(c).x, 8)
        self.assertTrue(analyse(sketch).fully_defined)
        sketch.set_values(height, (12,))  # changing a dimension moves the geometry
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(c).x, 12)
        self.assertAlmostEqual(sketch.point(d).x, 12)

    def test_conflicting_dimension_is_refused_and_changes_nothing(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 10)
        line = sketch.add_line(a, b)
        sketch.add_constraint("length", (line,), (10,))
        sketch.add_constraint("distance", (a, b), (12,))
        before = sketch.signature()
        result = solve(sketch)
        self.assertFalse(result.converged)
        self.assertEqual(sketch.signature(), before)

    def test_parallel_perpendicular_equal(self):
        sketch = Sketch()
        a, b, c, d, e, f = (sketch.add_point(x, z) for x, z in ((0, 0), (0, 10), (3, 0), (3.5, 8), (6, 1), (9, 2)))
        first, second, third = sketch.add_line(a, b), sketch.add_line(c, d), sketch.add_line(e, f)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("fixed", (b,), (0, 10))
        sketch.add_constraint("parallel", (first, second))
        sketch.add_constraint("perpendicular", (first, third))
        sketch.add_constraint("equal_length", (first, second))
        self.assertTrue(solve(sketch).converged)
        # the first line runs along z, so the second is parallel to it and as long; the third is square to it
        self.assertAlmostEqual(sketch.point(d).x, sketch.point(c).x, places=6)
        self.assertAlmostEqual(abs(sketch.point(d).z - sketch.point(c).z), 10, places=6)
        self.assertAlmostEqual(sketch.point(e).z, sketch.point(f).z, places=6)

    def test_tangent_line_and_arc(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 5)
        arc = sketch.add_arc(centre, start, end, ArcDirection.CW)
        tail = sketch.add_point(5.5, 8)  # the line leaves the arc start in a rough direction
        line = sketch.add_line(start, tail)
        sketch.add_constraint("fixed", (centre,), (0, 0))
        sketch.add_constraint("radius", (arc,), (5,))
        sketch.add_constraint("tangent_line_arc", (line, arc, start))
        self.assertTrue(solve(sketch).converged)
        radius_direction = (sketch.point(start).x - sketch.point(centre).x, sketch.point(start).z - sketch.point(centre).z)
        along = (sketch.point(tail).x - sketch.point(start).x, sketch.point(tail).z - sketch.point(start).z)
        self.assertAlmostEqual(radius_direction[0] * along[0] + radius_direction[1] * along[1], 0, places=6)

    def test_tangent_arcs(self):
        sketch = Sketch()
        c1, s1, e1 = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 5)
        c2, e2 = sketch.add_point(9, 1), sketch.add_point(14, 4)
        first = sketch.add_arc(c1, s1, e1, ArcDirection.CW)
        second = sketch.add_arc(c2, s1, e2)  # the second arc starts where the first starts
        sketch.add_constraint("fixed", (c1,), (0, 0))
        sketch.add_constraint("radius", (first,), (5,))
        sketch.add_constraint("tangent_arcs", (first, second, s1))
        self.assertTrue(solve(sketch).converged)
        a = (sketch.point(s1).x - sketch.point(c1).x, sketch.point(s1).z - sketch.point(c1).z)
        b = (sketch.point(s1).x - sketch.point(c2).x, sketch.point(s1).z - sketch.point(c2).z)
        self.assertAlmostEqual(a[0] * b[1] - a[1] * b[0], 0, places=5)

    def test_arc_end_stays_on_the_circle(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 7)
        arc = sketch.add_arc(centre, start, end)
        sketch.add_constraint("radius", (arc,), (6,))
        sketch.add_constraint("fixed", (centre,), (0, 0))
        self.assertTrue(solve(sketch).converged)
        for point_id in (start, end):
            point = sketch.point(point_id)
            self.assertAlmostEqual(math.hypot(point.x, point.z), 6, places=6)

    def test_angle_to_z_and_length(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(1, 10)
        line = sketch.add_line(a, b)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("length", (line,), (10,))
        sketch.add_constraint("angle_z", (line,), (math.radians(30),))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(b).z, 10 * math.cos(math.radians(30)), places=6)
        self.assertAlmostEqual(sketch.point(b).x, 10 * math.sin(math.radians(30)), places=6)

    def test_angle_between_lines_and_diameter(self):
        sketch = Sketch()
        a, b, c = sketch.add_point(0, 0), sketch.add_point(0, 10), sketch.add_point(3, 9)
        first, second = sketch.add_line(a, b), sketch.add_line(b, c)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("fixed", (b,), (0, 10))
        sketch.add_constraint("length", (second,), (4,))
        sketch.add_constraint("angle", (first, second), (math.radians(90),))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(c).z, 10, places=6)
        circle_centre, edge = sketch.add_point(0, 30), sketch.add_point(2, 30)
        circle = sketch.add_arc(circle_centre, edge, edge)
        sketch.add_constraint("diameter", (circle,), (14,))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.segment(sketch.arcs[circle]).radius, 7, places=6)

    def test_distance_to_the_origin_point(self):
        sketch = Sketch()
        a, b = sketch.add_point(2, 3), sketch.add_point(2, 9)
        sketch.add_line(a, b)
        sketch.add_constraint("distance_z", (ORIGIN, a), (4,))
        sketch.add_constraint("distance_x", (ORIGIN, a), (1,))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(a).z, 4)
        self.assertAlmostEqual(sketch.point(a).x, 1)

    def test_midpoint_and_point_on_line(self):
        sketch = Sketch()
        a, b, m, p = (sketch.add_point(x, z) for x, z in ((0, 0), (0, 10), (1, 4), (2, 3)))
        line = sketch.add_line(a, b)
        sketch.add_line(m, p)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("fixed", (b,), (0, 10))
        sketch.add_constraint("midpoint", (m, line))
        sketch.add_constraint("point_on_line", (p, line))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(m).z, 5)
        self.assertAlmostEqual(sketch.point(m).x, 0)
        self.assertAlmostEqual(sketch.point(p).x, 0)

    def test_equal_radius(self):
        sketch = Sketch()
        c1, s1, c2, s2 = (sketch.add_point(x, z) for x, z in ((0, 0), (3, 0), (0, 20), (5, 20)))
        first, second = sketch.add_arc(c1, s1, s1), sketch.add_arc(c2, s2, s2)
        sketch.add_constraint("radius", (first,), (3,))
        sketch.add_constraint("equal_radius", (first, second))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.segment(sketch.arcs[second]).radius, 3)

    def test_wrong_things_are_refused(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(1, 1)
        line = sketch.add_line(a, b)
        with self.assertRaises(SketchError):
            sketch.add_constraint("radius", (line,), (1,))
        with self.assertRaises(SketchError):
            sketch.add_constraint("horizontal", (a, a))
        sketch.add_constraint("horizontal", (a, b))
        with self.assertRaises(SketchError):
            sketch.add_constraint("horizontal", (a, b))


class KeepingConstraintsTests(unittest.TestCase):
    def test_deleting_a_line_removes_its_relations(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        line = sketch.add_line(a, b)
        sketch.add_constraint("length", (line,), (5,))
        sketch.delete_piece(line)
        self.assertEqual(sketch.constraints, {})

    def test_joining_points_keeps_relations_and_drops_empty_ones(self):
        sketch = Sketch()
        a, b, c = sketch.add_point(0, 0), sketch.add_point(0, 5), sketch.add_point(0.001, 5)
        sketch.add_line(a, b)
        sketch.add_line(c, sketch.add_point(4, 9))
        sketch.add_constraint("distance", (a, c), (5,))
        sketch.add_constraint("horizontal", (b, c))
        sketch.merge_points(b, c)
        kinds = sorted(c.kind for c in sketch.constraints.values())
        self.assertEqual(kinds, ["distance"])  # horizontal b-c became b-b: gone
        self.assertEqual(next(iter(sketch.constraints.values())).refs, (a, b))


class AnalysisTests(unittest.TestCase):
    def test_free_line_has_four_directions_and_pinning_reduces_them(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        line = sketch.add_line(a, b)
        self.assertEqual(analyse(sketch).free_directions, 4)
        sketch.add_constraint("fixed", (a,), (0, 0))
        self.assertEqual(analyse(sketch).free_directions, 2)
        self.assertEqual(analyse(sketch).fixed_points, frozenset({a}))
        sketch.add_constraint("length", (line,), (5,))
        sketch.add_constraint("angle_z", (line,), (math.pi / 2,))
        analysis = analyse(sketch)
        self.assertTrue(analysis.fully_defined)
        self.assertEqual(analysis.fixed_points, frozenset({a, b}))

    def test_repeated_relation_is_reported(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        line = sketch.add_line(a, b)
        sketch.add_constraint("length", (line,), (5,))
        sketch.add_constraint("distance", (a, b), (5,))
        self.assertTrue(analyse(sketch).dependent)

    def test_sketch_without_relations_is_free(self):
        self.assertEqual(analyse(Sketch()).free_directions, 0)


class DragTests(unittest.TestCase):
    def test_drag_target_pulls_a_free_point_all_the_way(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        sketch.add_line(a, b)
        sketch.add_constraint("horizontal", (a, b))
        result = solve(sketch, {b: Point(0, 9)})
        self.assertTrue(result.converged)
        self.assertAlmostEqual(sketch.point(b).z, 9, places=3)

    def test_drag_keeps_the_relations_exact(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        line = sketch.add_line(a, b)
        sketch.add_constraint("horizontal", (a, b))
        sketch.add_constraint("length", (line,), (5,))
        solve(sketch, {b: Point(3, 9)})  # the pull cannot be followed; the polish solve makes the relations exact
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(b).x, sketch.point(a).x, places=6)
        self.assertAlmostEqual(abs(sketch.point(b).z - sketch.point(a).z), 5, places=6)


if __name__ == "__main__":
    unittest.main()
