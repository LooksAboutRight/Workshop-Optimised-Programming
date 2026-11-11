"""File > Postprocessors: look at, write and change the post files (`*.post.ini`) that turn the program into G-code.

Left the pages of the post: the post itself, its settings, the code table, the modal groups and one page per concept (rapid,
feed, tool change ...). A concept page has the template, the sample output for two cases (every optional part present and
everything changed / nothing changed and every optional part gone) and a grid of the tokens that work in the concept.
The sample output follows the typing. A post that comes with WOP is read-only; Save as copy makes one of your own."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from ...core.program_model.units import XInputMode
from ...post.concepts import CONCEPTS
from ...post.post_constants import POST_FILE_SUFFIX
from ..app_model import AppModel, ModelError
from ..post_editor_model import PostEditorModel, Preview, TokenButton
from ..ui_constants import POST_EDITOR_TOKEN_GROUPS
from .qt_constants import POST_DEFAULT_NOTE, POST_DIALOG_HEIGHT_PX, POST_DIALOG_WIDTH_PX, POST_ERROR_COLOR, POST_ERROR_LINE_COLOR, POST_ERROR_LINE_TEXT_COLOR, POST_NEW_ID, POST_NEW_MARK, POST_OWN_NOTE, POST_PAGES, POST_PROBLEMS_MARK, POST_SHIPPED_MARK, POST_UNREADABLE_MARK, POST_TOKEN_COLUMNS, POST_TOKEN_LIST_HEIGHT_PX, POST_TOKEN_LIST_WIDTH_PX
from .post_editor_parts.codes import CodeTableMixin
from .post_editor_parts.functions import FunctionsMixin
from .post_editor_parts.groups import ModalGroupsMixin
from .post_editor_parts.modifiers import ModifiersMixin
from .post_editor_parts.pages import PagesMixin
from .post_editor_parts.files import FilesMixin
from .post_editor_parts.helpers import (  # noqa: F401  (names other modules import from here)
    NOTHING_WRITTEN,
    SEPARATOR_TEXT,
)


class TokenListDialog(QDialog):
    """Every token the program knows: what it is, where it works, its options. A double click puts it into the template."""

    def __init__(self, parent: QWidget, rows: list[tuple[str, str, str, str, str]]) -> None:
        super().__init__(parent)
        self.setWindowTitle("All tokens")
        self.resize(POST_TOKEN_LIST_WIDTH_PX, POST_TOKEN_LIST_HEIGHT_PX)
        self.chosen = ""
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search")
        self._search.textChanged.connect(self._filter)
        self._table = QTableWidget(len(rows), 5)
        self._table.setHorizontalHeaderLabels(["Token", "Works in", "Options", "What it is", "Example"])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(value))
        self._table.resizeColumnsToContents()
        self._table.cellDoubleClicked.connect(self._pick)
        note = QLabel("Double click a token to put it into the template.")
        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._table)
        layout.addWidget(note)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._table.rowCount()):
            haystack = " ".join(self._table.item(row, column).text() for column in range(self._table.columnCount())).lower()
            self._table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _pick(self, row: int, _column: int) -> None:
        self.chosen = self._table.item(row, 0).text()
        self.accept()


class PostEditorDialog(
    PagesMixin, FilesMixin, CodeTableMixin, ModalGroupsMixin, FunctionsMixin, ModifiersMixin, QDialog,
):
    def __init__(self, parent: QWidget, model: AppModel, start_id: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Postprocessors")
        self.resize(POST_DIALOG_WIDTH_PX, POST_DIALOG_HEIGHT_PX)
        self.model = model
        self.editor: PostEditorModel | None = None
        self._page = ""  # "post", "settings", "codes", "modal_groups" or the name of a concept
        self._loading = False
        self._setting_widgets: dict[str, QWidget] = {}
        self._build()
        self._fill_posts(select=start_id or model.postprocessor_id)

    def _fill_posts(self, select: str | None = None, extra_new: bool = False) -> None:
        self._posts.blockSignals(True)
        self._posts.clear()
        shipped = self.model.post_library.shipped
        names = {post_id: name for post_id, name, _state in self.model.post_editor_choices()}
        separated = False
        for post_id, name, state in self.model.post_editor_choices():
            if state and not separated:  # the posts that cannot be used stand apart
                self._posts.insertSeparator(self._posts.count())
                separated = True
            label = name if list(names.values()).count(name) == 1 else f"{name} [{post_id}]"
            mark = {"problems": POST_PROBLEMS_MARK, "unreadable": POST_UNREADABLE_MARK}.get(state, POST_SHIPPED_MARK if post_id in shipped else "")
            self._posts.addItem(label + mark, post_id)
        if extra_new:
            self._posts.addItem(POST_NEW_MARK, POST_NEW_ID)
        index = self._posts.findData(select) if select is not None else -1
        self._posts.setCurrentIndex(index if index >= 0 else 0)
        self._posts.blockSignals(False)
        target = self._posts.currentData()
        if self.editor is None or self.editor.post_id != target:
            self._load(target)
        else:
            self._refresh_all()

    def _post_chosen(self, _index: int) -> None:
        if self._loading:
            return
        target = self._posts.currentData()
        if self.editor is not None and target != self.editor.post_id and not self._leave_ok():
            self._fill_posts(select=self.editor.post_id, extra_new=self.editor.post_id == POST_NEW_ID)
            return
        self._load(target)

    def _load(self, post_id: str) -> None:
        self._loading = True
        try:
            self.editor = self.model.new_post_editor() if post_id == POST_NEW_ID else self.model.post_editor(post_id)
        except ModelError as error:
            self._say(str(error))
            self._loading = False
            return
        self._loading = False
        self._fill_pages()
        self._refresh_all()
        if self.editor.unreadable:
            self._say(self.editor.unreadable)

    def _fill_pages(self) -> None:
        keep = self._page
        self._pages.blockSignals(True)
        self._pages.clear()
        for item in self._page_items():
            self._pages.addItem(item)
        keys = self._page_keys()
        row = keys.index(keep) if keep in keys else 0
        self._pages.setCurrentRow(row)
        self._pages.blockSignals(False)
        self._page_chosen(row)

    def _key_of(self, row: int) -> str | None:
        keys = self._page_keys()
        return keys[row] if 0 <= row < len(keys) else None

    def _page_chosen(self, row: int) -> None:
        key = self._key_of(row)
        if key is None or self.editor is None:
            return
        self._page = key
        pages = [name for name, _title in POST_PAGES]
        self._stack.setCurrentIndex(pages.index(key) if key in pages else len(pages))
        self._fill_page()

    def _fill_page(self) -> None:
        editor = self.editor
        if editor is None:
            return
        self._loading = True
        try:
            if self._page == "post":
                self._id_label.setText(editor.post_id + POST_FILE_SUFFIX if editor.post_id else "(not saved yet)")
                self._name.setText(editor.name)
                self._description.setText(editor.meta("description"))
                problem = editor.problem()
                if editor.unreadable:
                    self._file_note.setText(f"This file cannot be read as text: {editor.unreadable}")
                else:
                    self._file_note.setText("The whole file reads without a problem." if problem is None else f"Problem in the file: {problem}")
            elif self._page == "settings":
                values = editor.settings()
                for key, widget in self._setting_widgets.items():
                    value = getattr(values, key)
                    if isinstance(widget, QComboBox):
                        widget.setCurrentText(str(value))
                    elif isinstance(widget, QCheckBox):
                        widget.setChecked(bool(value))
                    elif isinstance(widget, QSpinBox):
                        widget.setValue(int(value))
                    else:
                        widget.setText(str(value))
            elif self._page == "codes":
                self._fill_codes()
            elif self._page == "modal_groups":
                self._fill_modal_groups()
            else:
                self._fill_concept()
        finally:
            self._loading = False
        self._apply_read_only()
        if self._page not in {name for name, _title in POST_PAGES}:
            self._show_preview()

    def _fill_concept(self) -> None:
        editor, concept = self.editor, self._page
        own = editor.has_section(concept)
        function = editor.is_function(concept)
        self._concept_title.setText(f"[{concept}]  {editor.function_description(concept) if function else CONCEPTS[concept].description}")
        self._own.setVisible(not function)  # a custom concept is always the post's own
        self._fill_function_box()
        self._own.setChecked(own)
        self._own.setText(POST_OWN_NOTE if own else POST_DEFAULT_NOTE)
        self._template.setPlainText(editor.section(concept) if own else editor.default_section(concept))
        self._fill_tokens()

    def _fill_tokens(self) -> None:
        self._tokens.clear()
        groups: dict[str, list[TokenButton]] = {}
        for button in self.editor.token_buttons(self._page):
            groups.setdefault(button.group, []).append(button)
        order = [name for name, _test in POST_EDITOR_TOKEN_GROUPS]
        for group, buttons in sorted(groups.items(), key=lambda item: order.index(item[0]) if item[0] in order else len(order)):
            tab = QWidget()
            grid = QGridLayout(tab)
            for number, button in enumerate(buttons):
                widget = QPushButton(button.label)
                widget.setToolTip(button.help)
                widget.clicked.connect(lambda _checked=False, text=button.text: self._insert(text))
                grid.addWidget(widget, number // POST_TOKEN_COLUMNS, number % POST_TOKEN_COLUMNS)
            grid.setRowStretch(grid.rowCount(), 1)
            self._tokens.addTab(tab, group)

    def _apply_read_only(self) -> None:
        editor = self.editor
        read_only = editor is None or editor.shipped
        own = self.editor is not None and self.editor.has_section(self._page)
        for widget in (self._name, self._description):
            widget.setEnabled(not read_only)
        for widget in self._setting_widgets.values():
            widget.setEnabled(not read_only)
        self._codes_read_only(read_only)  # the tables stay enabled: a disabled table cannot be scrolled
        self._own.setEnabled(not read_only)
        self._template.setReadOnly(read_only or not own)
        self._tokens.setEnabled(not read_only and own)
        self._set_modifiers_enabled(not read_only and own)
        self._update_function_buttons()
        self._groups_read_only(read_only)
        self._update_buttons()

    def _edit(self, change) -> None:
        if self._loading or self.editor is None or self.editor.shipped:
            return
        change()
        self._update_buttons()
        if self._page == "post":
            self._file_note.setText("")

    def _setting_changed(self, key: str, text: str) -> None:
        self._edit(lambda: self.editor.set_setting(key, text))

    def _own_toggled(self, on: bool) -> None:
        if self._loading or self.editor is None or self.editor.shipped:
            return
        if on:
            self.editor.own_from_default(self._page)
        else:
            self.editor.use_default(self._page)
        self._fill_page()
        self._refresh_page_titles()
        self._update_buttons()

    def _preview_timer_start(self) -> None:
        if not self._loading:
            self._preview_timer.start()

    def _template_edited(self) -> None:
        editor = self.editor
        if editor is None or editor.shipped or not editor.has_section(self._page):
            return
        editor.set_section(self._page, self._template.toPlainText())
        self._update_buttons()
        self._show_preview()

    def _insert(self, text: str) -> None:
        self._template.insertPlainText(text)
        self._template.setFocus()

    def _all_tokens(self) -> None:
        editor = self.editor
        if editor is None:
            return
        rows = []
        for token in editor.tokens_for(self._page):
            options = sorted(token.options | ({"changed"} if token.changeable else set()))
            where = "every concept" if token.concepts is None else ", ".join(sorted(token.concepts))
            rows.append((f"<{token.name}>", where, ", ".join(options), token.description, token.example))
        dialog = TokenListDialog(self, rows)
        if dialog.exec() and dialog.chosen and self._template.isEnabled() and not self._template.isReadOnly():
            self._insert(dialog.chosen)

    def _show_preview(self) -> None:
        editor = self.editor
        if editor is None or self._page in {name for name, _title in POST_PAGES}:
            return
        x_mode = XInputMode.DIAMETER if self._x_mode.currentIndex() == 0 else XInputMode.RADIUS
        preview: Preview = editor.preview(self._page, x_mode)
        if preview.error:
            where = ""
            if preview.line is not None:
                where = f" (line {preview.line}" + (f", column {preview.column}" if preview.column else "") + ")"
            self._problem.setText(preview.error + where)
            self._hint.setText("")
            self._present.setPlainText(preview.error)
            self._absent.setPlainText("")
            self._mark_line(preview.line)
            return
        self._problem.setText(preview.note)
        self._hint.setText("; ".join(editor.literal_hints(self._page)))
        self._mark_line(None)
        self._present.setPlainText("\n".join(preview.present) if preview.present else NOTHING_WRITTEN)
        self._absent.setPlainText("\n".join(preview.absent) if preview.absent else NOTHING_WRITTEN)

    def _mark_line(self, line: int | None) -> None:
        selections = []
        if line is not None:
            block = self._template.document().findBlockByNumber(line - 1)
            if block.isValid():
                selection = QTextEdit.ExtraSelection()
                line_format = QTextCharFormat()
                line_format.setBackground(QColor(POST_ERROR_LINE_COLOR))
                line_format.setForeground(QColor(POST_ERROR_LINE_TEXT_COLOR))
                line_format.setProperty(QTextFormat.FullWidthSelection, True)
                selection.format = line_format
                selection.cursor = QTextCursor(block)
                selections.append(selection)
        self._template.setExtraSelections(selections)

    def _refresh_all(self) -> None:
        self._refresh_page_titles()
        self._fill_page()
        self._update_buttons()

    def _mark_problem_pages(self) -> None:
        """The pages of the post that have a problem are shown in red (the tooltip says what), the others as usual."""
        editor = self.editor
        if editor is None:
            return
        problems = {} if editor.shipped else editor.page_problems()
        keys = self._page_keys()
        for row, key in enumerate(keys):
            item = self._pages.item(row)
            if item is None or key is None:
                continue
            item.setData(Qt.ForegroundRole, QBrush(QColor(POST_ERROR_COLOR)) if key in problems else None)
            item.setToolTip(problems.get(key, ""))
        for key, label in self._page_problem_labels.items():
            label.setText(problems.get(key, ""))

    def _refresh_page_titles(self) -> None:
        if self.editor is None:
            return
        offset = len(POST_PAGES) + 1
        for number, concept in enumerate(self.editor.concepts()):
            item = self._pages.item(offset + number)
            own = self.editor.has_section(concept)
            item.setText(concept + ("" if own else "  (default)"))
            font = item.font()
            font.setItalic(not own)
            item.setFont(font)

    def _update_buttons(self) -> None:
        editor = self.editor
        if editor is None:
            return
        self._mark_problem_pages()
        shipped, new = editor.shipped, editor.post_id == POST_NEW_ID
        has_folder = self.model.user_folder is not None
        self._buttons["save"].setEnabled(not shipped and has_folder and (editor.dirty or new))
        self._buttons["copy"].setEnabled(has_folder and not editor.unreadable)
        self._buttons["import"].setEnabled(has_folder)
        self._buttons["delete"].setEnabled((not shipped or bool(editor.unreadable)) and not new and has_folder)
        self._buttons["folder"].setEnabled(has_folder)
        self.setWindowTitle(f"Postprocessors - {editor.name}" + (" *" if editor.dirty else ""))

    def _say(self, text: str) -> None:
        self._message.setText(text)
