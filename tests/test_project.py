import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from wop.core.contour import ContourDefinition, LineStep
from wop.core.geometry import Point

from tests.reference_program import reference_program
from wop.adapters.project_files import load_project, save_project
from wop.core.blocks.base import BlockError
from wop.core.blocks.turning_common import TurningSide
from wop.core.blocks.turning_contour import ContourTurningBlock
from wop.core.contour_solver import build_contour
from wop.core.program_model.program import plan_program
from wop.core.program_model.project import Project, ProjectSettings
from wop.core.files.project_io import (
    ProjectError,
    project_from_dict,
    project_from_json,
    project_to_dict,
    project_to_json,
)
from wop.core.program_model.units import XInputMode


def shaft_contour(contour_id="shaft"):
    points = [(10, 0), (10, -20), (12, -20), (12, -30)]
    steps = tuple(LineStep(Point(x, z)) for x, z in points[1:])
    return build_contour(contour_id, "shaft", ContourDefinition(Point(*points[0]), steps))


def contour_block(block_id, contour_id="shaft", **overrides):
    reference = reference_program().blocks[1]  # a turning block: reuse its spindle and tool
    values = dict(
        block_id=block_id, name=block_id, tool_number=reference.tool_number,
        spindle=reference.spindle, contour_id=contour_id, side=TurningSide.OUTSIDE,
        feed_mm_per_rev=0.2, depth_of_cut_mm=1, finish_allowance_mm=0.2,
    )
    values.update(overrides)
    return ContourTurningBlock(**values)


def full_project() -> "Project":
    program = reference_program()
    program = program.with_contour(shaft_contour())
    program = replace(program, blocks=program.blocks + (contour_block("k1"),))
    return Project(program, ProjectSettings("my part", XInputMode.RADIUS))


class ProjectFileTests(unittest.TestCase):
    def test_every_block_type_survives_a_round_trip(self):
        project = full_project()
        self.assertEqual(project_from_json(project_to_json(project)), project)

    def test_saving_a_loaded_project_gives_the_same_text(self):
        first = project_to_json(full_project())
        second = project_to_json(project_from_json(first))
        self.assertEqual(first, second)

    def test_the_file_on_disk_is_byte_identical_after_load_and_save(self):
        with tempfile.TemporaryDirectory() as folder:
            one = Path(folder) / "one.wop.json"
            two = Path(folder) / "two.wop.json"
            save_project(one, full_project())
            save_project(two, load_project(one))
            self.assertEqual(one.read_bytes(), two.read_bytes())
            self.assertNotIn(b"\r", one.read_bytes())
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_a_loaded_program_generates_the_same_moves(self):
        project = full_project()
        loaded = project_from_json(project_to_json(project))
        self.assertEqual(
            plan_program(loaded.program).operations, plan_program(project.program).operations
        )

    def test_the_program_keeps_its_own_tools(self):
        loaded = project_from_json(project_to_json(full_project()))
        self.assertEqual([t.number for t in loaded.program.tools], [1, 2])

    def test_damaged_files_are_refused_with_a_message(self):
        good = project_to_dict(full_project())
        cases = {
            "not json": "{nope",
            "not a project": "[1, 2]",
            "newer format": {**good, "format": 99},
            "missing part": {k: v for k, v in good.items() if k != "raw_part"},
            "unknown block type": {**good, "blocks": [{"type": "teleport", "parameters": {}}]},
            "bad block value": {
                **good,
                "blocks": [{"type": "facing", "parameters": {"block_id": 5}}],
            },
        }
        for label, content in cases.items():
            with self.subTest(label):
                with self.assertRaises(ProjectError):
                    if isinstance(content, str):
                        project_from_json(content)
                    else:
                        project_from_dict(content)

    def test_missing_references_are_refused(self):
        good = project_to_dict(full_project())
        no_contour = {**good, "contours": []}
        with self.assertRaises(ProjectError) as caught:
            project_from_dict(no_contour)
        self.assertIn("contour", str(caught.exception))
        no_tools = {**good, "tools": good["tools"][:1]}
        with self.assertRaises(ProjectError) as caught:
            project_from_dict(no_tools)
        self.assertIn("T2", str(caught.exception))


class SharedContourTests(unittest.TestCase):
    def test_two_blocks_share_one_contour_and_follow_an_edit(self):
        from wop.core.blocks.base import BlockContext
        from wop.core.program_model.stock import stock_region

        def moves(program, block):
            stock = stock_region(program.raw_part)
            context = BlockContext(
                program.raw_part, program.tool(block.tool_number), stock, program.safety,
                program.contours,
            )
            return block.generate(context).operations

        blocks = (contour_block("a"), contour_block("b", feed_mm_per_rev=0.3))
        program = replace(reference_program().with_contour(shaft_contour()), blocks=blocks)
        longer = build_contour(
            "shaft", "shaft",
            ContourDefinition(Point(10, 0), (LineStep(Point(10, -25)), LineStep(Point(12, -25)),
                                             LineStep(Point(12, -30)))),
        )
        edited = program.with_contour(longer)
        for block in blocks:
            self.assertNotEqual(moves(program, block), moves(edited, block))

    def test_replacing_a_contour_keeps_its_place_in_the_list(self):
        program = reference_program().with_contour(shaft_contour("a")).with_contour(shaft_contour("b"))
        program = program.with_contour(shaft_contour("a"))
        self.assertEqual([c.contour_id for c in program.contours], ["a", "b"])

    def test_a_contour_in_use_cannot_be_deleted(self):
        program = reference_program().with_contour(shaft_contour())
        program = replace(program, blocks=(contour_block("a"),))
        with self.assertRaises(BlockError) as caught:
            program.without_contour("shaft")
        self.assertIn("a", str(caught.exception))
        free = replace(program, blocks=())
        self.assertEqual(free.without_contour("shaft").contours, ())


class SingleBlockTests(unittest.TestCase):
    def setUp(self):
        self.program = reference_program()
        self.full = plan_program(self.program)

    def test_the_moves_of_a_block_equal_those_in_the_full_program(self):
        for index in range(len(self.program.blocks)):
            with self.subTest(block=index + 1):
                single = plan_program(self.program, only_block=index)
                self.assertEqual(len(single.blocks), 1)
                self.assertEqual(
                    single.blocks[0].result.operations, self.full.blocks[index].result.operations
                )
                self.assertAlmostEqual(
                    single.blocks[0].residual_before.area,
                    self.full.blocks[index].residual_before.area,
                )

    def test_the_block_starts_with_a_safe_tool_change_and_ends_safe(self):
        from wop.core.program_model.operations import Rapid, SetSpindle, ToolChange

        single = plan_program(self.program, only_block=3)  # the bore, tool 2
        kinds = [type(op) for op in single.blocks[0].operations]
        self.assertLess(kinds.index(Rapid), kinds.index(ToolChange))
        self.assertIn(SetSpindle, kinds)
        self.assertIsInstance(single.closing[0], Rapid)

    def test_a_block_number_that_does_not_exist_is_refused(self):
        with self.assertRaises(BlockError):
            plan_program(self.program, only_block=9)
        with self.assertRaises(BlockError):
            plan_program(self.program, only_block=-1)

    def test_changing_one_block_changes_only_that_block(self):
        blocks = list(self.program.blocks)
        blocks[2] = replace(blocks[2], feed_mm_per_rev=0.3)
        changed = plan_program(replace(self.program, blocks=tuple(blocks)))
        for index, (old, new) in enumerate(zip(self.full.blocks, changed.blocks)):
            with self.subTest(block=index + 1):
                if index == 2:
                    self.assertNotEqual(old.operations, new.operations)
                else:
                    self.assertEqual(old.operations, new.operations)


if __name__ == "__main__":
    unittest.main()
