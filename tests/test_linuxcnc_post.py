"""What the shipped LinuxCNC post writes: the header calls the work offset, the tool change is safe and calls the tool offset,
G0, G1, G2 and G3 and their coordinates are written only when they changed.

This says nothing about what the G-code means for a machine: the user checks that on the lathe.
"""

import re
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from tests.helpers import planned
from wop.adapters.post_library import load_post_library
from tests.post_helpers import unnumbered
from wop.core.program_model.operations import CoolantMode, SpindleMode, SpindleSetting
from wop.core.program_model.units import XInputMode
from wop.post.base import PostSettings
from wop.post.engine import TemplatePost

from wop.core.blocks import BLOCK_TYPES  # noqa: F401  (registers the block types)
from wop.core.files.project_io import project_from_json
from wop.post.context import make_context
from wop.post.generate import find_issues, generate_gcode

REFERENCE = Path(__file__).resolve().parent.parent / "examples" / "reference.wop.json"
MOTION = re.compile(r"^(G0|G1|G2|G3)\b")


def reference_code(work_offset="G54", offsets=None) -> list[str]:
    project = project_from_json(REFERENCE.read_text(encoding="utf-8"))
    program = project.program
    if offsets:
        tools = tuple(replace(t, offset_number=offsets.get(t.number)) for t in program.tools)
        program = replace(program, tools=tools)
    plan = planned(program)
    context = make_context(program, plan, "Test", "Lathe", datetime(2026, 10, 23), work_offset=work_offset)
    post = TemplatePost(unnumbered(load_post_library().posts["linuxcnc"]))
    settings = PostSettings(XInputMode.DIAMETER)
    accepted = {issue.key for issue in find_issues(plan, post.info, settings) if issue.key is not None}
    return generate_gcode(plan, post, settings, accepted, context=context).text.splitlines()


class LinuxcncPostTests(unittest.TestCase):
    def test_the_header_calls_the_work_offset(self):
        for offset in ("G54", "G57", "G59.1"):
            lines = reference_code(offset)
            at = next(i for i, line in enumerate(lines) if line.startswith("G18"))
            self.assertEqual(lines[at + 1], offset)

    def test_a_tool_change_stops_coolant_and_spindle_and_calls_the_offset_on_the_next_line(self):
        lines = reference_code()
        changes = [i for i, line in enumerate(lines) if line.endswith("M6")]
        self.assertTrue(changes)
        for at in changes:
            self.assertEqual(lines[at - 2:at], ["M9", "M5"])
            number = re.match(r"T(\d+) M6", lines[at]).group(1)
            self.assertEqual(lines[at + 1], f"G43 H{number}")

    def test_a_tool_offset_of_its_own_is_called(self):
        lines = reference_code(offsets={1: 11})
        first = next(i for i, line in enumerate(lines) if line == "T1 M6")
        self.assertEqual(lines[first + 1], "G43 H11")
        second = next(i for i, line in enumerate(lines) if line == "T2 M6")
        self.assertEqual(lines[second + 1], "G43 H2")

    def test_motion_codes_and_coordinates_are_written_only_when_they_changed(self):
        lines = reference_code()
        self.assertNotIn("", lines)
        mode = None
        x = z = None
        for line in lines:
            if line.startswith("("):
                continue
            words = line.split()
            if words and MOTION.match(words[0]):
                self.assertNotEqual(words[0], mode, f"{line!r} repeats the motion code")
                mode = words[0]
            elif words and words[0][0] in "XZ":
                self.assertIsNotNone(mode, line)
            for word in words:
                if word[0] == "X" and x is not None:
                    self.assertNotEqual(float(word[1:]), x, f"{line!r} repeats X")
                if word[0] == "Z" and z is not None:
                    self.assertNotEqual(float(word[1:]), z, f"{line!r} repeats Z")
                if word[0] == "X":
                    x = float(word[1:])
                if word[0] == "Z":
                    z = float(word[1:])

    def test_arcs_keep_their_centre(self):
        arcs = [line for line in reference_code() if line.startswith(("G2", "G3"))]
        self.assertTrue(arcs)
        for line in arcs:
            self.assertRegex(line, r" I-?[\d.]+ K-?[\d.]+")


class SpindleAndCoolantTests(unittest.TestCase):
    """The coolant codes are written only when they changed; the spindle codes every time."""

    def post(self):
        return TemplatePost(unnumbered(load_post_library().posts["linuxcnc"]))

    def test_a_new_speed_writes_the_spindle_codes_again(self):
        post = self.post()
        post.settings = PostSettings(XInputMode.DIAMETER)
        rpm = lambda value: SpindleSetting(SpindleMode.CONSTANT_RPM, value)  # noqa: E731
        self.assertEqual(post.set_spindle(rpm(1000)), ["G97 S1000 M3"])
        self.assertEqual(post.set_spindle(rpm(1200)), ["G97 S1200 M3"])
        self.assertEqual(post.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 120)), ["G96 S120 M3"])

    def test_after_a_stop_the_spindle_is_started_again(self):
        post = self.post()
        post.settings = PostSettings(XInputMode.DIAMETER)
        post.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1000))
        self.assertEqual(post.stop_spindle(), ["M5"])
        self.assertEqual(post.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)), ["G97 S1000 M3"])

    def test_a_coolant_code_is_not_repeated(self):
        post = self.post()
        self.assertEqual(post.set_coolant(CoolantMode.FLOOD), ["M8"])
        self.assertEqual(post.set_coolant(CoolantMode.FLOOD), [])
        self.assertEqual(post.set_coolant(CoolantMode.NONE), ["M9"])
        self.assertEqual(post.set_coolant(CoolantMode.FLOOD), ["M8"])


if __name__ == "__main__":
    unittest.main()
