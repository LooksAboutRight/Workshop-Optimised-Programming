"""The machine list: edit, import, export, make default, use in the project (requirements M8, M9, U6)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...adapters.machine_files import MACHINE_FILE_SUFFIX
from ...core.lathe.machine import MachineError
from ..app_model import AppModel, ModelError
from ..block_forms import FieldSpec, form_for, get_value, set_value
from ..machine_form import MachineForm, form_from_machine, machine_from_form
from .form_panel import FormPanel
from .small_screens import scrolling
from .qt_constants import (
    APP_NAME,
    DEFAULT_MACHINE_MARK,
    IN_PROJECT_MARK,
    MACHINE_DIALOG_HEIGHT_PX,
    MACHINE_DIALOG_WIDTH_PX,
    MACHINE_LIST_WIDTH_PX,
)
from .theme_qt import untouched_text_color

EXPORT_FILTER = f"WOP machine (*{MACHINE_FILE_SUFFIX})"


class MachinesDialog(QDialog):
    """The machines of the user on the left, the form of the chosen one on the right.

    Edits are saved when a field is left. A value that cannot be a machine yet (only one limit of an
    axis, say) is shown with a message and kept in the form, and saved as soon as it makes sense.
    """

    def __init__(self, parent: QWidget, model: AppModel) -> None:
        super().__init__(parent)
        self.setWindowTitle("Machines")
        self.resize(MACHINE_DIALOG_WIDTH_PX, MACHINE_DIALOG_HEIGHT_PX)
        self.model = model
        self._name: str | None = None  # the machine in the form
        self._value = MachineForm()  # what the form shows (may not be a valid machine yet)

        self._list = QListWidget()
        self._list.setMaximumWidth(MACHINE_LIST_WIDTH_PX)
        self._list.currentRowChanged.connect(self._selected)
        self._form = FormPanel()
        self._form.edited.connect(self._edited)
        self._form.rejected.connect(self._say)
        self._form.reset_requested.connect(self._reset)
        self._message = QLabel("")
        self._message.setWordWrap(True)

        buttons = QVBoxLayout()
        for text, handler in (
            ("New", self._new),
            ("Import...", self._import),
            ("Export...", self._export),
            ("Delete", self._delete),
            ("Make default", self._make_default),
            ("Use in project", self._use),
            ("Add project's machine", self._add_project_machine),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, h=handler: h())
            buttons.addWidget(button)
        buttons.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(self._list)
        left.addLayout(buttons)
        right = QVBoxLayout()
        right.addWidget(scrolling(self._form), 1)  # the form scrolls, so the window can be lower than the form
        right.addWidget(self._message)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        right.addWidget(close)
        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right, 1)
        self._fill_list(select=self._first_machine())  # opens at the machine of the project, else at the default machine

    # --- the list -----------------------------------------------------------------------

    def _first_machine(self) -> str | None:
        """The machine the project uses when it is in the list (the Setup button belongs to it), else the default one."""
        used = self.model.machine
        if used is not None and self.model.find_machine(used.name) is not None:
            return used.name
        return self.model.default_machine

    def _label(self, name: str) -> str:
        in_project = self.model.machine is not None and self.model.machine.name == name
        return name + (DEFAULT_MACHINE_MARK if name == self.model.default_machine else "") + (
            IN_PROJECT_MARK if in_project else ""
        )

    def _fill_list(self, select: str | None = None) -> None:
        wanted = select if select is not None else self._name
        names = [machine.name for machine in self.model.machines]
        self._list.blockSignals(True)
        self._list.clear()
        for name in names:
            self._list.addItem(self._label(name))
        self._list.blockSignals(False)
        if wanted in names:
            self._list.setCurrentRow(names.index(wanted))
        elif names:
            self._list.setCurrentRow(0)
        self._selected(self._list.currentRow())

    def _selected(self, row: int) -> None:
        machines = self.model.machines
        if not 0 <= row < len(machines):
            self._name = None
            self._form.clear()
            return
        self._name = machines[row].name
        self._value = form_from_machine(machines[row])
        self._message.setText("")
        self._show_form()

    def _show_form(self) -> None:
        name = self._name
        self._form.set_form(
            self._value,
            form_for(self._value, self.model.form_context()),
            self.model.project.settings.x_mode,
            lambda path, n=name: self.model.is_machine_field_touched(n, path[0]),
            untouched_text_color(self.palette()),
        )

    def _say(self, text: str) -> None:
        self._message.setText(text)

    # --- editing --------------------------------------------------------------------------

    def _edited(self, spec: FieldSpec, value) -> None:
        self._change(spec, value, touched=True)

    def _reset(self, spec: FieldSpec) -> None:
        self._change(spec, get_value(MachineForm(name=self._value.name), spec.path), touched=False)
        self._show_form()

    def _change(self, spec: FieldSpec, value, touched: bool) -> None:
        if self._name is None:
            return
        self._value = set_value(self._value, spec.path, value)
        try:
            machine = machine_from_form(self._value, self.model.find_machine(self._name))
            self.model.save_machine(machine, old_name=self._name)
            self._name = machine.name
            self._message.setText("")
        except (MachineError, ModelError) as error:
            self._message.setText(str(error))  # the value stays in the form and is saved once it makes sense
        self.model.set_machine_field_touched(self._name, spec.path[0], touched)
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        """Update the names in the list (a rename, the marks) without rebuilding the form being edited."""
        for row, machine in enumerate(self.model.machines):
            self._list.item(row).setText(self._label(machine.name))

    # --- buttons ----------------------------------------------------------------------------

    def _new(self) -> None:
        self._fill_list(self.model.new_machine())

    def _import(self) -> None:
        choices = self.model.importer_choices()
        label, accepted = QInputDialog.getItem(
            self, APP_NAME, "What kind of file is it?", [c[1] for c in choices], 0, False
        )
        if not accepted:
            return
        importer_id, _label, file_filter = next(c for c in choices if c[1] == label)
        name, _filter = QFileDialog.getOpenFileName(self, "Import machine", "", f"{file_filter};;All files (*)")
        if not name:
            return
        try:
            machine_name, notes = self.model.import_machine(importer_id, Path(name))
        except ModelError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return
        self._fill_list(machine_name)
        if notes:
            QMessageBox.information(self, APP_NAME, "\n".join(notes))

    def _export(self) -> None:
        if self._name is None:
            return
        name, _filter = QFileDialog.getSaveFileName(
            self, "Export machine", self._name + MACHINE_FILE_SUFFIX, EXPORT_FILTER
        )
        if name:
            try:
                self.model.export_machine(self._name, Path(name))
            except ModelError as error:
                QMessageBox.warning(self, APP_NAME, str(error))

    def _delete(self) -> None:
        if self._name is None:
            return
        question = f"Delete the machine {self._name!r} from the list? Projects keep their own copy."
        if QMessageBox.question(self, APP_NAME, question) == QMessageBox.Yes:
            self.model.delete_machine(self._name)
            self._name = None
            self._fill_list()

    def _make_default(self) -> None:
        if self._name is not None:
            self.model.set_default_machine(None if self.model.default_machine == self._name else self._name)
            self._fill_list()

    def _use(self) -> None:
        if self._name is not None:
            self.model.use_machine(self._name)
            self._fill_list()

    def _add_project_machine(self) -> None:
        try:
            self._fill_list(self.model.add_project_machine_to_list())
        except ModelError as error:
            QMessageBox.warning(self, APP_NAME, str(error))
