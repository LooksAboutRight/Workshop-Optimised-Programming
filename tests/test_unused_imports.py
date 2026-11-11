"""No module of wop imports a name it does not use (a leftover after a change makes the code harder to read).

A line with `noqa` is left alone (a name that other modules import from here); `__init__.py` files are skipped.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def unused_imports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    imported: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = (node.lineno, node.end_lineno)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    found = []
    for name, (first, last) in sorted(imported.items()):
        if name not in used and not any("noqa" in line for line in lines[first - 1:last]):
            found.append(f"{path.relative_to(ROOT)}:{first}: {name}")
    return found


class UnusedImportTests(unittest.TestCase):
    def test_every_imported_name_is_used(self):
        found = []
        for path in sorted((ROOT / "wop").rglob("*.py")):
            if path.name != "__init__.py":
                found += unused_imports(path)
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
