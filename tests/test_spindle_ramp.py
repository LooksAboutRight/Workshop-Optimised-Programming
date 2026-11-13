"""The speed ramp before a spindle stop: the post settings spindle_ramp_*, the template [spindle_ramp_step] and the token <spindle ramp>."""

import unittest
from pathlib import Path

from wop.core.geometry import Point
from wop.core.program_model.operations import LinearMove, SpindleDirection, SpindleMode, SpindleSetting
from wop.core.program_model.units import XInputMode
from wop.post.base import PostError, PostSettings
from wop.post.context import PostContext
from wop.post.engine import TemplatePost
from wop.post.post_definition import PostFileError, parse_post

LINUXCNC = Path(__file__).resolve().parent.parent / "wop" / "post" / "posts" / "linuxcnc.post.ini"
STEP = "[spindle_ramp_step]\n<code rpm> S<S> <spindle code>\n<code dwell> P<dwell decimals=1 zeros>\n"


def post_text(settings="spindle_ramp_step = 100\nspindle_ramp_min = 100\n", step=STEP, ramp_in_stop=True, ramp_in_change=True):
    text = LINUXCNC.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = text.replace("[settings]\n", "[settings]\n" + settings, 1)
    if ramp_in_change:
        text = text.replace("<code coolant_off>\n<code spindle_stop>\nT<tool number>", "<code coolant_off>\n<spindle ramp>\n<code spindle_stop>\nT<tool number>", 1)
    if ramp_in_stop:
        text = text.replace("[spindle_stop]\n<code spindle_stop>", "[spindle_stop]\n<spindle ramp>\n<code spindle_stop>", 1)
    return text + "\n" + step


def engine(context=None, **kwargs):
    instance = TemplatePost(parse_post(post_text(**kwargs), "ramp"), context or PostContext())
    instance.header(PostSettings(XInputMode.DIAMETER), [])
    return instance


RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 600)


class RampTests(unittest.TestCase):
    def test_a_stop_goes_down_in_steps_with_a_wait_each(self):
        instance = engine()
        instance.set_spindle(RPM)
        self.assertEqual(instance.stop_spindle(), ["G97 S500 M3", "G4 P1.0", "G97 S400 M3", "G4 P1.0", "G97 S300 M3", "G4 P1.0",
                                                   "G97 S200 M3", "G4 P1.0", "G97 S100 M3", "G4 P1.0", "M5"])

    def test_the_ramp_stops_at_the_minimum_and_without_a_ramp_nothing_changes(self):
        instance = engine(settings="spindle_ramp_step = 250\nspindle_ramp_min = 200\n")
        instance.set_spindle(RPM)
        self.assertEqual(instance.stop_spindle(), ["G97 S350 M3", "G4 P1.0", "M5"])  # the next step, 100, is below the minimum
        off = engine(settings="")
        off.set_spindle(RPM)
        self.assertEqual(off.stop_spindle(), ["M5"])

    def test_a_tool_change_slows_the_spindle_before_it_stops_and_a_stopped_spindle_is_not_slowed_again(self):
        instance = engine()
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 300))
        lines = instance.tool_change(2)
        self.assertEqual(lines[:2], ["M9", "G97 S200 M3"])
        self.assertIn("M5", lines)
        self.assertLess(lines.index("G97 S100 M3"), lines.index("M5"))
        self.assertEqual(instance.stop_spindle(), ["M5"])  # the spindle is off since the tool change: no second ramp

    def test_the_direction_of_the_last_start_is_kept(self):
        instance = engine()
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 200, direction=SpindleDirection.COUNTER_CLOCKWISE))
        self.assertEqual(instance.stop_spindle()[0], "G97 S100 M4")

    def test_a_ramp_in_constant_surface_speed_follows_the_radius_of_the_last_cut_and_the_limits(self):
        css = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 100, rpm_limit=2000)
        instance = engine(settings="spindle_ramp_step = 500\n")
        instance.set_spindle(css)
        instance.linear(LinearMove(Point(10, -5), 0.2))  # 100 m/min at a radius of 10 mm: 1591 rpm
        self.assertEqual(instance.stop_spindle()[::2][:3], ["G97 S1091 M3", "G97 S591 M3", "G97 S91 M3"])
        limited = engine(settings="spindle_ramp_step = 500\n")
        limited.set_spindle(css)
        limited.linear(LinearMove(Point(1, -5), 0.2))  # near the axis the speed would be 15915 rpm: the limit of the block stands
        self.assertEqual(limited.stop_spindle()[0], "G97 S1500 M3")
        machine = engine(PostContext(max_rpm=1200), settings="spindle_ramp_step = 500\n")
        machine.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 100))
        self.assertEqual(machine.stop_spindle()[0], "G97 S700 M3")  # no limit in the block: the highest speed of the machine

    def test_an_unknown_speed_is_refused_not_guessed(self):
        instance = engine()
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 100))
        with self.assertRaises(PostError) as caught:
            instance.stop_spindle()
        self.assertIn("rpm limit", str(caught.exception))

    def test_a_ramp_without_its_template_or_with_too_many_steps_is_refused(self):
        instance = engine(step="")
        instance.set_spindle(RPM)
        with self.assertRaises(PostError):
            instance.stop_spindle()
        many = engine(settings="spindle_ramp_step = 1\n")
        many.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 3000))
        with self.assertRaises(PostError):
            many.stop_spindle()

    def test_the_settings_are_numbers_that_are_not_negative(self):
        self.assertEqual(parse_post(post_text("spindle_ramp_step = 150,5\n"), "ramp").settings.spindle_ramp_step, 150.5)
        for bad in ("spindle_ramp_step = fast\n", "spindle_ramp_dwell = -1\n"):
            with self.assertRaises(PostFileError):
                parse_post(post_text(bad), "ramp")

    def test_the_example_post_writes_the_ramp(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "posts" / "linuxcnc_spindle_ramp.post.ini"
        instance = TemplatePost(parse_post(example.read_text(encoding="utf-8"), "example"), PostContext())
        instance.header(PostSettings(XInputMode.DIAMETER), [])
        instance.set_spindle(SpindleSetting(SpindleMode.CONSTANT_RPM, 300))
        self.assertEqual([line.split(" ", 1)[1] if line[:1] == "N" else line for line in instance.number_lines(instance.stop_spindle())][:2], ["G97 S200 M3", "G4 P1.0"])

    def test_the_token_works_only_where_a_stop_is_written(self):
        with self.assertRaises(Exception):
            parse_post(post_text().replace("[comment]\n", "[comment]\n<spindle ramp>\n", 1), "ramp")


if __name__ == "__main__":
    unittest.main()
