"""The example project of every block type (examples/blocks, made by tools/make_block_examples.py) loads and plans."""

import unittest
from pathlib import Path

from wop.core.program_model.operations import BlockBegin, BlockEnd
from wop.core.files.project_io import project_from_json

FOLDER = Path(__file__).resolve().parent.parent / "examples" / "blocks"

from wop.core.blocks import BLOCK_TYPES
from wop.core.program_model.program import plan_program


class BlockExampleTests(unittest.TestCase):
    def test_there_is_an_example_for_every_block_type(self):
        self.assertEqual(sorted(p.name.removesuffix(".wop.json") for p in FOLDER.glob("*.wop.json")), sorted(BLOCK_TYPES.names()))

    def test_every_example_plans_with_operations_in_its_block(self):
        for path in sorted(FOLDER.glob("*.wop.json")):
            with self.subTest(example=path.name):
                project = project_from_json(path.read_text(encoding="utf-8"))
                own = [block for block in project.program.blocks if block.type_name == path.name.removesuffix(".wop.json")]
                self.assertEqual(len(own), 1)  # one block of its type (the custom path example has a groove before it)
                plan = plan_program(project.program)
                self.assertEqual(plan.left_out, ())
                block_plan = next(p for p in plan.blocks if p.block.type_name == own[0].type_name)
                moves = [op for op in block_plan.operations if not isinstance(op, (BlockBegin, BlockEnd))]
                self.assertTrue(moves)


if __name__ == "__main__":
    unittest.main()
