"""A fillet or chamfer is one unit with its shortened pieces and its reference pieces (N43)."""

import copy
import unittest

from wop.core.geometry import Point
from wop.core.sketch.corners import chamfer_corner, fillet_corner
from wop.core.sketch.mirror import AXIS_Z, mirror_pieces
from wop.core.sketch.model import Sketch
from wop.core.sketch.pick import nearest_piece
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.ui.sketch_session import SketchSession


def _corner() -> tuple[Sketch, int, int, int]:
    """Two lines meeting at a right angle at (0, 10): one runs along z, one along x."""
    sketch = Sketch()
    a, corner, b = sketch.add_point(0, 0), sketch.add_point(0, 10), sketch.add_point(10, 10)
    sketch.add_line(a, corner)
    sketch.add_line(corner, b)
    return sketch, a, corner, b


def _rounded(chamfer: bool = False):
    sketch, a, corner, b = _corner()
    bevel = chamfer_corner(sketch, corner, 3) if chamfer else fillet_corner(sketch, corner, 3)
    return sketch, a, corner, b, bevel, sketch.corners[bevel]


def _ends(sketch: Sketch) -> list:
    """The two end positions of every line, sorted."""
    result = []
    for line in sketch.lines.values():
        ends = sorted([(round(sketch.point(line.start).x, 6), round(sketch.point(line.start).z, 6)),
                       (round(sketch.point(line.end).x, 6), round(sketch.point(line.end).z, 6))])
        result.append((ends[0], ends[1]))
    return sorted(result)


class LinkTests(unittest.TestCase):
    def test_a_fillet_and_a_chamfer_are_linked_to_their_pieces(self):
        for chamfer in (False, True):
            with self.subTest(chamfer=chamfer):
                sketch, _a, corner, _b, bevel, link = _rounded(chamfer)
                self.assertEqual(list(sketch.corners), [bevel])
                self.assertEqual(link.point, corner)
                self.assertTrue(all(sketch.lines[r].reference for r in link.references))
                self.assertFalse(any(sketch.lines[k].reference for k in link.kept))

    def test_the_reference_pieces_cannot_be_picked_but_the_sharp_corner_can(self):
        sketch, _a, corner, _b, _bevel, link = _rounded()
        # (x 0, z 9.5) is between the cut end of the vertical line and the sharp corner: only the reference line is there
        self.assertIsNone(nearest_piece(sketch, Point(0, 9.5), 0.2))
        self.assertTrue(set(link.references).isdisjoint(p.line_id for p in sketch.selectable_pieces() if hasattr(p, "line_id")))
        self.assertIn(corner, sketch.points)  # the point is still there to be picked and dimensioned

    def test_deleting_the_bevel_gives_the_sharp_corner_back(self):
        for chamfer in (False, True):
            with self.subTest(chamfer=chamfer):
                sketch, a, corner, b, bevel, link = _rounded(chamfer)
                sketch.delete_piece(bevel)
                self.assertEqual(sketch.corners, {})
                self.assertEqual(_ends(sketch), [((0, 0), (0, 10)), ((0, 10), (10, 10))])
                self.assertFalse(any(line.reference for line in sketch.lines.values()))
                self.assertEqual(sorted(sketch.points), sorted([a, corner, b]))  # the cut ends are gone
                self.assertEqual(sorted(sketch.lines), sorted(link.kept))

    def test_deleting_a_shortened_line_removes_the_bevel_and_the_other_line_grows_back(self):
        for chamfer in (False, True):
            for index in (0, 1):
                with self.subTest(chamfer=chamfer, deleted=index):
                    sketch, _a, _corner_id, _b, bevel, link = _rounded(chamfer)
                    sketch.delete_piece(link.kept[index])
                    self.assertEqual(sketch.corners, {})
                    self.assertNotIn(bevel, sketch.lines)
                    self.assertNotIn(bevel, sketch.arcs)
                    self.assertEqual(sorted(sketch.lines), [link.kept[1 - index]])
                    expected = [((0, 0), (0, 10))] if index == 1 else [((0, 10), (10, 10))]
                    self.assertEqual(_ends(sketch), expected)
                    self.assertFalse(sketch.arcs)

    def test_what_gives_the_direction_stays_and_what_touches_the_cut_end_goes(self):
        sketch, a, _corner_id, _b, bevel, link = _rounded()
        kept_line = link.kept[0]
        line = sketch.lines[kept_line]
        sketch.add_constraint("length", (kept_line,), (5.0,))
        sketch.add_constraint("angle_z", (kept_line,), (0.0,))
        sketch.add_constraint("distance_z", (a, link.ends[0]), (6.5,))
        sketch.add_constraint("vertical", (line.start, line.end), ())
        sketch.delete_piece(bevel)
        kinds = sorted(c.kind for c in sketch.constraints.values())
        self.assertIn("angle_z", kinds)
        self.assertIn("vertical", kinds)
        self.assertNotIn("length", kinds)
        self.assertNotIn("distance_z", kinds)
        for constraint in sketch.constraints.values():
            if constraint.kind == "vertical":
                self.assertTrue(set(constraint.refs) <= set(sketch.points))  # it follows the line to the sharp corner

    def test_a_reference_line_without_a_corner_becomes_an_ordinary_helper_line(self):
        sketch, _a, _corner_id, _b, bevel, link = _rounded()
        lone = sketch.add_line(sketch.add_point(50, 50), sketch.add_point(60, 60), reference=True)
        sketch.drop_unused_points()
        self.assertIn(lone, sketch.lines)
        self.assertEqual((sketch.lines[lone].reference, sketch.lines[lone].construction), (False, True))  # it can be picked and deleted
        self.assertEqual(list(sketch.corners), [bevel])
        self.assertTrue(all(r in sketch.lines for r in link.references))

    def test_the_link_is_saved_and_works_after_loading(self):
        sketch, _a, _corner_id, _b, bevel, _link = _rounded()
        again = sketch_from_dict(sketch_to_dict(sketch))
        self.assertEqual(again.corners, sketch.corners)
        again.delete_piece(bevel)
        self.assertEqual(_ends(again), [((0, 0), (0, 10)), ((0, 10), (10, 10))])

    def test_a_copy_for_undo_keeps_the_link(self):
        sketch, *_rest = _rounded()
        self.assertEqual(copy.deepcopy(sketch).corners, sketch.corners)

    def test_two_corners_of_one_outline_are_independent(self):
        sketch = Sketch()
        a, b, c, d = sketch.add_point(0, 0), sketch.add_point(0, 10), sketch.add_point(10, 10), sketch.add_point(10, 0)
        for start, end in ((a, b), (b, c), (c, d)):
            sketch.add_line(start, end)
        first = fillet_corner(sketch, b, 2)
        second = chamfer_corner(sketch, c, 2)
        self.assertEqual(len(sketch.corners), 2)
        sketch.delete_piece(first)
        self.assertEqual(list(sketch.corners), [second])
        self.assertEqual(sum(1 for line in sketch.lines.values() if line.reference), 2)

    def test_mirroring_the_pieces_of_a_corner_makes_no_unselectable_copy(self):
        sketch, _a, _corner_id, _b, bevel, link = _rounded()
        made = mirror_pieces(sketch, [link.kept[0], link.kept[1], bevel], AXIS_Z)
        sketch.drop_unused_points()
        self.assertTrue(made)
        self.assertEqual(len([line for line in sketch.lines.values() if line.reference]), 2)  # only the original references


class SessionTests(unittest.TestCase):
    def test_delete_and_undo_in_the_editor(self):
        sketch, _a, _corner_id, _b, bevel, link = _rounded()
        session = SketchSession(sketch)
        session.selected_pieces = {link.kept[0]}
        session.delete_selected()
        self.assertEqual(session.sketch.corners, {})
        self.assertEqual(sorted(session.sketch.lines), [link.kept[1]])
        session.undo()
        self.assertEqual(list(session.sketch.corners), [bevel])
        self.assertEqual(len(session.sketch.lines), 4)  # two shortened, two reference

    def test_a_box_around_the_corner_selects_no_reference_piece(self):
        sketch, _a, _corner_id, _b, _bevel, link = _rounded()
        session = SketchSession(sketch)
        session._select_in_box(Point(-5, -5), Point(20, 20), False)
        self.assertTrue(set(link.references).isdisjoint(session.selected_pieces))
        self.assertTrue(set(link.kept) <= session.selected_pieces)


if __name__ == "__main__":
    unittest.main()
