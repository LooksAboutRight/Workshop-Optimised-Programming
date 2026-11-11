"""Every dialog of WOP opens with the size and place it had when it was closed.

One filter on the application, so no dialog needs code of its own: when a dialog of WOP is shown, its last size and place are put back
(Qt's own text form, kept in the settings by the name of the dialog class); when it is closed, they are written. Dialogs of Qt itself (a
question, a file dialog) are left alone: their size comes from their text. The filter must be installed after `ScreenFitFilter`, which
then runs second and makes a restored window smaller when the screen is smaller than it was (a changed monitor).
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QObject
from PySide6.QtWidgets import QDialog

from ..app_model import AppModel

REMEMBERED_PROPERTY = "wop_dialog_remembered"  # set on a dialog the filter has looked at: it is looked at once per dialog object
KEY_PROPERTY = "wop_dialog_key"  # a dialog may set this to share or split the memory; the default is the name of its class
OWN_MODULE_PREFIX = "wop."


class DialogMemory(QObject):
    """Installed on the application: restores the geometry of a dialog of WOP when it is first shown and keeps it when it is closed."""

    def __init__(self, model: AppModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.model = model

    @staticmethod
    def key_of(dialog: QDialog) -> str:
        return str(dialog.property(KEY_PROPERTY) or type(dialog).__name__)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        if (
            event.type() == QEvent.Show and isinstance(watched, QDialog) and watched.isWindow()
            and type(watched).__module__.startswith(OWN_MODULE_PREFIX) and not watched.property(REMEMBERED_PROPERTY)
        ):
            watched.setProperty(REMEMBERED_PROPERTY, True)
            self._restore(watched)
            watched.finished.connect(lambda _result, dialog=watched: self._keep(dialog))
        return False

    def _restore(self, dialog: QDialog) -> None:
        text = self.model.dialog_geometry(self.key_of(dialog))
        if text:
            dialog.restoreGeometry(QByteArray.fromBase64(text.encode("ascii")))

    def _keep(self, dialog: QDialog) -> None:
        self.model.set_dialog_geometry(self.key_of(dialog), bytes(dialog.saveGeometry().toBase64()).decode("ascii"))
