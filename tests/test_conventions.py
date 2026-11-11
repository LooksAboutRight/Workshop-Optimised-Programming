"""Requirements A1 and A5: the core stays free of UI, LinuxCNC and magic numbers."""

import importlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKER_PATH = PROJECT_ROOT / "tools" / "check_conventions.py"
CORE_DIR = PROJECT_ROOT / "wop" / "core"
FORBIDDEN_TOP_LEVEL_MODULES = ("PySide6", "PyQt5", "PyQt6", "gi", "linuxcnc", "tkinter")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_conventions", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IMPORT_ALL_CORE = """
import importlib, pkgutil, sys
import wop.core
for info in pkgutil.iter_modules(wop.core.__path__):
    importlib.import_module("wop.core." + info.name)
print(",".join(name for name in %r if name in sys.modules))
"""


class CoreIndependenceTests(unittest.TestCase):
    def test_every_core_module_imports_without_gui_or_linuxcnc(self):
        # In a fresh interpreter: other tests in the same run may have imported a GUI toolkit already.
        result = subprocess.run(
            [sys.executable, "-c", IMPORT_ALL_CORE % (FORBIDDEN_TOP_LEVEL_MODULES,)],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")


class ConventionTests(unittest.TestCase):
    def test_core_has_no_violations(self):
        checker = load_checker()
        self.assertEqual(checker.find_violations(CORE_DIR), [])

    def test_checker_finds_a_module_dict_and_a_forbidden_import(self):
        checker = load_checker()
        sample = PROJECT_ROOT / "tests" / "_sample_bad_module.py"
        sample.write_text(
            "from wop.ui import something\nLIMITS = {'a': 1}\nvalue = 42 * 3.14\n",
            encoding="utf-8",
        )
        try:
            problems = checker.check_file(sample)
        finally:
            sample.unlink()
        text = "\n".join(problems)
        self.assertIn("forbidden import wop.ui", text)
        self.assertIn("module-level dict", text)
        self.assertNotIn("numeric literal", text)  # numbers are a rule for the reader now, not for the checker (the user's decision, 2026-10-22)


if __name__ == "__main__":
    unittest.main()
