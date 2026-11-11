"""Marks on pictures for the manual: popups put onto the picture of a window, the mouse pointer, numbered callouts and frames.

A picture of a window (`widget.grab()`) never holds what opens above it: a menu, the list of a dropdown, a hover text. These
are windows of their own. Here they are shown from code, grabbed on their own, and pasted onto the picture of the window at
the place where they would be on the screen. Nothing of the real screen or the real mouse is used, so the result does not
depend on what else is open and does not move your mouse. The mouse pointer is drawn into the picture (white with a black
edge, like the Windows pointer); callouts and frames are red, as in most manuals.

Used by `tools/manual_scenes.py`; the drawing is tested in `tests/test_picture_marks.py`. Coordinates of a `Picture` are those
of the window it was made from (logical pixels, the top left corner of the window is 0, 0).
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QThread
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QMenuBar, QToolTip, QWidget

RED = QColor(215, 25, 25)
POINTER_OUTLINE = ((0, 0), (0, 16.5), (4.2, 12.8), (7.3, 19.8), (9.9, 18.7), (6.9, 11.8), (11.8, 11.8))  # tip at 0, 0
POINTER_SCALE = 1.25  # a little bigger than the real pointer, so it can be seen on a picture that is scaled to a page
CALLOUT_RADIUS = 11.0
CALLOUT_LINE = 2.0
FRAME_LINE = 2.2
SETTLE_ROUNDS = 6
SETTLE_MS = 25


def disable_effects() -> None:
    """No fading or sliding of menus, dropdowns and hover texts: a grab must show them whole."""
    for effect in (Qt.UI_AnimateMenu, Qt.UI_FadeMenu, Qt.UI_AnimateCombo, Qt.UI_AnimateTooltip, Qt.UI_FadeTooltip):
        QApplication.setEffectEnabled(effect, False)


def settle() -> None:
    """Let Qt show what was just opened."""
    for _ in range(SETTLE_ROUNDS):
        QApplication.processEvents()
        QThread.msleep(SETTLE_MS)


# --- opening popups from code --------------------------------------------------------------------------------------------


def open_menu(menubar: QMenuBar, action) -> QMenu:
    """Open the menu of a menu bar entry just below it, as a click would."""
    menu = action.menu()
    menu.popup(menubar.mapToGlobal(menubar.actionGeometry(action).bottomLeft()))
    settle()
    return menu


def entry_of(menu: QMenu, text: str):
    """The entry of a menu with this text (the & of the shortcut letter ignored)."""
    found = next((a for a in menu.actions() if a.text().replace("&", "") == text), None)
    if found is None:
        raise KeyError(f"the menu has no entry {text!r}: {[a.text() for a in menu.actions()]}")
    return found


def entry_point(menu: QMenu, text: str) -> QPoint:
    """The middle of an entry of an open menu, as a position on the screen."""
    return menu.mapToGlobal(menu.actionGeometry(entry_of(menu, text)).center())


def open_dropdown(combo: QComboBox) -> QWidget:
    """Open the list of a dropdown; returns the window of the list."""
    combo.showPopup()
    settle()
    return combo.view().window()


def dropdown_item_point(combo: QComboBox, row: int) -> QPoint:
    """The middle of a row of the open list of a dropdown, as a position on the screen."""
    view = combo.view()
    return view.viewport().mapToGlobal(view.visualRect(view.model().index(row, 0)).center())


def show_hover_text(widget: QWidget, text: str | None = None) -> QWidget:
    """Show the hover text of a widget below its middle; returns the tip window."""
    place = widget.mapToGlobal(widget.rect().center())
    QToolTip.showText(place, widget.toolTip() if text is None else text, widget)
    settle()
    tip = next((w for w in QApplication.topLevelWidgets() if w.metaObject().className() == "QTipLabel" and w.isVisible()), None)
    if tip is None:
        raise RuntimeError("the hover text did not appear")
    return tip


def close_popups(*things) -> None:
    QToolTip.hideText()
    for thing in things:
        if isinstance(thing, QComboBox):
            thing.hidePopup()
        elif isinstance(thing, QWidget):
            thing.close()
    settle()


# --- the picture -----------------------------------------------------------------------------------------------------------


class Picture:
    """The picture of a window with what opens above it, a pointer, callouts and frames added."""

    def __init__(self, window: QWidget) -> None:
        self.window = window
        self.image: QImage = window.grab().toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._origin = window.mapToGlobal(QPoint(0, 0))

    def local(self, global_position: QPoint) -> QPoint:
        """A position on the screen as a position in the picture."""
        return global_position - self._origin

    def where(self, widget: QWidget) -> QRect:
        """The rectangle of a widget in the picture."""
        return QRect(self.local(widget.mapToGlobal(QPoint(0, 0))), widget.size())

    def _painter(self) -> QPainter:
        painter = QPainter(self.image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        return painter

    def add_popup(self, popup: QWidget) -> None:
        """Paste an open menu, dropdown list or hover text where it is on the screen."""
        pixmap = popup.grab()
        painter = self._painter()
        painter.drawPixmap(self.local(popup.mapToGlobal(QPoint(0, 0))), pixmap)
        painter.end()

    def pointer(self, at: QPoint | QPointF, scale: float = POINTER_SCALE) -> None:
        """The mouse pointer with its tip at `at`: white with a black edge."""
        painter = self._painter()
        polygon = QPolygonF([QPointF(at.x() + x * scale, at.y() + y * scale) for x, y in POINTER_OUTLINE])
        painter.setPen(QPen(Qt.black, 1.4 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.white)
        painter.drawPolygon(polygon)
        painter.end()

    def callout(self, number: int, at: QPoint | QPointF, target: QPoint | QPointF | None = None) -> None:
        """A red circle with a white number at `at`; with `target` an arrow from the circle to that point."""
        painter = self._painter()
        centre = QPointF(at)
        if target is not None:
            goal = QPointF(target)
            dx, dy = goal.x() - centre.x(), goal.y() - centre.y()
            length = math.hypot(dx, dy)
            if length > CALLOUT_RADIUS:
                ux, uy = dx / length, dy / length
                start = QPointF(centre.x() + ux * CALLOUT_RADIUS, centre.y() + uy * CALLOUT_RADIUS)
                painter.setPen(QPen(RED, CALLOUT_LINE, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(start, goal)
                wing = QPointF(-uy * 4.0, ux * 4.0)
                back = QPointF(goal.x() - ux * 9.0, goal.y() - uy * 9.0)
                painter.setPen(Qt.NoPen)
                painter.setBrush(RED)
                painter.drawPolygon(QPolygonF([goal, back + wing, back - wing]))
        painter.setPen(QPen(Qt.white, 1.6))
        painter.setBrush(RED)
        painter.drawEllipse(centre, CALLOUT_RADIUS, CALLOUT_RADIUS)
        font = QFont(self.window.font())
        font.setBold(True)
        font.setPixelSize(int(CALLOUT_RADIUS * 1.25))
        painter.setFont(font)
        painter.setPen(Qt.white)
        box = QRectF(centre.x() - CALLOUT_RADIUS, centre.y() - CALLOUT_RADIUS, 2 * CALLOUT_RADIUS, 2 * CALLOUT_RADIUS)
        painter.drawText(box, Qt.AlignCenter, str(number))
        painter.end()

    def frame(self, rect: QRect, margin: int = 3) -> None:
        """A red frame round a rectangle (a button, a field, a menu entry)."""
        painter = self._painter()
        painter.setPen(QPen(RED, FRAME_LINE))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(rect.adjusted(-margin, -margin, margin, margin)), 3, 3)
        painter.end()

    def crop(self, rect: QRect) -> None:
        """Keep only this part of the picture (the rectangle is cut to the picture)."""
        ratio = self.image.devicePixelRatio()
        box = rect.intersected(QRect(0, 0, int(self.image.width() / ratio), int(self.image.height() / ratio)))
        kept = self.image.copy(QRect(int(box.x() * ratio), int(box.y() * ratio), int(box.width() * ratio), int(box.height() * ratio)))
        kept.setDevicePixelRatio(ratio)
        self.image = kept
        self._origin = self._origin + box.topLeft()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.image.save(str(path)):
            raise OSError(f"cannot write {path}")
