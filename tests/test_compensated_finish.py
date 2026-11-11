"""The finishing pass with cutter compensation: lead-in, lead-out and the contour point on every move (turning blocks)."""

import unittest
from pathlib import Path

from tests.test_rough_follow import SPINDLE, block, generate, holder_cnmg, path_of
from wop.core.contour import ArcCenterStep, Contour, ContourDefinition, LineStep
from wop.core.contour_solver import solve_contour
from wop.core.geometry import ArcDirection, LineSegment, Point
from wop.core.nose_compensation import reference_path
from wop.core.program_model.operations import ArcMove, CompensationSide, LinearMove, MoveRole, Rapid
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.turning import TurningBlock
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.program_model.stock import stock_region

SHAPE = [(10, 0), (14, -3), (14, -20)]  # a chamfer at the front, a cylinder
STEPPED = [(8, 0), (8, -10), (14, -16), (14, -30)]  # a slope that makes an outer corner at its upper end
RAW = RawPart("steel", 40, 60)


def finishing(shape=SHAPE, **overrides):
    result, _shape = generate(shape, holder_cnmg(), RAW, finish_pass=True, cutter_compensation=True, **overrides)
    return result


def moves_with(operations, role):
    return [op for op in operations if getattr(op, "role", None) is role]


def between_lead_in_and_lead_out(operations):
    first = next(i for i, op in enumerate(operations) if getattr(op, "role", None) is MoveRole.LEAD_IN)
    last = next(i for i, op in enumerate(operations) if getattr(op, "role", None) is MoveRole.LEAD_OUT)
    return operations[first:last]


class CompensatedPassTests(unittest.TestCase):
    def test_without_the_checkbox_nothing_is_marked(self):
        result, _shape = generate(SHAPE, holder_cnmg(), RAW, finish_pass=True, cutter_compensation=False)
        for op in result.operations:
            self.assertIs(getattr(op, "role", MoveRole.NORMAL), MoveRole.NORMAL)
            self.assertIsNone(getattr(op, "contour_end", None))

    def test_without_a_finishing_pass_the_checkbox_does_nothing(self):
        result, _shape = generate(SHAPE, holder_cnmg(), RAW, finish_pass=False, cutter_compensation=True)
        self.assertEqual(moves_with(result.operations, MoveRole.LEAD_IN), [])
        self.assertEqual(moves_with(result.operations, MoveRole.LEAD_OUT), [])

    def test_one_lead_in_first_and_one_lead_out_last(self):
        operations = finishing().operations
        lead_in, lead_out = moves_with(operations, MoveRole.LEAD_IN), moves_with(operations, MoveRole.LEAD_OUT)
        self.assertEqual((len(lead_in), len(lead_out)), (1, 1))
        self.assertLess(operations.index(lead_in[0]), operations.index(lead_out[0]))
        self.assertEqual(lead_in[0].side, CompensationSide.RIGHT)  # an outside tool: the free side is on the right when travelling to the chuck

    def test_the_lead_in_starts_on_the_extension_of_the_first_piece_a_nose_radius_plus_a_margin_away(self):
        from wop.core.constants import COMPENSATION_LEAD_MARGIN_MM
        from wop.core.tooling.tool_reference import nose_circle

        operations = finishing().operations
        lead_in = moves_with(operations, MoveRole.LEAD_IN)[0]
        before = operations[operations.index(lead_in) - 1]
        radius, _centre = nose_circle(holder_cnmg())
        contour_start = Point(*SHAPE[0])
        self.assertAlmostEqual(before.end.distance_to(contour_start), radius + COMPENSATION_LEAD_MARGIN_MM, places=6)
        self.assertTrue(lead_in.contour_end.is_close(contour_start))
        chamfer = LineSegment(contour_start, Point(*SHAPE[1]))  # on the straight line through the first piece, in front of it
        cross = (before.end.x - chamfer.start.x) * (chamfer.end.z - chamfer.start.z) - (before.end.z - chamfer.start.z) * (chamfer.end.x - chamfer.start.x)
        self.assertAlmostEqual(cross, 0, places=6)
        self.assertGreater(before.end.z, chamfer.start.z)

    def test_the_tool_path_is_the_one_of_the_nose_offset(self):
        pieces = reference_path(path_of(*SHAPE), holder_cnmg(), True)
        ends = [op.end for op in between_lead_in_and_lead_out(finishing().operations)]
        self.assertGreaterEqual(len(ends), len(pieces) + 1)  # the lead-in, then the pieces (the block adds a last piece up to the stock)
        self.assertTrue(ends[0].is_close(pieces[0][1].start))  # the lead-in goes to the start of the first piece
        for got, (_index, want) in zip(ends[1:], pieces[:-1]):  # the last piece of the shape is cut back by the piece the block adds
            self.assertTrue(got.is_close(want.end), (got, want.end))

    def test_every_piece_of_the_contour_has_its_contour_point_and_the_corner_arc_has_none(self):
        operations = finishing(STEPPED).operations
        path = path_of(*STEPPED)
        inside = between_lead_in_and_lead_out(operations)[1:]
        contour_ends = [op.contour_end for op in inside if op.role is MoveRole.NORMAL]
        self.assertEqual(contour_ends[:len(path)], [segment.end for segment in path])  # then the piece up to the stock
        joins = moves_with(operations, MoveRole.JOIN)
        self.assertEqual(len(joins), 1)
        self.assertIsInstance(joins[0], ArcMove)
        self.assertIsNone(joins[0].contour_end)

    def test_a_contour_arc_carries_the_centre_of_the_contour(self):
        definition = ContourDefinition(Point(10, 0), (LineStep(Point(10, -10)), ArcCenterStep(Point(14, -14), Point(14, -10), ArcDirection.CCW)))
        shape = Contour("c", "t", tuple(solve_contour(definition)), definition)
        context = BlockContext(RAW, holder_cnmg(), stock_region(RAW), Safety(30, 10, 1), contours=(shape,))
        operations = block(finish_pass=True, cutter_compensation=True).generate(context).operations
        arcs = [op for op in between_lead_in_and_lead_out(operations) if isinstance(op, ArcMove) and op.role is MoveRole.NORMAL]
        self.assertEqual(len(arcs), 1)
        self.assertTrue(arcs[0].contour_center.is_close(Point(14, -10)))
        self.assertTrue(arcs[0].contour_end.is_close(Point(14, -14)))

    def test_the_lead_out_goes_out_radially_from_the_end_of_the_path(self):
        operations = finishing().operations
        lead_out = moves_with(operations, MoveRole.LEAD_OUT)[0]
        before = operations[operations.index(lead_out) - 1]
        self.assertAlmostEqual(lead_out.end.z, before.end.z)
        self.assertAlmostEqual(lead_out.end.x - before.end.x, 0.8 + 1.0, places=6)  # the nose radius plus the margin
        self.assertIsNone(lead_out.contour_end)

    def test_both_turning_blocks_have_the_checkbox_under_the_finishing_pass(self):
        for example in (TurningBlock.example("t1", 1, SPINDLE), ContourTurningBlock.example("t2", 1, SPINDLE)):
            fields = example.form_fields()
            with self.subTest(block=example.type_name):
                self.assertEqual(fields[fields.index("finish_spindle_value") + 1], "cutter_compensation")
                self.assertNotIn("cutter_compensation", example.form_disabled())

    def test_the_checkbox_is_greyed_out_without_the_finishing_pass(self):
        self.assertIn("cutter_compensation", block(finish_pass=False).form_disabled())


class ThroughThePostTests(unittest.TestCase):
    def test_a_post_with_compensation_writes_the_contour_and_the_codes_and_one_without_writes_the_path(self):
        from wop.core.program_model.units import XInputMode
        from wop.post.base import PostSettings
        from wop.post.engine import TemplatePost
        from wop.post.post_definition import parse_post

        text = (Path(__file__).parent / "data" / "posts" / "fake_comp.post.ini").read_text(encoding="utf-8")
        operations = finishing(STEPPED).operations
        outputs = {}
        for compensation in ("yes", "no"):
            post = TemplatePost(parse_post(text.replace("cutter_compensation = yes", f"cutter_compensation = {compensation}"), "c"))
            post.header(PostSettings(XInputMode.RADIUS), [])
            lines, position = [], None
            for op in operations:
                if isinstance(op, Rapid):
                    lines += post.rapid(op)
                elif isinstance(op, ArcMove):
                    lines += post.arc(op, position.x, position.z)
                elif isinstance(op, LinearMove):
                    lines += post.linear(op)
                position = getattr(op, "end", position)
            outputs[compensation] = lines
        yes, no = outputs["yes"], outputs["no"]
        self.assertTrue(any(line.startswith("Q42 ") for line in yes))
        self.assertTrue(any(line.startswith("Q40 ") for line in yes))
        self.assertFalse(any("Q4" in line for line in no))
        self.assertIn("Q42 Q1 X8 Z0", yes)  # the first point of the contour
        self.assertEqual(len(yes), len(no) - 1)  # the join arc is not written


if __name__ == "__main__":
    unittest.main()
