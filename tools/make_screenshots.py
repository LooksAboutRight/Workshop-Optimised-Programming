"""Take pictures of the WOP window, its dialogs and its pages, to check the layout and the colours.

Usage (project root):  python tools/make_screenshots.py [folder]
Needs PySide6. The default folder is `screenshots` (not part of the repository).

The pictures are named `<what>_<dark or light>.png`; the last part comes from the colours of the window, which follow the
operating system. To compare the themes: run it, change the theme of Windows by hand, run it again into the same folder, and
look at the pairs. Nothing of the system is changed. The program's own settings and libraries are not touched, and the example
projects are used as copies in a temporary folder (the entries Save and New project of the menus are not triggered either).

What is found by itself: every block of the example projects, a new block of every type, a new tool and workholding
of every type, every menu (opened as a picture) and every dialog that a menu entry opens (with all its tabs and
all the pages of its lists). Some views that need a special state are made by hand (`special_scenes`): add a scene there.
A scene that fails is listed at the end and in `_problems_<theme>.txt`; the others are still made.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QListWidget,
    QMenu,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.qt.main_window import MainWindow  # noqa: E402

DEFAULT_FOLDER = PROJECT_ROOT / "screenshots"
def example_path(name: str) -> Path:
    """A project of the shipped examples, or of the test projects (the collision demo, the compensation test)."""
    test_project = PROJECT_ROOT / "tests" / "data" / "projects" / name
    return test_project if test_project.exists() else PROJECT_ROOT / "examples" / name


EXAMPLE_PROJECTS = ("reference.wop.json", "collision_demo.wop.json", "compensation_test.wop.json")
WINDOW_SIZE = (1600, 950)
DARK_BELOW = 128  # lightness of the window colour (0 to 255) below which the theme is called dark
MAX_LIST_ROWS = 40  # a list with more rows is not a list of pages
SKIPPED_ACTIONS = ("exit", "quit", "close", "folder", "save", "new project")  # menu entries that are not triggered (words in their text)


class Shooter:
    def __init__(self, application: QApplication, folder: Path) -> None:
        self.application = application
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.names: set[str] = set()
        self.made = 0
        self.problems: list[str] = []
        lightness = application.palette().color(QPalette.Window).lightness()
        self.theme = "dark" if lightness < DARK_BELOW else "light"

    def shot(self, name: str, widget: QWidget) -> None:
        self.application.processEvents()
        base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
        unique, number = base, 2
        while unique in self.names:
            unique, number = f"{base}_{number}", number + 1
        self.names.add(unique)
        widget.grab().save(str(self.folder / f"{unique}_{self.theme}.png"))
        self.made += 1

    def scene(self, name: str, function) -> None:
        """Run one scene; an error is noted and the next scene goes on."""
        try:
            function()
        except Exception:  # noqa: BLE001 - the tool must go on with the other scenes
            self.problems.append(f"{name}: {traceback.format_exc().strip().splitlines()[-1]}")

    # --- dialogs ---------------------------------------------------------------------------------------------

    def walk_dialog(self, name: str, dialog: QDialog) -> None:
        """A picture of the dialog, then of every tab and every page of the lists in it."""
        dialog.show()
        self.application.processEvents()
        self.shot(name, dialog)
        for number, tabs in enumerate(dialog.findChildren(QTabWidget)):
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                self.shot(f"{name}_tab{number}_{tabs.tabText(index)}", dialog)
        for number, pages in enumerate(dialog.findChildren(QListWidget)):
            if not pages.isVisible() or not 1 < pages.count() <= MAX_LIST_ROWS:
                continue
            for row in range(pages.count()):
                pages.setCurrentRow(row)
                self.shot(f"{name}_list{number}_{pages.item(row).text()}", dialog)
            pages.setCurrentRow(0)

    def catch_dialogs(self, prefix: str):
        """Make the dialogs of the program show their picture instead of waiting for the user: every `exec` takes the
        pictures and returns at once, the standard boxes (questions, file choosers) answer nothing."""
        shooter = self
        count = [0]

        def exec_instead(dialog, *_args):
            count[0] += 1
            if isinstance(dialog, QMessageBox):
                dialog.show()
                shooter.shot(f"{prefix}_box{count[0]}", dialog)
                dialog.close()
                return QMessageBox.Cancel
            shooter.walk_dialog(f"{prefix}_{type(dialog).__name__}", dialog)
            dialog.close()
            return QDialog.Rejected

        def box(*_args, **_kwargs):
            return QMessageBox.Cancel

        QDialog.exec = exec_instead
        QMessageBox.exec = exec_instead
        for name in ("warning", "question", "information", "critical"):
            setattr(QMessageBox, name, staticmethod(box))
        for name in ("getOpenFileName", "getSaveFileName", "getExistingDirectory", "getOpenFileNames"):
            setattr(QFileDialog, name, staticmethod(lambda *_a, **_k: ("", "")))
        QInputDialog.getText = staticmethod(lambda *_a, **_k: ("", False))
        QInputDialog.getDouble = staticmethod(lambda *_a, **_k: (0.0, False))
        QInputDialog.getInt = staticmethod(lambda *_a, **_k: (0, False))
        QInputDialog.getItem = staticmethod(lambda *_a, **_k: ("", False))


def menu_pictures(shooter: Shooter, menu: QMenu, name: str) -> None:
    menu.adjustSize()
    shooter.shot(f"menu_{name}", menu)
    for action in menu.actions():
        if action.menu() is not None:
            menu_pictures(shooter, action.menu(), f"{name}_{action.text().replace('&', '')}")


def trigger_menu_entries(shooter: Shooter, window: MainWindow) -> list[str]:
    """Trigger every entry of the menu bar (the dialogs they open make their pictures). Returns what was skipped."""
    skipped: list[str] = []
    todo: list[tuple[str, object]] = []

    def collect(menu: QMenu, path: str) -> None:
        for action in menu.actions():
            text = action.text().replace("&", "")
            if action.menu() is not None:
                collect(action.menu(), f"{path}_{text}")
            elif text and not action.isSeparator():
                todo.append((f"{path}_{text}", action))

    for top in window.menuBar().actions():
        if top.menu() is not None:
            collect(top.menu(), top.text().replace("&", ""))
    for name, action in todo:
        if any(word in name.lower() for word in SKIPPED_ACTIONS) or not action.isEnabled():
            skipped.append(name)
            continue
        shooter.catch_dialogs(f"dialog_{re.sub('[^A-Za-z0-9]+', '_', name).strip('_')}")
        shooter.scene(name, action.trigger)
        shooter.application.processEvents()
    return skipped


def window_scenes(shooter: Shooter, window: MainWindow, model: AppModel, project: str, scratch: Path) -> None:
    """The window with every block of the project, and the other views. The project is a copy in the scratch folder."""
    copy = scratch / project
    shutil.copyfile(example_path(project), copy)
    model.open(copy)
    prefix = f"window_{project.split('.')[0]}"
    window.resize(*WINDOW_SIZE)
    window.show()
    model.select(None)
    shooter.shot(f"{prefix}_setup", window)
    window.centre.button_2d.setChecked(True)
    for index in range(len(model.blocks)):
        model.select(index)
        shooter.shot(f"{prefix}_block{index + 1}_2d", window)
    for index in range(len(model.blocks)):
        model.select(index)
        window.centre.button_3d.setChecked(True)
        shooter.shot(f"{prefix}_block{index + 1}_3d", window)
    window.centre.button_2d.setChecked(True)


def type_scenes(shooter: Shooter, window: MainWindow, model: AppModel) -> None:
    """A new block, tool and workholding of every type."""
    for type_name, _label in model.block_choices():
        shooter.scene(f"block {type_name}", lambda t=type_name: (model.select(model.add_block(t)), shooter.shot(f"new_block_{t}", window)))
    for type_name, _label in model.tool_type_choices():
        shooter.scene(f"tool {type_name}", lambda t=type_name: (model.add_tool_of_type(t), shooter.shot(f"new_tool_{t}", window)))
    for type_name, _label in model.workholding_type_choices():
        shooter.scene(f"workholding {type_name}", lambda t=type_name: (model.add_workholding_item(t), shooter.shot(f"new_workholding_{t}", window)))
    shooter.scene("contour", lambda: (model.select_contour(model.new_contour()), shooter.shot("new_contour", window)))


def special_scenes(shooter: Shooter, window: MainWindow, model: AppModel, folder: Path) -> None:
    """Views that need a state made by hand. Add new ones here: a function that makes the state and calls shooter.shot."""
    from wop.ui.app_model import ExportReport
    from wop.ui.qt.dialogs import ExportCheckDialog, IssuesDialog
    from wop.ui.qt.post_editor_dialog import PostEditorDialog

    def post_with_problem() -> None:
        editor = model.post_editor("linuxcnc")
        editor.set_section("feed", "G1 <Y>")  # an unknown token: the page, the list entry and the line turn red
        post_id = model.save_post(editor, model.unique_post_id("Broken post"))
        dialog = PostEditorDialog(window, model, post_id)
        shooter.walk_dialog("special_post_editor_with_problem", dialog)
        dialog.close()
        (model.posts_folder_path() / "binary.post.ini").write_bytes(bytes([255, 254, 0, 1]))
        model.reload_posts()
        dialog = PostEditorDialog(window, model, "binary")
        shooter.shot("special_post_editor_unreadable_file", dialog)
        dialog.close()

    def export_questions() -> None:
        dialog = ExportCheckDialog(window, ExportReport(False, ("block 2 is left out", "block 3: the post has no dwell")), lambda: ExportReport(True))
        dialog.show()
        shooter.shot("special_export_check", dialog)
        dialog.close()
        dialog = IssuesDialog(window, [])
        dialog.show()
        shooter.shot("special_issues_empty", dialog)
        dialog.close()

    def shape_dialogs() -> None:
        from wop.core.lathe.workholding import JAWS_KIND
        from wop.ui.qt.sketch_dialog import SketchDialog
        from wop.ui.qt.view3d_dialog import View3DDialog

        number = model.program.tools[0].number
        jaws = model.add_workholding_item(JAWS_KIND)
        picture = "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
        from wop.ui.qt.dialogs import ExportSelectedDialog

        for name, build in (
            ("tool_shape", lambda: SketchDialog(window, target=model.tool_sketch_target(number))),
            ("workholding_shape", lambda: SketchDialog(window, target=model.workholding_sketch_target(jaws))),
            ("view_3d_window", lambda: View3DDialog(window, model)),
            ("export_selected", lambda: ExportSelectedDialog(window, "title", lambda done: (picture, "notes", "code"), lambda done: None)),
        ):
            def one(build=build, name=name) -> None:
                dialog = build()
                shooter.walk_dialog(f"special_{name}", dialog)
                dialog.close()

            shooter.scene(name, one)

    def style_pictures_popup() -> None:
        from wop.ui.qt.style_preview import StylePreview, pictures_of
        from wop.ui.qt.theme_qt import color_set_from_palette

        colors = color_set_from_palette(window.palette())
        for block_type, keys in (("grooving", ("standard", "layers")), ("drilling", ("standard", "decreasing")), ("turning_contour", ("standard", "pockets_last"))):
            for key in keys:
                preview = StylePreview()
                preview.show_pictures(key, pictures_of(block_type, key, colors, window.palette().window().color().name()), window)
                shooter.shot(f"special_style_pictures_{block_type}_{key}", preview)
                preview.close()

    shooter.scene("style pictures", style_pictures_popup)
    shooter.scene("shape dialogs", shape_dialogs)
    def sketch_editor() -> None:
        """The sketch editor of a turning contour: a stepped shaft with a fillet and dimensions (tray closed, then open)."""
        from wop.core.geometry import Point
        from wop.core.sketch.modes import TURNING
        from wop.ui.qt.sketch_dialog import SketchDialog
        from wop.ui.sketch_constants import TOOL_DIMENSION, TOOL_LINE, TOOL_SELECT
        from wop.ui.sketch_session import SketchSession
        from wop.ui.sketch_target import SketchTarget

        session = SketchSession(target=SketchTarget(TURNING, "Sketch of Contour 1"))
        session.snapping = False
        tolerance = 0.5

        def click(x: float, z: float) -> None:
            session.move_hover(Point(x, z), tolerance)
            session.press(Point(x, z), tolerance)
            session.release(Point(x, z), tolerance)

        session.set_tool(TOOL_LINE)
        for x, z in ((10, 0), (10, -30), (18, -30), (18, -60)):
            click(x, z)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        click(10, -30)  # the corner point
        session.apply_corner("fillet", 3)
        session.set_tool(TOOL_DIMENSION)
        click(10, 0)  # a point and the spindle axis: the diameter
        click(0.1, -80)
        click(14, 12)
        click(18, -45)  # a line along the axis and the axis: its diameter
        click(0.1, -80)
        click(25, -52)
        click(18, -30)  # the length of the last step
        click(18, -60)
        click(26, -45)
        session.escape()
        dialog = SketchDialog(window, session=session)
        dialog.resize(1100, 720)
        dialog.canvas.scale = 8
        dialog.canvas.origin = QPointF(770, 540)  # the origin low and to the right: the part runs to negative Z, to the left
        dialog.canvas._placed = True
        dialog.show()
        shooter.shot("special_sketch_editor", dialog)
        dialog.splitter.open_panel(1)
        shooter.shot("special_sketch_editor_tray", dialog)
        dialog.close()

    shooter.scene("post with a problem", post_with_problem)
    shooter.scene("export dialogs", export_questions)
    shooter.scene("sketch editor", sketch_editor)


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    application = QApplication.instance() or QApplication(argv[:1])
    shooter = Shooter(application, folder)
    with tempfile.TemporaryDirectory() as scratch:
        model = AppModel(settings_path=Path(scratch) / "settings.json")
        window = MainWindow(model)
        window.resize(*WINDOW_SIZE)
        window.show()
        application.processEvents()
        for project in EXAMPLE_PROJECTS:
            shooter.scene(project, lambda p=project: window_scenes(shooter, window, model, p, Path(scratch)))
        shooter.scene("types", lambda: type_scenes(shooter, window, model))
        for number, top in enumerate(window.menuBar().actions()):
            if top.menu() is not None:
                shooter.scene(top.text(), lambda m=top.menu(), n=top.text().replace("&", ""): menu_pictures(shooter, m, n))
        skipped = trigger_menu_entries(shooter, window)
        special_scenes(shooter, window, model, folder)
        window.close()
    report = [f"{shooter.made} pictures ({shooter.theme} theme) in {folder}", f"menu entries not triggered: {', '.join(skipped) or 'none'}"]
    report += [f"PROBLEM {line}" for line in shooter.problems]
    (folder / f"_problems_{shooter.theme}.txt").write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
