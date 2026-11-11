"""The material list: change values, add, delete (requirements M5, U3)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_model import AppModel, ModelError
from ..block_forms import FieldSpec, form_for, set_value
from ..material_form import NewMaterial
from .form_panel import FormPanel
from .qt_constants import APP_NAME, MATERIAL_DIALOG_HEIGHT_PX, MATERIAL_DIALOG_WIDTH_PX


class MaterialsDialog(QDialog):
    """The materials on the left, name and specific cutting force of the chosen one on the right.

    A change is saved when a field is left. A value that cannot be saved (an empty name, a name that
    exists) stays in the form with a message until it is corrected.
    """

    def __init__(self, parent: QWidget, model: AppModel) -> None:
        super().__init__(parent)
        self.setWindowTitle("Materials")
        self.resize(MATERIAL_DIALOG_WIDTH_PX, MATERIAL_DIALOG_HEIGHT_PX)
        self.model = model
        self._name: str | None = None
        self._value = NewMaterial()
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._selected)
        self._form = FormPanel()
        self._form.edited.connect(self._edited)
        self._form.rejected.connect(self._say)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        new = QPushButton("New")
        new.clicked.connect(lambda _checked=False: self._new())
        delete = QPushButton("Delete")
        delete.setToolTip("Delete a material of yours, or bring a changed built-in material back")
        delete.clicked.connect(lambda _checked=False: self._delete())
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        for button in (new, delete):
            buttons.addWidget(button)
        left = QVBoxLayout()
        left.addWidget(self._list)
        left.addLayout(buttons)
        right = QVBoxLayout()
        right.addWidget(self._form)
        right.addWidget(self._message)
        right.addStretch(1)
        right.addWidget(close)
        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right, 1)
        self._fill_list()

    def _label(self, name: str) -> str:
        mark = self.model.material_marks(name)
        return f"{name} ({mark})" if mark else name

    def _fill_list(self, select: str | None = None) -> None:
        wanted = select if select is not None else self._name
        names = [material.name for material in self.model.materials.all()]
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
        materials = self.model.materials.all()
        if not 0 <= row < len(materials):
            self._name = None
            self._form.clear()
            return
        material = materials[row]
        self._name = material.name
        self._value = NewMaterial(material.name, material.specific_cutting_force_n_mm2)
        self._message.setText("")
        self._form.set_form(self._value, form_for(self._value), self.model.project.settings.x_mode)

    def _say(self, text: str) -> None:
        self._message.setText(text)

    def _edited(self, spec: FieldSpec, value) -> None:
        if self._name is None:
            return
        self._value = set_value(self._value, spec.path, value)
        try:
            self._name = self.model.save_material(
                self._name, self._value.name, self._value.specific_cutting_force_n_mm2
            )
            self._message.setText("")
            self._refresh_labels()
        except ModelError as error:
            self._message.setText(str(error))  # the value stays in the form until it can be saved

    def _refresh_labels(self) -> None:
        names = [material.name for material in self.model.materials.all()]
        if self._list.count() != len(names) or self._name not in names:
            self._fill_list(self._name)
            return
        for row, name in enumerate(names):
            self._list.item(row).setText(self._label(name))

    def _new(self) -> None:
        name = self.model.unique_material_name("New material")
        self.model.save_material(None, name, None)
        self._fill_list(name)

    def _delete(self) -> None:
        if self._name is None:
            return
        question = f"Delete {self._name!r}?"
        if self.model.materials.is_user_defined(self._name) and self.model.material_marks(self._name):
            question = f"Bring {self._name!r} back to its built-in values?"
        if self.model.material_in_use(self._name):
            question += " The raw part uses it."
        if QMessageBox.question(self, APP_NAME, question) != QMessageBox.Yes:
            return
        try:
            self.model.delete_material(self._name)
        except ModelError as error:
            QMessageBox.information(self, APP_NAME, str(error))
            return
        self._fill_list()
