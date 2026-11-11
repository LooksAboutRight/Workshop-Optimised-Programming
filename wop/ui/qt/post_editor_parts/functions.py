"""Custom concepts (functions) in the post editor: the list under the concepts, Add and Remove, and the box with the variables."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QInputDialog, QLabel, QLineEdit, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ....post.concepts import CONCEPTS
from ..qt_constants import (
    APP_NAME,
    POST_CUSTOM_CONCEPTS_TEXT,
    POST_PAGES,
    POST_VARIABLES_HEIGHT_PX,
    POST_VARIABLES_HINT,
)
from .helpers import SEPARATOR_TEXT


class FunctionsMixin:
    """The custom concepts. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _page_keys(self) -> list[str | None]:
        """What every row of the page list is: a page, a concept (by name), or None for a line that only divides the list."""
        names = self.editor.function_names() if self.editor is not None else []
        return [key for key, _title in POST_PAGES] + [None, *CONCEPTS, None, *names]

    def _page_items(self) -> list[QListWidgetItem]:
        items = []
        titles = dict(POST_PAGES)
        dividers = iter((SEPARATOR_TEXT, POST_CUSTOM_CONCEPTS_TEXT))
        for key in self._page_keys():
            if key is None:
                item = QListWidgetItem(next(dividers))
                item.setFlags(Qt.NoItemFlags)
            elif key in titles:
                item = QListWidgetItem(titles[key])
            else:
                own = self.editor.has_section(key)
                item = QListWidgetItem(key + ("" if own else "  (default)"))
                if not own:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
            items.append(item)
        return items

    def _build_page_buttons(self) -> QWidget:
        """The list of pages with the buttons for the custom concepts under it."""
        widget = QWidget()
        self._add_function_button = QPushButton("Add a concept...")
        self._add_function_button.setToolTip("A concept of your own: it has its own template, can use all the codes and can have variables")
        self._add_function_button.clicked.connect(self._add_function)
        self._remove_function_button = QPushButton("Remove this concept")
        self._remove_function_button.clicked.connect(self._remove_function)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pages, 1)
        layout.addWidget(self._add_function_button)
        layout.addWidget(self._remove_function_button)
        return widget

    def _build_function_box(self) -> QWidget:
        """The part of a custom concept's page above the template: its description and its variables."""
        box = QWidget()
        self._function_description = QLineEdit()
        self._function_description.setPlaceholderText("What this concept does")
        self._function_description.textEdited.connect(self._description_edited)
        hint = QLabel(POST_VARIABLES_HINT)
        hint.setWordWrap(True)
        self._variables = QPlainTextEdit()
        self._variables.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._variables.setMaximumHeight(POST_VARIABLES_HEIGHT_PX)
        self._variables.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._variables.textChanged.connect(self._variables_edited)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._function_description)
        layout.addWidget(hint)
        layout.addWidget(self._variables)
        return box

    def _fill_function_box(self) -> None:
        editor, name = self.editor, self._page
        function = editor.is_function(name)
        self._function_box.setVisible(function)
        if function:
            self._function_description.setText(editor.function_description(name))
            self._variables.setPlainText(editor.variables_text(name))

    def _update_function_buttons(self) -> None:
        editor = self.editor
        editable = editor is not None and not editor.shipped and not editor.unreadable
        self._add_function_button.setEnabled(editable)
        self._remove_function_button.setEnabled(editable and editor.is_function(self._page))
        self._function_description.setEnabled(editable)
        self._variables.setReadOnly(not editable)

    def _description_edited(self, text: str) -> None:
        self._edit(lambda: self.editor.set_function_description(self._page, text))
        self._concept_title.setText(f"[{self._page}]  {text}")

    def _variables_edited(self) -> None:
        if self._loading or self.editor is None or self.editor.shipped:
            return
        before = [variable.name for variable in self.editor.variables(self._page)]
        self._edit(lambda: self.editor.set_variables_text(self._page, self._variables.toPlainText()))
        if [variable.name for variable in self.editor.variables(self._page)] != before:
            self._fill_tokens()  # the variables are buttons of the token grid
        self._show_preview()

    def _add_function(self) -> None:
        if self.editor is None or self.editor.shipped:
            return
        name, accepted = QInputDialog.getText(self, APP_NAME, "Name of the concept (lower case letters, digits and _):")
        if not accepted or not name.strip():
            return
        description, accepted = QInputDialog.getText(self, APP_NAME, "What does it do?")
        if not accepted:
            return
        try:
            self.editor.add_function(name, description)
        except ValueError as error:
            self._say(str(error))
            return
        self._page = name.strip()
        self._fill_pages()
        self._update_buttons()

    def _remove_function(self) -> None:
        editor = self.editor
        if editor is None or editor.shipped or not editor.is_function(self._page):
            return
        if QMessageBox.question(self, APP_NAME, f"Remove the concept {self._page!r} with its template and variables?") != QMessageBox.Yes:
            return
        editor.remove_function(self._page)
        self._page = "post"
        self._fill_pages()
        self._update_buttons()
