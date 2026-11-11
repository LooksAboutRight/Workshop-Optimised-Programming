"""Field order of the turning contour, custom path, G-code and machine function forms."""

import unittest

from wop.core.program_model.operations import SpindleMode, SpindleSetting

from wop.core.blocks import BLOCK_TYPES
from wop.ui.block_forms import form_for

SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 800)


def paths(type_name):
    block = BLOCK_TYPES.get(type_name).example("b", 1, SPINDLE)
    return [".".join(spec.path) for spec in form_for(block)], {".".join(s.path): s.label for s in form_for(block)}


class FormOrderTests(unittest.TestCase):
    def test_turning_contour_has_the_style_and_the_contour_right_after_the_name_and_the_finishing_like_turning(self):
        names, labels = paths("turning_contour")
        self.assertEqual(names[:6], ["name", "style", "contour_id", "side", "pass_direction", "tool_number"])
        self.assertEqual(names[-1], "coolant")
        self.assertEqual(labels["finish_feed_mm_per_rev"], "Finishing feed")
        # the finishing as in turning: allowance, the checkbox, its feed and speed; the plunge fields after them
        order = ["finish_allowance_mm", "finish_pass", "finish_feed_mm_per_rev", "finish_spindle_value",
                 "plunge_feed_mm_per_rev", "plunge_depth_of_cut_mm", "min_free_angle_deg"]
        self.assertEqual([n for n in names if n in order], order)

    def test_custom_path_has_feed_and_the_draw_button_only(self):
        names, _ = paths("custom_path")
        self.assertEqual(names, ["name", "tool_number", "spindle.direction", "spindle.mode", "spindle.value", "spindle.rpm_limit", "feed_mm_per_rev", "coolant", "draw_path"])

    def test_machine_function_shows_the_dwell_only_for_a_dwell(self):
        names, _ = paths("machine_function")
        self.assertEqual(names, ["name", "function"])
