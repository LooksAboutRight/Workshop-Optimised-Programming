import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from make_animation import add_caption, choose_numbers, parallel_tasks, parse_blocks, select_frames_by_time, write_png_folder  # noqa: E402


class MakeAnimationHelperTests(unittest.TestCase):
    def test_caption_goes_inside_the_svg_and_is_escaped(self):
        text = add_caption('<svg viewBox="0 0 10 10"></svg>', "a < b & c")
        self.assertIn("a &lt; b &amp; c", text)
        self.assertTrue(text.rstrip().endswith("</svg>"))

    def test_real_time_picks_frames_by_machine_time(self):
        seconds = [1.0] * 10  # 10 s of machining
        picked = select_frames_by_time(seconds, fps=1, speedup=2)  # every 2 s of machine time
        self.assertEqual(picked[0], 0)
        self.assertEqual(picked[-1], 9)
        self.assertLess(len(picked), 10)
        self.assertEqual(picked, sorted(picked))

    def test_real_time_needs_positive_numbers(self):
        with self.assertRaises(ValueError):
            select_frames_by_time([1.0], fps=0, speedup=1)

    def test_blocks_are_counted_from_one(self):
        self.assertIsNone(parse_blocks(None))
        self.assertEqual(parse_blocks("3"), range(2, 3))
        self.assertEqual(parse_blocks("2-4"), range(1, 4))
        for bad in ("0", "4-2", "x"):
            with self.assertRaises(ValueError):
                parse_blocks(bad)

    def test_tasks_split_the_chosen_frames_by_block(self):
        entries = [(0, 1.0), (0, 1.0), (1, 1.0), (1, 1.0), (1, 1.0)]
        tasks = parallel_tasks(entries, [1, 3, 4], "f")
        self.assertEqual(tasks, [(0, 0, [1], "f"), (1, 2, [3, 4], "f")])

    def test_max_frames_limits_the_choice(self):
        self.assertEqual(choose_numbers([1.0] * 10, None, 25, 3), [0, 1, 2])

    def test_png_folder_numbers_the_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(write_png_folder([b"a", b"b"], Path(folder) / "f"), 2)
            self.assertTrue((Path(folder) / "f" / "frame_000002.png").exists())


if __name__ == "__main__":
    unittest.main()
