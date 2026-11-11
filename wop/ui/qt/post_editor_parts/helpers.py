"""Constants and small functions shared by the parts."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QTableWidget

from ....post.post_constants import POST_FILE_SUFFIX
from ....post.post_definition import DRILLING_STYLES, LINE_ENDINGS, THREADING_STYLES


CHOICES = {"line_ending": tuple(LINE_ENDINGS), "threading_style": THREADING_STYLES, "drilling_style": DRILLING_STYLES}


SPIN_MAX = 100000


NOTHING_WRITTEN = "(nothing is written)"


SEPARATOR_TEXT = "Concepts"


IMPORT_FILTER = f"WOP post (*{POST_FILE_SUFFIX});;All files (*)"


class CellEdit(QLineEdit):
    """A real text field inside a table cell: the cursor goes where you click, typing adds to the text. (The editor that Qt opens for a
    table cell selects all the text first, so the first key replaces everything, and an empty cell is hard to click into.)"""

    def __init__(self, table: QTableWidget, text: str) -> None:
        super().__init__(text)
        self._table = table

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().focusInEvent(event)
        index = self._table.indexAt(self.pos())  # the row of this field becomes the current row (for the Remove button)
        if index.isValid():
            self._table.setCurrentCell(index.row(), index.column())


def text_cell(table: QTableWidget, row: int, column: int, text: str, changed) -> CellEdit:
    """Put a text field into a cell; `changed()` is called after every edit by the user."""
    edit = CellEdit(table, text)
    edit.textEdited.connect(lambda _text: changed())
    table.setCellWidget(row, column, edit)
    return edit


def cell_text(table: QTableWidget, row: int, column: int) -> str:
    """The text of a cell: of its text field, else of its item."""
    widget = table.cellWidget(row, column)
    if isinstance(widget, QLineEdit):
        return widget.text()
    item = table.item(row, column)
    return item.text() if item is not None else ""


def fields_in_cells(table: QTableWidget) -> None:
    """The cells that can be edited hold text fields (`text_cell`); the table itself opens no editor of its own."""
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)


def cells_read_only(table: QTableWidget, read_only: bool) -> None:
    """Make the text fields of a table read only (or editable again). The table itself stays enabled: a disabled table cannot be scrolled."""
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            widget = table.cellWidget(row, column)
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(read_only)
