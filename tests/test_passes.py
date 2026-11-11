import unittest

from wop.core.passes import pass_levels


class PassLevelTests(unittest.TestCase):
    def test_equal_steps_and_last_pass_at_the_end(self):
        levels = pass_levels(15, 10, 2)
        self.assertEqual(len(levels), 3)
        self.assertAlmostEqual(levels[0], 15 - 5 / 3)
        self.assertEqual(levels[-1], 10)

    def test_steps_never_exceed_the_maximum(self):
        levels = pass_levels(0, -10, 3)
        steps = [a - b for a, b in zip([0] + levels, levels)]
        self.assertTrue(all(step <= 3 + 1e-9 for step in steps))

    def test_exact_multiple(self):
        self.assertEqual(len(pass_levels(0, 6, 2)), 3)

    def test_ascending(self):
        self.assertEqual(pass_levels(7, 9.8, 1)[-1], 9.8)

    def test_one_pass_if_step_is_larger_than_the_distance(self):
        self.assertEqual(pass_levels(0, -1, 5), [-1])

    def test_no_passes_if_start_equals_end(self):
        self.assertEqual(pass_levels(3, 3, 1), [])


if __name__ == "__main__":
    unittest.main()
