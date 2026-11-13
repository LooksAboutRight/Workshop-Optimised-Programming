"""The move to the tool change position can be written with the code of the controller: the post concept [change_position]."""

import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers import planned
from wop.core.files.project_io import project_from_json
from wop.core.geometry import Point
from wop.core.program_model.operations import Rapid
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings
from wop.post.context import PostContext, make_context
from wop.post.engine import TemplatePost
from wop.post.generate import generate_gcode
from wop.post.post_definition import parse_post

ROOT = Path(__file__).resolve().parent.parent
LINUXCNC = ROOT / "wop" / "post" / "posts" / "linuxcnc.post.ini"
MACHINE_CHANGE = PostContext(change_radius_mm=60, change_z_mm=20)


def text(change_position: str | None) -> str:
    base = LINUXCNC.read_text(encoding="utf-8").replace("\r\n", "\n")
    return base if change_position is None else base + f"\n[change_position]\n{change_position}\n"


def engine(change_position: str | None, context=None) -> TemplatePost:
    instance = TemplatePost(parse_post(text(change_position), "change"), context or PostContext())
    instance.header(PostSettings(XInputMode.RADIUS), [])
    return instance


class ChangePositionTests(unittest.TestCase):
    def test_a_move_to_the_change_position_is_written_with_the_template(self):
        instance = engine("G28 U0 W0")
        self.assertEqual(instance.rapid(Rapid(Point(30, 10), at_change=True)), ["G28 U0 W0"])

    def test_an_ordinary_rapid_move_is_not_touched(self):
        instance = engine("G28 U0 W0")
        self.assertEqual(instance.rapid(Rapid(Point(30, 10))), ["G0 X30 Z10"])

    def test_without_the_concept_nothing_changes(self):
        instance = engine(None)
        self.assertEqual(instance.rapid(Rapid(Point(30, 10), at_change=True)), ["G0 X30 Z10"])
        machine = engine(None, MACHINE_CHANGE)
        self.assertEqual(machine.rapid(Rapid(Point(30, 10), at_change=True)), ["G53 G0 X60 Z20"])

    def test_x_and_z_are_the_machine_position_or_else_the_work_position(self):
        template = "<code machine_coordinates> <code rapid> X<X> Z<Z>"
        self.assertEqual(engine(template, MACHINE_CHANGE).rapid(Rapid(Point(30, 10), at_change=True)), ["G53 G0 X60 Z20"])
        self.assertEqual(engine(template).rapid(Rapid(Point(30, 10), at_change=True)), ["G53 G0 X30 Z10"])

    def test_the_concept_wins_over_the_machine_rapid_of_the_post(self):
        instance = engine("G30 U0 W0", MACHINE_CHANGE)
        self.assertTrue(instance.has_change_position)
        self.assertEqual(instance.rapid(Rapid(Point(30, 10), at_change=True)), ["G30 U0 W0"])

    def test_the_position_is_not_known_afterwards(self):
        instance = engine("G28 U0 W0")
        instance.rapid(Rapid(Point(30, 10)))
        instance.rapid(Rapid(Point(30, 10), at_change=True))
        self.assertEqual(instance.rapid(Rapid(Point(30, 12))), ["X30 Z12"])  # both axes: X is not known to be unchanged (G0 stays: G28 is one-shot)

    def test_the_whole_program_writes_it_at_every_tool_change_and_at_the_end(self):
        project = project_from_json((ROOT / "examples" / "reference.wop.json").read_text(encoding="utf-8"))
        plan = planned(project.program)
        post = TemplatePost(parse_post(text("(go to the tool change position)\nG28 U0 W0"), "change"))
        context = make_context(project.program, plan, "t", "m", datetime(2026, 1, 1), machine=project.machine)
        code = generate_gcode(plan, post, PostSettings(XInputMode.DIAMETER), context=context).text.splitlines()
        changes = [i for i, line in enumerate(code) if line.endswith("M6")]
        self.assertTrue(changes)
        for at in changes:
            self.assertTrue(any(line.endswith("G28 U0 W0") for line in code[max(0, at - 6):at]), code[at - 6:at])  # before the tool is changed
        self.assertTrue(code[-1].endswith("M30") or any(line.endswith("G28 U0 W0") for line in code[-6:]))
        plain = generate_gcode(plan, TemplatePost(parse_post(text(None), "plain")), PostSettings(XInputMode.DIAMETER), context=context).text
        self.assertNotIn("G28", plain)


if __name__ == "__main__":
    unittest.main()
