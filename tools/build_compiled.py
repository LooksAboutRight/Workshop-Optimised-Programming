"""Compile the hot core of WOP with mypyc: the geometry, the chains and the tests of the analytic planner run as C code.

Usage (project root):
    python tools/build_compiled.py          compile (about half a minute), the compiled files lie next to the sources
    python tools/build_compiled.py --clean  remove every compiled file: WOP runs as plain Python again

Needs mypy (it brings mypyc) and setuptools, and a C compiler: on Windows the C++ build tools of Visual Studio (`pip install mypy
setuptools`). The program is the same with or without the compiled files, only faster with them; `tests/test_compiled_current.py`
fails when a compiled file is older than its source (then run this again, or --clean). mypyc is MIT-licensed; its support code is part
of the compiled files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wop.core.compiled import COMPILED_MODULES, GROUP_NAME, STAMP_FILE, compiled_files, write_stamp  # noqa: E402


def build() -> int:
    from mypyc.build import mypycify  # late: only needed here, and only on a machine that builds
    from setuptools import setup

    paths = [str(ROOT / module) for module in COMPILED_MODULES]
    setup(
        name="wop-compiled",
        ext_modules=mypycify(["--ignore-missing-imports", "--follow-imports=silent", *paths], group_name=GROUP_NAME),
        script_args=["build_ext", "--inplace", "--build-temp", str(ROOT / "build" / "mypyc-temp")],
    )
    write_stamp(ROOT)
    print(f"compiled {len(COMPILED_MODULES)} modules: {len(compiled_files(ROOT))} files")
    return 0


def clean() -> int:
    removed = compiled_files(ROOT)
    for path in removed:
        path.unlink()
    (ROOT / STAMP_FILE).unlink(missing_ok=True)
    print(f"removed {len(removed)} compiled files: WOP runs as plain Python")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Compile the hot core of WOP with mypyc (or remove the compiled files).")
    parser.add_argument("--clean", action="store_true", help="remove every compiled file")
    arguments = parser.parse_args(argv)
    if arguments.clean:
        return clean()
    clean()  # an old file of a module that is no longer compiled must not stay
    import os

    os.chdir(ROOT)  # build_ext --inplace puts the files under the working folder
    return build()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
