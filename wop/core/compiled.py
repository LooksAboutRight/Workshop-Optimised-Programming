"""Which modules of the core may be compiled with mypyc (`tools/build_compiled.py`), and where their compiled files lie.

A compiled module is a `.pyd` (Windows) or `.so` file next to its source; Python takes it instead of the `.py` file. Without the compiled
files WOP runs the same code as plain Python, only slower. Nothing here imports mypyc.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# the hot core (all in `wop/core/geometry/`): the points and pieces, the distances and crossings, the chains and their index, the tool
# as loops of edges, the penetration test, the contacts and the material a move removes
COMPILED_MODULES = (
    "wop/core/geometry/primitives.py",
    "wop/core/geometry/distance.py",
    "wop/core/geometry/intersect.py",
    "wop/core/geometry/chain_index.py",
    "wop/core/geometry/chains.py",
    "wop/core/geometry/tool_edges.py",
    "wop/core/geometry/penetration.py",
    "wop/core/geometry/contacts.py",
    "wop/core/geometry/removal.py",
)
GROUP_NAME = "wop_compiled"  # the shared file of mypyc's support code is `wop_compiled__mypyc...` in the project folder
COMPILED_SUFFIXES = (".pyd", ".so")
STAMP_FILE = "wop_compiled.stamp.json"  # in the project folder: the fingerprints of the sources of the last build


def compiled_files(root: Path) -> list[Path]:
    """Every compiled file of WOP under `root` (the modules and the shared support file)."""
    found = [path for suffix in COMPILED_SUFFIXES for path in (root / "wop").rglob(f"*{suffix}")]
    found += [path for suffix in COMPILED_SUFFIXES for path in root.glob(f"{GROUP_NAME}__mypyc*{suffix}")]
    found += [path for suffix in COMPILED_SUFFIXES for path in root.glob(f"*__mypyc*{suffix}")]
    return sorted(set(found))


def _fingerprints(root: Path) -> dict[str, str]:
    return {module: hashlib.sha256((root / module).read_bytes()).hexdigest() for module in COMPILED_MODULES}


def write_stamp(root: Path) -> None:
    """Note what was compiled: the fingerprint of every source (`tools/build_compiled.py`, after a build)."""
    (root / STAMP_FILE).write_text(json.dumps(_fingerprints(root), indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def stale_compiled(root: Path) -> list[str]:
    """Why the compiled files do not belong to the sources as they are now (a source changed after the last build, or no note of the
    build): empty when they do, or when there are no compiled files. The date of a file says nothing: the build keeps a module file whose
    content did not change, the code itself is in the shared file."""
    if not compiled_files(root):
        return []
    stamp = root / STAMP_FILE
    if not stamp.is_file():
        return [f"compiled files without {STAMP_FILE}"]
    noted = json.loads(stamp.read_text(encoding="utf-8"))
    return [f"{module} changed after the last build" for module, fingerprint in _fingerprints(root).items() if noted.get(module) != fingerprint]


def compiled_in_use() -> int:
    """How many of the compiled modules run as compiled code now (0: plain Python)."""
    import importlib

    names = [module.removesuffix(".py").replace("/", ".") for module in COMPILED_MODULES]
    return sum(1 for name in names if Path(importlib.import_module(name).__file__ or "").suffix in COMPILED_SUFFIXES)
