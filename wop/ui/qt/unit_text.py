"""A message box shows its lengths in the unit of the window (the other texts are converted where they are set)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QMessageBox

from ..display_units import is_inch, shown_text


class UnitTextFilter(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        if event.type() == QEvent.Show and isinstance(watched, QMessageBox):
            watched.setText(shown_text(watched.text()))
            watched.setInformativeText(shown_text(watched.informativeText()))
        return False


def install(application: QApplication) -> UnitTextFilter | None:
    if not is_inch():
        return None
    filter_ = UnitTextFilter(application)
    application.installEventFilter(filter_)
    return filter_
