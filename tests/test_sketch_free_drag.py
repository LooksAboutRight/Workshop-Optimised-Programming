"""Dragging a point of a shape that is not fully defined moves it in the direction that is still free (N46).

`tests/data/sketches/free_drag_contour.json` is the contour of the user's test (2026-10-29) with all its relations. Its relation
"diameter 4.789" is taken away: the points on the 65 degree line are then free to slide along it. Before the weak hold on the
other points and the back-off, the soft pull drifted along the free directions (a free line shrank to nothing), the relations
could not be made exact again and the whole drag was refused.
"""

import copy
import json
import unittest
from pathlib import Path

from wop.core.geometry import Point
from wop.core.sketch.sketch_io import sketch_from_dict
from wop.core.sketch.solver import analyse, solve
from wop.ui.sketch_session import SketchSession

DATA = Path(__file__).parent / "data" / "sketches" / "free_drag_contour.json"
DIAMETER_4_789 = 75  # the id of that relation in the file
ON_THE_65_DEGREE_LINE = (7, 58, 61)
FREE_LINE_END = 28  # the end of a line that only has a direction: its length is free
TOL = 0.05  # small: the points of this contour lie close together


def _sketch(with_the_dimension: bool = False):
    sketch = sketch_from_dict(json.loads(DATA.read_text(encoding="utf-8")))
    if not with_the_dimension:
        sketch.remove_constraint(DIAMETER_4_789)
    return sketch


def _drag(session: SketchSession, point_id: int, dx: float, dz: float, steps: int = 4) -> None:
    here = session.sketch.point(point_id).position
    session.snapping = False  # a point dropped on another one would join it
    session.set_tool("select")
    session.press(here, TOL)
    for step in range(1, steps + 1):
        session.drag(Point(here.x + dx * step / steps, here.z + dz * step / steps), TOL)
    session.release(Point(here.x + dx, here.z + dz), TOL)


class FreeDragTests(unittest.TestCase):
    def test_the_dimension_is_what_fixes_the_points_on_the_line(self):
        self.assertTrue({7, 58, 61} <= analyse(_sketch(True)).fixed_points)
        self.assertFalse({7, 58, 61} & analyse(_sketch()).fixed_points)

    def test_the_points_on_the_free_line_follow_the_mouse_along_it(self):
        for point_id in ON_THE_65_DEGREE_LINE:
            for delta in ((1, 0), (0, 1), (-1, 0), (0, -1), (3, 0), (0, 3)):
                with self.subTest(point=point_id, delta=delta):
                    session = SketchSession(_sketch())
                    before = session.sketch.point(point_id).position
                    _drag(session, point_id, *delta)
                    after = session.sketch.point(point_id).position
                    self.assertGreater(before.distance_to(after), 0.3, "the point did not move")
                    self.assertTrue(solve(copy.deepcopy(session.sketch)).converged)  # all relations hold
                    kept = session.sketch.point(FREE_LINE_END).position.distance_to(session.sketch.point(1).position)
                    self.assertGreater(kept, 5, "the free line shrank")

    def test_a_point_that_is_fixed_stays(self):
        session = SketchSession(_sketch())
        before = session.sketch.point(5).position
        _drag(session, 5, 2, 0)
        self.assertLess(before.distance_to(session.sketch.point(5).position), 1e-6)

    def test_every_point_can_be_dragged_without_the_relations_breaking(self):
        for point_id in list(_sketch().points):
            for delta in ((1, 0), (0, 3)):
                with self.subTest(point=point_id, delta=delta):
                    session = SketchSession(_sketch())
                    if point_id in session.hidden_points():
                        continue
                    _drag(session, point_id, *delta)
                    self.assertTrue(solve(copy.deepcopy(session.sketch)).converged)

    def test_the_drag_is_one_undo_step(self):
        session = SketchSession(_sketch())
        before = {i: p.position for i, p in session.sketch.points.items()}
        _drag(session, 7, 1, 0)
        session.undo()
        self.assertEqual({i: p.position for i, p in session.sketch.points.items()}, before)


if __name__ == "__main__":
    unittest.main()
