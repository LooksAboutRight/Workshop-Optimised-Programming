"""Check that the windows of WOP fit a small screen (the lathe PC may be 1024 x 768): the smallest size of the main window and of every dialog.

Usage (project root):  python tools/check_small_screen.py [--width 1024] [--height 768] [--taskbar 48]
Builds the main window and every dialog offscreen (real PySide6) with the Windows font Segoe UI 9, which is what the window uses on Windows, and
reads the smallest size each of them lets the user make it. A window fits when its smallest size is not larger than the free part of the screen
(the screen minus the taskbar) less the room for its frame (`SCREEN_MARGIN_X_PX`, `SCREEN_MARGIN_Y_PX`). Without the font (Linux, or Windows
without Segoe UI) the sizes would be those of another font: it says so and checks nothing (exit 0). Exit 1: a window does not fit.
Not measured: Windows display scaling (125 % makes everything larger), touch.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FONT_FAMILY = "Segoe UI"
FONT_POINTS = 9
WINDOWS_FONTS = "C:/Windows/Fonts"
NO_FONT_MARKER = "SKIPPED: no Segoe UI font here"
DEFAULT_TASKBAR_PX = 48  # the taskbar of Windows 11 at 100 % scaling


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check that the windows of WOP fit a small screen.")
    parser.add_argument("--width", type=int, default=1024, help="width of the screen in pixels (default 1024)")
    parser.add_argument("--height", type=int, default=768, help="height of the screen in pixels (default 768)")
    parser.add_argument("--taskbar", type=int, default=DEFAULT_TASKBAR_PX, help=f"height of the taskbar (default {DEFAULT_TASKBAR_PX})")
    args = parser.parse_args(argv[1:])
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if Path(WINDOWS_FONTS).is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", WINDOWS_FONTS)  # the offscreen platform has no fonts of its own: letters would be boxes

    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from wop.ui.qt.qt_constants import SCREEN_MARGIN_X_PX, SCREEN_MARGIN_Y_PX

    application = QApplication.instance() or QApplication([])
    if FONT_FAMILY not in QFontDatabase.families():
        print(NO_FONT_MARKER)
        return 0
    application.setFont(QFont(FONT_FAMILY, FONT_POINTS))
    limit_w = args.width - SCREEN_MARGIN_X_PX
    limit_h = args.height - args.taskbar - SCREEN_MARGIN_Y_PX
    print(f"screen {args.width} x {args.height}, taskbar {args.taskbar}: a window may not be larger than {limit_w} x {limit_h} at its smallest")

    from wop.core.lathe.workholding import JAWS_KIND
    from wop.ui.app_model import AppModel, ExportReport
    from wop.ui.qt.dialogs import ExportCheckDialog, ExportSelectedDialog, IssuesDialog
    from wop.ui.qt.machines_dialog import MachinesDialog
    from wop.ui.qt.main_window import MainWindow
    from wop.ui.qt.materials_dialog import MaterialsDialog
    from wop.ui.qt.post_editor_dialog import PostEditorDialog
    from wop.ui.qt.preferences_dialog import FixedValuesDialog, PreferencesDialog
    from wop.ui.qt.sketch_dialog import SketchDialog
    from wop.ui.qt.toolboxes_dialog import ToolboxesDialog
    from wop.ui.qt.view3d_dialog import View3DDialog

    scratch = tempfile.mkdtemp(prefix="wop_small_screen_")
    model = AppModel(settings_path=Path(scratch) / "settings.json")
    model.open(PROJECT_ROOT / "examples" / "pawn.wop.json")
    window = MainWindow(model)
    window.show()
    application.processEvents()
    def settle() -> None:
        for _ in range(3):  # the layout of the window follows a change of the panels a moment later
            application.processEvents()

    rows: list[tuple[str, int, int]] = []

    def measure(name: str, widget) -> None:
        hint, set_size = widget.minimumSizeHint(), widget.minimumSize()
        rows.append((name, max(hint.width(), set_size.width()), max(hint.height(), set_size.height())))

    settle()
    measure("main window, both panels open", window)
    window.splitter.close_panel(0)
    settle()
    measure("main window, flow list closed", window)
    window.splitter.close_panel(2)
    settle()
    measure("main window, both panels closed", window)
    window.splitter.open_panel(0)
    window.splitter.open_panel(2)
    settle()
    model.use_machine(model.new_machine())
    tool_number = model.program.tools[0].number
    jaws = model.add_workholding_item(JAWS_KIND)
    custom_path = model.add_block("custom_path")
    picture = "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
    post_with_function = PROJECT_ROOT / "examples" / "posts" / "linuxcnc_custom_function.post.ini"
    function_post = model.import_post(post_with_function)

    builders = (
        ("Machines", lambda: MachinesDialog(window, model)),
        ("Materials", lambda: MaterialsDialog(window, model)),
        ("Sketch of a tool", lambda: SketchDialog(window, target=model.tool_sketch_target(tool_number))),
        ("Sketch of jaws", lambda: SketchDialog(window, target=model.workholding_sketch_target(jaws))),
        ("Sketch of the raw part", lambda: SketchDialog(window, target=model.raw_part_sketch_target())),
        ("Sketch of a custom path", lambda: SketchDialog(window, target=model.path_sketch_target(custom_path))),
        ("3D view", lambda: View3DDialog(window, model)),
        ("Post editor", lambda: PostEditorDialog(window, model, "linuxcnc")),
        ("Post editor, post with a custom function", lambda: PostEditorDialog(window, model, function_post)),
        ("Preferences", lambda: PreferencesDialog(window, model)),
        ("Fixed values", lambda: FixedValuesDialog(window, "text")),
        ("Export check", lambda: ExportCheckDialog(window, ExportReport(False, ("block 2 is left out",)), lambda: ExportReport(True))),
        ("Export selected", lambda: ExportSelectedDialog(window, "title", lambda done: (picture, "notes", "code"), lambda done: None)),
        ("Issues", lambda: IssuesDialog(window, [])),
        ("Toolboxes", lambda: ToolboxesDialog(window, model)),
    )
    for name, build in builders:
        dialog = build()
        dialog.show()
        application.processEvents()
        if name.startswith("Post editor"):  # every page counts: the tallest one sets the smallest size when the pages do not scroll
            worst = (0, 0, "")
            for row in range(dialog._pages.count()):
                dialog._pages.setCurrentRow(row)
                application.processEvents()
                hint, set_size = dialog.minimumSizeHint(), dialog.minimumSize()
                worst = (max(worst[0], hint.width(), set_size.width()), max(worst[1], hint.height(), set_size.height()), worst[2])
            rows.append((f"{name} (the largest of all its pages)", worst[0], worst[1]))
        else:
            measure(name, dialog)
        dialog.close()

    too_large = 0
    width = max(len(name) for name, _w, _h in rows)
    for name, w, h in rows:
        fits = w <= limit_w and h <= limit_h
        too_large += not fits
        print(f"{'ok  ' if fits else 'NO  '} {name:<{width}}  {w:>5} x {h:<5}")
    print(f"{too_large} of {len(rows)} measurements do not fit" if too_large else f"all {len(rows)} measurements fit")
    return 1 if too_large else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
