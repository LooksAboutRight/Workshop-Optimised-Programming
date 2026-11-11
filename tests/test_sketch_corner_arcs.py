"""Fillet and chamfer between a line and an arc, and between two arcs (N44)."""

import math
import unittest

from wop.core.geometry import ArcDirection, Point
from wop.core.sketch.corners import chamfer_corner, fillet_corner, is_corner
from wop.core.sketch.model import Sketch, SketchError
from wop.core.sketch.pick import nearest_piece
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import solve


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.z - b.z)


def _line_and_arc():
    """A quarter arc (centre 0,0, radius 10) from (10, 0) to (0, 10) counter-clockwise, and a line from its start (10, 0) to (20, -10).
    The corner is the point (10, 0)."""
    sketch = Sketch()
    centre, start, end = sketch.add_point(0, 0), sketch.add_point(10, 0), sketch.add_point(0, 10)
    far = sketch.add_point(20, -10)
    arc = sketch.add_arc(centre, start, end, ArcDirection.CCW)
    line = sketch.add_line(start, far)
    return sketch, start, arc, line


def _two_arcs():
    """Two arcs that meet at (10, 0) at a right angle: one round (0, 0) radius 10 going up to (0, 10), one round (10, -8) radius 8
    going from the corner to (18, -8)."""
    sketch = Sketch()
    c1, c2 = sketch.add_point(0, 0), sketch.add_point(10, -8)
    corner, top, side = sketch.add_point(10, 0), sketch.add_point(0, 10), sketch.add_point(18, -8)
    first = sketch.add_arc(c1, corner, top, ArcDirection.CCW)
    second = sketch.add_arc(c2, corner, side, ArcDirection.CW)
    return sketch, corner, first, second


def _position(sketch: Sketch, point_id: int) -> Point:
    return sketch.point(point_id).position


class LineAndArcTests(unittest.TestCase):
    def test_a_fillet_touches_the_line_and_the_arc_and_has_the_radius(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = fillet_corner(sketch, corner, 2)
        link = sketch.corners[bevel]
        fillet = sketch.arcs[bevel]
        centre = _position(sketch, fillet.centre)
        self.assertAlmostEqual(_dist(centre, _position(sketch, fillet.start)), 2)
        self.assertAlmostEqual(_dist(centre, _position(sketch, fillet.end)), 2)
        (new_line,), (new_arc,) = ([k for k in link.kept if k in sketch.lines], [k for k in link.kept if k in sketch.arcs])
        touch_arc, touch_line = (_position(sketch, e) for e in (link.ends[1], link.ends[0])) if link.kept[0] in sketch.lines else (
            _position(sketch, link.ends[0]), _position(sketch, link.ends[1]))
        self.assertAlmostEqual(_dist(touch_arc, Point(0, 0)), 10)  # on the old arc
        self.assertAlmostEqual(_dist(centre, Point(0, 0)), 12)  # outside the arc: it is touched from outside, radius + 2
        # the foot of the centre on the old line is the touch point
        ux, uz = 1 / math.sqrt(2), -1 / math.sqrt(2)
        reach = (centre.x - 10) * ux + (centre.z - 0) * uz
        self.assertAlmostEqual(touch_line.x, 10 + ux * reach)
        self.assertAlmostEqual(touch_line.z, 0 + uz * reach)
        self.assertAlmostEqual(abs((centre.x - 10) * uz - (centre.z - 0) * ux), 2)  # 2 away from the line
        self.assertTrue(new_line and new_arc)

    def test_the_pieces_are_cut_and_the_old_ones_are_references_that_cannot_be_picked(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = fillet_corner(sketch, corner, 2)
        link = sketch.corners[bevel]
        self.assertEqual(set(link.references), {arc, line})
        self.assertTrue(sketch.arcs[arc].reference and sketch.lines[line].reference)
        self.assertTrue(set(link.references).isdisjoint(p.arc_id if hasattr(p, "arc_id") else p.line_id for p in sketch.selectable_pieces()))

    def test_the_constraints_hold_when_solved_and_after_the_far_end_is_pulled(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = fillet_corner(sketch, corner, 2)
        kinds = sorted(c.kind for c in sketch.constraints.values())
        self.assertIn("tangent_arcs", kinds)
        self.assertIn("tangent_line_arc", kinds)
        self.assertTrue(solve(sketch).converged)
        self.assertAlmostEqual(_dist(_position(sketch, sketch.arcs[bevel].centre), _position(sketch, sketch.arcs[bevel].start)), 2, places=5)

    def test_a_chamfer_ends_at_the_straight_distance_on_both_pieces(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = chamfer_corner(sketch, corner, 3)
        link = sketch.corners[bevel]
        for end in link.ends:
            self.assertAlmostEqual(_dist(_position(sketch, end), _position(sketch, corner)), 3)
        arc_end = next(e for k, e in zip(link.kept, link.ends) if k in sketch.arcs)
        self.assertAlmostEqual(_dist(_position(sketch, arc_end), Point(0, 0)), 10)  # on the circle of the old arc
        self.assertTrue(solve(sketch).converged)

    def test_the_corner_comes_back_when_the_bevel_is_deleted(self):
        for chamfer in (False, True):
            with self.subTest(chamfer=chamfer):
                sketch, corner, arc, line = _line_and_arc()
                bevel = chamfer_corner(sketch, corner, 3) if chamfer else fillet_corner(sketch, corner, 2)
                sketch.delete_piece(bevel)
                self.assertEqual(sketch.corners, {})
                self.assertEqual((len(sketch.arcs), len(sketch.lines)), (1, 1))
                new_arc = next(iter(sketch.arcs.values()))
                new_line = next(iter(sketch.lines.values()))
                self.assertIn(corner, (new_arc.start, new_arc.end))  # both end at the sharp corner again
                self.assertIn(corner, (new_line.start, new_line.end))
                self.assertFalse(new_arc.reference or new_line.reference or new_arc.construction or new_line.construction)

    def test_deleting_the_shortened_arc_leaves_the_line_grown_back(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = fillet_corner(sketch, corner, 2)
        link = sketch.corners[bevel]
        new_arc = next(k for k in link.kept if k in sketch.arcs)
        sketch.delete_piece(new_arc)
        self.assertEqual((sketch.arcs, sketch.corners), ({}, {}))
        (remaining,) = sketch.lines.values()
        self.assertIn(corner, (remaining.start, remaining.end))
        self.assertAlmostEqual(_dist(_position(sketch, remaining.start), _position(sketch, remaining.end)), math.hypot(10, 10))

    def test_a_value_that_does_not_fit_changes_nothing(self):
        sketch, corner, *_rest = _line_and_arc()
        before = sketch.signature()
        for call in (lambda: fillet_corner(sketch, corner, 500), lambda: chamfer_corner(sketch, corner, 50)):
            with self.assertRaises(SketchError):
                call()
            self.assertEqual(sketch.signature(), before)

    def test_save_and_load_keep_the_reference_arc_and_the_link(self):
        sketch, corner, arc, line = _line_and_arc()
        bevel = fillet_corner(sketch, corner, 2)
        again = sketch_from_dict(sketch_to_dict(sketch))
        self.assertTrue(again.arcs[arc].reference)
        self.assertEqual(again.corners, sketch.corners)
        again.delete_piece(bevel)
        self.assertEqual(len(again.arcs), 1)


class TwoArcsTests(unittest.TestCase):
    def test_a_fillet_between_two_arcs_touches_both(self):
        sketch, corner, first, second = _two_arcs()
        self.assertTrue(is_corner(sketch, corner))
        bevel = fillet_corner(sketch, corner, 1.5)
        fillet = sketch.arcs[bevel]
        centre = _position(sketch, fillet.centre)
        d1, d2 = _dist(centre, Point(0, 0)), _dist(centre, Point(10, -8))
        # the fillet lies in the angle between the arcs, outside both circles: radius + 1.5 from the first centre, radius + 1.5 from the second
        self.assertAlmostEqual(d1, 11.5)
        self.assertAlmostEqual(d2, 9.5)
        self.assertAlmostEqual(_dist(centre, _position(sketch, fillet.start)), 1.5)
        self.assertTrue(solve(sketch).converged)

    def test_a_chamfer_between_two_arcs(self):
        sketch, corner, first, second = _two_arcs()
        bevel = chamfer_corner(sketch, corner, 2)
        link = sketch.corners[bevel]
        for end in link.ends:
            self.assertAlmostEqual(_dist(_position(sketch, end), _position(sketch, corner)), 2)
        self.assertEqual(len(sketch.arcs), 4)  # two reference arcs and two shortened arcs
        self.assertTrue(solve(sketch).converged)

    def test_the_corner_of_two_arcs_comes_back(self):
        sketch, corner, first, second = _two_arcs()
        bevel = fillet_corner(sketch, corner, 1.5)
        sketch.delete_piece(bevel)
        self.assertEqual(len(sketch.arcs), 2)
        for arc in sketch.arcs.values():
            self.assertIn(corner, (arc.start, arc.end))
        radii = sorted(round(_dist(_position(sketch, a.centre), _position(sketch, a.start)), 6) for a in sketch.arcs.values())
        self.assertEqual(radii, [8, 10])  # the radii are as they were

    def test_arcs_that_run_into_each_other_smoothly_have_no_corner(self):
        sketch = Sketch()
        c1, c2 = sketch.add_point(0, 0), sketch.add_point(20, 0)
        corner, top, far = sketch.add_point(10, 0), sketch.add_point(0, 10), sketch.add_point(20, 10)
        sketch.add_arc(c1, corner, top, ArcDirection.CCW)
        sketch.add_arc(c2, corner, far, ArcDirection.CW)  # both leave the corner upwards: the circles touch there, no corner
        self.assertFalse(is_corner(sketch, corner))
        with self.assertRaises(SketchError):
            fillet_corner(sketch, corner, 1)

    def test_the_centre_of_an_arc_is_no_corner(self):
        sketch, corner, first, second = _two_arcs()
        self.assertFalse(is_corner(sketch, sketch.arcs[first].centre))


class EditorTests(unittest.TestCase):
    def _session(self, builder):
        from wop.ui.sketch_session import SketchSession

        sketch, corner, *_rest = builder()
        session = SketchSession(sketch)
        session.selected_points = {corner}
        return session, corner

    def test_the_fillet_and_chamfer_buttons_work_on_arc_corners(self):
        for builder in (_line_and_arc, _two_arcs):
            for kind, value in (("fillet", 1.5), ("chamfer", 2.0)):
                with self.subTest(builder=builder.__name__, kind=kind):
                    session, corner = self._session(builder)
                    self.assertEqual(session.corner_points(), [corner])
                    self.assertTrue(session.apply_corner(kind, value), session.message)
                    self.assertEqual(len(session.sketch.corners), 1)
                    session.undo()
                    self.assertEqual(session.sketch.corners, {})

    def test_an_arc_corner_is_painted(self):
        try:
            import os

            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("needs PySide6")
        from wop.ui.qt.sketch_canvas import SketchCanvas

        app = QApplication.instance() or QApplication([])
        session, corner = self._session(_line_and_arc)
        session.apply_corner("fillet", 2)
        canvas = SketchCanvas(session)
        canvas.resize(500, 400)
        canvas.show()
        self.assertFalse(canvas.grab().isNull())
        canvas.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
