"""The spindle direction: a field of the spindle setting of every block (clockwise unless the user says otherwise), kept by the planner,
written by the post as the code of its controller (M3 or M4 for LinuxCNC), and refused with a reason by a post that cannot reverse."""

import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import planned
from tests.post_helpers import limited_post, shipped_post
from tests.reference_program import reference_program
from wop.core.files.project_io import project_from_json, project_to_json
from wop.core.program_model.operations import SpindleDirection, SpindleMode, SpindleSetting, finishing_spindle
from wop.post.base import Feature, PostSettings
from wop.post.generate import find_issues, generate_gcode
from wop.core.program_model.units import XInputMode
from wop.ui.app_model import AppModel
from wop.ui.block_forms import form_for

CW, CCW = SpindleDirection.CLOCKWISE, SpindleDirection.COUNTER_CLOCKWISE
DIAMETER = PostSettings(XInputMode.DIAMETER)


def rpm(value, direction=CW):
    return SpindleSetting(SpindleMode.CONSTANT_RPM, value, direction=direction)


class SettingTests(unittest.TestCase):
    def test_a_spindle_runs_clockwise_unless_told_otherwise(self):
        self.assertIs(SpindleSetting(SpindleMode.CONSTANT_RPM, 100).direction, CW)

    def test_a_finishing_speed_keeps_the_direction(self):
        self.assertIs(finishing_spindle(rpm(500, CCW), 800).direction, CCW)

    def test_the_form_of_every_block_offers_the_direction_above_the_mode(self):
        model = AppModel()
        for type_name in model.block_types():
            with self.subTest(type_name):
                index = model.add_block(type_name)
                block = model.blocks[index]
                if not block.needs_tool:
                    continue
                paths = [".".join(spec.path) for spec in form_for(block, model.form_context())]
                at = paths.index("spindle.direction")
                self.assertIn(paths[at + 1], ("spindle.mode", "spindle.value"))  # a thread has a fixed speed: no mode
                self.assertLess(paths.index("tool_number"), at)

    def test_a_new_block_turns_clockwise_whatever_the_block_before_did(self):
        model = AppModel()
        first = model.add_block("turning")
        model.replace_block(first, replace(model.blocks[first], spindle=rpm(500, CCW)))
        model.select(first)
        second = model.add_block("facing")
        self.assertIs(model.blocks[second].spindle.direction, CW)

    def test_the_direction_survives_the_project_file(self):
        model = AppModel()
        index = model.add_block("turning")
        model.replace_block(index, replace(model.blocks[index], spindle=rpm(500, CCW)))
        again = project_from_json(project_to_json(model.project))
        self.assertIs(again.program.blocks[index].spindle.direction, CCW)


class PostTests(unittest.TestCase):
    def test_linuxcnc_writes_m3_and_m4(self):
        post = shipped_post()
        post.settings = DIAMETER
        self.assertEqual(post.set_spindle(rpm(1000)), ["G97 S1000 M3"])
        self.assertEqual(post.set_spindle(rpm(1000, CCW)), ["G97 S1000 M4"])
        self.assertEqual(post.set_spindle(rpm(1200, CCW)), ["G97 S1200 M4"])
        self.assertEqual(post.stop_spindle(), ["M5"])
        self.assertEqual(post.set_spindle(rpm(800, CCW)), ["G97 S800 M4"])

    def test_a_surface_speed_can_run_counter_clockwise(self):
        post = shipped_post()
        post.settings = DIAMETER
        lines = post.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120, 3000, direction=CCW))
        self.assertEqual(lines, ["G96 D3000 S120 M4"])

    def test_a_post_that_cannot_reverse_says_so_and_leaves_the_block_out(self):
        program = reference_program()
        blocks = list(program.blocks)
        blocks[0] = replace(blocks[0], spindle=rpm(800, CCW))
        program = replace(program, blocks=tuple(blocks))
        plan = planned(program)
        post = limited_post({Feature.SPINDLE_REVERSE})
        issues = find_issues(plan, post.info, DIAMETER)
        reasons = [issue.message for issue in issues if issue.block_index == 0 and "counter-clockwise" in issue.message]
        self.assertTrue(reasons)
        result = generate_gcode(plan, post, DIAMETER, {issue.key for issue in issues if issue.key is not None})
        self.assertIn(0, result.skipped_blocks)
        self.assertNotIn("M4", result.text)


if __name__ == "__main__":
    unittest.main()
