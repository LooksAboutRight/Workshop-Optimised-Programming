"""Pockets in the wanted lines of the analytic planner (wop/core/analytic/pockets.py) and the exact material (material.py).

A pocket line has a wall of material at both ends and is entered from above, so a pocket gets lines of its own at the plunge
depth of cut and keeps none of the lines of the normal depth of cut. An open line has at least one open end.
"""

import random
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import planned

from wop.core.geometry.chains import INSIDE, ON, loop_area, locate, region_of_loops
from wop.core.analytic.material import chains_of_region, is_uncut, stock_chains
from wop.core.analytic.pockets import PROBE_MM, end_is_open
from wop.core.analytic.wanted_lines import LineKind
from wop.core.blocks.base import BlockContext
from wop.core.geometry import Point
from wop.core.files.project_io import project_from_json
from wop.core.program_model.stock import stock_region

ROOT = Path(__file__).resolve().parent.parent
POCKET_PROJECT = ROOT / "examples" / "left_hand_rest_machining.wop.json"  # block 2: a valley between a steep wall and a crest
INSIDE_POCKET_PROJECT = ROOT / "tests" / "data" / "projects" / "inside_cavity_behind_narrow_mouth_along_z.wop.json"
SPACING_TOLERANCE_MM = 0.01


def plan_of(path, number, **changes):
    project = project_from_json(path.read_text(encoding="utf-8"))
    plan = planned(project.program)
    block_plan = next(b for b in plan.blocks if b.number == number)
    block = replace(block_plan.block, **changes) if changes else block_plan.block
    context = BlockContext(
        project.program.raw_part, project.program.equipped_tool(block.tool_number), block_plan.residual_before,
        project.program.safety, project.program.contours,
    )
    return project, block_plan, block.wanted_plan(context)


class PocketTests(unittest.TestCase):
    def test_a_pocket_line_has_walls_at_both_ends_and_an_open_line_has_an_open_end(self):
        project, block_plan, plan = plan_of(POCKET_PROJECT, 2)
        stock = chains_of_region(block_plan.residual_before)
        kinds = {line.kind for line in plan.lines}
        self.assertEqual(kinds, {LineKind.OPEN, LineKind.POCKET})
        for line in plan.lines:
            level, high, low = line.high.x, line.high.z, line.low.z
            ends = (end_is_open(stock, level, high + PROBE_MM, 0), end_is_open(stock, level, low - PROBE_MM, 0))
            if line.kind is LineKind.POCKET:
                self.assertEqual(ends, (False, False), f"pocket line at {level:.3f}")
            else:
                self.assertTrue(any(ends), f"open line at {level:.3f}")
            self.assertEqual((line.open_high, line.open_low), ends if line.kind is LineKind.OPEN else (False, False))

    def test_the_pocket_lines_are_spaced_by_the_plunge_depth_of_cut(self):
        counts = {}
        for plunge in (0.8, 0.4):
            _project, _block_plan, plan = plan_of(POCKET_PROJECT, 2, plunge_depth_of_cut_mm=plunge)
            radii = sorted({round(line.high.x, 6) for line in plan.lines if line.kind is LineKind.POCKET}, reverse=True)
            self.assertGreater(len(radii), 2)
            for above, below in zip(radii, radii[1:]):
                self.assertLessEqual(above - below, plunge + SPACING_TOLERANCE_MM)
            counts[plunge] = len(radii)
        self.assertGreater(counts[0.4], counts[0.8])

    def test_the_lines_of_a_pocket_are_numbered_by_pocket_and_layer(self):
        _project, _block_plan, plan = plan_of(POCKET_PROJECT, 2)
        pocket_lines = [line for line in plan.lines if line.kind is LineKind.POCKET]
        self.assertTrue(all(line.pocket >= 0 and line.layer >= 0 and line.level_number == -1 for line in pocket_lines))
        layers = sorted({line.layer for line in pocket_lines if line.pocket == 0})
        self.assertEqual(layers, list(range(len(layers))))
        self.assertTrue(all(line.pocket == -1 and line.layer == -1 and line.level_number >= 0 for line in plan.lines if line.kind is LineKind.OPEN))

    def test_a_contour_without_a_pocket_has_only_open_lines(self):
        _project, _block_plan, plan = plan_of(ROOT / "examples" / "reference.wop.json", 5)
        self.assertTrue(plan.lines)
        self.assertEqual({line.kind for line in plan.lines}, {LineKind.OPEN})

    def test_a_cavity_behind_a_narrow_mouth_is_a_pocket_inside_too(self):
        _project, _block_plan, plan = plan_of(INSIDE_POCKET_PROJECT, 1)
        self.assertIn(LineKind.POCKET, {line.kind for line in plan.lines})

    def test_a_plunge_depth_equal_to_the_depth_of_cut_keeps_the_normal_levels(self):
        project = project_from_json(POCKET_PROJECT.read_text(encoding="utf-8"))
        block = next(b for b in project.program.blocks if b.type_name == "turning_contour")
        _project, _block_plan, plan = plan_of(POCKET_PROJECT, 2, plunge_depth_of_cut_mm=block.depth_of_cut_mm)
        radii = sorted({round(line.high.x, 6) for line in plan.lines if line.kind is LineKind.POCKET}, reverse=True)
        steps = {round(a - b, 2) for a, b in zip(radii, radii[1:])}
        self.assertLessEqual(max(steps), block.depth_of_cut_mm + SPACING_TOLERANCE_MM)


class MaterialTests(unittest.TestCase):
    def test_the_bar_is_exact_and_has_the_area_of_the_stock_region(self):
        project = project_from_json((ROOT / "examples" / "reference.wop.json").read_text(encoding="utf-8"))
        raw = project.program.raw_part
        loops = stock_chains(raw)
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(loop_area(loops[0]), stock_region(raw).area, places=6)
        self.assertTrue(is_uncut(stock_region(raw), raw))

    def test_a_residual_after_a_block_is_not_the_bar(self):
        project = project_from_json((ROOT / "examples" / "reference.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        self.assertFalse(is_uncut(plan.blocks[1].residual_before, project.program.raw_part))

    def test_a_point_is_inside_the_loops_exactly_as_in_the_region(self):
        project = project_from_json(POCKET_PROJECT.read_text(encoding="utf-8"))
        plan = planned(project.program)
        region = plan.blocks[2].residual_before
        loops = chains_of_region(region)
        whole = region_of_loops(loops)
        random.seed(1)
        bounds = region.bounds
        for _ in range(300):
            point = Point(random.uniform(bounds.min_x, bounds.max_x), random.uniform(bounds.min_z, bounds.max_z))
            where, _piece = locate(point, loops, 0)
            if where == ON:
                continue
            self.assertEqual(where == INSIDE, whole.contains_point(point), f"{point}")


if __name__ == "__main__":
    unittest.main()
