import math
import unittest

from wop.core.tooling.tool import ToolError
from wop.core.tooling.tool_presets import drill_tool


class DrillPresetTests(unittest.TestCase):
    def test_a_118_degree_8_mm_drill_has_the_expected_outline(self):
        drill = drill_tool(1, "drill 8", diameter_mm=8, flute_length_mm=40, tip_angle_deg=118)
        pieces = drill.shape.pieces
        lip, flute = pieces[0].segment, pieces[1].segment
        self.assertAlmostEqual(lip.end.x, 4)
        self.assertAlmostEqual(lip.end.z, 4 / math.tan(math.radians(59)))
        self.assertAlmostEqual(flute.end.z, 40)
        self.assertAlmostEqual(max(p.segment.end.z for p in pieces), 40 + 30)
        self.assertEqual([p.role.value for p in pieces], ["cutter", "cutter", "holder", "holder", "cutter"])

    def test_impossible_drills_are_refused(self):
        for values in (dict(diameter_mm=0), dict(tip_angle_deg=0), dict(tip_angle_deg=200), dict(flute_length_mm=1)):
            with self.subTest(values=values), self.assertRaises(ToolError):
                drill_tool(1, "d", **values)


if __name__ == "__main__":
    unittest.main()
