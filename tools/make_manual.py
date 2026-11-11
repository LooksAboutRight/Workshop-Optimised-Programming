"""Make the user manual (docs/manual) as a PDF: `python tools/make_manual.py [--pictures]`.

Without an option it only builds the PDF from the pictures that are in `docs/manual/images`. With `--pictures` it
first runs `tools/make_screenshots.py` into `docs/manual/build/shots` and copies the pictures the manual uses (the list
`PICTURES` below) into `docs/manual/images`, then `tools/manual_scenes.py`, which makes the pictures with a menu, a dropdown
or a hover text open and the mouse pointer and red callouts in them (`COMPOSED`), so the pictures follow the program. Run it with the Windows theme set to
light: the manual is printed on white paper. The PDF is `docs/manual/build/WOP_manual.pdf`.

LaTeX: MiKTeX (or any pdflatex). The tool looks for `pdflatex` in the PATH and in the usual MiKTeX folders. Packages that
are missing are fetched by MiKTeX the first time.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANUAL = PROJECT_ROOT / "docs" / "manual"
BUILD = MANUAL / "build"
IMAGES = MANUAL / "images"
MAIN = "main"
PDF_NAME = "WOP_manual.pdf"
MAX_RUNS = 4  # LaTeX is run again until the contents and the references stop changing

# (picture of tools/make_screenshots.py without the theme and `.png`, name in docs/manual/images)
PICTURES = (
    ("menu_file", "menu_file"),
    ("window_collision_demo_setup", "window_setup"),
    ("dialog_file_export_g_code_exportcheckdialog", "export_found"),
    ("dialog_file_export_selected_blocks_exportselecteddialog", "export_selected"),
    ("dialog_file_machines_machinesdialog", "machines"),
    ("dialog_file_postprocessors_posteditordialog", "post_editor"),
    ("dialog_file_preferences_preferencesdialog", "preferences"),
    ("special_sketch_editor", "sketch_editor"),
    ("special_sketch_editor_tray", "sketch_editor_tray"),
    ("special_style_pictures_grooving_standard", "style_grooving_standard"),
    ("special_style_pictures_grooving_layers", "style_grooving_layers"),
    ("special_style_pictures_turning_contour_standard", "style_contour_standard"),
    ("special_style_pictures_turning_contour_pockets_last", "style_contour_pockets_last"),
)

# made by tools/manual_scenes.py straight into docs/manual/images (the same names as in `COMPOSED` there)
COMPOSED = (
    "file_menu_in_window", "sketch_hover_text", "preferences_dropdown", "window_parts", "setup_form", "setup_raw_part", "sketch_raw_part",
    "contour_form", "block_facing", "block_turning", "block_turning_contour", "block_drilling", "block_threading", "block_grooving",
    "block_machine_function", "block_custom_path", "sketch_path",
)

MIKTEX_FOLDERS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
    Path(os.environ.get("ProgramFiles", "")) / "MiKTeX" / "miktex" / "bin" / "x64",
)


def find_pdflatex() -> str:
    found = shutil.which("pdflatex")
    if found:
        return found
    for folder in MIKTEX_FOLDERS:
        candidate = folder / "pdflatex.exe"
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("pdflatex not found: install MiKTeX (https://miktex.org) or put pdflatex in the PATH")


def make_pictures() -> None:
    shots = BUILD / "shots"
    shutil.rmtree(shots, ignore_errors=True)
    subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "make_screenshots.py"), str(shots)], check=True)
    themes = {p.stem.rsplit("_", 1)[1] for p in shots.glob("*.png")}
    if themes != {"light"}:
        print(f"WARNING: the pictures are made in the {', '.join(sorted(themes))} theme; the manual wants light (change the Windows theme)")
    IMAGES.mkdir(parents=True, exist_ok=True)
    for source, name in PICTURES:
        picture = next(iter(sorted(shots.glob(f"{source}_*.png"))), None)
        if picture is None:
            raise SystemExit(f"the screenshot tool made no picture '{source}': the manual needs it")
        shutil.copyfile(picture, IMAGES / f"{name}.png")
    print(f"{len(PICTURES)} pictures copied to {IMAGES}")
    subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "manual_scenes.py"), str(IMAGES)], check=True)


def write_version() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    today = datetime.date.today().strftime("%d %B %Y").lstrip("0")
    (BUILD / "version.tex").write_text(
        f"\\newcommand{{\\wopversion}}{{{version}}}\n\\newcommand{{\\wopdate}}{{{today}}}\n", encoding="utf-8", newline="\n"
    )


def missing_pictures() -> list[str]:
    sources = [MANUAL / "main.tex", *sorted((MANUAL / "chapters").glob("*.tex"))]  # not the preamble: it only defines \shot
    used = set(re.findall(r"\\shot(?:\[[^\]]*\])?\{([^}]+)\}", "".join(p.read_text(encoding="utf-8") for p in sources)))
    return sorted(name for name in used if not (IMAGES / f"{name}.png").is_file())


def build_pdf() -> Path:
    write_version()
    lost = missing_pictures()
    if lost:
        raise SystemExit("pictures missing in docs/manual/images (run with --pictures): " + ", ".join(lost))
    pdflatex = find_pdflatex()
    command = [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "--enable-installer", f"-output-directory={BUILD}", f"{MAIN}.tex"]
    log = BUILD / f"{MAIN}.log"
    for run in range(1, MAX_RUNS + 1):
        done = subprocess.run(command, cwd=MANUAL, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            tail = "\n".join(done.stdout.splitlines()[-25:])
            raise SystemExit(f"pdflatex failed in run {run} (see {log}):\n{tail}")
        text = log.read_text(encoding="utf-8", errors="replace")
        if "Rerun to get" not in text and "Label(s) may have changed" not in text:
            break
    pdf = BUILD / f"{MAIN}.pdf"
    target = BUILD / PDF_NAME
    shutil.copyfile(pdf, target)
    pages = re.search(r"Output written on [^(]*\((\d+) pages", text.replace("\n", ""))  # the log breaks long lines
    warnings = len(re.findall(r"^(?:Overfull|Underfull) \\[hv]box", text, flags=re.M))
    undefined = re.findall(r"(?:Reference|Citation) `([^']+)' on page", text)
    print(f"{target}: {pages.group(1) if pages else '?'} pages after {run} run(s), {warnings} box warnings")
    if undefined:
        print("WARNING: undefined references: " + ", ".join(sorted(set(undefined))))
    return target


def main(argv: list[str]) -> int:
    if "--pictures" in argv:
        make_pictures()
    build_pdf()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
