"""Project files, the questions before something is lost, export of the G-code and the layout of the window."""

from __future__ import annotations

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
from pathlib import Path

from ....adapters.project_files import PROJECT_FILE_SUFFIX
from ....core.program_model.touched import SETUP_OWNER
from ...app_model import ModelError
from ..dialogs import ExportCheckDialog, ExportSelectedDialog, IssuesDialog
from ..qt_constants import APP_NAME, EXPORT_CHECK_NOT_RUN
from .helpers import GCODE_ENCODING, GCODE_FILTER, PROJECT_FILTER


class FilesMixin:
    """Project files, the questions before something is lost, export of the G-code and the layout of the window. (A part of MainWindow: it uses the attributes that MainWindow.__init__ sets.)"""

    def _restore_geometry(self) -> None:
        """The window comes back where and as big as the user left it."""
        saved = self.model.app_settings.window_geometry
        if saved:
            self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))

    def _remember_layout(self) -> None:
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.model.set_window_layout(geometry, tuple(self.splitter.sizes()))

    def _dialog_start(self, name: str = "", export: bool = False) -> str:
        """Where a file dialog starts: the folder of the last file (of its kind), with a suggested file name."""
        settings = self.model.app_settings
        folder = settings.last_export_folder if export else settings.last_folder
        return str(Path(folder) / name) if folder and Path(folder).is_dir() else name

    def _chosen(self, name: str, export: bool = False) -> str:
        """A file the user chose in a dialog: its folder is remembered. Returns the name."""
        if name:
            self.model.set_last_folder(Path(name), export)
        return name

    def _ask_save_changes(self) -> bool:
        """True if it is fine to go on: the project is saved or given up, and tools that differ from the library are
        written to it or left."""
        return self._ask_save_project() and self._ask_update_tool_library()

    def _ask_update_tool_library(self) -> bool:
        differing = self.model.tools_differing_from_library()
        new = self.model.tools_new_to_library()
        if not differing and not new:
            return True
        tool_name = lambda number: self.model.program.tool(number).name  # noqa: E731
        lines = []
        if differing:
            lines.append("These tools differ from the tool library: " + ", ".join(map(tool_name, differing)) + ".")
        if new:
            lines.append("These tools are not in the tool library yet: " + ", ".join(map(tool_name, new)) + ".")
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Question)
        box.setText("\n".join(lines) + "\nUpdate the library with them?")
        update = box.addButton("Update the library", QMessageBox.AcceptRole)
        box.addButton("Leave the library as it is", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is update:
            for number in (*differing, *new):
                try:
                    self.model.save_tool_to_library(number, replace_existing=True)
                except ModelError as error:
                    QMessageBox.warning(self, APP_NAME, str(error))
        return box.standardButton(box.clickedButton()) != QMessageBox.Cancel

    def _ask_save_project(self) -> bool:
        """True if it is fine to go on (saved, or the user does not want to save)."""
        if not self.model.dirty:
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "Save the changes first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self._save()
        return True

    def _new(self) -> None:
        if self._ask_save_changes():
            self.model.new()

    def _open(self) -> None:
        if not self._ask_save_changes():
            return
        name, _filter = QFileDialog.getOpenFileName(self, "Open project", self._dialog_start(), PROJECT_FILTER)
        if self._chosen(name):
            try:
                self.model.open(Path(name))
            except ModelError as error:
                QMessageBox.warning(self, APP_NAME, str(error))

    def _save(self) -> bool:
        if self.model.path is None:
            return self._save_as()
        return self._try_save(None)

    def _save_as(self) -> bool:
        name, _filter = QFileDialog.getSaveFileName(
            self, "Save project", self._dialog_start(f"project{PROJECT_FILE_SUFFIX}"), PROJECT_FILTER
        )
        return bool(self._chosen(name)) and self._try_save(Path(name))

    def _try_save(self, path: Path | None) -> bool:
        try:
            self.model.save(path)
        except (ModelError, OSError) as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return False
        return True

    def _generate(
        self, selection: tuple[int, ...] | None = None, done: bool = True, accepted: set | None = None, ask: bool = True,
        checks_run: bool = False,
    ):
        """The G-code result, after asking about the remedies. None if the user cancels.

        `accepted` is a set the caller keeps: once the user has answered the remedies question it is
        filled, and a later call with the same set does not ask again.

        `ask` False: no question about the problems the checker found (the preview of the export dialog lists them itself).
        `checks_run`: the user already ran the checks in the preview of the export dialog, so they run again without asking.
        """
        if ask:
            if not self._confirm_export(selection, done, checks_run):  # as drawn: the user decides, so the program asks
                return None
        try:
            result = self.model.gcode(selection=selection, unticked_done=done, accepted=accepted)
            if result.issues and (accepted is None or not accepted):
                dialog = IssuesDialog(self, result.issues)
                if not dialog.exec():
                    return None
                keys = dialog.accepted_keys()
                if accepted is not None:
                    accepted.update(keys)
                result = self.model.gcode(selection=selection, unticked_done=done, accepted=keys)
            return result
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, APP_NAME, f"Cannot make the G-code: {error}")
            return None

    def _confirm_export(self, selection: tuple[int, ...] | None, done: bool, checks_run: bool = False) -> bool:
        """Checks done and nothing found: yes without asking. Otherwise the window says what was found or that no checks
        have been run, and the user decides (the G-code is written as drawn)."""
        report = self.model.export_report(selection, done, run_check=checks_run)
        if report.checked and not report.problems:
            return True
        dialog = ExportCheckDialog(self, report, lambda: self.model.export_report(selection, done, run_check=True))
        return dialog.exec() == QDialog.Accepted

    def _gcode_name(self) -> str:
        """The suggested name of the G-code file: the title of the setup when the user has given one, else the file name of the
        project (without .wop.json or .json), else the title."""
        path, title = self.model.path, self.model.project.settings.title
        if title.strip() and self.model.is_touched(SETUP_OWNER, ("title",)):
            stem = title
        elif path is not None:
            stem = path.name.removesuffix(PROJECT_FILE_SUFFIX).removesuffix(".json")
        else:
            stem = title
        cleaned = "".join(c if c.isalnum() or c in " -_." else "_" for c in stem).strip(" .")
        return cleaned or "program"

    def _save_gcode(self, result) -> None:
        suggestion = f"{self._gcode_name()}{self.model.gcode_suffix()}"
        name, _filter = QFileDialog.getSaveFileName(self, "Export G-code", self._dialog_start(suggestion, export=True), GCODE_FILTER)
        if self._chosen(name, export=True):
            Path(name).write_text(result.text, encoding=GCODE_ENCODING, newline="\n")
            note = "" if result.complete else " (INCOMPLETE: blocks with open issues were left out)"
            self._say(f"Written {name} with the post {self.model.post_title()}{note}")

    def _export(self, only_block: int | None) -> None:
        result = self._generate(None if only_block is None else (only_block,))
        if result is not None:
            self._save_gcode(result)

    def _export_selected(self) -> None:
        """The ticked blocks: look at them and save their G-code (B15)."""
        selection = self.model.ticked_indices()
        if not selection:
            self._say("Tick at least one block first.")
            return
        accepted: set = set()  # the remedies the user accepts are asked once, not at every change of the switch
        ran = {"checks": False}  # the user pressed Run checks now in the preview

        def build(done: bool):
            self.model.unticked_done = done  # the dialog opens with the last choice next time
            result = self._generate(selection, done, accepted, ask=False)  # the preview lists the problems itself
            if result is None:
                return None
            analysis = self.model.selection_analysis(selection, done, run_check=ran["checks"])
            lines = [f"PROBLEM: {analysis.error}"] if analysis.error else []
            lines += [f"note: {m}" for m in analysis.messages]
            lines += [f"COLLISION: {f.message} - {f.remedy}" for f in analysis.findings]
            if not analysis.checked:
                lines.append(EXPORT_CHECK_NOT_RUN)
            return self.model.picture(analysis=analysis), "\n".join(lines) or "No problems found.", result.text

        def run_checks() -> None:
            ran["checks"] = True

        def save(done: bool) -> None:
            result = self._generate(selection, done, accepted, checks_run=ran["checks"])
            if result is not None:
                self._save_gcode(result)

        numbers = ", ".join(str(i + 1) for i in selection)
        ExportSelectedDialog(
            self, f"Export selected blocks: {numbers}", build, save, self.model.unticked_done,
            None if self.model.auto_check else run_checks,  # checks off: the preview offers Run checks now
        ).exec()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if self._ask_save_changes():
            self._remember_layout()
            event.accept()
        else:
            event.ignore()
