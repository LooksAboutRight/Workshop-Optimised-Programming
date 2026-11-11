"""The pictures of the manual that need something to be open above a window: a menu, a dropdown list, a hover text.

Usage (project root):  python tools/manual_scenes.py [folder]     (default folder: docs/manual/images)
Run by `tools/make_manual.py --pictures`; the other pictures of the manual come from `tools/make_screenshots.py`.

Each scene opens the thing from code, pastes it onto the picture of the window, adds the mouse pointer (white with a black
edge) and red callouts or frames where the text of the manual points at something, and crops the result. A scene that fails
is listed at the end; the others are still made. `COMPOSED` names the pictures (so `tools/make_manual.py` and the test know them).
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import replace
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QPoint, QPointF, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QToolButton  # noqa: E402

import picture_marks as marks  # noqa: E402
from wop.core.blocks.custom_path import CustomPathBlock  # noqa: E402
from wop.core.constants import CLAMP_PLANE_POINT  # noqa: E402
from wop.core.contour import ContourDefinition, LineStep  # noqa: E402
from wop.core.contour_solver import build_contour  # noqa: E402
from wop.core.geometry import Point  # noqa: E402
from wop.core.program_model.touched import SETUP_OWNER  # noqa: E402
from wop.core.sketch.model import Sketch  # noqa: E402
from wop.core.sketch.modes import RAW_PART, contour_from_sketch  # noqa: E402
from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.block_forms import form_for  # noqa: E402
from wop.ui.qt.main_window import MainWindow  # noqa: E402
from wop.ui.qt.preferences_dialog import PreferencesDialog  # noqa: E402
from wop.ui.qt.sketch_dialog import SketchDialog  # noqa: E402

DEFAULT_FOLDER = PROJECT_ROOT / "docs" / "manual" / "images"
COMPOSED = (
    "file_menu_in_window", "sketch_hover_text", "preferences_dropdown", "window_parts", "setup_form", "setup_raw_part", "sketch_raw_part",
    "contour_form", "block_facing", "block_turning", "block_turning_contour", "block_drilling", "block_threading", "block_grooving",
    "block_machine_function", "block_custom_path", "sketch_path",
)
FORM_WINDOW_SIZE = (1600, 1500)  # tall: a long form fits in the right column without scrolling
SHAFT = ((0, 0), (10, 0), (10, -20), (15, -20), (15, -30), (15, -50), (0, -50))  # a stepped raw part: radius 10, then 15; the jaws begin at z -30
SHAFT_CLAMP_INDEX = 4
PATH_SCALE_PX_PER_MM = 14  # the path picture is zoomed in so that the small example path can be seen
SHAFT_CONTOUR = ((8, 0), (8, -10), (12, -10), (12, -25), (14, -25), (14, -40))  # the stepped shaft of the block examples
WINDOW_SIZE = (1600, 950)
EXAMPLE = "collision_demo.wop.json"


def file_menu_in_window(window: MainWindow) -> marks.Picture:
    """The File menu open over the main window, the pointer on Export G-code."""
    window.show()
    QApplication.processEvents()
    file_action = next(a for a in window.menuBar().actions() if a.text().replace("&", "") == "File")
    menu = marks.open_menu(window.menuBar(), file_action)
    picture = marks.Picture(window)
    picture.add_popup(menu)
    shape = window.menuBar().actionGeometry(file_action)
    picture.frame(QRect(picture.local(window.menuBar().mapToGlobal(shape.topLeft())), shape.size()), margin=1)
    entry = picture.local(marks.entry_point(menu, "Export G-code..."))
    picture.pointer(entry + QPoint(-45, 2))  # on the words of the entry, not over its shortcut
    picture.crop(QRect(0, 0, 470, 330))
    marks.close_popups(menu)
    return picture


def sketch_hover_text() -> marks.Picture:
    """The sketch editor with the hover text of the Mirror button and the pointer on the button."""
    dialog = SketchDialog()
    dialog.resize(900, 640)
    dialog.show()
    QApplication.processEvents()
    button = dialog.tool_buttons["mirror"]
    tip = marks.show_hover_text(button)
    picture = marks.Picture(dialog)
    picture.add_popup(tip)
    here = picture.where(button)
    picture.frame(here)
    picture.pointer(here.center() + QPoint(2, 2))
    picture.crop(QRect(0, 0, 420, 330))
    marks.close_popups()
    dialog.close()
    return picture


def preferences_dropdown(window: MainWindow, model: AppModel) -> marks.Picture:
    """The preferences with the list of the material of a new project open and the pointer on one entry."""
    dialog = PreferencesDialog(window, model)
    dialog.resize(980, 520)
    dialog.show()
    QApplication.processEvents()
    combo = next(editor for editor in dialog._editors.values() if isinstance(editor, QComboBox))
    popup = marks.open_dropdown(combo)
    picture = marks.Picture(dialog)
    picture.add_popup(popup)
    row = min(1, combo.count() - 1)
    picture.callout(1, picture.where(combo).topLeft() + QPoint(-18, 8), picture.where(combo).topLeft() + QPoint(-2, 8))
    picture.pointer(picture.local(marks.dropdown_item_point(combo, row)) + QPoint(20, 0))
    picture.crop(QRect(0, 0, 980, 260))
    marks.close_popups(combo)
    dialog.close()
    return picture



def window_parts(window: MainWindow) -> marks.Picture:
    """The whole window with eight numbered parts (the chapter 'The main window' explains them)."""
    window.show()
    window.centre.button_2d.setChecked(True)
    QApplication.processEvents()
    picture = marks.Picture(window)
    where = picture.where
    left, middle, right = (window.splitter.widget(i) for i in range(3))
    names = ("Add block", "Delete", "Up", "Down", "Export selected...")
    buttons = [w for kind in (QPushButton, QToolButton) for w in left.findChildren(kind) if w.text() in names and w.isVisible()]
    union = where(buttons[0])
    for button in buttons[1:]:
        union = union.united(where(button))
    controls = [window.centre.button_2d, window.centre.button_3d, window.centre.upto, window.centre.step_check, window.centre.reset_button]
    row = where(controls[0])
    for widget in controls[1:]:
        row = row.united(where(widget))
    messages = where(window.messages)
    area = QRect(where(middle).left(), row.bottom() + 6, where(middle).width(), messages.top() - row.bottom() - 12)
    picture.frame(QRect(0, 0, 420, where(window.menuBar()).height()), margin=0)
    picture.frame(where(window.flow), margin=2)
    picture.frame(union, margin=2)
    picture.frame(row, margin=2)
    picture.frame(area, margin=0)
    picture.frame(messages, margin=2)
    picture.frame(where(right), margin=0)
    for handle in (window.splitter.handle(1), window.splitter.handle(2)):
        picture.frame(where(handle), margin=1)
    picture.callout(1, QPoint(445, 16))
    picture.callout(2, where(window.flow).center() + QPoint(0, 160))
    picture.callout(3, union.center() + QPoint(0, -38))
    picture.callout(4, QPoint(row.right() + 24, row.center().y()))
    picture.callout(5, area.center() + QPoint(0, 150))
    picture.callout(6, QPoint(messages.right() - 24, messages.center().y()))
    picture.callout(7, QPoint(where(right).right() - 24, where(window.form_title).center().y()))
    spot = where(window.splitter.handle(1)).center()
    picture.callout(8, spot + QPoint(-24, -70), spot + QPoint(-3, -50))
    return picture


def _form_picture(window: MainWindow) -> marks.Picture:
    """The right column of the window (the title and the form) as a picture."""
    window._show_form()  # the colours of what was typed
    window.show()
    QApplication.processEvents()
    picture = marks.Picture(window)
    column = picture.where(window.splitter.widget(2))
    top = picture.where(window.form_title)
    height = window.form.sizeHint().height() + (top.height() + 16) + 24
    picture.crop(QRect(column.left(), top.top() - 8, column.width(), height))
    return picture


def _touch_all(model: AppModel, index: int) -> None:
    """The values of a block as if the user had typed them (they are shown in the normal colour, not as presets)."""
    owner = model.block_owner(index)
    for spec in form_for(model.blocks[index], model.form_context()):
        model.set_touched(owner, spec.path)


def _touch_setup(model: AppModel) -> None:
    for spec in form_for(model.setup_form(), model.form_context()):
        model.set_touched(SETUP_OWNER, spec.path)


def setup_form(window: MainWindow, model: AppModel) -> marks.Picture:
    model.select(None)
    _touch_setup(model)
    QApplication.processEvents()
    return _form_picture(window)


def _stepped_raw_part() -> Sketch:
    shaft = Sketch()
    ids = [shaft.add_point(x, z) for x, z in SHAFT]
    for first, second in zip(ids, ids[1:]):
        shaft.add_line(first, second)
    shaft.label_point(ids[SHAFT_CLAMP_INDEX], CLAMP_PLANE_POINT)
    return shaft


def setup_raw_part(window: MainWindow, model: AppModel) -> marks.Picture:
    """The Setup after a raw part was drawn: the numbers of the part are grey, the button goes back to a bar."""
    model.draw_raw_part(contour_from_sketch(_stepped_raw_part(), RAW_PART, "raw", "Raw part"))
    model.select(None)
    _touch_setup(model)
    QApplication.processEvents()
    return _form_picture(window)


def sketch_raw_part(window: MainWindow, model: AppModel) -> marks.Picture:
    """The sketch editor of the raw part: a stepped shaft, the clamping plane named and drawn as a green dashed line."""
    dialog = SketchDialog(window, target=model.raw_part_sketch_target())
    dialog.resize(1000, 600)
    dialog.show()
    QApplication.processEvents()
    picture = marks.Picture(dialog)
    canvas = picture.where(dialog.canvas).topLeft()
    clamp_at = canvas + dialog.canvas.to_screen(Point(15, -30)).toPoint()
    picture.callout(1, clamp_at + QPoint(70, -40), clamp_at + QPoint(4, -3))
    dialog.close()
    return picture


def contour_form(window: MainWindow, model: AppModel) -> marks.Picture:
    window.show()
    if not model.program.contours:  # the example has none: the shaft of the block examples
        steps = tuple(LineStep(Point(x, z)) for x, z in SHAFT_CONTOUR[1:])
        model.set_contour(build_contour("shaft", "stepped shaft", ContourDefinition(Point(*SHAFT_CONTOUR[0]), steps)))
    model.select_contour(model.program.contours[0].contour_id)
    QApplication.processEvents()
    picture = marks.Picture(window)
    column = picture.where(window.splitter.widget(2))
    top = picture.where(window.form_title)
    panel = picture.where(window.contour_panel)
    picture.crop(QRect(column.left(), top.top() - 8, column.width(), panel.bottom() - top.top() + 20))
    return picture


def _block_picture(window: MainWindow, model: AppModel, type_name: str) -> marks.Picture:
    index = model.add_block(type_name)
    _touch_all(model, index)
    QApplication.processEvents()
    return _form_picture(window)


def sketch_path(window: MainWindow, model: AppModel) -> marks.Picture:
    """The sketch editor of a custom path: the safe point and the part in green, the path stepped to its second piece."""
    index = model.add_block("custom_path")
    block = model.blocks[index]
    sample = CustomPathBlock.sample(block.block_id, block.tool_number, block.spindle)
    model.replace_block(index, replace(block, sketch=sample.sketch))
    dialog = SketchDialog(window, target=model.path_sketch_target(index))
    dialog.resize(1100, 700)
    dialog.show()
    QApplication.processEvents()
    dialog.canvas.scale = PATH_SCALE_PX_PER_MM
    dialog.canvas.origin = QPointF(dialog.canvas.width() * 0.62, dialog.canvas.height() * 0.8)
    dialog.session.step_forward()
    dialog.session.step_forward()
    QApplication.processEvents()
    picture = marks.Picture(dialog)
    dialog.close()
    return picture


def _form_scenes(folder: Path, scratch: str, problems: list[str], application: QApplication) -> int:
    """The pictures of forms and sketch dialogs, made in a tall window of their own so that a long form does not scroll."""
    model = AppModel(settings_path=Path(scratch) / "settings_forms.json")
    copy = Path(scratch) / "forms_example.wop.json"
    shutil.copyfile(PROJECT_ROOT / "tests" / "data" / "projects" / EXAMPLE, copy)
    model.open(copy)
    window = MainWindow(model)
    window.resize(*FORM_WINDOW_SIZE)
    overview_model = AppModel(settings_path=Path(scratch) / "settings_overview.json")
    overview_copy = Path(scratch) / "overview_example.wop.json"
    shutil.copyfile(PROJECT_ROOT / "examples" / "reference.wop.json", overview_copy)
    overview_model.open(overview_copy)
    overview_window = MainWindow(overview_model)
    overview_window.resize(*WINDOW_SIZE)
    overview_model.select(2)
    scenes = [
        ("window_parts", lambda: window_parts(overview_window)),
        ("setup_form", lambda: setup_form(window, model)),
        ("contour_form", lambda: contour_form(window, model)),
        ("sketch_path", lambda: sketch_path(window, model)),
    ]
    for type_name in ("facing", "turning", "turning_contour", "drilling", "threading", "grooving", "machine_function", "custom_path"):
        scenes.append((f"block_{type_name}", lambda t=type_name: _block_picture(window, model, t)))
    scenes += [("setup_raw_part", lambda: setup_raw_part(window, model)), ("sketch_raw_part", lambda: sketch_raw_part(window, model))]
    made = 0
    for name, scene in scenes:
        try:
            scene().save(folder / f"{name}.png")
            made += 1
        except Exception:  # a scene must not stop the others
            problems.append(f"{name}: {traceback.format_exc().strip().splitlines()[-1]}")
        application.processEvents()
    _close(window)
    _close(overview_window)
    return made


def _close(window: MainWindow) -> None:
    """Close a window without the questions (save the project, update the tool library): nobody is there to answer."""
    window.model.dirty = False
    window._ask_save_changes = lambda: True
    window.close()


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    application = QApplication.instance() or QApplication(argv[:1])
    marks.disable_effects()
    problems: list[str] = []
    made = 0
    with tempfile.TemporaryDirectory() as scratch:
        model = AppModel(settings_path=Path(scratch) / "settings.json")
        copy = Path(scratch) / EXAMPLE
        shutil.copyfile(PROJECT_ROOT / "tests" / "data" / "projects" / EXAMPLE, copy)
        model.open(copy)
        window = MainWindow(model)
        window.resize(*WINDOW_SIZE)
        scenes = (
            ("file_menu_in_window", lambda: file_menu_in_window(window)),
            ("sketch_hover_text", sketch_hover_text),
            ("preferences_dropdown", lambda: preferences_dropdown(window, model)),
        )
        for name, scene in scenes:
            try:
                scene().save(folder / f"{name}.png")
                made += 1
            except Exception:  # a scene must not stop the others
                problems.append(f"{name}: {traceback.format_exc().strip().splitlines()[-1]}")
            application.processEvents()
        _close(window)
        made += _form_scenes(folder, scratch, problems, application)
    print(f"{made} composed pictures in {folder}")
    for line in problems:
        print(f"PROBLEM {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
