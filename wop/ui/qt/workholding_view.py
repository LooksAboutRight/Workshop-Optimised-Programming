"""The Workholding view in the centre (work package WH2): the saved chuck jaws and chuck bodies, a picture, Add and Delete.

Add makes an item of the chosen type with a placeholder shape; "Sketch editor..." reshapes it. The
form of the chosen item (name, number and width of the jaws) is in the right panel. Which items the program uses is
chosen in the Setup; "none" there means the flat clamping plane is checked.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..app_model import AppModel, ModelError
from ..contour_picture import contour_svg
from .qt_constants import WORKHOLDING_SHAPE_HINT, WORKHOLDING_VIEW_INFO
from ...core.sketch.model import SketchError
from .sketch_dialog import SketchDialog


class WorkholdingView(QWidget):
    notice = Signal(str)  # a short message for the window's messages box

    def __init__(self, model: AppModel) -> None:
        super().__init__()
        self.model = model
        self._building = False
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self._chosen)
        self.picture = QSvgWidget()
        self.info = QLabel(WORKHOLDING_VIEW_INFO)
        self.info.setWordWrap(True)
        add = QToolButton()
        add.setText("Add workholding")
        add.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add)
        for type_name, label in model.workholding_type_choices():
            menu.addAction(label).triggered.connect(lambda _checked=False, t=type_name: self._add(t))
        add.setMenu(menu)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        sketch = QPushButton("Sketch editor...")
        sketch.setToolTip("Draw the outline in the sketch editor (relations, dimensions, import of a DXF drawing). " + WORKHOLDING_SHAPE_HINT)
        sketch.clicked.connect(self._edit_sketch)
        buttons = QHBoxLayout()
        for widget in (add, delete, sketch):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.items, 1)
        layout.addWidget(self.picture, 2)
        layout.addWidget(self.info)

    def refresh(self) -> None:
        self._building = True
        self.items.clear()
        chosen = -1
        for row, item in enumerate(self.model.workholding_library):
            extra = f", {item.jaw_count} jaws" if item.kind == "jaws" else ""
            self.items.addItem(f"{item.name}  ({item.kind}{extra})")
            if item.name == self.model.selected_workholding:
                chosen = row
        self.items.setCurrentRow(chosen)
        self._building = False
        item = self.model.selected_workholding_item()
        if item is None:
            svg = "<svg xmlns='http://www.w3.org/2000/svg'/>"
        else:
            svg = contour_svg(item.outline, self.model.colors)
        self.picture.load(QByteArray(svg.encode("utf-8")))

    def _chosen(self, row: int) -> None:
        library = self.model.workholding_library
        if self._building or not 0 <= row < len(library):
            return
        self.model.select_workholding(library[row].name)

    def _add(self, type_name: str) -> None:
        try:
            self.model.add_workholding_item(type_name)
        except ModelError as error:
            self.notice.emit(str(error))

    def _edit_sketch(self) -> None:
        if self.model.selected_workholding is None:
            return
        try:
            SketchDialog(self, target=self.model.workholding_sketch_target(self.model.selected_workholding)).exec()
        except (ModelError, SketchError) as error:
            self.notice.emit(str(error))

    def _delete(self) -> None:
        if self.model.selected_workholding is None:
            return
        try:
            self.model.remove_workholding(self.model.selected_workholding)
        except ModelError as error:
            self.notice.emit(str(error))
