"""The tip of the tool swept along a straight move as one region (wop/core/geometry/tip_sweep.py), against the strips of its cutting edges."""

import math
import unittest
from pathlib import Path

from wop.core.geometry import LineSegment, Point

from wop.adapters.project_files import load_project
from wop.core.geometry.chains import loop_area, region_of_loops
from wop.core.geometry.removal import strips
from wop.core.geometry.tip_sweep import swept_tip, tip_hull
from wop.core.analytic.tool_outline import tool_loops
from wop.core.geometry.tool_edges import ToolEdge, translated_segment

ROOT = Path(__file__).resolve().parent.parent


class TipSweepTests(unittest.TestCase):
    def setUp(self):
        program = load_project(ROOT / "examples" / "left_hand_rest_machining.wop.json").program
        self.tool = tool_loops(program.equipped_tool(1))

    def test_a_turning_tool_has_a_convex_tip(self):
        hull = tip_hull(self.tool)
        self.assertIsNotNone(hull)
        self.assertGreater(loop_area(hull), 0)  # counter-clockwise

    def test_the_swept_tip_covers_the_strips_and_the_tip_at_both_ends_and_nothing_more(self):
        hull = tip_hull(self.tool)
        start = Point(20, -5)
        for degrees in (0, 30, 90, 135, 180, 200, 270, 315):
            with self.subTest(direction=degrees):
                angle = math.radians(degrees)
                vector = (3 * math.cos(angle), 3 * math.sin(angle))
                swept = region_of_loops([swept_tip(hull, start, vector)])
                reference = region_of_loops(strips(self.tool, start, vector))
                for at in (start, Point(start.x + vector[0], start.z + vector[1])):
                    reference = reference.union(region_of_loops([tuple(translated_segment(segment, at.x, at.z) for segment in hull)]))
                self.assertLess(swept.difference(reference).area, 0.01)  # nothing more than the tip sweeps
                self.assertLess(reference.difference(swept).area, 0.01)  # and all of it (the arcs are chords in the referee)

    def test_cutting_edges_that_are_not_one_run_have_no_tip(self):
        corners = [Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4)]
        edges = [LineSegment(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]
        two_runs = [tuple(ToolEdge(edge, number % 2 == 0) for number, edge in enumerate(edges))]  # the bottom and the top cut, the sides do not
        self.assertIsNone(tip_hull(two_runs))

    def test_a_tip_whose_chord_leaves_the_tool_has_no_tip(self):
        # a notch: the cutting run goes up into it and down again, the chord across it runs outside the tool
        corners = [Point(0, 0), Point(2, 1), Point(4, 0), Point(4, 4), Point(0, 4)]
        edges = [LineSegment(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]
        notch = [tuple(ToolEdge(edge, number < 2) for number, edge in enumerate(edges))]
        self.assertIsNone(tip_hull(notch))


if __name__ == "__main__":
    unittest.main()
