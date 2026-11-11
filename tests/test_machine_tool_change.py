"""The tool change position of the machine in machine coordinates (G53), the folders of the file dialogs and the name of the G-code file."""

import unittest
from dataclasses import replace
from pathlib import Path

from wop.core.geometry import Point
from wop.core.program_model.operations import Rapid
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings
from wop.post.context import PostContext
from wop.post.engine import TemplatePost
from wop.post.post_definition import parse_post

LINUXCNC = Path(__file__).resolve().parent.parent / "wop" / "post" / "posts" / "linuxcnc.post.ini"


def post(context: PostContext) -> TemplatePost:
    instance = TemplatePost(parse_post(LINUXCNC.read_text(encoding="utf-8"), LINUXCNC.stem), context)
    instance.settings = PostSettings(XInputMode.DIAMETER)
    return instance


class MachineToolChangeTests(unittest.TestCase):
    def test_the_move_to_the_change_position_is_written_in_machine_coordinates_with_the_diameter(self):
        instance = post(PostContext(change_radius_mm=60, change_z_mm=-150))
        self.assertEqual(instance.rapid(Rapid(Point(25, 10), at_change=True)), ["G53 G0 X120 Z-150"])
        self.assertEqual(instance.tool_change(2), ["M9", "M5", "T2 M6", "G43 H2"])

    def test_any_other_rapid_move_stays_in_work_coordinates(self):
        instance = post(PostContext(change_radius_mm=60, change_z_mm=-150))
        self.assertEqual(instance.rapid(Rapid(Point(25, 10))), ["G0 X50 Z10"])

    def test_without_a_machine_position_the_move_is_written_in_work_coordinates(self):
        instance = post(PostContext())
        self.assertEqual(instance.rapid(Rapid(Point(25, 10), at_change=True)), ["G0 X50 Z10"])
        self.assertEqual(instance.tool_change(2), ["M9", "M5", "T2 M6", "G43 H2"])

    def test_both_axes_are_written_by_the_next_move(self):
        instance = post(PostContext(change_radius_mm=60, change_z_mm=-150))
        instance.rapid(Rapid(Point(30, 5)))
        instance.rapid(Rapid(Point(25, 10), at_change=True))
        self.assertEqual(instance.rapid(Rapid(Point(30, 5))), ["X60 Z5"])  # G0 is still the motion mode of the controller


if __name__ == "__main__":
    unittest.main()
