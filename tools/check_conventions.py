"""Check the coding conventions of wop/core (requirements A1 and A5).

Reports:
- module-level dicts outside constants.py
- imports of ui/hosts/adapters/post, of GUI toolkits or of LinuxCNC

Usage: python tools/check_conventions.py [core_dir]
Exit code 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

CONSTANTS_FILE = "constants.py"
FORBIDDEN_WOP_PACKAGES = ("wop.ui", "wop.hosts", "wop.adapters", "wop.post")
FORBIDDEN_THIRD_PARTY = ("PySide6", "PyQt5", "PyQt6", "gi", "linuxcnc", "tkinter")
RELATIVE_IMPORT_LEAVING_CORE_LEVEL = 2


def _is_dict_value(node: ast.AST | None) -> bool:
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    )


def _forbidden_module(name: str) -> bool:
    if name.split(".")[0] in FORBIDDEN_THIRD_PARTY:
        return True
    return any(name == pkg or name.startswith(pkg + ".") for pkg in FORBIDDEN_WOP_PACKAGES)


def check_file(path: Path, core_dir: Path | None = None) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_constants = path.name == CONSTANTS_FILE
    # A file in a sub-package (wop/core/blocks) needs one more dot to reach core.
    depth = len(path.relative_to(core_dir).parent.parts) if core_dir else 0
    leaving_level = RELATIVE_IMPORT_LEAVING_CORE_LEVEL + depth
    problems: list[str] = []

    if not is_constants:
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_dict_value(node.value):
                problems.append(f"{path}:{node.lineno}: module-level dict")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden_module(alias.name):
                    problems.append(f"{path}:{node.lineno}: forbidden import {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.level >= leaving_level:
                problems.append(f"{path}:{node.lineno}: relative import leaves core")
            if node.level == 0 and node.module and _forbidden_module(node.module):
                problems.append(f"{path}:{node.lineno}: forbidden import {node.module}")
    return problems


def find_violations(core_dir: Path) -> list[str]:
    problems: list[str] = []
    for path in sorted(core_dir.rglob("*.py")):
        problems.extend(check_file(path, core_dir))
    return problems


def main(argv: list[str]) -> int:
    default_dir = Path(__file__).resolve().parent.parent / "wop" / "core"
    core_dir = Path(argv[1]) if len(argv) > 1 else default_dir
    problems = find_violations(core_dir)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s) found")
        return 1
    print("conventions ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
