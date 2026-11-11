import math
import unittest

from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point
from wop.core.sketch.constants import ORIGIN
from wop.core.sketch.corners import chamfer_corner, fillet_corner
from wop.core.geometry.intersect import fraction_along, intersections
from wop.core.sketch.loops import find_chains
from wop.core.sketch.mirror import AXIS_X, AXIS_Z, mirror_pieces
from wop.core.sketch.model import Sketch, SketchError
from wop.core.sketch.solver import analyse, solve
from wop.core.sketch.trim import trim_piece


def _corner() -> tuple[Sketch, int, int, int]:
    """Two lines meeting at a right angle at (0, 10): one runs along z, one along x."""
    sketch = Sketch()
    a, corner, b = sketch.add_point(0, 0), sketch.add_point(0, 10), sketch.add_point(10, 10)
    sketch.add_line(a, corner)
    sketch.add_line(corner, b)
    return sketch, a, corner, b


class IntersectTests(unittest.TestCase):
    def test_line_line(self):
        found = intersections(LineSegment(Point(0, 0), Point(10, 10)), LineSegment(Point(0, 10), Point(10, 0)))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].is_close(Point(5, 5)))

    def test_lines_that_do_not_reach_each_other(self):
        self.assertEqual(intersections(LineSegment(Point(0, 0), Point(1, 1)), LineSegment(Point(0, 10), Point(10, 0))), [])

    def test_line_and_circle(self):
        circle = ArcSegment(Point(0, 5), Point(0, 5), Point(0, 0), ArcDirection.CCW)
        found = intersections(LineSegment(Point(-10, 0), Point(10, 0)), circle)
        self.assertEqual(len(found), 2)

    def test_circle_and_circle(self):
        first = ArcSegment(Point(0, 5), Point(0, 5), Point(0, 0), ArcDirection.CCW)
        second = ArcSegment(Point(0, 11), Point(0, 11), Point(0, 6), ArcDirection.CCW)
        self.assertEqual(len(intersections(first, second)), 2)

    def test_arc_only_counts_where_the_arc_is(self):
        quarter = ArcSegment(Point(5, 0), Point(0, 5), Point(0, 0), ArcDirection.CCW)
        found = intersections(LineSegment(Point(-10, 0), Point(10, 0)), quarter)
        self.assertEqual(len(found), 1)  # the line z=0 touches the arc only at its start
        far = intersections(LineSegment(Point(-10, -3), Point(10, -3)), quarter)
        self.assertEqual(far, [])

    def test_fraction_along(self):
        self.assertAlmostEqual(fraction_along(LineSegment(Point(0, 0), Point(0, 10)), Point(0, 2.5)), 0.25)
        quarter = ArcSegment(Point(5, 0), Point(0, 5), Point(0, 0), ArcDirection.CCW)
        self.assertAlmostEqual(fraction_along(quarter, Point(math.sqrt(12.5), math.sqrt(12.5))), 0.5)


def _real_lines(sketch: Sketch):
    return [line for line in sketch.lines.values() if not line.construction]


class CornerTests(unittest.TestCase):
    def test_fillet_rounds_a_right_angle_and_keeps_the_sharp_corner_as_a_reference(self):
        sketch, a, corner, b = _corner()
        old = sorted(sketch.lines)
        arc = fillet_corner(sketch, corner, 3)
        self.assertIn(corner, sketch.points)  # the original corner is still there to dimension
        segment = sketch.segment(sketch.arcs[arc])
        self.assertAlmostEqual(segment.radius, 3)
        self.assertAlmostEqual(segment.sweep, math.pi / 2)
        self.assertTrue(solve(sketch).converged)
        for line_id in old:  # the old lines run on to the corner, as thin reference lines that are not part of the outline
            line = sketch.lines[line_id]
            self.assertTrue(line.construction and line.reference and not line.cutting)
        self.assertEqual(len(_real_lines(sketch)), 2)  # two new lines
        chains = find_chains(sketch)
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0].pieces), 3)  # new line, arc, new line

    def test_the_new_lines_match_the_old_ones(self):
        sketch, a, corner, b = _corner()
        fillet_corner(sketch, corner, 3)
        old = [line for line in sketch.lines.values() if line.reference]
        new = _real_lines(sketch)
        for line in new:
            self.assertEqual(len({line.start, line.end} & {a, b}), 1)  # it shares the far end with its old line
        held = [c for c in sketch.constraints.values() if c.kind == "point_on_line"]
        self.assertEqual(sorted(c.refs[1] for c in held), sorted(line.line_id for line in old))  # its new end is held on the old line
        for c in held:
            self.assertTrue(any(c.refs[0] in (line.start, line.end) for line in new))

    def test_the_original_corner_can_be_dimensioned_and_the_fillet_follows(self):
        sketch, a, corner, b = _corner()
        arc = fillet_corner(sketch, corner, 3)
        sketch.add_constraint("fixed", (a,), (0, 0))
        old = next(line for line in sketch.lines.values() if line.reference and {a, corner} == {line.start, line.end})
        length = sketch.add_constraint("length", (old.line_id,), (10,))
        sketch.set_values(length, (14,))  # the sharp corner is moved by its own dimension
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(corner).position.distance_to(sketch.point(a).position), 14)
        self.assertAlmostEqual(sketch.segment(sketch.arcs[arc]).radius, 3)  # and the round corner has moved with it
        self.assertEqual(len(find_chains(sketch)[0].pieces), 3)

    def test_fillet_stays_tangent_when_the_lines_move(self):
        sketch, a, corner, b = _corner()
        arc = fillet_corner(sketch, corner, 3)
        sketch.move_point(a, 0, -5)
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.segment(sketch.arcs[arc]).radius, 3)

    def test_fillet_radius_can_be_changed_afterwards(self):
        sketch, a, corner, b = _corner()
        fillet_corner(sketch, corner, 3)
        (radius,) = [c for c in sketch.constraints.values() if c.kind == "radius"]
        sketch.set_values(radius.constraint_id, (4,))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.segment(next(iter(sketch.arcs.values()))).radius, 4)

    def test_chamfer_cuts_the_corner_and_has_its_distances_from_the_corner(self):
        sketch, a, corner, b = _corner()
        line = chamfer_corner(sketch, corner, 2)
        self.assertAlmostEqual(sketch.segment(sketch.lines[line]).length, math.hypot(2, 2))
        self.assertEqual(len(find_chains(sketch)[0].pieces), 3)
        distances = [c for c in sketch.constraints.values() if c.kind == "distance"]
        self.assertEqual(len(distances), 2)
        self.assertTrue(all(corner in c.refs and c.values == (2,) for c in distances))
        for point_id in (a, corner, b):  # the corner itself held in place, so only the two distances can move the chamfer
            sketch.add_constraint("fixed", (point_id,), (sketch.point(point_id).x, sketch.point(point_id).z))
        for c in distances:
            sketch.set_values(c.constraint_id, (3,))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.segment(sketch.lines[line]).length, math.hypot(3, 3))

    def test_a_value_that_does_not_fit_changes_nothing(self):
        sketch, a, corner, b = _corner()
        before = sketch.signature()
        for call in (lambda: fillet_corner(sketch, corner, 30), lambda: chamfer_corner(sketch, corner, 30)):
            with self.assertRaises(SketchError):
                call()
            self.assertEqual(sketch.signature(), before)  # it stops before it has touched anything

    def test_corner_value_too_big_or_wrong_place(self):
        sketch, a, corner, b = _corner()
        with self.assertRaises(SketchError):
            fillet_corner(sketch, a, 1)  # a is the end of one line only
        with self.assertRaises(SketchError):
            chamfer_corner(sketch, corner, 0)
        fillet_corner(sketch, corner, 3)
        with self.assertRaises(SketchError):
            fillet_corner(sketch, corner, 1)  # the corner holds only reference lines now

    def test_two_corners_of_one_outline(self):
        sketch = Sketch()
        a, b, c, d = (sketch.add_point(x, z) for x, z in ((0, 0), (0, 20), (20, 20), (20, 40)))
        for start, end in ((a, b), (b, c), (c, d)):
            sketch.add_line(start, end)
        fillet_corner(sketch, b, 2)
        chamfer_corner(sketch, c, 2)
        self.assertTrue(solve(sketch).converged)
        self.assertEqual(len(find_chains(sketch)[0].pieces), 5)  # line, arc, line, chamfer, line

    def test_the_reference_lines_are_saved(self):
        import json

        from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict

        sketch, a, corner, b = _corner()
        fillet_corner(sketch, corner, 3)
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(sketch))))
        self.assertEqual(again.signature(), sketch.signature())
        self.assertEqual(sum(line.reference for line in again.lines.values()), 2)

    def test_fillet_of_an_acute_corner(self):
        sketch = Sketch()
        a, corner, b = sketch.add_point(10, 0), sketch.add_point(0, 0), sketch.add_point(10, 10)
        sketch.add_line(a, corner)
        sketch.add_line(corner, b)
        arc = fillet_corner(sketch, corner, 1)
        self.assertAlmostEqual(sketch.segment(sketch.arcs[arc]).radius, 1)
        self.assertTrue(solve(sketch).converged)


class TrimTests(unittest.TestCase):
    def _cross(self) -> tuple[Sketch, int, int]:
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 20)
        c, d = sketch.add_point(-5, 10), sketch.add_point(5, 10)
        return sketch, sketch.add_line(a, b), sketch.add_line(c, d)

    def test_trim_the_end_of_a_line(self):
        sketch, horizontal, vertical = self._cross()
        trim_piece(sketch, horizontal, Point(0, 15))  # the part past the crossing at z = 10
        line = sketch.lines[horizontal]
        self.assertAlmostEqual(sketch.point(line.end).z, 10)
        self.assertTrue(solve(sketch).converged)

    def test_trim_the_middle_of_a_line_makes_two_pieces(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 30)
        long_line = sketch.add_line(a, b)
        for z in (10, 20):
            top, bottom = sketch.add_point(5, z), sketch.add_point(-5, z)
            sketch.add_line(top, bottom)
        trim_piece(sketch, long_line, Point(0, 15))
        real = [line for line in sketch.lines.values() if sketch.point(line.start).x == 0 and sketch.point(line.end).x == 0]
        spans = sorted((sorted([sketch.point(l.start).z, sketch.point(l.end).z]) for l in real))
        self.assertEqual(len(spans), 2)
        self.assertAlmostEqual(spans[0][1], 10)
        self.assertAlmostEqual(spans[1][0], 20)
        self.assertTrue(solve(sketch).converged)

    def test_trim_a_piece_with_no_crossing_deletes_it(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 5)
        line = sketch.add_line(a, b)
        trim_piece(sketch, line, Point(0, 2))
        self.assertEqual(sketch.lines, {})

    def test_the_new_end_joins_the_point_that_is_there(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 20)
        middle, side = sketch.add_point(0, 10), sketch.add_point(8, 10)
        line = sketch.add_line(a, b)
        other = sketch.add_line(middle, side)  # starts exactly on the line
        trim_piece(sketch, line, Point(0, 15))
        self.assertEqual(sketch.lines[line].end, middle)
        self.assertTrue(other in sketch.lines)

    def test_trim_a_circle_leaves_an_arc(self):
        sketch = Sketch()
        centre, edge = sketch.add_point(0, 0), sketch.add_point(0, 5)
        circle = sketch.add_arc(centre, edge, edge)
        left, right = sketch.add_point(-8, -3), sketch.add_point(8, -3)
        sketch.add_line(left, right)  # crosses the circle twice at z = -3
        # trim the part below the line (z < -3): the click is at z = -4.9
        trim_piece(sketch, circle, Point(0.5, -4.9))
        segment = sketch.segment(sketch.arcs[circle])
        self.assertFalse(segment.is_full_circle)
        self.assertGreater(segment.sweep, math.pi)  # more than half of the circle is left
        self.assertTrue(solve(sketch).converged)

    def test_trim_a_circle_needs_two_crossings(self):
        sketch = Sketch()
        centre, edge = sketch.add_point(0, 0), sketch.add_point(0, 5)
        circle = sketch.add_arc(centre, edge, edge)
        with self.assertRaises(SketchError):
            trim_piece(sketch, circle, Point(5, 0))

    def test_trim_an_arc_end(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 5)
        arc = sketch.add_arc(centre, start, end)
        low, high = sketch.add_point(-1, 3), sketch.add_point(8, 3)
        sketch.add_line(low, high)  # cuts the arc at z = 3
        trim_piece(sketch, arc, Point(1, 4.9))  # the click is near the end (z = 5)
        segment = sketch.segment(sketch.arcs[arc])
        self.assertAlmostEqual(segment.end.z, 3)
        self.assertAlmostEqual(segment.radius, 5)
        self.assertTrue(solve(sketch).converged)


class MirrorTests(unittest.TestCase):
    def _profile(self) -> tuple[Sketch, list[int]]:
        sketch = Sketch()
        a, b, c = sketch.add_point(0, 0), sketch.add_point(10, 0), sketch.add_point(10, 20)
        return sketch, [sketch.add_line(a, b), sketch.add_line(b, c)]

    def test_mirror_about_the_z_axis(self):
        sketch, lines = self._profile()
        created = mirror_pieces(sketch, lines, AXIS_Z)
        self.assertEqual(len(created), 2)
        xs = sorted(p.x for p in sketch.points.values())
        self.assertEqual(xs, [-10, -10, 0, 10, 10])  # the point on the axis is shared
        self.assertTrue(solve(sketch).converged)
        self.assertEqual(len(find_chains(sketch)), 1)

    def test_mirror_stays_symmetric_when_one_side_moves(self):
        sketch, lines = self._profile()
        mirror_pieces(sketch, lines, AXIS_Z)
        moved = next(i for i, p in sketch.points.items() if p.x == 10 and p.z == 20)
        solve(sketch, {moved: Point(12, 25)})  # a drag: pull the point, then the relations are made exact
        self.assertTrue(solve(sketch).converged)
        # the mouse pull is soft (the other points hold on a little), so the point lands within a hundredth of the mouse
        self.assertTrue(any(abs(p.x + 12) < 0.01 and abs(p.z - 25) < 0.01 for p in sketch.points.values()))

    def test_mirror_about_the_x_axis_and_a_line(self):
        sketch, lines = self._profile()
        mirror_pieces(sketch, lines, AXIS_X)
        self.assertEqual(sorted(p.z for p in sketch.points.values()), [-20, 0, 0, 20])  # the points on the axis are shared
        self.assertTrue(solve(sketch).converged)

    def test_mirror_about_a_construction_line(self):
        sketch, lines = self._profile()
        a, b = sketch.add_point(0, -5), sketch.add_point(0, 30)
        axis = sketch.add_line(a, b, construction=True)  # along z at x = 0, like the spindle axis
        mirror_pieces(sketch, lines, axis)
        self.assertTrue(solve(sketch).converged)
        self.assertIn(-10, [round(p.x, 6) for p in sketch.points.values()])
        self.assertEqual(len([line for line in sketch.lines.values() if not line.construction]), 4)

    def test_mirror_an_arc_turns_its_direction(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 5), sketch.add_point(5, 5), sketch.add_point(0, 10)
        arc = sketch.add_arc(centre, start, end, ArcDirection.CCW)
        (created,) = mirror_pieces(sketch, [arc], AXIS_Z)
        self.assertIs(sketch.arcs[created].direction, ArcDirection.CW)
        self.assertTrue(solve(sketch).converged)
        original, copy = sketch.segment(sketch.arcs[arc]), sketch.segment(sketch.arcs[created])
        self.assertAlmostEqual(original.radius, copy.radius)

    def test_nothing_selected_is_an_error(self):
        sketch, lines = self._profile()
        with self.assertRaises(SketchError):
            mirror_pieces(sketch, [], AXIS_Z)


class SymmetricRelationTests(unittest.TestCase):
    def test_symmetric_about_a_line_and_axes(self):
        sketch = Sketch()
        a, b = sketch.add_point(0, 0), sketch.add_point(0, 10)
        axis = sketch.add_line(a, b)
        p, q = sketch.add_point(3, 2), sketch.add_point(-1, 4)
        sketch.add_line(p, q)
        sketch.add_constraint("fixed", (a,), (0, 0))
        sketch.add_constraint("fixed", (b,), (0, 10))
        sketch.add_constraint("fixed", (p,), (3, 2))
        sketch.add_constraint("symmetric", (p, q, axis))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(q).x, -3, places=6)
        self.assertAlmostEqual(sketch.point(q).z, 2, places=6)

    def test_about_the_origin_axes(self):
        sketch = Sketch()
        p, q = sketch.add_point(3, 2), sketch.add_point(-1, 4)
        sketch.add_line(p, q)
        sketch.add_constraint("fixed", (p,), (3, 2))
        sketch.add_constraint("symmetric_axis_x", (p, q))
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(sketch.point(q).x, 3, places=6)
        self.assertAlmostEqual(sketch.point(q).z, -2, places=6)
        self.assertTrue(analyse(sketch).fully_defined)
        self.assertEqual(ORIGIN, 0)


if __name__ == "__main__":
    unittest.main()
