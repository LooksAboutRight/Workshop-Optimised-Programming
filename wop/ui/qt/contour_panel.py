"""The right panel while a contour is chosen (requirement C9): its name, the Sketch editor button and what is wrong with it.

The outline is drawn in the sketch editor (`SketchDialog`); the centre view shows the contour. Only the name is edited here.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class ContourPanel(QWidget):
    """`model` is the program (`AppModel`)."""

    sketch_requested = Signal()  # the "Sketch editor..." button

    def __init__(self, model) -> None:
        super().__init__()
        self.model = model
        self._name = QLineEdit()
        self._name.editingFinished.connect(self._name_changed)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        sketch_button = QPushButton("Sketch editor...")
        sketch_button.setToolTip("Draw this contour in the sketch editor (relations, dimensions, import of a DXF drawing)")
        sketch_button.clicked.connect(lambda _checked=False: self.sketch_requested.emit())
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self._name)
        layout.addWidget(sketch_button)
        layout.addWidget(self._status)
        layout.addStretch(1)

    def show_contour(self) -> None:
        contour = self.model.chosen_contour()
        if contour is None:
            self._name.clear()
            self._status.clear()
            return
        if self._name.text() != contour.name:
            self._name.setText(contour.name)
        self._status.setText(contour.error or "The contour is fine.")

    def _name_changed(self) -> None:
        name = self._name.text().strip()
        contour = self.model.chosen_contour()
        if contour is not None and name and name != contour.name:
            self.model.rename_contour(contour.contour_id, name)
