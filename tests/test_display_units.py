"""The window can show inches while the program, the files and the G-code stay as they are (requirement M14)."""

import unittest
from unittest import mock

from wop.core.program_model.units import XInputMode
from wop.ui import app_constants, display_units
from wop.ui.block_forms import FieldKind, FieldSpec, FormError, from_display, parse_text, to_display

FEED = FieldSpec(("feed_mm_per_rev",), "Feed", FieldKind.FLOAT, "mm/rev")
RADIUS = FieldSpec(("r_mm",), "X radius", FieldKind.FLOAT, "mm", is_radius=True)
LIMITED = FieldSpec(("v",), "Length", FieldKind.OPTIONAL_FLOAT, "mm", minimum=0, maximum=50)
ANGLE = FieldSpec(("a_deg",), "Angle", FieldKind.FLOAT, "deg")


def inches():
    return mock.patch.object(app_constants, "DISPLAY_UNITS", "inch")


class DisplayUnitTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(app_constants, "DISPLAY_UNITS", "mm")  # whatever the user chose in Preferences
        patch.start()
        self.addCleanup(patch.stop)

    def test_millimetres_are_the_default(self):
        self.assertEqual(to_display(FEED, 0.254, XInputMode.RADIUS), 0.254)
        self.assertEqual(display_units.shown_unit("mm/rev"), "mm/rev")

    def test_lengths_and_feeds_are_shown_in_inches(self):
        with inches():
            self.assertAlmostEqual(to_display(RADIUS, 25.4, XInputMode.RADIUS), 1)
            self.assertAlmostEqual(to_display(RADIUS, 25.4, XInputMode.DIAMETER), 2)  # a diameter, in inches
            self.assertAlmostEqual(to_display(FEED, 0.254, XInputMode.RADIUS), 0.01)
            self.assertEqual([display_units.shown_unit(u) for u in ("mm", "mm/rev", "mm/min")], ["in", "in/rev", "in/min"])

    def test_what_is_not_a_length_stays(self):
        with inches():
            self.assertEqual(to_display(ANGLE, 45, XInputMode.RADIUS), 45)
            self.assertEqual(display_units.shown_unit("deg"), "deg")
            self.assertEqual(display_units.shown_unit("RPM"), "RPM")

    def test_typing_in_inches_gives_the_same_millimetres(self):
        with inches():
            for spec in (FEED, RADIUS):
                for mode in XInputMode:
                    self.assertAlmostEqual(from_display(spec, to_display(spec, 12.7, mode), mode), 12.7)
            self.assertAlmostEqual(from_display(RADIUS, 1, XInputMode.RADIUS), 25.4)

    def test_an_empty_optional_number_stays_empty_and_limits_are_in_millimetres(self):
        with inches():
            self.assertIsNone(to_display(LIMITED, None, XInputMode.RADIUS))
            self.assertAlmostEqual(parse_text(LIMITED, "1"), 1)  # 25.4 mm: inside 0 to 50
            with self.assertRaises(FormError):
                parse_text(LIMITED, "3")  # 76.2 mm

    def test_messages_get_their_lengths_in_inches(self):
        text = "the feed 0.254 mm/rev is too high; the groove 25.4 mm wide at 508 mm/min, 210 N/mm2, M8, 10 mm2"
        self.assertEqual(display_units.shown_text(text), text)  # metric: as it is
        with inches():
            self.assertEqual(
                display_units.shown_text(text),
                "the feed 0.01 in/rev is too high; the groove 1 in wide at 20 in/min, 210 N/mm2, M8, 10 mm2",
            )
            self.assertEqual(display_units.shown_text("Z -12.7 mm and 0.05 mm"), "Z -0.5 in and 0.002 in")

    def test_cutting_speed_has_a_unit_that_follows_the_mode_and_is_shown_in_feet_per_minute(self):
        from dataclasses import dataclass, replace

        from wop.core.program_model.operations import SpindleMode, SpindleSetting
        from wop.ui.block_forms import form_for

        @dataclass(frozen=True)
        class Holder:
            spindle: SpindleSetting

        css = SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, 100)
        for spindle, unit in ((css, "m/min"), (replace(css, mode=SpindleMode.CONSTANT_RPM), "RPM")):
            specs = {s.path: s for s in form_for(Holder(spindle))}
            self.assertEqual(specs[("spindle", "value")].unit, unit)
            self.assertEqual(specs[("spindle", "rpm_limit")].unit, "RPM")
        value = {s.path: s for s in form_for(Holder(css))}[("spindle", "value")]
        self.assertAlmostEqual(to_display(value, 100, XInputMode.RADIUS), 100)
        with inches():
            self.assertAlmostEqual(to_display(value, 100, XInputMode.RADIUS), 328.084, places=3)
            self.assertAlmostEqual(from_display(value, 328.084, XInputMode.RADIUS), 100, places=2)
            self.assertEqual(display_units.shown_unit("m/min"), "ft/min")
            self.assertEqual(display_units.shown_unit("RPM"), "RPM")
            self.assertEqual(display_units.shown_text("CSS 100 m/min (max 3000 rpm), 2 mm"), "CSS 328 ft/min (max 3000 rpm), 0.0787 in")

    def test_iso_tool_forms_stay_in_millimetres(self):
        from wop.core.tool_types.holder import HolderDefinition
        from wop.ui.block_forms import form_for, spec_scale, spec_unit

        with inches():
            specs = form_for(HolderDefinition())
            self.assertTrue(specs)
            self.assertTrue(all(spec.metric and spec_scale(spec) == 1 and spec_unit(spec) == spec.unit for spec in specs))


if __name__ == "__main__":
    unittest.main()
