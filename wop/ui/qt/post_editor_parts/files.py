"""The post editor's file actions: new, save, import, delete."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
from pathlib import Path

from ....post.post_constants import POST_FILE_SUFFIX
from ...app_model import ModelError
from ..qt_constants import APP_NAME, POST_NEW_ID
from .helpers import IMPORT_FILTER


class FilesMixin:
    """The post editor's file actions: new, save, import, delete. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _leave_ok(self) -> bool:
        """True when the post in the editor may be left: nothing changed, or the user saved it or let the changes go."""
        editor = self.editor
        if editor is None or not editor.dirty or editor.shipped:
            return True
        answer = QMessageBox.question(
            self, APP_NAME, f"Save the changes of {editor.name!r}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self._save()
        return True

    def _new(self) -> None:
        if not self._leave_ok():
            return
        self._fill_posts(select=POST_NEW_ID, extra_new=True)

    def _save(self) -> bool:
        editor = self.editor
        if editor is None or editor.shipped:
            return False
        if editor.post_id == POST_NEW_ID:
            return self._save_as()
        return self._write(editor.post_id)

    def _save_as(self) -> bool:
        editor = self.editor
        if editor is None:
            return False
        suggestion = editor.name if editor.post_id == POST_NEW_ID else f"{editor.name} copy"
        name, accepted = QInputDialog.getText(self, APP_NAME, "Name of the post:", text=suggestion)
        if not accepted or not name.strip():
            return False
        editor.set_meta("name", name.strip())
        return self._write(self.model.unique_post_id(name.strip()))

    def _write(self, post_id: str) -> bool:
        try:
            saved = self.model.save_post(self.editor, post_id)
        except ModelError as error:
            self._say(str(error))
            return False
        self._say(f"Saved as {saved}{POST_FILE_SUFFIX}")
        self._fill_posts(select=saved)
        return True

    def _import(self) -> None:
        if not self._leave_ok():
            return
        name, _filter = QFileDialog.getOpenFileName(self, "Import a post", "", IMPORT_FILTER)
        if not name:
            return
        try:
            post_id = self.model.import_post(Path(name))
        except ModelError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return
        self._say(f"Imported as {post_id}{POST_FILE_SUFFIX}")
        self._fill_posts(select=post_id)

    def _delete(self) -> None:
        editor = self.editor
        if editor is None or (editor.shipped and not editor.unreadable) or editor.post_id == POST_NEW_ID:
            return
        if QMessageBox.question(self, APP_NAME, f"Delete the post {editor.name!r}? The file is removed.") != QMessageBox.Yes:
            return
        try:
            self.model.delete_post(editor.post_id)
        except ModelError as error:
            self._say(str(error))
            return
        self.editor = None
        self._fill_posts(select=self.model.postprocessor_id)

    def _open_folder(self) -> None:
        folder = self.model.posts_folder_path()
        if folder is None:
            self._say("The settings are not kept in a folder, so there is no posts folder.")
            return
        self._say(f"Posts folder: {folder}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def done(self, result: int) -> None:  # noqa: N802 (Qt name)
        if self._leave_ok():
            super().done(result)
