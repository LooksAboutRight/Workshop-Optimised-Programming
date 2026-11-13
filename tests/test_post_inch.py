"""G-code in inches: the unit of the machine sets the units code, scales lengths and feeds and picks the inch decimals."""

import unittest

from wop.core.geometry import Point
from wop.core.program_model.operations import LinearMove, SpindleMode, SpindleSetting
from wop.core.program_model.units import UnitSystem, XInputMode
from wop.post.base import PostSettings
from wop.post.engine import TemplatePost
from wop.post.post_definition import parse_post

POST = """[post]
name = Inch
format_version = 1

[settings]
decimals = 3
decimals_inch = 4
feed_decimals = 3
feed_decimals_inch = 5

[codes]
rapid = G0
feed = G1
css = G96
rpm = G97
units_mm = G21
units_inch = G20

[setup]
<units code>

[rapid]
<code rapid> X<X> Z<Z>

[feed]
<code feed> X<X> Z<Z> F<F>

[spindle_css]
<code css> S<S>

[spindle_rpm]
<code rpm> S<S>
"""


def post(unit):
    instance = TemplatePost(parse_post(POST, "inch"))
    lines = instance.header(PostSettings(XInputMode.RADIUS, unit), [])
    return instance, lines


class InchOutputTests(unittest.TestCase):
    def test_the_units_code_follows_the_unit(self):
        self.assertEqual(post(UnitSystem.METRIC)[1], ["G21"])
        self.assertEqual(post(UnitSystem.IMPERIAL)[1], ["G20"])

    def test_millimetres_stay_as_they_are(self):
        instance, _ = post(UnitSystem.METRIC)
        self.assertEqual(instance.linear(LinearMove(Point(25.4, -12.7), 0.254)), ["G1 X25.4 Z-12.7 F0.254"])

    def test_lengths_and_feeds_are_converted_with_the_inch_decimals(self):
        instance, _ = post(UnitSystem.IMPERIAL)
        self.assertEqual(instance.linear(LinearMove(Point(25.4, -12.7), 0.254)), ["G1 X1 Z-0.5 F0.01"])
        self.assertEqual(instance.linear(LinearMove(Point(10, -3), 0.2)), ["G1 X0.3937 Z-0.1181 F0.00787"])

    def test_constant_surface_speed_is_in_feet_per_minute_and_rpm_is_not_converted(self):
        instance, _ = post(UnitSystem.IMPERIAL)
        self.assertEqual(instance.set_spindle(SpindleSetting(mode=SpindleMode.CONSTANT_SURFACE_SPEED, value=100)), ["G96 S328.1"])
        self.assertEqual(instance.set_spindle(SpindleSetting(mode=SpindleMode.CONSTANT_RPM, value=1200)), ["G97 S1200"])


if __name__ == "__main__":
    unittest.main()
