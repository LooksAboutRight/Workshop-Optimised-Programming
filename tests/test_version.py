"""One version: the number in pyproject.toml is the one the post token <WOP version> writes."""

import tomllib
import unittest
from pathlib import Path

from wop.post.post_constants import WOP_VERSION_TEXT

ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    def test_the_version_of_the_program_and_of_the_package_are_the_same(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["version"], WOP_VERSION_TEXT)


if __name__ == "__main__":
    unittest.main()
