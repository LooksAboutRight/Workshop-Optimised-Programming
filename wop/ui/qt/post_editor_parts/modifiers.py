"""The row of modifier buttons under the sample output of a concept: they change the selected part of the template."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMenu, QPushButton, QToolButton

from ...template_edit import (
    Edit,
    TemplateEditError,
    apply_changed,
    apply_comment,
    apply_optional,
    apply_protect,
    apply_unwrap,
    available_options,
    remove_option,
    set_option,
    token_at,
    written_options,
)
from ..qt_constants import APP_NAME, POST_MODIFIER_BUTTONS, POST_NO_TOKEN_TEXT


class ModifiersMixin:
    """The modifier buttons. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _build_modifier_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._modifier_widgets: list = []
        actions = {
            "changed": apply_changed, "optional": apply_optional, "protect": apply_protect, "comment": apply_comment,
            "unwrap": apply_unwrap,
        }
        for key, text, tip in POST_MODIFIER_BUTTONS:
            if key == "options":
                widget = QToolButton()
                widget.setText(text)
                widget.setPopupMode(QToolButton.InstantPopup)
                self._options_menu = QMenu(widget)
                self._options_menu.setToolTipsVisible(True)
                self._options_menu.aboutToShow.connect(self._fill_options_menu)
                widget.setMenu(self._options_menu)
            else:
                widget = QPushButton(text)
                widget.clicked.connect(lambda _checked=False, f=actions[key]: self._template_action(f))
            widget.setToolTip(tip)
            widget.setFocusPolicy(Qt.NoFocus)  # a click must not take the selection away from the template
            row.addWidget(widget)
            self._modifier_widgets.append(widget)
        row.addStretch(1)
        return row

    def _set_modifiers_enabled(self, on: bool) -> None:
        for widget in self._modifier_widgets:
            widget.setEnabled(on)

    def _selection(self) -> tuple[int, int]:
        cursor = self._template.textCursor()
        return cursor.selectionStart(), cursor.selectionEnd()

    def _apply_edit(self, edit: Edit) -> None:
        """Put the new text in as one step for Undo and select the changed places."""
        cursor = self._template.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(edit.text)
        cursor.endEditBlock()
        cursor.setPosition(edit.start)
        cursor.setPosition(edit.end, QTextCursor.KeepAnchor)
        self._template.setTextCursor(cursor)

    def _template_action(self, change: Callable[..., Edit]) -> None:
        if self.editor is None or self.editor.shipped or not self.editor.has_section(self._page):
            return
        start, end = self._selection()
        try:
            edit = change(self._template.toPlainText(), start, end)
        except TemplateEditError as error:
            self._say(str(error))
            return
        self._say("")
        self._apply_edit(edit)

    def _fill_options_menu(self) -> None:
        menu = self._options_menu
        menu.clear()
        text = self._template.toPlainText()
        start, end = self._selection()
        found = token_at(text, start, end)
        if found is None:
            menu.addAction(POST_NO_TOKEN_TEXT).setEnabled(False)
            return
        current = written_options(found)
        for name, meaning, takes_value in available_options(found.token):
            shown = name if not takes_value else (f"{name}={current[name]}" if name in current else f"{name}=...")
            action = menu.addAction(shown)
            action.setCheckable(True)
            action.setChecked(name in current)
            action.setToolTip(meaning)
            action.triggered.connect(lambda _checked=False, n=name, v=takes_value, m=meaning: self._option_chosen(text, found, n, v, m))

    def _option_chosen(self, text: str, found, name: str, takes_value: bool, meaning: str) -> None:
        if self.editor is None or self.editor.shipped:
            return
        try:
            if name in written_options(found):
                edit = remove_option(text, found, name)
            elif takes_value:
                value, accepted = QInputDialog.getText(self, APP_NAME, f"{name}: {meaning}")
                if not accepted:
                    return
                edit = set_option(text, found, name, value.strip())
            else:
                edit = set_option(text, found, name, None)
        except TemplateEditError as error:
            self._say(str(error))
            return
        self._say("")
        self._apply_edit(edit)

