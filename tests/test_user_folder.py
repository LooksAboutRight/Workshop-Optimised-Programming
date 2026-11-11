import tempfile
import unittest
from pathlib import Path

from wop.core.files.user_folder import APP_FOLDER_NAME, PORTABLE_FOLDER_NAME, user_folder


class UserFolderTests(unittest.TestCase):
    def test_without_a_portable_folder_the_per_user_place_is_used(self):
        with tempfile.TemporaryDirectory() as program:
            self.assertEqual(user_folder(Path(program)).name, APP_FOLDER_NAME)

    def test_a_user_data_folder_next_to_the_program_wins(self):
        with tempfile.TemporaryDirectory() as program:
            (Path(program) / PORTABLE_FOLDER_NAME).mkdir()
            self.assertEqual(user_folder(Path(program)), Path(program) / PORTABLE_FOLDER_NAME)

    def test_a_file_with_that_name_does_not_count(self):
        with tempfile.TemporaryDirectory() as program:
            (Path(program) / PORTABLE_FOLDER_NAME).write_text("x")
            self.assertEqual(user_folder(Path(program)).name, APP_FOLDER_NAME)


if __name__ == "__main__":
    unittest.main()
