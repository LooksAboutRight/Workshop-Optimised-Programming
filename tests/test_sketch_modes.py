import json
import unittest

from wop.core.contour import Contour, NamedPoint
from wop.core.files.contour_io import contour_from_dict, contour_to_dict
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point
from wop.core.sketch.modes import (
    FREE,
    TOOL,
    TURNING,
    WORKHOLDING,
    contour_from_sketch,
    problems,
    sketch_from_contour,
)
from wop.core.sketch.model import Sketch, SketchError
from wop.core.sketch.sketch_io import sketch_from_dict, sketch_to_dict
from wop.core.sketch.solver import solve
from wop.core.tooling.tool import Tool, ToolSegmentRole
from wop.core.files.tool_io import tool_from_dict, tool_to_dict
from wop.core.tooling.tool_shape import tool_from_contour


def _open_profile() -> Sketch:
    sketch = Sketch()
    a, b, c = sketch.add_point(5, 0), sketch.add_point(5, -20), sketch.add_point(10, -30)
    sketch.add_line(a, b)
    sketch.add_line(b, c)
    return sketch


def _closed_box(low: float = 0) -> Sketch:
    sketch = Sketch()
    corners = [sketch.add_point(x, z) for x, z in ((low, 0), (low + 4, 0), (low + 4, -10), (low, -10))]
    for i in range(4):
        sketch.add_line(corners[i], corners[(i + 1) % 4])
    return sketch


class IoTests(unittest.TestCase):
    def test_a_sketch_survives_json(self):
        sketch = Sketch()
        centre, start, end = sketch.add_point(0, 0), sketch.add_point(5, 0), sketch.add_point(0, 5)
        arc = sketch.add_arc(centre, start, end, ArcDirection.CW, cutting=True)
        tail = sketch.add_point(9, 9)
        sketch.add_line(end, tail, construction=True)
        sketch.add_constraint("radius", (arc,), (5,))
        sketch.add_constraint("fixed", (centre,), (0, 0))
        sketch.label_point(tail, "tip")
        again = sketch_from_dict(json.loads(json.dumps(sketch_to_dict(sketch))))
        self.assertEqual(again.signature(), sketch.signature())
        self.assertEqual(again.arcs[arc], sketch.arcs[arc])
        self.assertEqual(again.labels, {"tip": tail})
        self.assertEqual(again.add_point(1, 1), sketch.add_point(1, 1))  # new ids go on from the same number
        self.assertTrue(solve(again).converged)

    def test_broken_data_is_an_error_not_a_crash(self):
        with self.assertRaises(SketchError):
            sketch_from_dict({"format": 1})
        with self.assertRaises(SketchError):
            sketch_from_dict({"format": 99})


class ProblemTests(unittest.TestCase):
    def test_free_sketch_has_no_problems(self):
        self.assertEqual(problems(Sketch(), FREE), [])

    def test_turning_contour_wants_one_open_chain_above_the_axis(self):
        self.assertEqual(problems(_open_profile(), TURNING), [])
        self.assertIn("Draw the outline first", problems(Sketch(), TURNING)[0])
        self.assertTrue(any("open" in p for p in problems(_closed_box(), TURNING)))
        below = Sketch()
        below.add_line(below.add_point(5, 0), below.add_point(-3, -10))
        self.assertTrue(any("below the spindle axis" in p for p in problems(below, TURNING)))

    def test_two_separate_outlines_are_a_problem(self):
        sketch = _open_profile()
        sketch.add_line(sketch.add_point(30, 0), sketch.add_point(30, -5))
        self.assertTrue(any("separate parts" in p for p in problems(sketch, TURNING)))

    def test_tool_and_workholding_want_a_closed_outline(self):
        self.assertEqual(problems(_closed_box(), TOOL), [])
        self.assertEqual(problems(_closed_box(-2), WORKHOLDING), [])  # below the axis is fine here
        self.assertTrue(any("not closed" in p for p in problems(_open_profile(), TOOL)))

    def test_an_outline_that_crosses_or_touches_itself_is_a_problem(self):
        crossing = Sketch()
        points = [crossing.add_point(x, z) for x, z in ((5, 0), (5, -20), (8, -20), (8, -10), (3, -10))]
        for first, second in zip(points, points[1:]):
            crossing.add_line(first, second)
        self.assertTrue(any("crosses or touches itself" in p for p in problems(crossing, TURNING)))
        touching = Sketch()
        points = [touching.add_point(x, z) for x, z in ((5, 0), (5, -20), (8, -20), (8, -10), (5, -10))]
        for first, second in zip(points, points[1:]):
            touching.add_line(first, second)
        self.assertTrue(any("crosses or touches itself" in p for p in problems(touching, TURNING)))
        self.assertFalse(any("itself" in p for p in problems(_open_profile(), TURNING)))
        self.assertFalse(any("itself" in p for p in problems(_closed_box(), TOOL)))

    def test_construction_pieces_do_not_count(self):
        sketch = _open_profile()
        sketch.add_line(sketch.add_point(30, 0), sketch.add_point(30, -5), construction=True)
        self.assertEqual(problems(sketch, TURNING), [])


class ContourTests(unittest.TestCase):
    def test_turning_contour_from_a_sketch_keeps_the_sketch(self):
        contour = contour_from_sketch(_open_profile(), TURNING, "contour1", "Part")
        self.assertTrue(contour.is_valid)
        self.assertEqual(len(contour.segments), 2)
        self.assertFalse(contour.is_closed)
        self.assertTrue(contour.segments[0].start.is_close(Point(5, 0)))
        again = contour_from_dict(json.loads(json.dumps(contour_to_dict(contour))))
        self.assertEqual(again.sketch, contour.sketch)
        self.assertEqual(sketch_from_contour(again).signature(), sketch_from_dict(contour.sketch).signature())

    def test_a_turning_contour_starts_at_its_highest_z_whichever_way_it_was_drawn(self):
        sketch = Sketch()
        a, b, c = sketch.add_point(10, -30), sketch.add_point(5, -20), sketch.add_point(5, 0)  # drawn from the chuck end
        sketch.add_line(a, b)
        sketch.add_line(b, c)
        contour = contour_from_sketch(sketch, TURNING, "c", "n")
        self.assertTrue(contour.segments[0].start.is_close(Point(5, 0)))
        self.assertTrue(contour.segments[-1].end.is_close(Point(10, -30)))
        for before, after in zip(contour.segments, contour.segments[1:]):
            self.assertTrue(before.end.is_close(after.start))
        self.assertEqual(sketch_from_contour(contour).signature(), sketch_from_dict(contour.sketch).signature())  # the sketch is still its own

    def test_the_drawing_order_decides_the_direction_of_a_closed_or_free_outline(self):
        sketch = _closed_box()
        contour = contour_from_sketch(sketch, WORKHOLDING, "c", "n")
        self.assertTrue(contour.segments[0].start.is_close(Point(0, 0)))

    def test_bad_sketch_raises_with_the_reasons(self):
        with self.assertRaises(SketchError) as caught:
            contour_from_sketch(_closed_box(), TURNING, "c", "n")
        self.assertIn("open", str(caught.exception))
        with self.assertRaises(SketchError):
            contour_from_sketch(Sketch(), FREE, "c", "n")

    def test_tool_contour_has_cutting_flags_and_named_points(self):
        sketch = _closed_box()
        first = min(sketch.lines)
        sketch.update_piece(first, cutting=True)
        tip = min(sketch.points)
        sketch.label_point(tip, "tip")
        contour = contour_from_sketch(sketch, TOOL, "tool_shape", "T1")
        self.assertTrue(contour.is_closed)
        self.assertEqual(sum(contour.cutting), 1)
        self.assertEqual(contour.points, (NamedPoint("tip", 0, 0),))
        tool = tool_from_contour(Tool(1, "T1", _any_shape()), contour)
        roles = [piece.role for piece in tool.shape.pieces]
        self.assertEqual(roles.count(ToolSegmentRole.CUTTER), 1)
        self.assertEqual(tool.points[0].name, "tip")

    def test_workholding_has_no_cutting_flags(self):
        sketch = _closed_box()
        sketch.update_piece(min(sketch.lines), cutting=True)
        self.assertEqual(contour_from_sketch(sketch, WORKHOLDING, "w", "Jaws").cutting, ())

    def test_contour_without_a_sketch_becomes_one(self):
        segments = (
            LineSegment(Point(5, 0), Point(5, -10)),
            ArcSegment(Point(5, -10), Point(10, -15), Point(10, -10), ArcDirection.CW),
            LineSegment(Point(10, -15), Point(10, -30)),
        )
        contour = Contour("c", "Old", segments, cutting=(False, True, False), points=(NamedPoint("tip", 5, 0),))
        sketch = sketch_from_contour(contour)
        self.assertEqual(len(sketch.points), 5)  # 4 ends, shared, and the arc centre
        self.assertEqual(len(sketch.lines), 2)
        self.assertEqual(len(sketch.arcs), 1)
        self.assertTrue(next(iter(sketch.arcs.values())).cutting)
        self.assertEqual(sketch.labels["tip"], min(sketch.points))
        back = contour_from_sketch(sketch, TURNING, "c", "Old")
        self.assertEqual(back.segments, segments)

    def test_full_circle_contour(self):
        circle = ArcSegment(Point(0, 5), Point(0, 5), Point(0, 0), ArcDirection.CCW)
        sketch = sketch_from_contour(Contour("c", "Hole", (circle,)))
        self.assertEqual(len(sketch.points), 2)
        again = contour_from_sketch(sketch, WORKHOLDING, "c", "Hole")
        self.assertTrue(again.is_closed)
        self.assertTrue(again.segments[0].is_full_circle)


class ToolSketchTests(unittest.TestCase):
    def test_tool_keeps_its_sketch_in_the_file(self):
        contour = contour_from_sketch(_closed_box(), TOOL, "tool_shape", "T1")
        tool = tool_from_contour(Tool(1, "T1", _any_shape()), contour)
        self.assertIsNotNone(tool.sketch)
        again = tool_from_dict(json.loads(json.dumps(tool_to_dict(tool))))
        self.assertEqual(again.sketch, tool.sketch)


def _any_shape():
    from wop.core.tooling.tool import ToolSegment, ToolShape

    box = _closed_box()
    contour = contour_from_sketch(box, TOOL, "x", "x")
    return ToolShape(tuple(ToolSegment(s, ToolSegmentRole.HOLDER) for s in contour.segments))


if __name__ == "__main__":
    unittest.main()
