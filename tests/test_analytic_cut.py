"""The first cut of the analytic planner: the planning tool, the penetration test, the removal and step B (reach, ride up).

Where an area is compared, the referee is the `Region` of the program (`region_of_loops`).
"""

import unittest
from pathlib import Path

from tests.helpers import planned
from wop.core.geometry import ArcSegment, LineSegment, Point

from wop.core.geometry.chains import loop_area, oriented, polygon_loop, region_of_loops
from wop.core.analytic.cut_list import Cut, CutKind
from wop.core.analytic.rapids import RapidTool, _leaving, _way
from wop.core.analytic.wanted_lines import WantedLine
from wop.core.geometry.penetration import NO_EDGE, RegionIndex, blocked_by_material, blocked_by_part, penetrations
from wop.core.analytic.reach import keep_loops
from wop.core.geometry.removal import cut, strips
from wop.core.analytic.tool_outline import back_sides, planning_loops, tool_loops
from wop.core.geometry.tool_edges import ToolEdge
from wop.core.blocks.base import BlockContext
from wop.core.constants import CHAIN_SNAP_MM, CUT_END_SNAP_MM
from wop.core.files.project_io import project_from_json

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "left_hand_rest_machining.wop.json"
TOLERANCE = CHAIN_SNAP_MM


def box_loop(x0, z0, x1, z1):
    return oriented(polygon_loop([Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1)]), True)


def tool_square(size, cutting=True):
    """A square tool with its tip at the origin (its lower left corner); `cutting` says which edges cut (all, or a list of four)."""
    flags = [cutting] * 4 if isinstance(cutting, bool) else list(cutting)
    corners = [Point(0, 0), Point(size, 0), Point(size, size), Point(0, size)]
    return [tuple(ToolEdge(LineSegment(a, b), flag) for a, b, flag in zip(corners, corners[1:] + corners[:1], flags))]


class PenetrationTests(unittest.TestCase):
    def setUp(self):
        self.region = RegionIndex([box_loop(0, 0, 10, 10)])

    def test_a_tool_outside_does_not_penetrate_and_one_that_touches_does_not_either(self):
        tool = tool_square(2)
        self.assertEqual(penetrations(tool, self.region, Point(20, 20), TOLERANCE), [])
        self.assertEqual(penetrations(tool, self.region, Point(10, 0), TOLERANCE), [])  # shares the edge x = 10
        self.assertEqual(penetrations(tool, self.region, Point(10 + TOLERANCE / 2, 5), TOLERANCE), [])

    def test_the_edges_that_go_in_are_named_and_marked(self):
        tool = tool_square(2, [True, False, True, False])  # edges 0 and 2 cut (the ones along x), 1 and 3 do not
        found = penetrations(tool, self.region, Point(9, 4), TOLERANCE)  # the left part of the tool is inside
        self.assertTrue(found)
        self.assertTrue({p.edge for p in found} >= {0, 2, 3})
        self.assertTrue(all(p.cutting == (p.edge in (0, 2)) for p in found if p.edge != NO_EDGE))
        self.assertTrue(blocked_by_part(tool, self.region, Point(9, 4)))
        self.assertTrue(blocked_by_material(tool, self.region, Point(9, 4)))  # the edge that does not cut is in the material

    def test_a_cutting_edge_may_be_in_material_when_no_other_edge_is(self):
        tool = tool_square(2, [False, False, False, True])  # only the edge at z = size cuts; the tool tip is at the corner (0, 0)
        # the whole tool except nothing: put the tool so that only its upper edge (z = 2) is inside a thin region
        thin = RegionIndex([box_loop(-5, 1.5, 5, 3)])
        found = penetrations(tool, thin, Point(0, 0), TOLERANCE)
        self.assertTrue(found)
        self.assertTrue(any(p.cutting for p in found))

    def test_a_tool_completely_inside_and_a_region_completely_inside_the_tool(self):
        self.assertTrue(blocked_by_part(tool_square(2), self.region, Point(4, 4)))  # inside
        small = RegionIndex([box_loop(1, 1, 1.5, 1.5)])
        found = penetrations(tool_square(4), small, Point(0, 0), TOLERANCE)  # the region is inside the tool
        self.assertTrue(any(p.edge == NO_EDGE for p in found))


class RemovalTests(unittest.TestCase):
    def test_a_square_tool_moved_through_material_removes_what_it_sweeps(self):
        material = [box_loop(-20, -20, 20, 20)]
        tool = tool_square(2)
        path = [LineSegment(Point(0, 0), Point(0, 5))]
        left, taken = cut(material, tool, path, TOLERANCE)
        removed = region_of_loops(material).difference(region_of_loops(left)).area
        self.assertAlmostEqual(removed, 2 * 7, places=3)  # width 2, length 5 + the tool length 2
        self.assertAlmostEqual(sum(loop_area(loop) for loop in taken), 2 * 7, places=3)  # width 2, length 5 + the tool length 2

    def test_an_edge_that_does_not_cut_removes_nothing(self):
        material = [box_loop(-20, -20, 20, 20)]
        left, taken = cut(material, tool_square(2, False), [LineSegment(Point(0, 0), Point(0, 5))], TOLERANCE)
        self.assertAlmostEqual(sum(loop_area(loop) for loop in left), 1600, places=6)
        self.assertEqual(taken, [])

    def test_a_move_along_an_edge_draws_no_strip_for_it(self):
        self.assertEqual(len(strips(tool_square(2), Point(0, 0), (0, 5))), 2)  # the two edges across the move; the two along it draw nothing

    def test_the_nose_arc_of_a_real_tool_is_swept_exactly(self):
        project = project_from_json(EXAMPLE.read_text(encoding="utf-8"))
        tool = tool_loops(project.program.equipped_tool(4))
        loops = strips(tool, Point(0, 0), (0, -10))
        self.assertTrue(any(isinstance(piece, ArcSegment) for loop in loops for piece in loop))  # an arc strip: the arc, its copy and the two joining lines


class PlanningToolTests(unittest.TestCase):
    def setUp(self):
        self.project = project_from_json(EXAMPLE.read_text(encoding="utf-8"))

    def test_the_sides_come_from_the_shape(self):
        program = self.project.program
        self.assertEqual(back_sides(program.equipped_tool(4), 1), (1, -1))  # a symmetric V insert: neutral
        self.assertEqual(len(back_sides(program.equipped_tool(5), 1)), 1)  # a turning tool has one back side

    def test_the_planning_copy_has_the_back_edge_turned_and_stays_closed(self):
        tool = self.project.program.equipped_tool(4)
        real, copy = tool_loops(tool)[0], planning_loops(tool, 1, 5)[0]
        self.assertEqual(len(copy), len(real) + 2)  # one connecting edge for each of the two back edges
        for index, edge in enumerate(copy):
            self.assertTrue(edge.segment.end.is_close(copy[(index + 1) % len(copy)].segment.start))
        self.assertGreater(abs(loop_area(tuple(e.segment for e in copy))), abs(loop_area(tuple(e.segment for e in real))))  # the wedge adds area

    def test_no_clearance_leaves_the_tool_as_it_is(self):
        tool = self.project.program.equipped_tool(4)
        self.assertEqual(planning_loops(tool, 1, 0), tool_loops(tool))


class RoughingCutsTests(unittest.TestCase):
    def setUp(self):
        self.project = project_from_json(EXAMPLE.read_text(encoding="utf-8"))
        self.plan = planned(self.project.program)
        self.block_plan = next(b for b in self.plan.blocks if b.number == 2)  # the right-hand roughing block with a pocket
        program = self.project.program
        self.context = BlockContext(
            program.raw_part, program.equipped_tool(self.block_plan.block.tool_number), self.block_plan.residual_before,
            program.safety, program.contours,
        )

    def test_the_first_cut_is_made_and_the_material_adds_up(self):
        cut_ = self.block_plan.block.roughing_cuts(self.context)
        self.assertIsNotNone(cut_)
        self.assertTrue(cut_.cuts)
        stock = self.block_plan.residual_before.area
        self.assertAlmostEqual(sum(loop_area(l) for l in cut_.residual) + sum(loop_area(l) for l in cut_.removed), stock, delta=0.05)
        self.assertGreater(sum(loop_area(l) for l in cut_.removed), 1)

    def test_a_line_goes_as_far_as_the_tool_reaches_and_not_further(self):
        block = self.block_plan.block
        cut_ = block.roughing_cuts(self.context)
        inputs = block._analytic_inputs(self.context)
        path, outside, outer = inputs.path, inputs.outside, inputs.outer
        bounds = self.context.residual.bounds
        clearance = self.context.safety.clearance_mm
        keep = RegionIndex(keep_loops(path, outside, block.finish_allowance_mm, outer, bounds.min_x - clearance, self.context.raw_part.clamp_z_mm - clearance))
        planning = planning_loops(self.context.tool, 1, block.min_free_angle_deg)
        for listed in (c for c in cut_.cuts if c.kind is CutKind.LINE):
            start, end = listed.start, listed.end
            self.assertFalse(blocked_by_part(planning, keep, start, TOLERANCE))
            self.assertFalse(blocked_by_part(planning, keep, end, TOLERANCE))
            if end.z > listed.source.low.z + 2 * TOLERANCE:  # it stopped before the end of the wanted stretch: one step further is a collision
                self.assertTrue(blocked_by_part(planning, keep, Point(end.x, end.z - 0.05), TOLERANCE))

    def test_the_lines_lie_inside_the_wanted_stretches_and_the_ride_up_goes_up(self):
        block = self.block_plan.block
        cut_ = block.roughing_cuts(self.context)
        wanted = block.wanted_plan(self.context)
        for start, end in ((c.start, c.end) for c in cut_.cuts):
            self.assertTrue(any(l.low.z - TOLERANCE <= end.z and start.z <= l.high.z + TOLERANCE and abs(l.high.x - start.x) < 1e-6 for l in wanted.lines))
        for ride in (c.ride for c in cut_.cuts if c.kind is CutKind.LINE and not c.source.open_low):
            if ride:
                self.assertGreater(max(piece.end.x for piece in ride), ride[0].start.x)  # up first (a way over a bump may come down after)

    def test_all_lines_are_cut_one_after_the_other_and_the_material_adds_up(self):
        cut_ = self.block_plan.block.roughing_cuts(self.context)
        self.assertGreater(len(cut_.cuts), 30)  # the open lines and the lines of the pocket (at the plunge depth of cut)
        self.assertEqual(cut_.failed_lines, 0)
        stock = self.block_plan.residual_before.area
        self.assertAlmostEqual(sum(loop_area(l) for l in cut_.residual) + sum(loop_area(l) for l in cut_.removed), stock, delta=0.1)
        radii = [c.start.x for c in cut_.cuts if c.kind is CutKind.LINE]
        self.assertEqual(radii, sorted(radii, reverse=True))  # the lines from the free side towards the part (a pass goes behind the lines it relies on)

    def test_a_neutral_tool_cuts_like_a_right_hand_one_and_a_left_hand_tool_is_planned_mirrored(self):
        from wop.core.analytic.replay import replay

        program = self.project.program
        self.assertIsNotNone(self.block_plan.block.roughing_cuts(self.context))  # tool 4 is a symmetric V insert
        rest = next(b for b in self.plan.blocks if b.number == 3)  # the rest block with a left-hand tool
        context = BlockContext(program.raw_part, program.equipped_tool(rest.block.tool_number), rest.residual_before, program.safety, program.contours)
        cut_ = rest.block.roughing_cuts(context)
        lines = [c for c in cut_.cuts if c.kind is CutKind.LINE and not c.start.is_close(c.end)]
        self.assertTrue(lines)
        self.assertTrue(all(c.end.z > c.start.z for c in lines))  # back in the real coordinates: it cuts from the chuck side towards the front
        self.assertEqual(replay(cut_, tool_loops(context.tool), TOLERANCE).findings, ())  # the real left-hand tool, in the real coordinates

    def test_an_inside_block_is_planned_mirrored_and_keeps_both_sides_of_the_axis(self):
        project = project_from_json((ROOT / "tests" / "data" / "projects" / "inside_cavity_behind_narrow_mouth_along_z.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        bp = plan.blocks[0]
        context = BlockContext(project.program.raw_part, project.program.equipped_tool(bp.block.tool_number), bp.residual_before, project.program.safety, project.program.contours)
        first = bp.block.roughing_cuts(context)
        self.assertTrue(first.cuts)
        self.assertTrue(first.both_sides)
        self.assertLess(min(p.x for loop in first.material for piece in loop for p in (piece.start, piece.end)), 0)  # the far side of the bar
        self.assertTrue(all(c.start.x > 0 for c in first.cuts))  # the lines are cut on this side

class RideOverTests(unittest.TestCase):
    def test_a_line_that_meets_a_bump_lower_than_the_line_above_goes_over_it_and_on(self):
        project = project_from_json((ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        block_plan = next(b for b in plan.blocks if b.number == 2)
        program = project.program
        context = BlockContext(program.raw_part, program.equipped_tool(block_plan.block.tool_number), block_plan.residual_before, program.safety, program.contours)
        cut_ = block_plan.block.roughing_cuts(context)
        self.assertEqual(cut_.failed_lines, 0)
        # a front stretch that meets the bump: up the bump, over it, down again (to its level or to the pocket line just under it)
        front = next(i for i, c in enumerate(cut_.cuts) if c.start.z == 0 and c.ride and max(p.end.x for p in c.ride) > c.start.x + 0.1 and c.ride[-1].end.x <= c.start.x + 1e-6)
        listed = cut_.cuts[front]
        self.assertLessEqual(listed.start.x - listed.ride[-1].end.x, block_plan.block.plunge_depth_of_cut_mm + 1e-6)
        behind_start = cut_.cuts[front + 1].start
        self.assertTrue(behind_start.is_close(listed.ride[-1].end, 1e-6))  # and on from there: the next line begins where the tool arrives
        stock = block_plan.residual_before.area
        self.assertAlmostEqual(sum(loop_area(l) for l in cut_.residual) + sum(loop_area(l) for l in cut_.removed), stock, delta=0.1)
        self.assertTrue(cut_.cuts[front + 1].joined)  # the line pulled out of the list has no entry of its own

    def test_every_line_has_a_way_in_that_ends_at_its_start(self):
        project = project_from_json((ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        block_plan = next(b for b in plan.blocks if b.number == 2)
        program = project.program
        context = BlockContext(program.raw_part, program.equipped_tool(block_plan.block.tool_number), block_plan.residual_before, program.safety, program.contours)
        cut_ = block_plan.block.roughing_cuts(context)
        self.assertEqual((cut_.failed_lines, cut_.unreachable_lines), (0, 0))
        entered = [c for c in cut_.cuts if c.kind is CutKind.LINE and not c.joined]
        self.assertTrue(any(c.entry for c in entered))
        for c in entered:
            for before, after in zip(c.entry, c.entry[1:]):
                self.assertTrue(before.end.is_close(after.start, 1e-6))  # one continuous path
            if c.entry:
                self.assertTrue(c.entry[-1].end.is_close(c.start, 1e-6))  # to the place where the cut begins
                if c.rapid or c.retreat or c.entry[0].start.distance_to(c.start) > CUT_END_SNAP_MM:
                    self.assertGreater(c.entry[0].start.distance_to(c.start), 0.5)  # and it begins away from it, in the air
                # else the tool stands at the start already (where the pass before ended): a feed move of a few thousandths closes the path
        walls = [c for c in entered if not c.source.open_high and c.entry and (c.rapid or c.retreat or c.entry[0].start.distance_to(c.start) > CUT_END_SNAP_MM)]
        self.assertTrue(walls)
        for c in walls:
            self.assertGreater(c.entry[0].start.x, c.start.x)  # a wall at the start: the way in comes from above

    def test_the_cuts_are_connected_by_free_rapids(self):
        project = project_from_json((ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        block_plan = next(b for b in plan.blocks if b.number == 2)
        program = project.program
        tool = program.equipped_tool(block_plan.block.tool_number)
        context = BlockContext(program.raw_part, tool, block_plan.residual_before, program.safety, program.contours)
        cut_ = block_plan.block.roughing_cuts(context)
        self.assertEqual(cut_.unconnected_cuts, 0)
        self.assertTrue(any(c.rapid for c in cut_.cuts))
        block = block_plan.block
        inputs = block._analytic_inputs(context)
        path, outside, outer = inputs.path, inputs.outside, inputs.outer
        bounds = context.residual.bounds
        keep = RegionIndex(keep_loops(path, outside, block.finish_allowance_mm, outer, bounds.min_x - context.safety.clearance_mm, context.raw_part.clamp_z_mm - context.safety.clearance_mm))
        real = tool_loops(tool)
        safe = program.safety.safe_radius_mm
        first = cut_.cuts[0]
        self.assertAlmostEqual(first.rapid[0].start.x, safe)  # the block begins at the safe radius ...
        self.assertTrue(first.rapid[-1].end.is_close(first.entry[0].start if first.entry else first.start, 1e-6))  # ... and goes to the first cut
        self.assertAlmostEqual(cut_.leave_rapid[-1].end.x, safe)  # and ends at the safe point
        self.assertGreaterEqual(cut_.leave_rapid[-1].end.z, program.safety.safe_z_mm)
        previous = None
        for c in cut_.cuts:
            if previous is not None and not c.joined:
                moves = [*c.retreat, *c.rapid, *c.entry]
                here = previous.ride[-1].end if previous.ride else previous.end
                for piece in moves:  # one continuous path from the end of the cut before to the start of this one
                    self.assertTrue(here.is_close(piece.start, 1e-6), (here, piece))
                    here = piece.end
                self.assertTrue(here.is_close(c.start, 1e-6))
                for piece in c.rapid:
                    self.assertIsInstance(piece, LineSegment)
                    for i in range(21):  # the whole tool, not only the planning one, stays out of the part and its allowance
                        self.assertFalse(blocked_by_part(real, keep, piece.point_at(i / 20), 0.01), piece)
            previous = c

    def test_every_cut_knows_its_start_its_kind_and_its_line(self):
        project = project_from_json((ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        block_plan = next(b for b in plan.blocks if b.number == 2)
        program = project.program
        context = BlockContext(program.raw_part, program.equipped_tool(block_plan.block.tool_number), block_plan.residual_before, program.safety, program.contours)
        cuts = block_plan.block.roughing_cuts(context).cuts
        self.assertTrue(any(c.kind is CutKind.DIP for c in cuts))
        self.assertTrue(any(c.joined for c in cuts))
        for c in cuts:
            self.assertIsNotNone(c.source)
            if c.kind is CutKind.LINE:
                self.assertGreaterEqual(c.start.z, c.end.z)  # a cut runs from the front towards the chuck: the start is the high-Z end
                self.assertAlmostEqual(c.start.x, c.end.x, places=6)
            else:
                self.assertTrue(c.start.is_close(c.end) and c.ride and not c.joined)


class UnreachableLineTests(unittest.TestCase):
    def test_a_line_with_no_way_in_is_not_cut_and_nothing_under_it_and_a_note_says_so(self):
        # the planning rule: a line the tool cannot get to is not cut, the block is not given back to the old planner; the lines under it in
        # the same stretch of Z are not cut either (they would take both layers at once); no project has such a line, so the way in to the
        # first pocket line under the top layer of the pocket of contour_bump_pocket #2 is taken away
        from unittest import mock

        from wop.core.analytic import roughing_cuts as roughing_cuts_module
        from wop.core.analytic.replay import replay
        from wop.core.program_model.operations import LinearMove

        project = project_from_json((ROOT / "tests" / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8"))
        program = project.program
        block_plan = next(b for b in planned(program).blocks if b.number == 2)
        block = block_plan.block
        context = BlockContext(program.raw_part, program.equipped_tool(block.tool_number), block_plan.residual_before, program.safety, program.contours)
        real_entry = roughing_cuts_module._entry
        whole = block.roughing_cuts(context)
        pocket = [c for c in whole.cuts if c.kind is CutKind.LINE and c.source.layer >= 1]
        chosen = max((c for c in pocket if not c.joined), key=lambda c: c.start.x)  # the highest pocket line under the first layer with a way in of its own
        under = [c for c in pocket if c.start.x < chosen.start.x - 1e-3 and c.end.z < chosen.start.z and c.start.z > chosen.end.z]
        self.assertGreater(len(under), 1)

        def no_way_to_the_pocket_line(planner, stock, start, wall):
            if start.is_close(chosen.start, 1e-6):
                return None
            return real_entry(planner, stock, start, wall)

        real_plunge = roughing_cuts_module._plunge
        real_wall_entry = roughing_cuts_module._wall_entry

        def no_wall_way_to_the_pocket_line(planner, ordered, material, line, start, axis, beside):
            return None if start.is_close(chosen.start, 1e-6) else real_wall_entry(planner, ordered, material, line, start, axis, beside)

        def no_plunge_there(planner, material, start):
            return None if start.is_close(chosen.start, 1e-6) else real_plunge(planner, material, start)

        with mock.patch.object(roughing_cuts_module, "_entry", no_way_to_the_pocket_line), mock.patch.object(roughing_cuts_module, "_plunge", no_plunge_there),                 mock.patch.object(roughing_cuts_module, "_wall_entry", no_wall_way_to_the_pocket_line):
            first = block.roughing_cuts(context)
            result = block.generate(context)
        self.assertEqual(first.unreachable_lines, 1 + len(under))  # the line and the pocket lines under it
        self.assertFalse([c for c in first.cuts if c.kind is CutKind.LINE and c.start.x < chosen.start.x + 1e-3 and c.end.z < chosen.start.z and c.start.z > chosen.end.z])
        self.assertEqual(replay(first, tool_loops(context.tool), TOLERANCE).findings, ())
        self.assertTrue(any("not cut: the tool has no free way in" in m for m in result.messages))
        self.assertFalse(any("the old planner roughs this block" in m for m in result.messages))
        self.assertTrue(any("is not cut: the tool cannot reach it" in m for m in result.messages))
        self.assertTrue([op for op in result.operations if isinstance(op, LinearMove)])


class RetreatTests(unittest.TestCase):
    def test_a_tool_at_the_bottom_of_a_slot_goes_back_the_way_it_came_and_then_rapids(self):
        # a block (radius 0 to 10) with a slot that runs down from the top at z -3 to -5 slanting to a chamber at radius 2 to 4: no rapid
        # leaves the chamber straight, round a corner or over the stock; the tool goes back up the slot along its way in, then rapids
        material = [oriented(polygon_loop([Point(0, -14), Point(10, -14), Point(10, -5), Point(4, -11), Point(2, -11), Point(2, -7), Point(10, -3), Point(10, 0), Point(0, 0)]), True)]
        inside = Point(2.6, -9.5)
        way_in = (LineSegment(Point(11, -3.4), Point(10.2, -3.6)), LineSegment(Point(10.2, -3.6), inside))
        before = Cut(inside, inside, (), WantedLine(0, inside, inside), entry=way_in)
        tool = tool_square(0.8)
        entry, retreat, rapid = _way(_leaving(before), (), Point(12, -20), RapidTool.of(tool, 1.0), material)
        self.assertEqual(entry, ())
        self.assertEqual(len(retreat), 2)  # back up the slot (the cut that begins where it ends adds no move of no length), then the rise out of the clearance at feed (X12)
        self.assertTrue(retreat[0].start.is_close(inside) and retreat[0].end.is_close(Point(10.2, -3.6)))
        self.assertTrue(retreat[1].start.is_close(Point(10.2, -3.6)) and retreat[1].end.x > 10.2 and retreat[1].end.z == -3.6)
        self.assertTrue(rapid and rapid[0].start.is_close(retreat[1].end) and rapid[-1].end.is_close(Point(12, -20)))

if __name__ == "__main__":
    unittest.main()
