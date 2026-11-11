"""Drilling cycles in the post engine: G81 / G82 / G83 / G73 of the shipped LinuxCNC post, the concept chosen by what the
hole needs, a hole the post has no concept for or a hole inside a hole that is there (plain moves then), and a post with
`drilling_style = expanded` (plain moves)."""

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from wop.adapters.project_files import load_project
from wop.core.program_model.operations import DrillMode, DrillOperation
from wop.core.program_model.program import plan_program
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings
from wop.post.context import make_context
from wop.post.engine import TemplatePost
from wop.post.generate import generate_gcode
from wop.post.post_definition import parse_post

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ROOT / "wop" / "post" / "posts" / "linuxcnc.post.ini"
DIAMETER = PostSettings(XInputMode.DIAMETER)
MACHINE_TESTS = Path(tempfile.mkdtemp(prefix="wop_machine_tests_"))  # made by the tool, as the user makes them for the lathe


def setUpModule() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_machine_tests.py"), str(MACHINE_TESTS)], check=True, capture_output=True, cwd=ROOT)


def tearDownModule() -> None:
    import shutil

    shutil.rmtree(MACHINE_TESTS, ignore_errors=True)


def definition(path: Path):
    return parse_post(path.read_text(encoding="utf-8").replace("line_numbers = yes", "line_numbers = no"), "linuxcnc")


def project_lines(project: str, post_path: Path) -> list[str]:
    program = load_project(MACHINE_TESTS / f"{project}.wop.json").program
    plan = plan_program(program)
    context = make_context(program, plan, "t", "m", datetime(2026, 1, 1))
    return generate_gcode(plan, TemplatePost(definition(post_path)), DIAMETER, context=context).text.splitlines()


def hole(operation: DrillOperation) -> list[str]:
    post = TemplatePost(definition(SHIPPED))
    post.state.x, post.state.z = 0, operation.retract_z
    return post.drill(operation, DIAMETER)


class CycleCodeTests(unittest.TestCase):
    def test_the_four_test_projects_write_their_cycle_in_the_plane_g17(self):
        for project, cycle in (
            ("test_5a_drill_g81", "G81 X0 Z-13.803 R1 F0.1"),
            ("test_5b_drill_g82", "G82 X0 Z-13.803 R1 P2 F0.1"),
            ("test_5c_drill_g83", "G83 X0 Z-13.803 R1 Q4 F0.1"),
            ("test_5d_drill_g73", "G73 X0 Z-13.803 R1 Q4 F0.1"),
        ):
            with self.subTest(project):
                lines = project_lines(project, SHIPPED)
                start = lines.index("G17")
                self.assertEqual(lines[start:start + 5], ["G17", cycle, "G80", "G18", "G0 Z10"])  # G0 is written again: G80 ended the motion mode

    def test_a_post_with_drilling_style_expanded_writes_plain_moves(self):
        text = SHIPPED.read_text(encoding="utf-8").replace("drilling_style = cycle", "drilling_style = expanded")
        program = load_project(MACHINE_TESTS / "test_5c_drill_g83.wop.json").program
        plan = plan_program(program)
        context = make_context(program, plan, "t", "m", datetime(2026, 1, 1))
        lines = generate_gcode(plan, TemplatePost(parse_post(text, "linuxcnc")), DIAMETER, context=context).text.splitlines()
        self.assertNotIn("G17", lines)
        self.assertFalse(any(line.startswith("G83") for line in lines))

    def test_a_hole_whose_concept_the_post_does_not_have_is_written_as_plain_moves(self):
        peck_and_dwell = DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1, peck_depth_mm=3, mode=DrillMode.PECK, dwell_s=1)
        lines = hole(peck_and_dwell)  # the test post has no [peck_dwell_drill_cycle]
        self.assertFalse(any(line.startswith(("G8", "G73")) for line in lines), lines)
        self.assertNotIn("G17", lines)
        self.assertIn("G1 Z-10", lines)
        self.assertIn("G4 P1", lines)
        self.assertEqual(hole(peck_and_dwell)[-1], lines[-1])  # the engine state is as before: the same again gives the same lines

    def test_a_post_with_the_concept_writes_the_hole_with_pecks_and_a_dwell_as_a_cycle(self):
        extra = """[peck_dwell_drill_cycle]
<code peck_drill_cycle> X0 Z<drill end Z> R<drill retract Z> Q<drill peck> P<drill dwell> F<F>

[machine_rapid]
"""
        text = SHIPPED.read_text(encoding="utf-8").replace("[machine_rapid]\n", extra)
        post = TemplatePost(parse_post(text, "linuxcnc"))
        lines = post.drill(DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1, peck_depth_mm=3, mode=DrillMode.PECK, dwell_s=1), DIAMETER)
        self.assertEqual(lines, ["G83 X0 Z-10 R2 Q3 P1 F0.1"])

    def test_a_hole_inside_a_hole_that_is_there_is_written_as_plain_moves(self):
        lines = hole(DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1, air_z=-4))
        self.assertFalse(any(line.startswith("G8") for line in lines), lines)
        self.assertIn("G1 Z-10 F0.1", lines)


if __name__ == "__main__":
    unittest.main()
