"""The code table page of the post editor: the fixed codes under their headings, the work offsets, then the codes of the user."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ....post.post_constants import CODE_CUSTOM_HEADING, CODE_WORK_OFFSET_HEADING
from ..qt_constants import POST_UNGROUPED_NOTE
from .helpers import cell_text, cells_read_only, fields_in_cells, text_cell

HEADING, OFFSET_HEADING, FIXED, OFFSET, CUSTOM = "heading", "offset_heading", "fixed", "offset", "custom"  # what a row of the table is
HEADINGS = (HEADING, OFFSET_HEADING)


class CodeTableMixin:
    """The code table page. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _build_codes_page(self) -> QWidget:
        page = QWidget()
        hint = QLabel(
            "The codes the templates use as <code name>. The names above the line are known to the program (their names cannot be changed): type "
            "the code of your controller, or leave it empty when the controller has no such function. The work offsets (G54 ...) are the list the "
            "Setup form offers; add the ones your controller has. Below them you can add codes of your own. "
            "The modal group of a code comes from the Modal groups page; <code name changed> writes a code only when the last code of "
            "its group was another one."
        )
        hint.setWordWrap(True)
        self._codes_note = QLabel("")
        self._codes_note.setWordWrap(True)
        self._codes = QTableWidget(0, 4)
        self._codes.setHorizontalHeaderLabels(["Name", "Code", "Modal group", "Meaning"])
        fields_in_cells(self._codes)
        self._codes.horizontalHeader().setStretchLastSection(True)
        self._codes.setColumnWidth(0, 190)
        self._codes.setColumnWidth(1, 150)
        self._codes.setColumnWidth(2, 190)
        self._code_kinds: list[str] = []
        self._add_offset_button = QPushButton("Add a work offset")
        self._add_offset_button.clicked.connect(self._add_offset)
        self._add_code_button = QPushButton("Add a code of your own")
        self._add_code_button.clicked.connect(self._add_code)
        self._remove_code_button = QPushButton("Remove the selected code or work offset")
        self._remove_code_button.clicked.connect(self._remove_code)
        row = QHBoxLayout()
        row.addWidget(self._add_offset_button)
        row.addWidget(self._add_code_button)
        row.addWidget(self._remove_code_button)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(hint)
        layout.addWidget(self._codes_note)
        layout.addWidget(self._codes, 1)
        layout.addLayout(row)
        layout.addWidget(self._problem_label("codes"))
        return page

    def _fill_codes(self) -> None:
        table, editor = self._codes, self.editor
        table.setRowCount(0)
        self._code_kinds = []
        headings = editor.code_headings()
        rows = editor.code_rows()
        last = None
        for name, code, group, fixed, meaning in rows:
            if not fixed:
                continue
            if headings[name] != last:
                last = headings[name]
                self._add_code_heading(last)
            self._append_code_row(name, code, group, FIXED, meaning)
        self._add_code_heading(CODE_WORK_OFFSET_HEADING, OFFSET_HEADING)
        for name, code, group in editor.work_offset_rows():
            self._append_code_row(name, code, group, OFFSET, "")
        self._add_code_heading(CODE_CUSTOM_HEADING)
        for name, code, group, fixed, meaning in rows:
            if not fixed:
                self._append_code_row(name, code, group, CUSTOM, "")
        self._update_codes_note()

    def _add_code_heading(self, text: str, kind: str = HEADING) -> None:
        row = self._codes.rowCount()
        self._codes.insertRow(row)
        item = QTableWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self._codes.setItem(row, 0, item)
        self._codes.setSpan(row, 0, 1, 4)
        self._code_kinds.append(kind)

    def _append_code_row(self, name: str, code: str, group: str, kind: str, meaning: str, at: int | None = None) -> None:
        table = self._codes
        row = table.rowCount() if at is None else at
        table.insertRow(row)
        if kind in (FIXED, OFFSET):
            first = QTableWidgetItem(name)
            first.setFlags(first.flags() & ~Qt.ItemIsEditable)  # the name of a fixed code cannot be changed
            first.setToolTip(meaning)
            table.setItem(row, 0, first)
        else:
            text_cell(table, row, 0, name, self._codes_changed)
        text_cell(table, row, 1, code, self._codes_changed)
        for column, text in ((2, group), (3, meaning)):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column == 2:
                item.setToolTip("The modal group of this code comes from the Modal groups page.")
            table.setItem(row, column, item)
        self._code_kinds.insert(row, kind)

    def _add_offset(self) -> None:
        """A new work offset at the end of the list; its name is its number."""
        if self.editor is None or self.editor.shipped:
            return
        end = self._code_kinds.index(OFFSET_HEADING) + 1 + self._code_kinds.count(OFFSET)
        self._loading = True
        self._append_code_row(self.editor.work_offset_name(self._code_kinds.count(OFFSET) + 1), "", "", OFFSET, "", at=end)
        self._loading = False
        self._codes.cellWidget(end, 1).setFocus()

    def _add_code(self) -> None:
        if self.editor is None or self.editor.shipped:
            return
        self._loading = True
        self._append_code_row("", "", "", CUSTOM, "")
        self._loading = False
        self._codes.cellWidget(self._codes.rowCount() - 1, 0).setFocus()

    def _remove_code(self) -> None:
        row = self._codes.currentRow()
        if 0 <= row < len(self._code_kinds) and self._code_kinds[row] in (CUSTOM, OFFSET) and self.editor is not None and not self.editor.shipped:
            self._codes.removeRow(row)
            del self._code_kinds[row]
            self._codes_changed()

    def _codes_changed(self) -> None:
        table = self._codes
        position = 0
        for row, kind in enumerate(self._code_kinds):  # the work offsets are numbered in the order of their rows
            if kind == OFFSET:
                position += 1
                table.item(row, 0).setText(self.editor.work_offset_name(position))
        rows = [(cell_text(table, row, 0), cell_text(table, row, 1)) for row, kind in enumerate(self._code_kinds) if kind not in HEADINGS]
        self._edit(lambda: self.editor.set_code_rows(rows))
        for row, kind in enumerate(self._code_kinds):  # the group column follows what was typed
            item = table.item(row, 2)
            if kind not in HEADINGS and item is not None:
                item.setText(self.editor.group_of_code(cell_text(table, row, 1)))
        self._update_codes_note()

    def _codes_read_only(self, read_only: bool) -> None:
        cells_read_only(self._codes, read_only)
        self._add_offset_button.setEnabled(not read_only)
        self._add_code_button.setEnabled(not read_only)
        self._remove_code_button.setEnabled(not read_only)

    def _update_codes_note(self) -> None:
        """Say which codes of the table are in no modal group."""
        if self.editor is None:
            return
        names = self.editor.ungrouped_codes()
        self._codes_note.setText(POST_UNGROUPED_NOTE.format(names=", ".join(names)) if names else "")
