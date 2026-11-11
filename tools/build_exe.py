"""Build WOP.exe (the whole program in one folder or one file) with PyInstaller. Run it ON WINDOWS.

Usage (project root):
    python tools/build_exe.py
    python tools/build_exe.py --onefile --name WOP --console

First time: pip install pyinstaller PySide6 ezdxf  (the tool offers to install PyInstaller itself).
The result is dist/<name>/<name>.exe (folder mode, starts fast) or dist/<name>.exe (--onefile, one file, starts
slower and virus scanners like it less). Only start the .exe in dist: the working folder (build) holds an
unfinished copy that fails with 'Failed to load Python DLL'. The tool then starts the .exe with --selftest (no window) and says whether
every part the program loads by name is inside. Nothing is changed in the program itself.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = PROJECT_ROOT / "tools" / "wop_app.py"
sys.path.insert(0, str(PROJECT_ROOT))  # the project, not this folder: for the name below
from wop.core.compiled import GROUP_NAME  # noqa: E402  (the name of the shared file of the compiled core)

DEFAULT_NAME = "WOP"
SELFTEST_REPORT = "wop_selftest.txt"
SELFTEST_SECONDS = 180
WORK_SUBFOLDER = "pyinstaller_work"
PORTABLE_FOLDER = "user_data"
LICENSE_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md")  # the licences, and the README with the warning that a post can crash a machine
ZIP_LEFT_OUT = ("wop_selftest.txt",)  # not in the zip; also the settings of the folder `user_data` (they are the builder's own), only its README goes in
EXAMPLES_FOLDER = "examples"  # the example projects, posts and the example machine: the user of the zip has no repository to find them in
MANUAL_PDF = Path("docs") / "manual" / "build" / "WOP_manual.pdf"  # made by `python tools/make_manual.py`; goes next to WOP.exe when it exists (GUESS: the manual is in the zip)
MANUAL_NAME = "WOP_manual.pdf"
LICENSE_FOLDER = "licenses"  # the texts of the LGPL-3.0 and GPL-3.0 (Qt is shipped in the folder: the LGPL asks for a copy of them)
PORTABLE_README = (
    "Settings, machines, libraries and conventions of WOP are kept in this folder (it sits next to WOP.exe,\n"
    "so the whole program folder can be copied to another PC). Delete this folder to use %APPDATA%\\WOP instead.\n"
)
# Packages the program loads by name (plug-in modules) or that bring their own DLLs / data: collect everything.
COLLECT_SUBMODULES = ("wop",)
COLLECT_DATA = ("wop",)  # the post files (`wop/post/posts/*.post.ini`) are data, not modules
COLLECT_ALL = ("ezdxf",)
# Not used by WOP, pulled in by hooks or by `--collect-all ezdxf` (its optional drawing and image add-ons): PIL, lxml and yaml are about
# 20 MB; the Qt modules are the ones WOP never imports (it uses QtCore, QtGui, QtWidgets, QtSvg, QtSvgWidgets, QtOpenGL, QtOpenGLWidgets).
EXCLUDED = (
    "tkinter", "matplotlib", "pytest", "IPython", "PIL", "lxml", "yaml",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts",
)
# Files of the built folder (relative to `_internal`) that nothing in WOP needs: the Qt translations (the program is English), the
# plug-ins for touch, the virtual keyboard, PDF and other image formats, network information and TLS, the Direct2D / minimal platforms, and the
# C speed-ups of ezdxf and their C source (it runs without them; WOP reads a DXF file only on import). Kept: the platforms `windows` and `offscreen` (the
# self-test), the SVG image and icon plug-ins, the style, JPEG, and `opengl32sw.dll` (the software OpenGL the program restarts with on a
# computer without OpenGL 2).
PRUNE = tuple(f"PySide6/{name}" for name in (
    "translations", "plugins/generic", "plugins/networkinformation", "plugins/platforminputcontexts", "plugins/tls",
    "plugins/platforms/qdirect2d.dll", "plugins/platforms/qminimal.dll",
    "plugins/imageformats/qpdf.dll", "plugins/imageformats/qicns.dll", "plugins/imageformats/qico.dll", "plugins/imageformats/qtga.dll",
    "plugins/imageformats/qtiff.dll", "plugins/imageformats/qwbmp.dll", "plugins/imageformats/qwebp.dll", "plugins/imageformats/qgif.dll",
    "Qt6Pdf.dll", "Qt6Quick.dll", "Qt6Qml*.dll", "Qt6VirtualKeyboard.dll", "Qt6Network.dll", "QtNetwork.pyd",
)) + ("ezdxf/acc/*.pyd", "ezdxf/**/*.c", "ezdxf/**/*.pyx", "ezdxf/**/*.pxd", "ezdxf/**/*.h")


def build_command(name: str, onefile: bool, console: bool, icon: Path | None, dist: Path, work: Path, compiled: bool = False) -> list[str]:
    """The PyInstaller command line. `compiled`: the compiled core (`tools/build_compiled.py`) goes in too; its shared file is imported only
    by the compiled modules, where PyInstaller cannot see it."""
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", name, "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
        "--paths", str(PROJECT_ROOT),
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
    ]
    for package in COLLECT_SUBMODULES:
        command += ["--collect-submodules", package]
    for package in COLLECT_DATA:
        command += ["--collect-data", package]
    for package in COLLECT_ALL:
        command += ["--collect-all", package]
    for module in EXCLUDED:
        command += ["--exclude-module", module]
    if compiled:
        command += ["--hidden-import", f"{GROUP_NAME}__mypyc"]
    if icon is not None:
        command += ["--icon", str(icon)]
    command.append(str(ENTRY_POINT))
    return command


def compile_core() -> bool:
    """Compile the hot core with mypyc (`tools/build_compiled.py`) before PyInstaller; False (the .exe runs it as plain Python) when mypyc
    or a C compiler is missing: the program is the same, only slower."""
    if subprocess.run([sys.executable, "-c", "import mypyc"], capture_output=True).returncode != 0:
        print("mypyc is not installed (pip install mypy setuptools): the core goes in as plain Python, slower")
        return False
    if subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "build_compiled.py")], cwd=PROJECT_ROOT).returncode != 0:
        print("compiling the core failed (the messages above say why): it goes in as plain Python, slower")
        subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "build_compiled.py"), "--clean"], cwd=PROJECT_ROOT)
        return False
    return True


def prune(folder: Path) -> int:
    """Remove the files of `PRUNE` from the built folder (folder mode); the number of bytes that went."""
    root = folder / "_internal"
    freed = 0
    for pattern in PRUNE:
        for found in root.glob(pattern):
            if found.is_dir():
                freed += sum(f.stat().st_size for f in found.rglob("*") if f.is_file())
                shutil.rmtree(found)
            elif found.is_file():
                freed += found.stat().st_size
                found.unlink()
    return freed


def project_version() -> str:
    """The version of `pyproject.toml`."""
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def zip_name(name: str, version: str) -> str:
    """The name of the zip for a release: `WOP-0.1.0-windows.zip`."""
    system = "windows" if sys.platform == "win32" else sys.platform
    return f"{name}-{version}-{system}.zip"


def copy_examples(folder: Path) -> None:
    """The example folder of the repository next to the program (`folder`/examples)."""
    shutil.copytree(PROJECT_ROOT / EXAMPLES_FOLDER, folder / EXAMPLES_FOLDER, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))


def copy_manual(folder: Path) -> bool:
    """The PDF of the user manual next to the program; False when it has not been built."""
    source = PROJECT_ROOT / MANUAL_PDF
    if not source.is_file():
        return False
    shutil.copy2(source, folder / MANUAL_NAME)
    return True


def zip_files(folder: Path) -> list[Path]:
    """The files of a built folder that go into the zip: everything but the self-test report and the settings the builder made in
    `user_data` (its README is kept: the folder is the portable settings folder)."""
    found = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if not path.is_file() or path.name in ZIP_LEFT_OUT:
            continue
        if relative.parts[0] == PORTABLE_FOLDER and relative.name != "README.txt":
            continue
        found.append(path)
    return found


def make_zip(target: Path, base: Path, files: list[Path]) -> None:
    """Pack `files` into `target`; names inside start at `base` (so the zip holds the folder `WOP`, not its parts)."""
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(base).as_posix())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def exe_path(name: str, onefile: bool, dist: Path) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return dist / f"{name}{suffix}" if onefile else dist / name / f"{name}{suffix}"


def pyinstaller_available() -> bool:
    return subprocess.run([sys.executable, "-c", "import PyInstaller"], capture_output=True).returncode == 0


def clear_old_build(folder: Path, backup: Path) -> bool:
    """Remove the old built folder (PyInstaller does it too, but fails with a bad message if a file is in use).

    The user_data folder inside it (the user's settings) is copied to `backup` first. False = could not remove.
    """
    if not folder.exists():
        return True
    if (folder / PORTABLE_FOLDER).is_dir():
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(folder / PORTABLE_FOLDER, backup)
    try:
        shutil.rmtree(folder)
    except OSError as error:
        print(f"cannot remove the old build {folder}: {error}")
        print("A file in it is in use: close WOP.exe (also check the task manager) and any window showing the folder, then try again.")
        return False
    return True


def selftest(exe: Path) -> bool:
    """Start the built program with --selftest and read its report."""
    report = exe.parent / SELFTEST_REPORT
    report.unlink(missing_ok=True)
    try:
        subprocess.run([str(exe), "--selftest"], timeout=SELFTEST_SECONDS, capture_output=True)
    except subprocess.TimeoutExpired:
        print("selftest: the program did not finish")
        return False
    if not report.exists():
        print("selftest: the program wrote no report (it did not start?). Build again with --console to see the error.")
        return False
    text = report.read_text(encoding="utf-8")
    print(text)
    return "SELFTEST OK" in text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build WOP.exe with PyInstaller (run on Windows).")
    parser.add_argument("--name", default=DEFAULT_NAME, help="name of the program (default WOP)")
    parser.add_argument("--onefile", action="store_true", help="one .exe file instead of a folder")
    parser.add_argument("--console", action="store_true", help="show a text window too (to see error messages)")
    parser.add_argument("--icon", type=Path, help="an .ico file for the program")
    parser.add_argument("--dist", type=Path, default=PROJECT_ROOT / "dist", help="where the result goes (default dist)")
    parser.add_argument("--work", type=Path, default=PROJECT_ROOT / "build" / WORK_SUBFOLDER,
                        help="working folder (default build/pyinstaller_work; do NOT start the exe in there)")
    parser.add_argument("--no-test", action="store_true", help="do not run the selftest after the build")
    parser.add_argument("--zip", action="store_true", help="also pack the result into WOP-<version>-windows.zip (after the self-test; prints its SHA-256)")
    parser.add_argument("--plain", action="store_true", help="do not compile the core first (the .exe runs it as plain Python, slower)")
    args = parser.parse_args(argv[1:])

    if not pyinstaller_available():
        print("PyInstaller is not installed. Install it with:  pip install pyinstaller")
        return 1
    if args.icon is not None and not args.icon.exists():
        print(f"the icon file {args.icon} does not exist")
        return 1
    backup = args.work / "user_data_backup"
    if not args.onefile and not clear_old_build(args.dist / args.name, backup):
        return 1
    if args.plain:  # compiled files left from an earlier build would go into the .exe without their shared file: it would not start
        subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "build_compiled.py"), "--clean"], cwd=PROJECT_ROOT)
    compiled = not args.plain and compile_core()
    command = build_command(args.name, args.onefile, args.console, args.icon, args.dist, args.work, compiled)
    print("running:", " ".join(command))
    if subprocess.run(command, cwd=PROJECT_ROOT).returncode != 0:
        print("PyInstaller failed (the messages above say why)")
        return 1
    exe = exe_path(args.name, args.onefile, args.dist)
    if not exe.exists():
        print(f"expected {exe} but it is not there")
        return 1
    print(f"built {exe}")
    if not args.onefile:
        print(f"pruned {prune(exe.parent) / 1_000_000:.0f} MB of files WOP does not use")
    print(f"START THIS ONE: {exe}   (the copies in {args.work} are unfinished and do not start)")
    data = (exe.parent / PORTABLE_FOLDER).resolve()
    if backup.is_dir():  # the settings of the old build come back
        shutil.copytree(backup, data, dirs_exist_ok=True)
    data.mkdir(exist_ok=True)
    for name in LICENSE_FILES:  # the licence of WOP and of what is inside the folder go with it
        shutil.copy2(PROJECT_ROOT / name, exe.parent / name)
    shutil.copytree(PROJECT_ROOT / LICENSE_FOLDER, exe.parent / LICENSE_FOLDER, dirs_exist_ok=True)
    copy_examples(exe.parent)
    if not copy_manual(exe.parent):
        print(f"WARNING: no manual PDF ({MANUAL_PDF}): run `python tools/make_manual.py` first, or the zip has no manual")
    (data / "README.txt").write_text(PORTABLE_README, encoding="utf-8")
    print(f"portable settings folder: {data}")
    if not args.no_test and not selftest(exe):
        print("the selftest FAILED: the .exe is missing parts")
        return 1
    if args.zip:  # after the self-test: a zip of a broken build would be a trap
        if args.onefile:
            base, files = args.dist, [exe, *(args.dist / name for name in LICENSE_FILES), *args.dist.glob(MANUAL_NAME), *sorted((args.dist / LICENSE_FOLDER).glob("*")),
                                  *(path for path in sorted((args.dist / EXAMPLES_FOLDER).rglob("*")) if path.is_file())]
        else:
            base, files = exe.parent.parent, zip_files(exe.parent)
        target = args.dist / zip_name(args.name, project_version())
        make_zip(target, base, files)
        print(f"packed {target} ({target.stat().st_size / 1_000_000:.0f} MB)")
        print(f"SHA-256: {sha256_of(target)}  {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
