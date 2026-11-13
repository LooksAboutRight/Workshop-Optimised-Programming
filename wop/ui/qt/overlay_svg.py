"""An SVG picture with small widgets laid over its corners (requirements V3, V5)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QWidget

from ..ui_constants import WHEEL_NOTCH_UNITS, ZOOM_MIN, ZOOM_PER_WHEEL_NOTCH
from ..view_zoom import ZoomPan
from .qt_constants import OVERLAY_MARGIN_PX, ZOOM_REDRAW_DELAY_MS

TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT = "top-left", "top-right", "bottom-left", "bottom-right"


class OverlaySvgWidget(QSvgWidget):
    """The picture keeps its aspect ratio; overlays stay in the corners of the whole widget and
    never change the size or position of the drawing, unless the user zooms (wheel) or pans (drag with the left
    or middle button); a double click, or `reset_view`, shows the whole picture again.

    The renderer only enlarges the picture, so its lines get thicker; `zoom_settled` tells the owner to draw the picture
    again with lines of 1 / `zoom` of their width (`line_scale`)."""

    zoom_settled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(ZOOM_REDRAW_DELAY_MS)
        self._settle_timer.timeout.connect(self.zoom_settled)
        self.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        self._overlays: list[tuple[QWidget, str]] = []
        self._view = ZoomPan()
        self._drag_from: QPointF | None = None
        self._home: tuple[float, float, float, float] | None = None  # the part of the picture shown first (picture units)

    def set_home(self, home: tuple[float, float, float, float] | None) -> None:
        """The rectangle of the picture the window shows first (and on reset); the rest of the picture is reached by zooming out."""
        self._home = home

    # --- zoom and pan -------------------------------------------------------------------

    def _base_rect(self) -> tuple[float, float, float, float]:
        """Where the picture lies without zoom: fitted into the widget, centred; with a home rectangle, that rectangle is
        the one that is fitted and centred (the rest of the picture lies round it)."""
        size = self.renderer().defaultSize()
        if size.width() <= 0 or size.height() <= 0:
            return (0.0, 0.0, float(self.width()), float(self.height()))
        if self._home is not None and self._home[2] > 0 and self._home[3] > 0:
            x, y, width, height = self._home
            scale = min(self.width() / width, self.height() / height)
            return (self.width() / 2 - (x + width / 2) * scale, self.height() / 2 - (y + height / 2) * scale,
                    size.width() * scale, size.height() * scale)
        scale = min(self.width() / size.width(), self.height() / size.height())
        width, height = size.width() * scale, size.height() * scale
        return ((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _min_zoom(self) -> float:
        """How far the picture can be zoomed out: 1 is the home view; with a home rectangle the whole picture fits at the end."""
        size = self.renderer().defaultSize()
        if self._home is None or self._home[2] <= 0 or self._home[3] <= 0 or size.width() <= 0 or size.height() <= 0:
            return ZOOM_MIN
        home_scale = min(self.width() / self._home[2], self.height() / self._home[3])
        whole_scale = min(self.width() / size.width(), self.height() / size.height())
        return min(whole_scale / home_scale, ZOOM_MIN)

    def _centre_whole(self) -> None:
        """Zoomed out as far as it goes: the whole picture sits in the middle of the widget."""
        base = self._base_rect()
        width, height = base[2] * self._view.zoom, base[3] * self._view.zoom
        self._view.origin = (((self.width() - width) / 2 - base[0]) / base[2], ((self.height() - height) / 2 - base[1]) / base[3])

    def _window_rect(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, float(self.width()), float(self.height()))

    def line_scale(self) -> float:
        """What the line widths of the picture are multiplied by so they keep their width on the screen."""
        return self._min_zoom() / self._view.zoom  # the lines of the whole picture are as thick as without a home rectangle

    def reset_view(self) -> None:
        zoomed = not self._view.is_default
        self._view.reset()
        self.update()
        if zoomed:
            self._settle_timer.start()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(*self._view.view_rect(self._base_rect()))
        painter.setClipRect(rect)  # what lies outside the picture (a rapid move to the tool change position) is cut off
        self.renderer().render(painter, rect)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt name)
        notches = event.angleDelta().y() / WHEEL_NOTCH_UNITS
        if notches:
            cursor = event.position()
            before = self._view.zoom
            self._view.zoom_at(
                (cursor.x(), cursor.y()), self._base_rect(), ZOOM_PER_WHEEL_NOTCH ** notches, self._window_rect(), self._min_zoom(),
            )
            if self._view.zoom <= self._min_zoom() < ZOOM_MIN:
                self._centre_whole()
            self.update()
            if self._view.zoom != before:
                self._settle_timer.start()
            event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._drag_from = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if self._drag_from is not None:
            here = event.position()
            self._view.pan_by(here.x() - self._drag_from.x(), here.y() - self._drag_from.y(), self._base_rect(), self._window_rect(), self._min_zoom())
            self._drag_from = here
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self._drag_from = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self.reset_view()

    def add_overlay(self, widget: QWidget, corner: str) -> None:
        widget.setParent(self)
        self._overlays.append((widget, corner))
        widget.show()
        self.place_overlays()

    def place_overlays(self) -> None:
        for widget, corner in self._overlays:
            widget.adjustSize()
            x = OVERLAY_MARGIN_PX if corner in (TOP_LEFT, BOTTOM_LEFT) else self.width() - widget.width() - OVERLAY_MARGIN_PX
            y = OVERLAY_MARGIN_PX if corner in (TOP_LEFT, TOP_RIGHT) else self.height() - widget.height() - OVERLAY_MARGIN_PX
            widget.move(max(0, x), max(0, y))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self.place_overlays()
