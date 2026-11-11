"""write_text_atomically: one step, LF line ends, a line end at the end, the folder is made."""

import tempfile
import unittest
from pathlib import Path

from wop.core.files.atomic_file import TEMPORARY_SUFFIX, write_text_atomically


class AtomicFileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "new folder" / "file.json"

    def test_the_text_is_written_with_lf_and_a_final_line_end(self):
        write_text_atomically(self.path, "a\nb")
        self.assertEqual(self.path.read_bytes(), b"a\nb\n")

    def test_a_text_that_ends_with_a_line_end_gets_no_second_one(self):
        write_text_atomically(self.path, "a\n")
        self.assertEqual(self.path.read_bytes(), b"a\n")

    def test_the_old_file_is_replaced_and_no_temporary_file_is_left(self):
        write_text_atomically(self.path, "old")
        write_text_atomically(self.path, "new")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "new\n")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["file.json"])
        self.assertFalse(self.path.with_name(self.path.name + TEMPORARY_SUFFIX).exists())

    def test_the_encoding_is_used(self):
        write_text_atomically(self.path, "ä", "utf-8")
        self.assertEqual(self.path.read_bytes(), "ä\n".encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
