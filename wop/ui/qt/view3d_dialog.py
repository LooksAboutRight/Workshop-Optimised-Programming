"""The 3D view window (requirement Z1): drag to turn, wheel to zoom."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QVBoxLayout, QWidget

from ..app_model import AppModel
from .gl_view import GLSceneView
from .qt_constants import DIALOG_HEIGHT_PX, DIALOG_WIDTH_PX


class View3DDialog(QDialog):
    """Follows the program: it redraws when the model changes or another block is selected."""

    def __init__(self, parent: QWidget, model: AppModel) -> None:
        super().__init__(parent)
        self.setWindowTitle("3D view")
        self.resize(DIALOG_WIDTH_PX, DIALOG_HEIGHT_PX)
        self.model = model
        self._view = GLSceneView(turns=True)
        self._upto = QCheckBox("Only up to the selected block")
        self._upto.setChecked(True)
        self._upto.toggled.connect(lambda _checked: self._draw())
        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        layout.addWidget(QLabel("Drag with the mouse to turn, wheel to zoom. A quarter is cut away."))
        layout.addWidget(self._upto)
        model.subscribe(self._draw)
        model.subscribe_results(self._draw)  # the plan made in the background
        self.finished.connect(lambda _result: model.unsubscribe(self._draw))
        self._draw()

    @property
    def camera(self):
        return self._view.camera

    def _upto_block(self) -> int | None:
        return self.model.selected if self._upto.isChecked() else None

    def _draw(self) -> None:
        try:
            scene = self.model.scene3d(self._upto_block())
        except ValueError:
            scene = self.model.scene3d(None)
        self._view.set_scene(scene)
