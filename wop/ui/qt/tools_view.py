"""The Tools view in the centre (requirement T8): the tools of the program, their picture, Add and Delete.

Add makes a tool of the chosen type with the default values of its form. The form is in the right panel and
changes the tool as soon as a value is entered; clicking a tool in the list shows it.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..app_model import TOOL_DIFFERS_FROM_LIBRARY, AppModel, ModelError
from ..tool_preview import tool_svg
from ...core.sketch.model import SketchError
from .qt_constants import NO_TOOLS_TEXT, TOOL_OFFSET_MAX, TOOL_SHAPE_HINT
from .sketch_dialog import SketchDialog


class ToolsView(QWidget):
    notice = Signal(str)  # a short message for the window's messages box

    def __init__(self, model: AppModel) -> None:
        super().__init__()
        self.model = model
        self._building = False
        self._shown: list = []  # the tools of the list, in the order of the tool numbers
        self.tools = QListWidget()
        self.tools.currentRowChanged.connect(self._chosen)
        self.picture = QSvgWidget()
        self.toolbox_line = QLabel()
        self.toolbox_line.setToolTip("The toolbox the tools of this project came from. Tools > Use toolbox puts another one in.")
        self.make_default = QPushButton("Make default")
        self.make_default.setToolTip("A new project starts with the tools of the default toolbox. This makes the toolbox of this project the default.")
        self.make_default.clicked.connect(self._make_default)
        self.info = QLabel()
        self.info.setWordWrap(True)
        add = QToolButton()
        add.setText("Add tool")
        add.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add)
        for type_name, label in model.tool_type_choices():
            menu.addAction(label).triggered.connect(lambda _checked=False, t=type_name: self._add(t))
        add.setMenu(menu)
        from_library = QToolButton()
        from_library.setText("Add from library")
        from_library.setPopupMode(QToolButton.InstantPopup)
        self._library_menu = QMenu(from_library)
        self._library_menu.aboutToShow.connect(self._fill_library_menu)
        from_library.setMenu(self._library_menu)
        self.save_to_library = QPushButton("Save to library")
        self.save_to_library.clicked.connect(self._save_to_library)
        as_toolbox = QPushButton("Save as toolbox...")
        as_toolbox.setToolTip("Make a toolbox of the tools of this project (the tools must be in the library first). "
                              "A new project can start with it.")
        as_toolbox.clicked.connect(self._save_as_toolbox)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        sketch = QPushButton("Sketch editor...")
        sketch.setToolTip("Draw the outline in the sketch editor (relations, dimensions, import of a DXF drawing). " + TOOL_SHAPE_HINT)
        sketch.clicked.connect(self._edit_sketch)
        self.offset = QSpinBox()
        self.offset.setRange(0, TOOL_OFFSET_MAX)
        self.offset.setSpecialValueText("tool number")
        self.offset.setToolTip("The tool offset the post calls after the tool change (G43 H..). 'tool number': the offset has the "
                               "number of the tool. Set another number when the offset of this tool sits elsewhere in the tool table.")
        self.offset.valueChanged.connect(self._offset_chosen)
        buttons = QHBoxLayout()
        for widget in (add, from_library, self.save_to_library, as_toolbox, delete, sketch, QLabel("Tool offset:"), self.offset):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        toolbox_row = QHBoxLayout()
        toolbox_row.addWidget(self.toolbox_line)
        toolbox_row.addWidget(self.make_default)
        toolbox_row.addStretch(1)
        layout.addLayout(toolbox_row)
        layout.addLayout(buttons)
        layout.addWidget(self.tools, 1)
        layout.addWidget(self.picture, 2)
        layout.addWidget(self.info)

    def refresh(self) -> None:
        self._building = True
        self.tools.clear()
        self.toolbox_line.setText(self.model.toolbox_line())
        box = self.model.current_toolbox()
        is_default = box is not None and self.model.default_toolbox is not None and box.name.casefold() == self.model.default_toolbox.casefold()
        self.make_default.setEnabled(box is not None and not is_default)
        chosen = -1
        self._shown = sorted(self.model.program.tools, key=lambda t: t.number)
        if not self._shown:
            placeholder = QListWidgetItem(NO_TOOLS_TEXT)
            placeholder.setFlags(Qt.NoItemFlags)  # not a tool: it cannot be chosen
            placeholder.setForeground(self.palette().color(QPalette.Disabled, QPalette.Text))
            self.tools.addItem(placeholder)
        for row, tool in enumerate(self._shown):
            differs = " *" if self.model.tool_library_state(tool.number) == TOOL_DIFFERS_FROM_LIBRARY else ""
            self.tools.addItem(f"T{tool.number}  {tool.name}{differs}  ({tool.kind or 'shape'}, {tool.material.value})")
            if tool.number == self.model.selected_tool:
                chosen = row
        self.tools.setCurrentRow(chosen)
        self._building = False
        tool = next((t for t in self.model.program.tools if t.number == self.model.selected_tool), None)
        self._building = True
        self.offset.setEnabled(tool is not None)
        self.offset.setValue(0 if tool is None or tool.offset_number is None else tool.offset_number)
        self._building = False
        self.save_to_library.setEnabled(tool is not None)
        state = None if tool is None else self.model.tool_library_state(tool.number)
        self.save_to_library.setText("Update library tool" if state == TOOL_DIFFERS_FROM_LIBRARY else "Save to library")
        self.save_to_library.setToolTip("Write the chosen tool to the tool library in use. '*' in the list marks a tool "
                                        "that differs from the library tool of the same name.")
        lines = [] if tool is None else self.model.tool_info(tool.number)
        self.info.setText("\n".join(lines))
        self.picture.load(QByteArray(b"<svg xmlns='http://www.w3.org/2000/svg'/>" if tool is None
                                     else tool_svg(tool, self.model.colors).encode("utf-8")))

    def _fill_library_menu(self) -> None:
        self._library_menu.clear()
        names = [tool.name for tool in self.model.tool_library]
        for name in names:
            self._library_menu.addAction(name).triggered.connect(lambda _checked=False, n=name: self._add_from_library(n))
        if not names:
            self._library_menu.addAction("(the library is empty)").setEnabled(False)

    def _add_from_library(self, name: str) -> None:
        try:
            self.model.add_tool_from_library(name)
        except ModelError as error:
            self.notice.emit(str(error))

    def _save_to_library(self) -> None:
        number = self.model.selected_tool
        if number is None:
            return
        replace_existing = False
        if self.model.tool_library_state(number) == TOOL_DIFFERS_FROM_LIBRARY:
            name = self.model.program.tool(number).name
            answer = QMessageBox.question(
                self, "Tool library", f"The library has another tool called {name!r}. Replace it with this one?",
            )
            if answer != QMessageBox.Yes:
                return
            replace_existing = True
        try:
            self.notice.emit(self.model.save_tool_to_library(number, replace_existing))
        except ModelError as error:
            self.notice.emit(str(error))
        self.refresh()

    def _save_as_toolbox(self) -> None:
        current = self.model.current_toolbox()
        update = False
        if current is not None:  # the project has a toolbox: change that one or make another one
            ask = QMessageBox(self)
            ask.setWindowTitle("Save as toolbox")
            ask.setText(f"The tools of this project came from the toolbox {current.name!r}.")
            update_button = ask.addButton(f"Update {current.name!r}", QMessageBox.AcceptRole)
            new_button = ask.addButton("Make a new toolbox...", QMessageBox.ActionRole)
            ask.addButton(QMessageBox.Cancel)
            ask.exec()
            if ask.clickedButton() is update_button:
                update, name = True, current.name
            elif ask.clickedButton() is new_button:
                name = None
            else:
                return
        else:
            name = None
        if name is None:
            name, accepted = QInputDialog.getText(self, "Save as toolbox", "Name of the new toolbox:")
            if not accepted or not name.strip():
                return
            name = name.strip()
        try:
            self.model.save_project_tools_as_toolbox(name, update=update)
        except ModelError as error:
            self.notice.emit(str(error))
            return
        self.notice.emit(f"The toolbox {name!r} is " + ("updated" if update else "in the tool library"))

    def _make_default(self) -> None:
        try:
            self.model.make_current_toolbox_default()
        except ModelError as error:
            self.notice.emit(str(error))
            return
        self.notice.emit(f"{self.model.default_toolbox!r} is the default toolbox: a new project starts with its tools")

    def _offset_chosen(self, value: int) -> None:
        if self._building or self.model.selected_tool is None:
            return
        try:
            self.model.set_tool_offset(self.model.selected_tool, value or None)
        except ModelError as error:
            self.notice.emit(str(error))

    def _chosen(self, row: int) -> None:
        if self._building or not 0 <= row < len(self._shown):
            return
        self.model.select_tool(self._shown[row].number)

    def _add(self, type_name: str) -> None:
        try:
            self.model.add_tool_of_type(type_name)
        except ModelError as error:
            self.notice.emit(str(error))

    def _edit_sketch(self) -> None:
        if self.model.selected_tool is None:
            return
        try:
            SketchDialog(self, target=self.model.tool_sketch_target(self.model.selected_tool)).exec()
        except (ModelError, SketchError) as error:
            self.notice.emit(str(error))

    def _delete(self) -> None:
        if self.model.selected_tool is None:
            return
        try:
            self.model.remove_tool(self.model.selected_tool)
        except ModelError as error:
            self.notice.emit(str(error))
