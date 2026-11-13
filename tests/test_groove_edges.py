"""A chamfer or a fillet on the edge of a groove wall: the geometry, the moves, the order of the styles (requirement B3)."""

import math
import unittest

from wop.core.blocks.base import BlockError
from wop.core.blocks.groove_edges import EdgeKind, edge_moves, edge_pieces, edge_region
from wop.core.blocks.groove_style import (
    EDGE_HIGH, EDGE_LOW, EdgeCut, GrooveInput, GrooveStyleError, Plunge, check_plunges, edge_sizes, edges_first_plan, standard_plan, wall_steps,
)
from wop.core.constants import GROOVE_EDGE_RELIEF_MM
from wop.core.files.project_io import _block_from_data, _block_to_data
from wop.core.geometry import ArcSegment, LineSegment, Point
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid
from wop.ui.block_forms import form_for
from tests.test_blocks_grooving import block, context


def feeds(result):
    return [op for op in result.operations if isinstance(op, (LinearMove, ArcMove))]


class EdgeGeometryTests(unittest.TestCase):
    def test_a_chamfer_takes_a_triangle_and_a_fillet_the_rest_of_a_square(self):
        for sign, high, wall in ((1, True, -10), (1, False, -14), (-1, True, -10), (-1, False, -14)):
            self.assertAlmostEqual(edge_region(EdgeKind.CHAMFER, 1, high, 10, wall, sign).area, 0.5)
            self.assertAlmostEqual(edge_region(EdgeKind.FILLET, 1, high, 10, wall, sign).area, 1 - math.pi / 4, places=2)

    def test_no_edge_has_no_pieces_and_no_region(self):
        self.assertEqual(edge_pieces(EdgeKind.NONE, 1, True, 10, -10, 1), ())
        self.assertTrue(edge_region(EdgeKind.CHAMFER, 0, True, 10, -10, 1).is_empty)

    def test_the_edge_runs_from_the_surface_to_the_wall_beyond_the_wall(self):
        (line,) = edge_pieces(EdgeKind.CHAMFER, 1, True, 10, -10, 1)
        self.assertEqual((line.start, line.end), (Point(10, -9), Point(9, -10)))  # towards the face (higher Z) at the surface
        (low,) = edge_pieces(EdgeKind.CHAMFER, 1, False, 10, -14, 1)
        self.assertEqual((low.start, low.end), (Point(10, -15), Point(9, -14)))
        (inside,) = edge_pieces(EdgeKind.CHAMFER, 1, True, 10, -10, -1)  # a bore: the groove goes out, to a larger radius
        self.assertEqual(inside.end, Point(11, -10))

    def test_a_fillet_is_a_quarter_circle_tangent_to_the_wall_and_the_surface(self):
        (arc,) = edge_pieces(EdgeKind.FILLET, 2, True, 10, -10, 1)
        self.assertIsInstance(arc, ArcSegment)
        self.assertAlmostEqual(arc.sweep, math.pi / 2)
        self.assertEqual(arc.center, Point(8, -8))

    def test_a_chamfer_is_started_the_clearance_before_the_surface_on_its_line(self):
        moves = edge_moves(EdgeKind.CHAMFER, 1, True, 10, -10, 1, 1)
        self.assertEqual(moves.lead, Point(11, -8))
        self.assertEqual(moves.pieces[0].end, Point(9, -10))
        fillet = edge_moves(EdgeKind.FILLET, 1, True, 10, -10, 1, 1)
        self.assertEqual(fillet.lead, Point(11, -9))
        self.assertIsInstance(fillet.pieces[0], LineSegment)
        self.assertIsInstance(fillet.pieces[1], ArcSegment)


class EdgeBlockTests(unittest.TestCase):
    def removed(self, **overrides):
        values = dict(start_z_mm=-10, width_mm=3, bottom_radius_mm=12)
        values.update(overrides)
        return block(**values).generate(context())

    def test_an_edge_takes_its_part_off_the_material(self):
        plain = self.removed().removed.area
        self.assertAlmostEqual(self.removed(right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1).removed.area - plain, 0.5, places=1)
        self.assertAlmostEqual(self.removed(left_edge_kind=EdgeKind.CHAMFER, left_edge_mm=1).removed.area - plain, 0.5, places=1)
        both = self.removed(right_edge_kind=EdgeKind.FILLET, right_edge_mm=1, left_edge_kind=EdgeKind.FILLET, left_edge_mm=1)
        self.assertAlmostEqual(both.removed.area - plain, 2 * (1 - math.pi / 4), places=1)
        self.assertEqual(both.messages, ())

    def test_the_right_chamfer_is_cut_with_the_right_corner_along_a_diagonal(self):
        result = self.removed(right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1)
        diagonal = [op for op in feeds(result) if op.end.x == 14.0 and op.end.z == -13]  # corner at (14, -10), blade 3 wide: tip at -13
        self.assertEqual(len(diagonal), 1)

    def test_a_fillet_is_an_arc_move(self):
        result = self.removed(right_edge_kind=EdgeKind.FILLET, right_edge_mm=1)
        arcs = [op for op in feeds(result) if isinstance(op, ArcMove)]
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0].end, Point(14.0, -13))

    def test_no_edge_changes_nothing(self):
        self.assertEqual(self.removed(right_edge_kind=EdgeKind.NONE, right_edge_mm=3).operations, self.removed().operations)

    def test_the_outline_follows_the_edges(self):
        outline = block(start_z_mm=-10, width_mm=3, bottom_radius_mm=12, right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1,
                        left_edge_kind=EdgeKind.FILLET, left_edge_mm=1).target_outline(context())
        for a, b in zip(outline, outline[1:]):
            self.assertAlmostEqual(a.end.distance_to(b.start), 0)  # one connected line
        self.assertEqual(outline[0].start, Point(15, -9))
        self.assertEqual(outline[-1].end, Point(15, -14))

    def test_an_edge_must_have_a_size_and_be_smaller_than_the_groove_is_deep(self):
        with self.assertRaises(BlockError):
            block(right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=0)
        with self.assertRaises(BlockError):
            self.removed(bottom_radius_mm=14.5, right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1)

    def test_the_edges_are_in_the_form_and_greyed_without_a_kind(self):
        specs = {spec.path[0]: spec for spec in form_for(block())}
        self.assertEqual(specs["right_edge_kind"].label, "Right edge (face side)")
        self.assertFalse(specs["right_edge_mm"].enabled)
        edged = {spec.path[0]: spec for spec in form_for(block(right_edge_kind=EdgeKind.CHAMFER))}
        self.assertTrue(edged["right_edge_mm"].enabled)

    def test_the_edges_are_saved_and_an_old_block_gets_none(self):
        edged = block(right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=0.8, left_edge_kind=EdgeKind.FILLET, left_edge_mm=0.4)
        data = _block_to_data(edged)
        self.assertEqual(_block_from_data(data), edged)
        for name in ("left_edge_kind", "left_edge_mm", "right_edge_kind", "right_edge_mm"):
            data["parameters"].pop(name, None)
        self.assertEqual(_block_from_data(data).right_edge_kind, EdgeKind.NONE)


class EdgeStyleTests(unittest.TestCase):
    def through(self, style, **overrides):
        values = dict(start_z_mm=-10, width_mm=3, bottom_radius_mm=0, right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1, style=style)
        values.update(overrides)
        return block(**values)

    def moves(self, style, **overrides):
        """The cutting moves in the order they are made: 'edge' for the end of the diagonal, else the radius the blade goes to."""
        steps = []
        for op in feeds(self.through(style, **overrides).generate(context())):
            steps.append("edge" if (op.end.x, op.end.z) == (14.0, -13) else round(op.end.x, 3))
        return steps

    def test_the_edges_first_style_cuts_the_edge_and_the_wall_in_one_move_while_the_part_is_held(self):
        relief = 15 - 1 - GROOVE_EDGE_RELIEF_MM
        order = self.moves("edges_first")
        self.assertEqual(order[:3], [relief, "edge", 0.0])
        ops = [op for op in self.through("edges_first").generate(context()).operations if isinstance(op, (LinearMove, ArcMove, Rapid))]
        at = next(i for i, op in enumerate(ops) if isinstance(op, LinearMove) and (op.end.x, op.end.z) == (14.0, -13))
        self.assertIsInstance(ops[at + 1], LinearMove)  # straight on down the wall: no retract between the edge and the wall
        self.assertEqual((ops[at + 1].end.x, ops[at + 1].end.z), (0.0, -13))

    def test_the_wall_of_the_part_is_cut_first_so_the_part_comes_off_at_its_length(self):
        for style in ("standard", "edges_first", "layers"):
            result = self.through(style, right_edge_kind=EdgeKind.NONE, width_mm=6).generate(context())
            full_depth = [op for op in feeds(result) if op.end.x == 0.0]
            self.assertEqual(full_depth[0].end.z, -10 - 3, style)  # the blade at the wall of the part: its right side at Z -10

    def test_the_other_styles_cut_the_edge_after_the_cut_off_and_say_so(self):
        order = self.moves("standard")
        self.assertLess(order.index(0.0), order.index("edge"))
        self.assertTrue(any("part is off" in m and "Edges before full depth" in m for m in self.through("standard").generate(context()).messages))
        self.assertFalse(any("part is off" in m for m in self.through("edges_first").generate(context()).messages))

    def test_a_groove_with_a_floor_is_not_a_cut_off(self):
        floor = block(start_z_mm=-10, width_mm=3, bottom_radius_mm=10, right_edge_kind=EdgeKind.CHAMFER, right_edge_mm=1)
        self.assertFalse(any("part is off" in m for m in floor.generate(context()).messages))

    def test_the_edge_style_is_the_standard_style_without_an_edge(self):
        plain = block(start_z_mm=-10, width_mm=3, bottom_radius_mm=0)
        first = block(start_z_mm=-10, width_mm=3, bottom_radius_mm=0, style="edges_first")
        self.assertEqual(plain.generate(context()).operations, first.generate(context()).operations)

    def test_the_wall_of_an_edge_keeps_a_skin_that_the_edge_move_takes(self):
        wide = self.through("edges_first", width_mm=6)
        first_relief = next(op for op in feeds(wide.generate(context())))
        self.assertEqual(first_relief.end.z, -10 - 0.2 - 3)  # the roughing stays GROOVE_EDGE_SKIN_MM away from the wall of the part
        self.assertAlmostEqual(wide.generate(context()).removed.area, 6 * 15 + 0.5, places=1)  # but all of it is cut in the end

    def test_the_move_down_the_wall_after_the_corner_keeps_the_peck_depth(self):
        from wop.core.blocks.grooving import GroovePeckMode

        for mode in GroovePeckMode:
            result = self.through("edges_first", peck_depth_mm=4, peck_mode=mode).generate(context())
            ops = result.operations
            at = next(i for i, op in enumerate(ops) if isinstance(op, LinearMove) and (op.end.x, op.end.z) == (14.0, -13))
            down = []
            for op in ops[at + 1:]:
                if isinstance(op, LinearMove) and op.end.z == -13:
                    down.append(op.end.x)
                if isinstance(op, Rapid) and op.end.z != -13:
                    break
            starts = [14.0] + down[:-1]
            self.assertEqual(down[-1], 0.0, mode)
            self.assertTrue(all(start - end <= 4 + 1e-9 for start, end in zip(starts, down)), (mode, down))  # no peck deeper than the form says
            self.assertGreater(len(down), 1)
            between = ops[at + 2: at + 4]
            self.assertTrue(all(isinstance(op, Rapid) for op in between), mode)  # a retract between two pecks

    def test_a_large_edge_is_cut_in_passes_of_at_most_the_one_sided_cut(self):
        self.assertEqual(edge_sizes(0.5, 1.0), [0.5])
        self.assertEqual(edge_sizes(2.5, 1.0), [2.5 / 3, 5 / 3, 2.5])
        self.assertEqual(edge_sizes(2.0, 1.0), [1.0, 2.0])
        big = self.through("edges_first", right_edge_mm=2.5, one_sided_cut_value=1.0)
        result = big.generate(context())
        diagonals = [op for op in feeds(result) if abs(op.end.z + 13) < 1e-9 and op.end.x not in (0.0,) and 11 < op.end.x < 15]
        self.assertEqual([round(op.end.x, 3) for op in diagonals], [round(15 - size, 3) for size in edge_sizes(2.5, 1.0)])
        self.assertAlmostEqual(result.removed.area - self.through("edges_first", right_edge_kind=EdgeKind.NONE).generate(context()).removed.area, 2.5 ** 2 / 2, places=1)

    def test_a_wall_step_list_puts_the_small_passes_before_the_one_move_with_the_wall(self):
        groove = GrooveInput(
            blade_mm=3, wall_low_z=-13, wall_high_z=-10, rough_low_z=-13, rough_high_z=-10, surface_radius=15, rough_bottom_radius=0,
            final_radius=0, one_sided_mm=1, peck_depth_mm=None, finishing=False, finish_stop_early_mm=0.2, edge_high_mm=2.5,
        )
        steps = wall_steps(groove)
        self.assertEqual([type(step).__name__ for step in steps], ["EdgeCut", "EdgeCut", "Plunge"])
        self.assertEqual(steps[-1].edge, EDGE_HIGH)
        self.assertEqual(steps[-1].z, -13)

    def test_every_wall_is_final_before_its_edge_is_cut_when_there_is_a_finishing_pass(self):
        groove = GrooveInput(
            blade_mm=3, wall_low_z=-13, wall_high_z=-10, rough_low_z=-12.8, rough_high_z=-10.2, surface_radius=15, rough_bottom_radius=0.2,
            final_radius=0, one_sided_mm=1, peck_depth_mm=None, finishing=True, finish_stop_early_mm=0.2, edge_high_mm=1, relief_radius=13.5,
        )
        steps = standard_plan(groove)
        plunges = [s for s in steps if isinstance(s, Plunge)]
        self.assertTrue(plunges[-1].finishing)
        self.assertEqual(plunges[-1].edge, EDGE_HIGH)  # the finishing plunge of that wall is the one that cuts the edge
        self.assertTrue(all(p.radius == 0.2 for p in plunges[:-1]) or any(p.finishing for p in plunges[:-1]))
        self.assertTrue(isinstance(edges_first_plan(groove)[0], Plunge))

    def test_an_edge_cut_for_a_wall_without_an_edge_is_refused(self):
        groove = GrooveInput(
            blade_mm=3, wall_low_z=-13, wall_high_z=-10, rough_low_z=-13, rough_high_z=-10, surface_radius=15, rough_bottom_radius=0,
            final_radius=0, one_sided_mm=1, peck_depth_mm=None, finishing=False, finish_stop_early_mm=0.2, edge_high_mm=1,
        )
        check_plunges(groove, [Plunge(-13, 5), EdgeCut(EDGE_HIGH)], "test")
        check_plunges(groove, [Plunge(-13, 0, finishing=True, edge=EDGE_HIGH)], "test")
        with self.assertRaises(GrooveStyleError):
            check_plunges(groove, [Plunge(-13, 5), EdgeCut(EDGE_LOW)], "test")
        with self.assertRaises(GrooveStyleError):
            check_plunges(groove, [Plunge(-12, 0, finishing=True, edge=EDGE_HIGH)], "test")  # not at the wall of the edge
        with self.assertRaises(GrooveStyleError):
            check_plunges(groove, [EdgeCut(EDGE_HIGH, 5)], "test")  # larger than the edge


if __name__ == "__main__":
    unittest.main()
