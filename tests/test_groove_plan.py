import unittest

from wop.core.blocks.groove_plan import finish_steps, rough_plunges


def covered(plunges, blade):
    return sorted((z, z + blade) for z in plunges)


class RoughPlungeTests(unittest.TestCase):
    def test_a_groove_as_wide_as_the_blade_gets_one_plunge(self):
        self.assertEqual(rough_plunges(-10, -7, 3, 1), [-10])

    def test_the_front_wall_gets_a_surrounded_plunge_and_a_one_sided_one(self):
        # groove 0..6, blade 3: 2 (surrounded), 3 (the wall cut takes the strip 5..6), then steps of 1 to the other wall
        self.assertEqual(rough_plunges(0, 6, 3, 1), [2, 3, 1, 0])

    def test_a_plunge_that_would_cut_only_air_is_left_out(self):
        self.assertEqual(rough_plunges(0, 4.5, 3, 1), [0.5, 1.5, 0])

    def test_a_real_groove_goes_in_steps_of_the_limit_towards_the_chuck(self):
        plunges = rough_plunges(-47.8, -40.2, 3, 1)
        self.assertEqual([round(z, 3) for z in plunges], [-44.2, -43.2, -45.2, -46.2, -47.2, -47.8])

    def test_a_wide_groove_goes_in_the_same_steps_all_the_way(self):
        plunges = rough_plunges(-59.8, -40.2, 3, 1)
        self.assertEqual([round(z, 3) for z in plunges[:6]], [-44.2, -43.2, -45.2, -46.2, -47.2, -48.2])
        self.assertAlmostEqual(plunges[-1], -59.8)
        chain = [plunges[0], *plunges[2:]]  # the front wall plunge adds nothing below the first one
        steps = [a - b for a, b in zip(chain, chain[1:])]
        self.assertTrue(all(step <= 1 + 1e-9 for step in steps))

    def test_every_plunge_after_the_first_cuts_at_most_the_limit_on_one_side(self):
        blade, cap = 3, 1
        for width in (4.5, 5, 6, 7.6, 8, 9, 12.3, 20, 41):
            plunges = rough_plunges(0, width, blade, cap)
            self.assertEqual(plunges[1], width - blade)  # the front wall plunge is the second one
            self.assertEqual(plunges[-1], 0)             # the wall nearer the chuck is the last one
            lowest = plunges[0]  # what is cleared reaches down to the lowest tip so far
            for z in plunges[1:]:
                self.assertLessEqual(lowest - z, cap + 1e-9, (width, plunges))  # the strip it takes on its chuck side
                lowest = min(lowest, z)

    def test_the_whole_groove_is_covered_without_gaps(self):
        for width in (4.5, 6, 9, 12.3, 20, 41):
            spans = covered(rough_plunges(0, width, 3, 1), 3)
            self.assertAlmostEqual(spans[0][0], 0)
            self.assertAlmostEqual(spans[-1][1], width)
            for (_a, end), (start, _b) in zip(spans, spans[1:]):
                self.assertGreaterEqual(end, start)

    def test_a_one_sided_cut_as_wide_as_the_blade_needs_no_first_plunge(self):
        self.assertEqual(rough_plunges(0, 6, 3, 3), [3, 0])


class FinishStepTests(unittest.TestCase):
    def test_a_narrow_groove_gets_one_plunge(self):
        self.assertEqual(finish_steps(0, 3, 3, 1.5), [(0, None)])

    def test_up_to_two_blades_the_two_plunges_cover_the_bottom(self):
        self.assertEqual(finish_steps(0, 5, 3, 1.5), [(2, None), (0, None)])
        self.assertEqual(finish_steps(0, 6, 3, 1.5), [(3, None), (0, None)])

    def test_a_wide_groove_gets_two_passes_that_overlap_by_one_blade(self):
        steps = finish_steps(0, 20, 3, 1.5)
        self.assertEqual(steps, [(17, 1.5), (0, 1.5)])  # both end at the same place: that strip is passed twice
