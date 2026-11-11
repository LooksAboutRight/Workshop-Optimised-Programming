"""The compiled modules (`tools/build_compiled.py`, mypyc) belong to the sources as they are now: Python takes a compiled file instead
of its source, so one that is older than its source would hide a change of the code."""

import unittest
from pathlib import Path

from wop.core.compiled import COMPILED_MODULES, compiled_files, stale_compiled

ROOT = Path(__file__).resolve().parent.parent


class CompiledCurrentTests(unittest.TestCase):
    def test_no_compiled_module_is_older_than_its_source(self):
        stale = stale_compiled(ROOT)
        self.assertEqual(stale, [], "run python tools/build_compiled.py (or --clean to run as plain Python)")

    def test_the_list_names_existing_sources(self):
        for module in COMPILED_MODULES:
            with self.subTest(module=module):
                self.assertTrue((ROOT / module).is_file())

    def test_the_compiled_files_are_found(self):
        for path in compiled_files(ROOT):
            self.assertTrue(path.suffix in (".pyd", ".so"))


if __name__ == "__main__":
    unittest.main()
