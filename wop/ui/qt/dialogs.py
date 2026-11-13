"""Dialogs: a small generic form dialog, the issues dialog and the export-selected dialog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...core.program_model.units import XInputMode
from ..block_forms import FieldSpec, form_for, set_value
from ..display_units import shown_text
from .form_panel import FormPanel
from .qt_constants import (
    DIALOG_HEIGHT_PX,
    DIALOG_NOTES_HEIGHT_PX,
    DIALOG_WIDTH_PX,
    EXPORT_CHECK_ANYWAY,
    EXPORT_CHECK_BUSY,
    EXPORT_CHECK_FOUND,
    EXPORT_CHECK_MIN_HEIGHT_PX,
    EXPORT_CHECK_NOT_RUN,
    EXPORT_CHECK_NOT_RUN_LEFT_OUT,
    EXPORT_CHECK_RUN_NOW,
    EXPORT_CHECK_TITLE,
    EXPORT_CHECK_WITHOUT,
)


class FormDialog(QDialog):
    """Edit one dataclass in a form. `value` is the edited copy after OK."""

    def __init__(self, parent: QWidget, title: str, value: Any, x_mode: XInputMode) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.value = value
        self._x_mode = x_mode
        self._form = FormPanel()
        self._form.edited.connect(self._edited)
        self._form.rejected.connect(self._show_error)
        self._message = QLabel("")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self._form)
        layout.addWidget(self._message)
        layout.addWidget(buttons)
        self._form.set_form(value, form_for(value), x_mode)

    def _edited(self, spec: FieldSpec, new_value: Any) -> None:
        try:
            self.value = set_value(self.value, spec.path, new_value)
            self._message.setText("")
        except ValueError as error:
            self._show_error(str(error))
            self._form.set_form(self.value, form_for(self.value), self._x_mode)

    def _show_error(self, text: str) -> None:
        self._message.setText(text)


class IssuesDialog(QDialog):
    """What the controller cannot do, with a check box to accept each remedy."""

    def __init__(self, parent: QWidget, issues) -> None:
        super().__init__(parent)
        self.setWindowTitle("The controller cannot do everything")
        self._boxes: list[tuple[QCheckBox, object]] = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tick the remedies you accept. Blocks without an accepted remedy are left out."))
        for issue in issues:
            if issue.key is None:
                layout.addWidget(QLabel(f"{issue.message}: no safe remedy, the block is left out"))
                continue
            box = QCheckBox(f"{issue.message}: {issue.remedy_text}")
            box.setChecked(True)
            layout.addWidget(box)
            self._boxes.append((box, issue.key))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accepted_keys(self) -> set:
        return {key for box, key in self._boxes if box.isChecked()}


class ExportCheckDialog(QDialog):
    """Before the G-code leaves: what the checks found, or that they have not been run.

    Checks off: "no checks have been run" with Run checks now (the window fills with the findings, or the export goes
    on at once when there are none), Export without checks and Cancel. Findings: Export anyway and Cancel. Blocks that
    are left out are listed in every case. Accepted = export, rejected = cancel.
    """

    def __init__(self, parent: QWidget, report, run_checks: Callable[[], Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle(EXPORT_CHECK_TITLE)
        self.resize(DIALOG_WIDTH_PX // 2, EXPORT_CHECK_MIN_HEIGHT_PX)
        self._run_checks = run_checks
        self._heading = QLabel()
        self._heading.setWordWrap(True)
        self._list = QPlainTextEdit()
        self._list.setReadOnly(True)
        self._run = QPushButton(EXPORT_CHECK_RUN_NOW)
        self._run.clicked.connect(lambda _checked=False: self._run_now())
        self._export = QPushButton()
        self._export.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (self._run, self._export, cancel):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self._heading)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)
        self._show(report)

    def _show(self, report) -> None:
        problems = list(report.problems)
        if report.checked:
            self._heading.setText(EXPORT_CHECK_FOUND.format(count=len(problems)))
            self._export.setText(EXPORT_CHECK_ANYWAY)
        else:
            self._heading.setText(EXPORT_CHECK_NOT_RUN + (EXPORT_CHECK_NOT_RUN_LEFT_OUT if problems else ""))
            self._export.setText(EXPORT_CHECK_WITHOUT)
        self._run.setVisible(not report.checked)
        self._run.setDefault(not report.checked)
        self._list.setVisible(bool(problems))
        self._list.setPlainText(shown_text("\n".join(f"- {line}" for line in problems)))

    def _run_now(self) -> None:
        self._heading.setText(EXPORT_CHECK_BUSY)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # show the text before the check holds the window
        try:
            report = self._run_checks()
        finally:
            QApplication.restoreOverrideCursor()
        if report.checked and not report.problems:
            self.accept()  # nothing found: on to the export
            return
        self._show(report)


class ExportSelectedDialog(QDialog):
    """The ticked blocks on their own (requirements B9, B15): picture, findings and G-code.

    A switch says whether the unticked blocks count as done (their material is gone) or not done;
    `build(done)` makes the three texts for the chosen state and the window saves the G-code.
    """

    def __init__(
        self,
        parent: QWidget,
        title: str,
        build: Callable[[bool], tuple[str, str, str] | None],
        save: Callable[[bool], None],
        done: bool = True,
        run_checks: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(DIALOG_WIDTH_PX, DIALOG_HEIGHT_PX)
        self._build = build
        self._picture = QSvgWidget()
        self._picture.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        self._notes = QPlainTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setMaximumHeight(DIALOG_NOTES_HEIGHT_PX)
        self._code = QPlainTextEdit()
        self._code.setReadOnly(True)
        self._done = QRadioButton("done (their material is gone)")
        self._not_done = QRadioButton("not done (their material is still there)")
        self._done.setChecked(done)
        self._not_done.setChecked(not done)
        self._done.toggled.connect(lambda _on: self._show())
        switch = QHBoxLayout()
        switch.addWidget(QLabel("Blocks that are not ticked count as:"))
        switch.addWidget(self._done)
        switch.addWidget(self._not_done)
        switch.addStretch(1)
        self._run_button = QPushButton(EXPORT_CHECK_RUN_NOW)
        self._run_button.setToolTip("Collisions and power are not checked automatically: check these blocks now")
        self._run_button.setVisible(run_checks is not None)
        self._run_button.clicked.connect(lambda _checked=False: self._run(run_checks))
        save_button = QPushButton("Save G-code...")
        save_button.clicked.connect(lambda _checked=False: save(self._done.isChecked()))
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(self._run_button)
        row.addWidget(save_button)
        row.addWidget(close_button)
        left = QVBoxLayout()
        left.addWidget(self._picture, 1)
        left.addWidget(self._notes)
        columns = QHBoxLayout()
        columns.addLayout(left, 1)
        columns.addWidget(self._code, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(switch)
        layout.addLayout(columns)
        layout.addLayout(row)
        self._show()

    def _run(self, run_checks: Callable[[], None] | None) -> None:
        if run_checks is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            run_checks()
            self._show()  # the preview is made again, now with the checks
        finally:
            QApplication.restoreOverrideCursor()
        self._run_button.setVisible(False)

    def _show(self) -> None:
        shown = self._build(self._done.isChecked())
        if shown is None:
            return
        svg, notes, gcode = shown
        self._picture.load(QByteArray(svg.encode("utf-8")))
        self._notes.setPlainText(shown_text(notes))
        self._code.setPlainText(gcode)


