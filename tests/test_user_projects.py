"""Projects the user sent while trying the program (tests/data/projects): they must keep loading, planning and
writing G-code. They use big bars: with the raster stand-in start with
WOP_STANDIN_DOMAIN="-70,70,-170,40" (slow); otherwise nothing special is needed."""

import os
import sys
import unittest
from pathlib import Path

from wop.core.program_model.operations import BlockBegin, BlockEnd
from wop.core.files.project_io import project_from_json

PROJECTS = Path(__file__).parent / "data" / "projects"

from wop.core.program_model.program import plan_program
from tests.post_helpers import shipped_post
from wop.post.base import PostSettings
from wop.post.generate import generate_gcode


def load(name):
    return project_from_json((PROJECTS / name).read_text(encoding="utf-8"))


# The raster stand-in (sandbox only) has a small area: its default is too small for these bars.
STANDIN_TOO_SMALL = hasattr(sys.modules.get("wop.core.geometry.region"), "CELL") and not os.environ.get("WOP_STANDIN_DOMAIN")


@unittest.skipIf(STANDIN_TOO_SMALL, "the stand-in area is too small for these bars")
class UserProjectTests(unittest.TestCase):
    def check(self, name, blocks):
        project = load(name)
        self.assertEqual([b.type_name for b in project.program.blocks], blocks)
        plan = plan_program(project.program)
        self.assertEqual(plan.left_out, ())
        self.assertEqual(len(plan.blocks), len(blocks))
        for block_plan in plan.blocks:
            moves = [op for op in block_plan.operations if not isinstance(op, (BlockBegin, BlockEnd))]
            self.assertTrue(moves, f"block {block_plan.number} has no operations")
        result = generate_gcode(plan, shipped_post(), PostSettings(project.settings.x_mode))
        self.assertTrue(result.complete, [issue.message for issue in result.issues])
        return plan

    def test_grooving_on_a_tube(self):
        plan = self.check("grooving.wop.json", ["turning", "grooving", "grooving", "grooving"])
        self.assertFalse([m for m in plan.messages if "error" in m.lower()])

    def test_turning_a_tube_in_five_blocks(self):
        self.check("tube_turning.wop.json", ["turning"] * 5)

    def test_two_drillings(self):
        self.check("drilling.wop.json", ["drilling", "drilling"])


if __name__ == "__main__":
    unittest.main()
