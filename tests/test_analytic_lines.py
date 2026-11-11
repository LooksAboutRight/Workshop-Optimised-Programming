"""The wanted lines of the analytic planner (wop/core/analytic/wanted_lines.py).

(The comparison of every line with the region the old planner roughed is gone: since the contour block builds its own result, the old
planner no longer runs in a plan.)
"""

import unittest
from pathlib import Path

from tests.helpers import planned

from wop.core.blocks.base import BlockContext
from wop.core.files.project_io import project_from_json

ROOT = Path(__file__).resolve().parent.parent


class WantedLinesTests(unittest.TestCase):
    def test_a_block_without_a_contour_has_no_plan(self):
        project = project_from_json((ROOT / "examples" / "reference.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        facing = plan.blocks[0]
        context = BlockContext(project.program.raw_part, project.program.equipped_tool(1), facing.residual_before, project.program.safety)
        self.assertIsNone(facing.block.wanted_plan(context))


if __name__ == "__main__":
    unittest.main()
