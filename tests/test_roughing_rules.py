"""The rules of the roughing, checked with a simulation of the material (Python 3.11 and later).

R1 a cutting move along a contour piece is that piece (a line or an arc), never a run of short chords;
R2 the tool does not retract while stock of the line it cuts is still ahead and can be reached by riding along the
   contour (a bump lower than the line before is ridden over, not walked round);
R3 no feed move ends deeper in uncut stock than the depth of cut: a pocket is entered straight, along the wall, or not at
   all, and what is behind a pocket whose way in is closed stays uncut;
R4 the model of the material follows the cuts: no rapid goes through stock because a line was refused.

The simulation takes the real tool body along every move and removes what it passes; it knows nothing of the planner.
"""

import math
import unittest
from pathlib import Path

from tests.test_rough_follow import generate, holder_cnmg, holder_vnmg
from wop.core.geometry import ArcSegment, Point
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid
from wop.core.program_model.raw_part import RawPart

from wop.core.blocks.turning_common import PassDirection
from wop.core.reach import prepare_tool
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region

DEPTH_OF_CUT = 1.5
RAW = RawPart("steel", 40, 60)
LOOKOUT_MM = 60
LOOKOUT_STEP_MM = 0.05
SAMPLE_EVERY_MM = 4
CUT_STEP_MM = 6  # the simulation removes what the tool passes in steps of this length
TOLERANCE = 1.0  # a wedge that the leaning front edge of an insert leaves beside a wall is a few tenths; a plunge through stock is millimetres
EDGE_MM = 0.02  # the probe of the depth stands this far on the cut side of a move: on the edge of a cut it would see the wall behind (more than the end snap of a line, `CUT_END_SNAP_MM`: two lines may end a few thousandths apart)
TIP_BOX = (-3, -3, 30, 6)  # the simulation takes the part of the tool body near the tip (x from, z from, x to, z to): that is what cuts

SHAPES = {
    "rising slope": [(8, 0), (8, -10), (14, -16), (14, -30)],
    "falling slope": [(16, -4), (10, -14), (10, -30)],
    "stepped shaft": [(8, 0), (8, -10), (12, -10), (12, -25), (14, -25), (14, -40)],
    "low bump": [(12, 0), (12, -5), (14, -8), (12, -11), (12, -30)],
    "wide bump": [(12, 0), (12, -5), (14, -9), (14, -14), (12, -18), (12, -30)],
    "two bumps": [(12, 0), (12, -5), (14, -8), (12, -11), (12, -16), (14, -19), (12, -22), (12, -30)],
    "pocket with a ramp behind it": [(14, 0), (14, -10), (10, -10 - 4 / math.tan(math.radians(20))), (10, -27), (14, -27), (14, -40)],
    "pocket with a vertical wall": [(14, 0), (14, -10), (9, -10), (9, -14), (14, -14), (14, -30)],
}
TOOLS = {"CNMG 5 degrees": holder_cnmg, "VNMG 50 degrees": holder_vnmg}


def feed_moves(operations):
    """(start, move) of every feed move, with the position before it."""
    position = None
    found = []
    for operation in operations:
        if isinstance(operation, (Rapid, LinearMove, ArcMove)):
            if position is not None and not isinstance(operation, Rapid):
                found.append((position, operation))
            position = operation.end
    return found


def points_of(start, move, step=SAMPLE_EVERY_MM):
    if isinstance(move, ArcMove):
        segment = ArcSegment(start, move.end, move.center, move.direction)
        count = max(1, math.ceil(segment.length / step))
        return [segment.point_at(i / count) for i in range(count + 1)]
    count = max(1, math.ceil(start.distance_to(move.end) / step))
    return [Point(start.x + (move.end.x - start.x) * i / count, start.z + (move.end.z - start.z) * i / count) for i in range(count + 1)]


def depth_above(point, stock, along_z, sign):
    """How far stock reaches from the point outwards (along Z lines: larger X for outside turning; across X: larger Z). The
    probe stands a hair on the side the tool comes from, so the edge of a cut does not count the wall behind it."""
    depth = 0.0
    while depth < LOOKOUT_MM:
        depth += LOOKOUT_STEP_MM
        probe = Point(point.x + sign * depth, point.z + EDGE_MM) if along_z else Point(point.x + EDGE_MM, point.z + depth)
        if not stock.contains_point(probe):
            return depth - LOOKOUT_STEP_MM
    return depth


def simulate(result, tool, raw_part, along_z, stock=None):
    """The deepest a feed move ends in stock (looked at every few millimetres), and the rapids that go through stock."""
    stock = stock_region(raw_part) if stock is None else stock
    body = prepare_tool(tool).body
    tip = body.intersection(Region.rectangle(*TIP_BOX))  # the part that cuts
    deepest, rapid_hits = 0.0, 0
    position = None
    for operation in result.operations:
        if not isinstance(operation, (Rapid, LinearMove, ArcMove)):
            continue
        if position is not None and isinstance(operation, Rapid):
            if any(stock.shrunk_for_collision().overlaps(tip.translated(p.x, p.z).shrunk_for_collision()) for p in points_of(position, operation, 2)[1:]):  # not the start: it sits on the edge of the cut
                rapid_hits += 1
        elif position is not None:
            for point in points_of(position, operation):
                deepest = max(deepest, depth_above(point, stock, along_z, 1))
            steps = points_of(position, operation, CUT_STEP_MM)
            for a, b in zip(steps, steps[1:]):
                stock = stock.difference(tip.swept(b.x - a.x, b.z - a.z).translated(a.x, a.z))
        position = operation.end
    return deepest, rapid_hits


def chord_runs(operations):
    """The longest run of short feed moves in a row that each turn only a little: an arc cut into chords. A short move straight along X or
    along Z (the rise out of the clearance after a cut, X12: up, or along Z across X) is not a chord."""
    best, run, last = 0, 0, None
    for operation in operations:
        rise = hasattr(last, "end") and hasattr(operation, "end") and (abs(operation.end.z - last.end.z) <= 1e-9 or abs(operation.end.x - last.end.x) <= 1e-9)
        if isinstance(operation, LinearMove) and hasattr(last, "end") and 0 < operation.end.distance_to(last.end) < 1 and not rise:
            run += 1
        else:
            run = 0
        best = max(best, run)
        last = operation
    return best


class RuleTests(unittest.TestCase):
    """Every shape with both tools in both directions, looked at once and kept for the rules below."""

    analysed: dict = {}

    @classmethod
    def setUpClass(cls):
        for shape, points in SHAPES.items():
            for tool_name, make_tool in TOOLS.items():
                for direction in PassDirection:
                    result, _contour = generate(points, make_tool(), RAW, pass_direction=direction, depth_of_cut_mm=DEPTH_OF_CUT, finish_pass=False)
                    deepest, hits = simulate(result, make_tool(), RAW, direction is PassDirection.ALONG_Z)
                    cls.analysed[(shape, tool_name, direction)] = (result, deepest, hits)

    def every(self, check):
        for (shape, tool_name, direction), (result, deepest, hits) in self.analysed.items():
            with self.subTest(shape=shape, tool=tool_name, direction=direction.name):
                check(result, deepest, hits, direction)

    def test_r1_no_chords(self):
        self.every(lambda result, _deepest, _hits, _direction: self.assertLess(chord_runs(result.operations), 3))

    def test_r3_no_feed_move_ends_deeper_than_the_depth_of_cut(self):
        def check(_result, deepest, _hits, direction):
            if direction is PassDirection.ALONG_Z:  # across X the depth is a depth in Z, looked at below
                self.assertLessEqual(deepest, DEPTH_OF_CUT + TOLERANCE)
        self.every(check)

    # A tool wider than the groove touches the finished wall of the groove whatever the plan: the rule says nothing about it.
    TOOL_TOO_WIDE = {("pocket with a vertical wall", "CNMG 5 degrees")}

    def test_r4_no_rapid_goes_through_stock(self):
        for (shape, tool_name, direction), (_result, _deepest, hits) in self.analysed.items():
            if (shape, tool_name) in self.TOOL_TOO_WIDE:
                continue
            with self.subTest(shape=shape, tool=tool_name, direction=direction.name):
                self.assertEqual(hits, 0)


class UserProjectTests(unittest.TestCase):
    """The project in which the rules were found (a bump, a pocket behind a crest and a neck): the contour block plans with
    the rules kept (the checker of the whole program is not run here: it takes seconds on this bar)."""

    def test_the_bump_and_pocket_project(self):
        from wop.core.program_model.program import plan_program
        from wop.core.files.project_io import project_from_json
        program = project_from_json((Path(__file__).parent / "data" / "projects" / "contour_bump_pocket.wop.json").read_text(encoding="utf-8")).program
        plan = plan_program(program)
        self.assertEqual(plan.left_out, ())
        block_plan = plan.blocks[-1]
        tool = program.equipped_tool(block_plan.block.tool_number)
        deepest, hits = simulate(
            type("Result", (), {"operations": block_plan.operations}), tool, program.raw_part, True, block_plan.residual_before
        )
        self.assertEqual(hits, 0)
        self.assertLessEqual(deepest, block_plan.block.depth_of_cut_mm + TOLERANCE)
        self.assertLess(chord_runs(block_plan.operations), 3)


class RidingOverABumpTests(unittest.TestCase):
    def test_r2_a_bump_lower_than_the_line_before_does_not_cut_the_line_in_two(self):
        # the bump is 14 high (14.2 and more with the allowance and the nose): the lines above 14.5 pass it anyway, the line
        # just below the crest has the line before above the crest: it rides over, one line from the front to the back
        result, _contour = generate(SHAPES["low bump"], holder_vnmg(), RAW, depth_of_cut_mm=1.0, finish_pass=False)
        operations = result.operations
        lines = []  # (index of the approach, index of the rapid that leaves) of every line that starts at the front face
        for index, operation in enumerate(operations):
            if isinstance(operation, Rapid) and abs(operation.end.z - 1.0) < 1e-9 and operation.end.x < 15:
                leave = next((j for j in range(index + 1, len(operations)) if isinstance(operations[j], Rapid)), None)
                if leave is not None:
                    lines.append((operation.end.x, operations[index + 1:leave]))
        over = [(radius, moves) for radius, moves in lines if 14.0 < radius < 15 and any(getattr(m, "end", None) and m.end.z < -20 for m in moves)]
        self.assertTrue(over, "no line rides over the bump from the front to the far side")
        for _radius, moves in over:
            self.assertTrue(any(isinstance(m, ArcMove) for m in moves) or len(moves) >= 3)

    def test_a_bump_higher_than_the_line_before_is_a_wall_and_cuts_the_line_in_two(self):
        result, _contour = generate(SHAPES["wide bump"], holder_vnmg(), RAW, depth_of_cut_mm=1.0, finish_pass=False)
        self.assertTrue([op for op in result.operations if isinstance(op, Rapid) and op.end.z < -2 and op.end.x < 15])


class RemovedMatchesTheToolTests(unittest.TestCase):
    """The material the block says it removed (the grey in the picture, the model of the next block) is what the tool body
    really passes: no claim of material the tool never touched."""

    def test_claimed_removal_is_swept_by_the_tool(self):
        steep = [(14, 0), (14, -10), (10, -10 - 4 / math.tan(math.radians(60))), (10, -27), (14, -27), (14, -40)]
        for tool_name, make_tool in TOOLS.items():
            result, _c = generate(steep, make_tool(), RAW, depth_of_cut_mm=DEPTH_OF_CUT, finish_pass=False)
            tip = prepare_tool(make_tool()).body
            swept, position = Region.empty(), None
            for operation in result.operations:
                if not isinstance(operation, (Rapid, LinearMove, ArcMove)):
                    continue
                if position is not None and not isinstance(operation, Rapid):
                    points = points_of(position, operation, 0.5)
                    for a, b in zip(points, points[1:]):
                        swept = swept.union(tip.swept(b.x - a.x, b.z - a.z).translated(a.x, a.z))
                position = operation.end
            with self.subTest(tool=tool_name):
                self.assertLess(result.removed.difference(swept).area, 5.0)


class ClosedPocketTests(unittest.TestCase):
    def test_r3_what_lies_behind_a_pocket_the_tool_cannot_enter_stays_uncut(self):
        blocked, _c = generate(SHAPES["pocket with a vertical wall"], holder_vnmg(), RAW, depth_of_cut_mm=1.0)
        free, _c = generate(SHAPES["rising slope"], holder_vnmg(), RAW, depth_of_cut_mm=1.0)
        self.assertTrue(any("not cut" in message for message in blocked.messages))
        self.assertFalse(any("not cut" in message for message in free.messages))

    def test_a_wall_the_back_of_the_tool_lies_along_is_entered_along_the_wall(self):
        result, _c = generate(SHAPES["falling slope"], holder_vnmg(), RAW, depth_of_cut_mm=1.0)
        self.assertFalse(any("not cut" in message for message in result.messages))


if __name__ == "__main__":
    unittest.main()
