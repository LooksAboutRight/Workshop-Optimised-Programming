"""Start the WOP window.

Usage (project root):  python tools/wop_app.py [-p [report file]] [project file]
Needs PySide6 (pip install PySide6).

--selftest       do not open a window: load every part of the program (also the plug-in modules found by name,
                 ezdxf, Qt SVG, Qt OpenGL), write the result to wop_selftest.txt next to the program and exit
                 (0 = all found). Used by tools/build_exe.py to check the .exe.

-p / --profile   measure where the time goes while the window runs; when the window is
                 closed a text report is written (default wop_profile.txt in the current folder).
                 Without it nothing is measured and nothing is slowed down.
"""

import cProfile
import io
import pstats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wop.ui.qt.app import main  # noqa: E402

SELFTEST_FLAG = "--selftest"
SELFTEST_REPORT = "wop_selftest.txt"
MIN_REGISTRY_ENTRIES = 1


def _check_dxf() -> str:
    """Write a small DXF with ezdxf and read it back through the program's own reader (ezdxf and what it needs are in the .exe)."""
    import tempfile

    import ezdxf
    from wop.adapters.dxf_files import read_dxf

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "selftest.dxf"
        document = ezdxf.new()
        document.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
        document.saveas(path)
        drawing = read_dxf(path)
    return f"{type(drawing).__name__}"


def _check_window() -> str:
    """Build the main window without showing it (the Qt platform `offscreen`, so no screen is needed) and paint it: the Qt plug-ins that
    were not pruned from the .exe (style, SVG icons and images) must be there, the pruned ones must not be needed."""
    import os
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from wop.ui.app_model import AppModel
    from wop.ui.qt.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        window = MainWindow(AppModel(settings_path=Path(folder) / "settings.json"))
        window.resize(1000, 700)
        picture = window.grab()
        window.close()
    app.processEvents()
    if picture.isNull() or picture.width() < 100:
        raise RuntimeError("the window did not paint")
    return f"{picture.width()} x {picture.height()} px"


def selftest() -> int:
    """Check that everything the program finds by name is there (a built .exe may miss modules). 0 = fine."""
    import importlib

    lines, failed = [], False
    try:
        importlib.import_module("wop.ui.app_model")  # imports the whole program
        from wop.core.blocks.base import BLOCK_TYPES
        from wop.core.tool_types.base import TOOL_TYPES
        from wop.core.workholding_types.base import WORKHOLDING_TYPES
        from wop.adapters.post_library import load_post_library
        from wop.core.blocks.styles import STYLES

        library = load_post_library()
        counts = {
            "block types": len(BLOCK_TYPES.names()), "tool types": len(TOOL_TYPES.types()),
            "workholding types": len(WORKHOLDING_TYPES.types()),
            "post files": len(library.shipped) - len(library.problems),  # a file that does not read counts as missing
            "styles": sum(len(STYLES.styles_for(name)) - 1 for name in BLOCK_TYPES.names()),  # besides "standard" (grooving, turning contour)
        }
        for name, count in counts.items():
            ok = count >= MIN_REGISTRY_ENTRIES
            failed = failed or not ok
            lines.append(f"{'ok  ' if ok else 'FAIL'} {name}: {count}")
    except Exception as error:  # noqa: BLE001 - the report must name whatever went wrong
        failed = True
        lines.append(f"FAIL loading the program: {error!r}")
    for module in ("ezdxf", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"):
        try:
            importlib.import_module(module)
            lines.append(f"ok   {module}")
        except Exception as error:  # noqa: BLE001
            failed = True
            lines.append(f"FAIL {module}: {error!r}")
    for name, check in (("a DXF file is written and read", _check_dxf), ("the main window is built and painted", _check_window)):
        try:
            lines.append(f"ok   {name}: {check()}")
        except Exception as error:  # noqa: BLE001
            failed = True
            lines.append(f"FAIL {name}: {error!r}")
    from wop.core.compiled import COMPILED_MODULES, compiled_in_use

    lines.append(f"info compiled core: {compiled_in_use()} of {len(COMPILED_MODULES)} modules (0: plain Python, slower; tools/build_compiled.py)")
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    verdict = "SELFTEST FAILED" if failed else "SELFTEST OK"
    (base / SELFTEST_REPORT).write_text("\n".join(lines + [verdict]) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines + [verdict]))
    return 1 if failed else 0


PROFILE_FLAGS = ("-p", "--profile")
PROFILE_DEFAULT_REPORT = "wop_profile.txt"
PROFILE_ROWS = 40  # lines per table in the report
PROFILE_SORTS = (
    ("Most time inside the function itself (tottime)", pstats.SortKey.TIME),
    ("Most time including everything it calls (cumulative)", pstats.SortKey.CUMULATIVE),
)
PROFILE_ONLY_WOP = "wop"  # third table: restricted to functions of this project


def _split_profile_arguments(argv: list[str]) -> tuple[list[str], Path | None]:
    """The arguments without the profile flag, and the report file (None: no profiling)."""
    if not any(arg in PROFILE_FLAGS for arg in argv):
        return argv, None
    rest, report, position = [], Path(PROFILE_DEFAULT_REPORT), 0
    while position < len(argv):
        arg = argv[position]
        if arg in PROFILE_FLAGS:
            following = argv[position + 1] if position + 1 < len(argv) else ""
            if following.endswith(".txt"):  # an optional name for the report
                report, position = Path(following), position + 1
        else:
            rest.append(arg)
        position += 1
    return rest, report


def _write_report(profile: cProfile.Profile, report: Path) -> None:
    parts = []
    for title, key in PROFILE_SORTS:
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats(key).print_stats(PROFILE_ROWS)
        parts.append(f"=== {title} ===\n{stream.getvalue()}")
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats(pstats.SortKey.CUMULATIVE).print_stats(PROFILE_ONLY_WOP, PROFILE_ROWS)
    parts.append(f"=== Only functions of WOP, by cumulative time ===\n{stream.getvalue()}")
    report.write_text("\n".join(parts), encoding="utf-8")
    print(f"Profile report written to {report.resolve()}")


if __name__ == "__main__":
    if SELFTEST_FLAG in sys.argv:
        sys.exit(selftest())
    arguments, report_file = _split_profile_arguments(sys.argv)
    if report_file is None:
        sys.exit(main(arguments))
    profiler = cProfile.Profile()
    try:
        profiler.runcall(main, arguments)
    finally:
        _write_report(profiler, report_file)
