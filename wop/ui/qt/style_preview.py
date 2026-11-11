"""The style dropdown of a block: hovering an entry of the open list shows the path of that style on the sample parts of its block type."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QModelIndex, QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QLabel, QWidget

from ..style_picture import style_pictures
from ..theme import ColorSet
from .qt_constants import STYLE_PICTURE_COLUMNS, STYLE_PICTURE_HINT, STYLE_PICTURE_GAP_PX, STYLE_PICTURE_WIDTH_PX
from .theme_qt import color_set_from_palette

_cache: dict[tuple, list[tuple[str, QPixmap | None, str]]] = {}  # (block type, style key, window colour) -> (caption, picture, problem)


def _pixmap(svg: str) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    size = renderer.defaultSize()
    height = max(1, round(STYLE_PICTURE_WIDTH_PX * size.height() / max(1, size.width())))
    image = QImage(STYLE_PICTURE_WIDTH_PX, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def pictures_of(block_type: str, key: str, colors: ColorSet, window_color: str) -> list[tuple[str, QPixmap | None, str]]:
    """The pictures of a style, made the first time they are asked for (they are not stored anywhere else)."""
    found = _cache.get((block_type, key, window_color))
    if found is None:
        found = [(p.caption, _pixmap(p.svg) if p.svg else None, p.problem) for p in style_pictures(block_type, key, colors)]
        _cache[(block_type, key, window_color)] = found
    return found


class StylePreview(QFrame):
    """A small window without a frame next to the open list: one picture with its caption for every sample."""

    def __init__(self) -> None:
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self._layout = QGridLayout(self)
        self._layout.setSpacing(STYLE_PICTURE_GAP_PX)

    def show_pictures(self, title: str, pictures: list[tuple[str, QPixmap | None, str]], beside: QWidget) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            old = item.widget()
            if old is not None:
                old.setParent(None)  # at once: a widget waiting for deleteLater would still count for the size
                old.deleteLater()
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: bold")
        self._layout.addWidget(heading, 0, 0, 1, STYLE_PICTURE_COLUMNS)
        hint = QLabel(STYLE_PICTURE_HINT)
        self._layout.addWidget(hint, 1, 0, 1, STYLE_PICTURE_COLUMNS)
        for number, (caption, pixmap, problem) in enumerate(pictures):
            picture = QLabel()
            if pixmap is not None:
                picture.setPixmap(pixmap)
            else:
                picture.setText(problem or "cannot be drawn")
                picture.setWordWrap(True)
                picture.setFixedWidth(STYLE_PICTURE_WIDTH_PX)
            text = QLabel(caption)
            text.setAlignment(Qt.AlignHCenter)
            cell = QWidget()
            column = QGridLayout(cell)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(picture, 0, 0, Qt.AlignTop)
            column.addWidget(text, 1, 0, Qt.AlignTop)
            self._layout.addWidget(cell, 2 + number // STYLE_PICTURE_COLUMNS, number % STYLE_PICTURE_COLUMNS, Qt.AlignTop)
        for number in range(self._layout.count()):  # new widgets of a window that is shown stay hidden, and a layout skips them
            self._layout.itemAt(number).widget().show()
        self._layout.activate()
        self.resize(self._layout.totalSizeHint())
        screen = beside.screen().availableGeometry()
        right = beside.mapToGlobal(QPoint(beside.width(), 0))
        x = right.x() + STYLE_PICTURE_GAP_PX
        if x + self.width() > screen.right():  # no room on the right: on the left of the list
            x = beside.mapToGlobal(QPoint(0, 0)).x() - self.width() - STYLE_PICTURE_GAP_PX
        y = min(right.y(), screen.bottom() - self.height())
        self.move(max(x, screen.left()), max(y, screen.top()))
        self.show()


class StyleCombo(QComboBox):
    """A dropdown whose entries are styles (the key is the item data): hovering an entry of the open list shows its pictures."""

    def __init__(self, block_type: str) -> None:
        super().__init__()
        self._block_type = block_type
        self._preview = StylePreview()
        self.view().setMouseTracking(True)
        self.view().entered.connect(self._hovered)

    def _hovered(self, index: QModelIndex) -> None:
        key = self.itemData(index.row())
        if key is None or not self.view().isVisible():
            return
        colors = color_set_from_palette(self.palette())
        window_color = self.palette().window().color().name()
        title = self.itemText(index.row())
        self._preview.show_pictures(title, pictures_of(self._block_type, str(key), colors, window_color), self.view().window())

    def hidePopup(self) -> None:
        self._preview.hide()
        super().hidePopup()
