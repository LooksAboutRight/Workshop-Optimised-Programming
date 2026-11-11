"""The toolboxes of the tool library: create, rename, delete, the default one, and the tools of a box with their numbers (T17).

A change is saved as soon as it is valid (a number used twice stays in the table with a message until it is corrected).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.tooling.toolbox import Toolbox, ToolboxEntry
from ..app_model import AppModel, ModelError
from .qt_constants import APP_NAME, TOOL_OFFSET_MAX, TOOLBOX_DIALOG_HEIGHT_PX, TOOLBOX_DIALOG_WIDTH_PX

DEFAULT_MARK = "  (default)"
COLUMN_TOOL, COLUMN_NUMBER, COLUMN_OFFSET = range(3)


class ToolboxesDialog(QDialog):
    """The toolboxes of the active tool library on the left, the tools of the chosen one on the right."""

    def __init__(self, parent: QWidget, model: AppModel) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Toolboxes of the library {model.active_library_name('tools')!r}")
        self.resize(TOOLBOX_DIALOG_WIDTH_PX, TOOLBOX_DIALOG_HEIGHT_PX)
        self.model = model
        self._name: str | None = None
        self._building = False
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._selected)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Tool of the library", "Tool number", "Tool offset"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(COLUMN_TOOL, 260)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        self._hint = QLabel("A toolbox is a set of library tools with the numbers they have in the project. A new project gets a copy "
                            "of the default toolbox; 'Use toolbox' in the Tools menu puts a toolbox into the open project.")
        self._hint.setWordWrap(True)
        new = QPushButton("New")
        new.clicked.connect(lambda _checked=False: self._new())
        rename = QPushButton("Rename")
        rename.clicked.connect(lambda _checked=False: self._rename())
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda _checked=False: self._delete())
        self._default = QPushButton("Make default")
        self._default.setToolTip("A new project starts with a copy of the default toolbox. Without one it has no tools.")
        self._default.clicked.connect(lambda _checked=False: self._toggle_default())
        add_tool = QPushButton("Add tool")
        add_tool.clicked.connect(lambda _checked=False: self._add_row())
        remove_tool = QPushButton("Remove tool")
        remove_tool.clicked.connect(lambda _checked=False: self._remove_row())
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        left_buttons = QHBoxLayout()
        for button in (new, rename, delete):
            left_buttons.addWidget(button)
        left = QVBoxLayout()
        left.addWidget(self._list)
        left.addLayout(left_buttons)
        left.addWidget(self._default)
        right_buttons = QHBoxLayout()
        right_buttons.addWidget(add_tool)
        right_buttons.addWidget(remove_tool)
        right_buttons.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(self._table, 1)
        right.addLayout(right_buttons)
        right.addWidget(self._message)
        columns = QHBoxLayout()
        columns.addLayout(left, 1)
        columns.addLayout(right, 2)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self._hint)
        layout.addLayout(columns, 1)
        layout.addLayout(bottom)
        self._fill_list(self.model.default_toolbox or (self.model.toolboxes[0].name if self.model.toolboxes else None))

    # --- the list of boxes -------------------------------------------------------

    def _fill_list(self, choose: str | None) -> None:
        self._building = True
        self._list.clear()
        row = -1
        for index, box in enumerate(self.model.toolboxes):
            is_default = self.model.default_toolbox is not None and box.name.casefold() == self.model.default_toolbox.casefold()
            self._list.addItem(box.name + (DEFAULT_MARK if is_default else ""))
            if choose is not None and box.name.casefold() == choose.casefold():
                row = index
        self._list.setCurrentRow(row)
        self._building = False
        self._selected(row)

    def _selected(self, row: int) -> None:
        if self._building:
            return
        boxes = self.model.toolboxes
        self._name = boxes[row].name if 0 <= row < len(boxes) else None
        self._message.setText("" if self._name is not None else "No toolbox yet: press New.")
        self._fill_table()
        is_default = self._name is not None and self.model.default_toolbox is not None and self._name.casefold() == self.model.default_toolbox.casefold()
        self._default.setText("No default toolbox" if is_default else "Make default")
        self._default.setEnabled(self._name is not None)

    def _new(self) -> None:
        name, accepted = QInputDialog.getText(self, "New toolbox", "Name of the toolbox:")
        if accepted and name.strip():
            self._action(lambda: self.model.save_toolbox(Toolbox(name.strip())), name.strip())

    def _rename(self) -> None:
        if self._name is None:
            return
        name, accepted = QInputDialog.getText(self, "Rename toolbox", "New name:", text=self._name)
        if accepted and name.strip():
            box = next(b for b in self.model.toolboxes if b.name == self._name)
            self._action(lambda: self.model.save_toolbox(Toolbox(name.strip(), box.entries), old_name=self._name), name.strip())

    def _delete(self) -> None:
        if self._name is None:
            return
        if QMessageBox.question(self, APP_NAME, f"Delete the toolbox {self._name!r}? Projects that were made with it keep their tools.") != QMessageBox.Yes:
            return
        self._action(lambda: self.model.delete_toolbox(self._name), None)

    def _toggle_default(self) -> None:
        if self._name is None:
            return
        is_default = self.model.default_toolbox is not None and self._name.casefold() == self.model.default_toolbox.casefold()
        self._action(lambda: self.model.set_default_toolbox(None if is_default else self._name), self._name)

    def _action(self, action, choose: str | None) -> None:
        try:
            action()
        except ModelError as error:
            self._message.setText(str(error))
            return
        self._fill_list(choose)

    # --- the tools of a box ------------------------------------------------------

    def _library_names(self) -> list[str]:
        return [tool.name for tool in self.model.tool_library]

    def _fill_table(self) -> None:
        self._building = True
        self._table.setRowCount(0)
        box = next((b for b in self.model.toolboxes if b.name == self._name), None)
        for entry in () if box is None else box.entries:
            self._append_row(entry.tool_name, entry.number, entry.offset_number or 0)
        self._building = False

    def _append_row(self, tool_name: str, number: int, offset: int) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        combo = QComboBox()
        combo.addItems(self._library_names())
        combo.setCurrentText(tool_name)
        combo.currentIndexChanged.connect(lambda _index: self._commit())
        number_box = QSpinBox()
        number_box.setRange(1, TOOL_OFFSET_MAX)
        number_box.setValue(number)
        number_box.editingFinished.connect(self._commit)
        number_box.valueChanged.connect(lambda _value: self._commit())
        offset_box = QSpinBox()
        offset_box.setRange(0, TOOL_OFFSET_MAX)
        offset_box.setSpecialValueText("tool number")
        offset_box.setValue(offset)
        offset_box.valueChanged.connect(lambda _value: self._commit())
        self._table.setCellWidget(row, COLUMN_TOOL, combo)
        self._table.setCellWidget(row, COLUMN_NUMBER, number_box)
        self._table.setCellWidget(row, COLUMN_OFFSET, offset_box)

    def _add_row(self) -> None:
        if self._name is None:
            self._message.setText("Make a toolbox first: press New.")
            return
        names = self._library_names()
        if not names:
            self._message.setText("The tool library has no tools yet: save tools to the library first (Tools view, 'Save to library').")
            return
        used = {self._table.cellWidget(r, COLUMN_TOOL).currentText() for r in range(self._table.rowCount())}
        numbers = [self._table.cellWidget(r, COLUMN_NUMBER).value() for r in range(self._table.rowCount())]
        self._building = True
        self._append_row(next((n for n in names if n not in used), names[0]), max(numbers, default=0) + 1, 0)
        self._building = False
        self._commit()

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._commit()

    def _commit(self) -> None:
        """Save the box as the table shows it, when it is valid; else say what is wrong and leave the table as it is."""
        if self._building or self._name is None:
            return
        entries = tuple(
            ToolboxEntry(
                self._table.cellWidget(r, COLUMN_TOOL).currentText(),
                self._table.cellWidget(r, COLUMN_NUMBER).value(),
                self._table.cellWidget(r, COLUMN_OFFSET).value() or None,
            )
            for r in range(self._table.rowCount())
        )
        try:
            self.model.save_toolbox(Toolbox(self._name, entries))
        except (ModelError, ValueError) as error:
            self._message.setText(f"Not saved: {error}")
            return
        self._message.setText("Saved.")
