"""Source files and functions stay small enough to read.

A file of more than FILE_LIMIT lines or a function of more than FUNCTION_LIMIT lines fails this test, unless it is listed
below with the reason why splitting it does not make sense. Most of the time the better answer is to split it (a part
by topic, as `wop/ui/model/` does for `AppModel`). An exception whose file or function got short enough must be removed
from the list, so the list only ever shrinks. Tests are not counted (a test module is a list of small independent tests).
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE_LIMIT = 600  # lines of a source file
FUNCTION_LIMIT = 200  # lines of a function or method
SCANNED = ("wop", "tools", "hosts")
SKIPPED_PARTS = ("sandbox_standin", "__pycache__")

# path -> reason why it may be longer. (empty reason is not accepted)
FILE_EXCEPTIONS: dict[str, str] = {}
# "path:function" -> reason
FUNCTION_EXCEPTIONS: dict[str, str] = {}


def source_files():
    for folder in SCANNED:
        for path in sorted((ROOT / folder).rglob("*.py")):
            if not any(part in path.parts for part in SKIPPED_PARTS):
                yield path


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


class SourceSizeTests(unittest.TestCase):
    def test_files_are_not_too_long(self):
        long = {relative(p): len(p.read_text(encoding="utf-8").splitlines()) for p in source_files()}
        long = {name: count for name, count in long.items() if count > FILE_LIMIT}
        unlisted = sorted(f"{name} ({count} lines)" for name, count in long.items() if name not in FILE_EXCEPTIONS)
        self.assertEqual(unlisted, [], f"split these files (parts by topic) or list them in FILE_EXCEPTIONS with a reason; limit {FILE_LIMIT}")
        stale = sorted(name for name in FILE_EXCEPTIONS if name not in long)
        self.assertEqual(stale, [], "these files are short enough now: remove them from FILE_EXCEPTIONS")

    def test_functions_are_not_too_long(self):
        long: dict[str, int] = {}
        for path in source_files():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    size = node.end_lineno - node.lineno + 1
                    if size > FUNCTION_LIMIT:
                        long[f"{relative(path)}:{node.name}"] = size
        unlisted = sorted(f"{name} ({size} lines)" for name, size in long.items() if name not in FUNCTION_EXCEPTIONS)
        self.assertEqual(unlisted, [], f"split these functions or list them in FUNCTION_EXCEPTIONS with a reason; limit {FUNCTION_LIMIT}")
        stale = sorted(name for name in FUNCTION_EXCEPTIONS if name not in long)
        self.assertEqual(stale, [], "these functions are short enough now: remove them from FUNCTION_EXCEPTIONS")

    def test_every_exception_has_a_reason(self):
        for name, reason in {**FILE_EXCEPTIONS, **FUNCTION_EXCEPTIONS}.items():
            self.assertGreater(len(reason.strip()), 20, f"{name}: say why splitting does not make sense")


if __name__ == "__main__":
    unittest.main()
