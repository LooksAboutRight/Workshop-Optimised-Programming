"""The modal groups page of the post editor and the note of the code table."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ....post.modal_groups import FIXED_NAMES
from ..qt_constants import POST_CUSTOM_GROUPS_TEXT
from .helpers import cell_text, cells_read_only, fields_in_cells, text_cell


class ModalGroupsMixin:
    """The modal groups page: one line per group, the fixed groups on top (their names cannot be changed), then the groups of the
    user. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _build_modal_groups_page(self) -> QWidget:
        page = QWidget()
        hint = QLabel(
            "Which codes cancel each other. Type the G and M codes of each group, separated by spaces. The code table takes its modal group "
            "from here: <code name changed> writes a code only when the last code of its group was another one. A code can be in one "
            "group only. The groups above the line are known to the program (their names cannot be changed); below it you can add your own."
        )
        hint.setWordWrap(True)
        self._groups = QTableWidget(0, 3)
        self._groups.setHorizontalHeaderLabels(["Group", "Codes", "Meaning"])
        fields_in_cells(self._groups)
        self._groups.horizontalHeader().setStretchLastSection(True)
        self._groups.setColumnWidth(0, 200)
        self._groups.setColumnWidth(1, 420)
        self._add_group_button = QPushButton("Add a group of your own")
        self._add_group_button.clicked.connect(self._add_group)
        self._remove_group_button = QPushButton("Remove the selected group")
        self._remove_group_button.clicked.connect(self._remove_group)
        row = QHBoxLayout()
        row.addWidget(self._add_group_button)
        row.addWidget(self._remove_group_button)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(hint)
        layout.addWidget(self._groups, 1)
        layout.addLayout(row)
        layout.addWidget(self._problem_label("modal_groups"))
        return page

    @staticmethod
    def _group_item(text: str, editable: bool, tip: str = "") -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if tip:
            item.setToolTip(tip)
        return item

    def _fill_modal_groups(self) -> None:
        self._groups.setRowCount(0)
        rows = self.editor.modal_groups()
        for name, codes, fixed in (row for row in rows if row[2]):
            self._append_group_row(name, codes, True)
        separator_row = self._groups.rowCount()
        self._groups.insertRow(separator_row)
        separator = self._group_item(POST_CUSTOM_GROUPS_TEXT, False)
        separator.setFlags(Qt.NoItemFlags)
        font = separator.font()
        font.setBold(True)
        separator.setFont(font)
        self._groups.setItem(separator_row, 0, separator)
        self._groups.setSpan(separator_row, 0, 1, 3)
        for name, codes, fixed in (row for row in rows if not row[2]):
            self._append_group_row(name, codes, False)

    def _append_group_row(self, name: str, codes: str, fixed: bool) -> None:
        row = self._groups.rowCount()
        self._groups.insertRow(row)
        meaning = self.editor.modal_group_meaning(name) if fixed else ""
        if fixed:
            self._groups.setItem(row, 0, self._group_item(name, False, meaning))  # the name of a fixed group cannot be changed
        else:
            text_cell(self._groups, row, 0, name, self._modal_groups_changed)
        text_cell(self._groups, row, 1, codes, self._modal_groups_changed)
        self._groups.setItem(row, 2, self._group_item(meaning, False, meaning))

    def _modal_groups_changed(self) -> None:
        rows: list[tuple[str, str]] = []
        for row in range(self._groups.rowCount()):
            if row == len(FIXED_NAMES):
                continue  # the line that stands before the groups of the user
            rows.append((cell_text(self._groups, row, 0), cell_text(self._groups, row, 1)))
        self._edit(lambda: self.editor.set_modal_groups(rows))
        self._update_codes_note()

    def _add_group(self) -> None:
        if self.editor is None or self.editor.shipped:
            return
        self._loading = True
        self._append_group_row("", "", False)
        self._loading = False
        self._groups.cellWidget(self._groups.rowCount() - 1, 0).setFocus()

    def _remove_group(self) -> None:
        row = self._groups.currentRow()
        if row > len(FIXED_NAMES) and self.editor is not None and not self.editor.shipped:  # only a group of the user
            self._groups.removeRow(row)
            self._modal_groups_changed()

    def _groups_read_only(self, read_only: bool) -> None:
        cells_read_only(self._groups, read_only)
        self._add_group_button.setEnabled(not read_only)
        self._remove_group_button.setEnabled(not read_only)
