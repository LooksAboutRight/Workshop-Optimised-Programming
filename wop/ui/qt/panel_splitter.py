"""A splitter whose handles can be seen and clicked, so a collapsed side panel is never lost (usability).

- The handle shows a grip (three dots) and, when the panel next to it is collapsed, an arrow that points to where
  the panel will open.
- A click on the handle (no dragging) collapses an open panel or opens a collapsed one; dragging works as usual.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPalette, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QSplitter, QSplitterHandle

from .qt_constants import (
    HANDLE_ARROW_PX,
    HANDLE_BACKGROUND_ALPHA,
    HANDLE_CLICK_SLOP_PX,
    HANDLE_DOT_GAP_PX,
    HANDLE_DOT_PX,
    MESSAGE_HANDLE_HEIGHT_PX,
    PANEL_HANDLE_WIDTH_PX,
)

DOTS = 3


class PanelHandle(QSplitterHandle):
    def __init__(self, orientation, splitter: "PanelSplitter") -> None:
        super().__init__(orientation, splitter)
        self._press = None

    def _panel_index(self) -> int | None:
        """The widget this handle opens and closes: the one on the outer side (first or last)."""
        splitter = self.splitter()
        index = splitter.indexOf(self)  # handle i sits in front of widget i
        last = splitter.count() - 1
        if index == 1 and splitter.is_side_panel(0):
            return 0
        if index == last and splitter.is_side_panel(last):
            return last
        return None

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        background = self.palette().color(QPalette.Mid)
        background.setAlpha(HANDLE_BACKGROUND_ALPHA)
        painter.fillRect(self.rect(), background)  # a light strip, so the handle is seen even when a panel is shut
        colour = self.palette().color(self.foregroundRole())
        colour.setAlpha(160)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        centre_x, centre_y = self.width() / 2, self.height() / 2
        panel = self._panel_index()
        if panel is not None and self.splitter().is_collapsed(panel):
            # an arrow towards the side where the panel opens: right for the left panel, left for the right one
            direction = 1 if panel == 0 else -1
            arrow = HANDLE_ARROW_PX
            painter.drawPolygon(QPolygonF([
                QPointF(centre_x - direction * arrow / 2, centre_y - arrow),
                QPointF(centre_x - direction * arrow / 2, centre_y + arrow),
                QPointF(centre_x + direction * arrow / 2, centre_y),
            ]))
            return
        radius = HANDLE_DOT_PX / 2
        for k in range(DOTS):
            offset = (k - (DOTS - 1) / 2) * HANDLE_DOT_GAP_PX
            painter.drawEllipse(QPointF(centre_x, centre_y + offset), radius, radius)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self._press = event.globalPosition()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().mouseReleaseEvent(event)
        if self._press is None:
            return
        moved = (event.globalPosition() - self._press).manhattanLength()
        self._press = None
        panel = self._panel_index()
        if moved <= HANDLE_CLICK_SLOP_PX and panel is not None:
            self.splitter().toggle_panel(panel)
        self.update()


class PanelSplitter(QSplitter):
    """Three parts: a left panel, the middle, a right panel. The outer two can be collapsed and opened again."""

    MIDDLE = 1  # the part that gives and takes the room of a panel that is closed or opened

    def __init__(self) -> None:
        super().__init__(Qt.Horizontal)
        self.setHandleWidth(PANEL_HANDLE_WIDTH_PX)
        self.setChildrenCollapsible(True)
        self._open_widths: dict[int, int] = {}
        self._open_minimums: dict[int, int] = {}  # the minimum width of a side panel while it is open: a shut one counts as nothing in the size of the window
        self._open_policies: dict[int, QSizePolicy] = {}  # its size policy while it is open (a shut one ignores what its content asks for)
        self.splitterMoved.connect(lambda _pos, _index: self._handles_changed())

    def addWidget(self, widget) -> None:  # noqa: N802 (Qt name)
        super().addWidget(widget)
        self._open_minimums[self.indexOf(widget)] = widget.minimumWidth()
        self._open_policies[self.indexOf(widget)] = widget.sizePolicy()

    def setSizes(self, sizes) -> None:  # noqa: N802 (Qt name)
        super().setSizes(sizes)
        self._apply_minimums()

    def _apply_minimums(self) -> None:
        """A shut side panel has no minimum width (else the window could not be smaller than with the panel open); an open one has its own."""
        sizes = self.sizes()
        for index in range(self.count()):
            if self.is_side_panel(index):
                shut = sizes[index] == 0
                panel = self.widget(index)
                panel.setMinimumWidth(0 if shut else self._open_minimums.get(index, 0))
                if index in self._open_policies:
                    policy = QSizePolicy(self._open_policies[index])
                    if shut:
                        policy.setHorizontalPolicy(QSizePolicy.Ignored)  # else the splitter still counts the width the content would like
                    panel.setSizePolicy(policy)

    def createHandle(self) -> QSplitterHandle:  # noqa: N802 (Qt name)
        return PanelHandle(self.orientation(), self)

    def is_side_panel(self, index: int) -> bool:
        return self.count() >= 3 and index in (0, self.count() - 1)

    def is_collapsed(self, index: int) -> bool:
        return self.sizes()[index] == 0

    def toggle_panel(self, index: int) -> None:
        if self.is_collapsed(index):
            self.open_panel(index)
        else:
            self.close_panel(index)

    def close_panel(self, index: int) -> None:
        sizes = self.sizes()
        if sizes[index] == 0:
            return
        self._open_widths[index] = sizes[index]
        middle = self.MIDDLE
        sizes[middle] += sizes[index]
        sizes[index] = 0
        self.setSizes(sizes)
        self._handles_changed()

    def open_panel(self, index: int) -> None:
        sizes = self.sizes()
        if sizes[index] > 0:
            return
        wanted = max(self._open_widths.get(index, 0), self._open_minimums.get(index, 0))
        middle = self.MIDDLE
        wanted = min(wanted, max(0, sizes[middle] - self.widget(middle).minimumWidth()))  # keep the middle usable
        sizes[middle] -= wanted
        sizes[index] = wanted
        self.setSizes(sizes)
        self._handles_changed()

    def _handles_changed(self) -> None:
        self._apply_minimums()
        sizes = self.sizes()
        for index in (0, self.count() - 1):
            if sizes[index] > 0:
                self._open_widths[index] = sizes[index]  # where to open again after the user dragged it shut
        for k in range(1, self.count()):
            self.handle(k).update()


class RightPanelSplitter(PanelSplitter):
    """Two parts: the middle and one panel on the right, which can be collapsed and opened again (the tray of the sketch editor)."""

    MIDDLE = 0

    def is_side_panel(self, index: int) -> bool:
        return self.count() >= 2 and index == self.count() - 1


class GripHandle(QSplitterHandle):
    """The handle of a stack splitter: a light strip with a row of three dots, so the user sees that the border can be dragged."""

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        background = self.palette().color(QPalette.Mid)
        background.setAlpha(HANDLE_BACKGROUND_ALPHA)
        painter.fillRect(self.rect(), background)
        colour = self.palette().color(self.foregroundRole())
        colour.setAlpha(160)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        radius = HANDLE_DOT_PX / 2
        for k in range(DOTS):
            offset = (k - (DOTS - 1) / 2) * HANDLE_DOT_GAP_PX
            painter.drawEllipse(QPointF(self.width() / 2 + offset, self.height() / 2), radius, radius)


class StackSplitter(QSplitter):
    """Two parts one above the other (the picture and the messages): the user drags the border between them to change the ratio."""

    def __init__(self) -> None:
        super().__init__(Qt.Vertical)
        self.setHandleWidth(MESSAGE_HANDLE_HEIGHT_PX)
        self.setChildrenCollapsible(False)

    def createHandle(self) -> QSplitterHandle:  # noqa: N802 (Qt name)
        return GripHandle(self.orientation(), self)
