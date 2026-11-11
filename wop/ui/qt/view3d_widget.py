"""The 3D view as a widget for the centre of the window (requirement V5).

The view direction is fixed (turning gave odd angles). Drag with the left or middle mouse button (or a finger or
pen) to move the picture, wheel to zoom, double click or "Reset view" to come back to the start. The drawing is done by
`GLSceneView` with OpenGL.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ..app_model import AppModel
from .gl_view import BOTTOM_LEFT, GLSceneView
from .qt_constants import VIEW3D_HINT


class View3DWidget(GLSceneView):
    """Shows the part after the chosen block. The camera is kept while the user switches to 2D and back."""

    def __init__(
        self, model: AppModel, upto_block: Callable[[], int | None], step: Callable[[], int | None] = lambda: None
    ) -> None:
        super().__init__()
        self.model = model
        self._upto_block = upto_block
        self._step = step
        hint = QLabel(VIEW3D_HINT)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.add_overlay(hint, BOTTOM_LEFT)

    def draw(self) -> None:
        upto = self._upto_block()
        step = self._step()
        try:
            scene = self.model.scene3d(upto, None, step)
        except ValueError:
            scene = self.model.scene3d(None, None, step)
        self.set_scene(scene)
