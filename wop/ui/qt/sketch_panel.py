"""The list of relations and dimensions of the sketch editor (on the right of the picture)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.sketch.relations import relation_for
from ..display_units import is_inch, shown_unit
from ..sketch_session import SketchSession
from .number_boxes import NumberBox
from .sketch_view_constants import PANEL_MIN_PX, VALUE_DECIMALS, VALUE_DECIMALS_INCH, VALUE_LIMIT


def value_decimals() -> int:
    return VALUE_DECIMALS_INCH if is_inch() else VALUE_DECIMALS


def constraint_text(session: SketchSession, constraint_id: int) -> str:
    constraint = session.sketch.constraints[constraint_id]
    relation = relation_for(constraint.kind)
    if not relation.dimension:
        return relation.label
    return f"{session.kind_label(constraint.kind, constraint.refs)}  {session.display_value(constraint):.{value_decimals()}f} {shown_unit(relation.unit)}"


def ask_value(parent: QWidget, title: str, label: str, shown: float) -> float | None:
    """Ask for one number (a dimension, the size of a fillet); "." and "," both work as the decimal point."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    box = NumberBox()
    box.setRange(-VALUE_LIMIT, VALUE_LIMIT)
    box.setDecimals(value_decimals())
    box.setValue(shown)
    form = QFormLayout()
    form.addRow(label, box)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addLayout(form)
    layout.addWidget(buttons)
    box.setFocus()
    if not dialog.exec():
        return None
    box.interpretText()  # a number typed and not yet committed
    return box.value()


class ConstraintPanel(QWidget):
    def __init__(self, session: SketchSession) -> None:
        super().__init__()
        self.session = session
        self.setMinimumWidth(PANEL_MIN_PX)
        self._selecting = False  # the list itself changed the selection: do not rebuild it in the middle of that
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._current_changed)
        self.list.itemDoubleClicked.connect(lambda item: self.edit_constraint(item.data(256)))
        self.remove_button = QPushButton("Remove")
        self.remove_button.setAutoDefault(False)
        self.remove_button.setFocusPolicy(Qt.NoFocus)
        self.remove_button.clicked.connect(self._remove)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Relations and dimensions"))
        layout.addWidget(self.list, 1)
        layout.addWidget(self.remove_button)
        layout.addWidget(self.status)
        session.subscribe(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        wanted = self.session.selected_constraint
        self.remove_button.setEnabled(wanted is not None)
        self.status.setText(self._status_text())
        if self._selecting:
            return
        self.list.blockSignals(True)
        self.list.clear()
        for constraint_id in self.session.sketch.constraints:
            item = QListWidgetItem(constraint_text(self.session, constraint_id))
            item.setData(256, constraint_id)  # Qt.UserRole
            self.list.addItem(item)
            if constraint_id == wanted:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)

    def _status_text(self) -> str:
        if not self.session.sketch.points:
            return ""
        analysis = self.session.analysis
        text = "Fully defined" if analysis.fully_defined else f"{analysis.free_directions} free movements (blue = can still move)"
        return text + ("\nSome relations repeat each other" if analysis.dependent else "")

    def _current_changed(self, item: QListWidgetItem | None, _previous) -> None:
        self._selecting = True
        try:
            self.session.select_constraint(None if item is None else item.data(256))
        finally:
            self._selecting = False

    def _remove(self) -> None:
        if self.session.selected_constraint is not None:
            self.session.remove_constraint(self.session.selected_constraint)

    def edit_constraint(self, constraint_id: int) -> None:
        constraint = self.session.sketch.constraints[constraint_id]
        relation = relation_for(constraint.kind)
        if not relation.dimension:
            return
        label = self.session.kind_label(constraint.kind, constraint.refs)
        shown = ask_value(self, label, f"{label} ({shown_unit(relation.unit)}):", self.session.display_value(constraint))
        if shown is not None:
            self.session.edit_dimension(constraint_id, shown)
