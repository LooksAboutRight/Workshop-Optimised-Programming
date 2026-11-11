"""No module of wop uses a name that is not defined or imported in it (the mistake that only shows when the code runs).

A small stand-in for a linter: for every function, the names that are not local and not module names or builtins.
"""

import builtins
import symtable
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "wop"


def module_names(table: symtable.SymbolTable) -> set[str]:
    return {symbol.get_name() for symbol in table.get_symbols() if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()}


def unresolved(table: symtable.SymbolTable, known: set[str]) -> list[str]:
    found = []
    for symbol in table.get_symbols():
        name = symbol.get_name()
        if table.get_type() != "module" and symbol.is_global() and symbol.is_referenced() and not symbol.is_assigned():
            if name not in known:
                found.append(f"{name} (in {table.get_name()}, line {table.get_lineno()})")
    for child in table.get_children():
        found += unresolved(child, known)
    return found


class UndefinedNameTests(unittest.TestCase):
    def test_every_module_only_uses_names_it_has(self):
        problems = []
        for path in sorted(ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            table = symtable.symtable(source, str(path), "exec")
            known = module_names(table) | set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
            for name in unresolved(table, known):
                problems.append(f"{path.relative_to(ROOT.parent)}: {name}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
