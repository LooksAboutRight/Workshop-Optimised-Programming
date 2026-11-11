"""Reading and writing post files on disk."""

import tempfile
import unittest
from pathlib import Path

from wop.adapters.post_files import load_post_file, load_post_folder, post_id_of, save_post_text
from wop.post.post_definition import PostFileError

FAKES = Path(__file__).resolve().parent / "data" / "posts"
GOOD = "[post]\nname = Good\nformat_version = 1\n[rapid]\nG0 X<X>\n"


class PostFileTests(unittest.TestCase):
    def test_the_id_is_the_file_name_without_the_suffix(self):
        self.assertEqual(post_id_of(Path("a/linuxcnc.post.ini")), "linuxcnc")
        self.assertEqual(post_id_of(Path("odd.ini")), "odd")

    def test_a_file_is_read(self):
        definition = load_post_file(FAKES / "fake_motion.post.ini")
        self.assertEqual((definition.post_id, definition.name), ("fake_motion", "Fake motion"))

    def test_a_bad_file_names_itself_and_the_place(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.post.ini"
            path.write_text(GOOD + "G1 <Y>\n", encoding="utf-8")
            with self.assertRaises(PostFileError) as caught:
                load_post_file(path)
        self.assertIn("bad.post.ini", str(caught.exception))
        self.assertIn("unknown token <Y>", str(caught.exception))

    def test_a_file_that_is_not_there(self):
        with self.assertRaises(PostFileError):
            load_post_file(Path("nowhere.post.ini"))

    def test_saving_writes_the_text_as_it_is_also_with_problems(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mine.post.ini"
            save_post_text(path, GOOD + "<Q>")  # an unfinished post is saved: the editor shows the problems
            self.assertTrue(path.exists())
            save_post_text(path, GOOD.rstrip(chr(10)))
            self.assertEqual(path.read_text(encoding="utf-8"), GOOD)
            self.assertEqual(load_post_file(path).name, "Good")

    def test_one_bad_file_in_a_folder_does_not_stop_the_others(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "good.post.ini").write_text(GOOD, encoding="utf-8")
            (Path(folder) / "bad.post.ini").write_text("nonsense", encoding="utf-8")
            (Path(folder) / "other.txt").write_text("x", encoding="utf-8")
            posts, problems = load_post_folder(Path(folder))
        self.assertEqual(list(posts), ["good"])
        self.assertEqual(len(problems), 1)
        self.assertIn("bad.post.ini", problems[0])

    def test_a_missing_folder_is_empty(self):
        self.assertEqual(load_post_folder(Path("no_such_folder")), ({}, []))


if __name__ == "__main__":
    unittest.main()
