"""Roughing never touches the finished part and goes at most `GRAZE_FRACTION` (30 %) of the finishing allowance deep into it
(decided with the user 2026-10-22; a fraction, because the user may ask for an allowance of 0.075 mm). Finishing follows the contour whatever the tool can reach: the checker reports that, and the user turns finishing
off for blocks the tool cannot do. Here every contour block of the example and test projects is planned without finishing pass
(so all moves are roughing) and the swept tool body is held against the part and its allowance."""

import glob
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import planned
from wop.adapters.project_files import load_project
from wop.core.constants import COLLISION_PENETRATION_TOLERANCE_MM
from wop.core.geometry import Point, segments_to_polyline
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid
from wop.core.reach import prepare_tool
from wop.core.geometry.region import Region
from wop.core.verify import move_points, plain_moves

ROOT = Path(__file__).parent.parent
GRAZE_FRACTION = 0.3  # how deep the tool body may go into the finishing allowance during roughing, of the allowance
PROJECTS = sorted(glob.glob(str(ROOT / "examples" / "*.wop.json"))) + sorted(glob.glob(str(ROOT / "tests" / "data" / "projects" / "*.json")))


def contour_blocks_without_finishing(path: str):
    program = load_project(Path(path)).program
    blocks = tuple(replace(b, finish_pass=False) if b.type_name == "turning_contour" else b for b in program.blocks)
    return replace(program, blocks=blocks)


def keep_of(program, block, residual_before) -> Region:
    """The part: what the block must leave (the material on the part's side of its contour)."""
    contour = program.contour(block.contour_id)
    line = segments_to_polyline(list(contour.segments))
    under = Region.from_points([Point(0, max(p.z for p in line)), *line, Point(0, min(p.z for p in line))])
    if block.side.value == "outside":
        return residual_before.intersection(under)
    return residual_before.difference(under)


def skin_of(program, block, residual_before, keep) -> Region:
    """The part and its finishing allowance: the allowance lies on the contour the block finishes, not on the front face of the part
    beside the start of the contour (a face the block does not finish: the tool may touch it, as it may touch any face it does not cut)."""
    skin = keep.offset(block.finish_allowance_mm)
    start = program.contour(block.contour_id).segments[0].start
    bounds, front, allowance = residual_before.bounds, residual_before.bounds.max_z, block.finish_allowance_mm
    if abs(start.z - front) > allowance:
        return skin
    # from over the corner of the contour (the rounded skin reaches into the air in front of it) along the face
    low, high = (start.x - allowance, bounds.max_x + allowance) if block.side.value == "inside" else (bounds.min_x - allowance, start.x + allowance)
    return skin.difference(Region.rectangle(low, front, high, front + 2 * allowance)) if high > low else skin


def worst_roughing_contact(program):
    """[(block number, area into the part, area deeper than GRAZE_MM into the part and its allowance)] of the worst move."""
    plan = planned(program)
    found = []
    for index, block_plan in enumerate(plan.blocks):
        block = block_plan.block
        if block.type_name != "turning_contour":
            continue
        keep = keep_of(program, block, block_plan.residual_before)
        skin = skin_of(program, block, block_plan.residual_before, keep)
        graze = GRAZE_FRACTION * block.finish_allowance_mm
        tool = prepare_tool(program.equipped_tool(block.tool_number))
        into_part, into_skin = 0.0, 0.0
        position = None
        for operation in block_plan.operations:
            for move in plain_moves(operation):
                if not isinstance(move, (Rapid, LinearMove, ArcMove)):
                    continue
                for point in move_points(position, move):
                    into_part = max(into_part, tool.body.shrunk_for_collision().translated(point.x, point.z).overlap_area(keep))
                    into_skin = max(into_skin, tool.body.shrunk_for_collision(2 * graze + COLLISION_PENETRATION_TOLERANCE_MM).translated(point.x, point.z).overlap_area(skin))
                position = move.end
        found.append((index + 1, into_part, into_skin))
    return found


class RoughingKeepsOffThePartTests(unittest.TestCase):
    def test_no_contour_block_of_the_example_and_test_projects_is_roughed_into_the_part(self):
        for path in PROJECTS:
            with self.subTest(project=Path(path).name):
                for number, into_part, into_skin in worst_roughing_contact(contour_blocks_without_finishing(path)):
                    self.assertEqual(into_part, 0.0, f"block {number} cuts into the part")
                    self.assertEqual(into_skin, 0.0, f"block {number} goes deeper than {GRAZE_FRACTION:.0%} of the allowance into it")


    def test_what_the_bar_cannot_reach_stays_in_the_residual(self):
        # the cavity of `inside_cavity_behind_narrow_mouth_across_x`: without finishing pass the material that the shortened lines
        # left is still there after the block (with a finishing pass the skin round it is cut and the piece is cut off)
        program = contour_blocks_without_finishing(str(ROOT / "tests" / "data" / "projects" / "inside_cavity_behind_narrow_mouth_across_x.wop.json"))
        plan = planned(program)
        cavity = plan.blocks[0].residual_after.intersection(Region.rectangle(18, -19, 23, -10))
        self.assertGreater(cavity.area, 40)  # about 5 x 9 mm of the cavity: the bar cannot reach it


if __name__ == "__main__":
    unittest.main()
