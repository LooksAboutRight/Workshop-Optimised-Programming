"""A click anywhere in the program ends the editing of a number or text field (the value is taken over).

Qt takes a typed value over when the field loses the focus. A click on a part that does not take the focus (the views in
the middle, a label, an empty area) leaves the focus in the field, so the value stayed unsent until Enter or a click into
another field."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit, QWidget
from shiboken6 import isValid


class ClickCommit(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        if event.type() == QEvent.MouseButtonPress and isinstance(watched, QWidget):
            editor = QApplication.focusWidget()
            if isinstance(editor, (QLineEdit, QAbstractSpinBox)) and not self._inside_field(editor, watched):
                QTimer.singleShot(0, lambda: self._leave_if_still_there(editor))  # after the click had its chance to take the focus
        return False

    @staticmethod
    def _inside_field(editor: QWidget, clicked: QWidget) -> bool:
        field = editor.parentWidget() if isinstance(editor.parentWidget(), QAbstractSpinBox) else editor  # a spin box edits in its own line
        return clicked is field or field.isAncestorOf(clicked)

    @staticmethod
    def _leave_if_still_there(editor: QWidget) -> None:
        if isValid(editor) and QApplication.focusWidget() is editor:
            editor.clearFocus()


def install(application: QApplication) -> ClickCommit:
    filter_ = ClickCommit(application)
    application.installEventFilter(filter_)
    return filter_
