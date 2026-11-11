"""Windows that fit a small screen (the lathe PC may be 1024 x 768).

Two helpers and one filter: `scrolling` puts a page into a scroll area, so the page no longer sets the smallest size of the window (it scrolls when
the window is smaller than it wants to be); `ScreenFitFilter` keeps a window that opens larger than the screen inside the part of the screen the
desktop leaves free. `tools/check_small_screen.py` and `tests/test_small_screen.py` measure the smallest size of the windows.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QDialog, QFrame, QMainWindow, QScrollArea, QWidget

from .qt_constants import SCREEN_MARGIN_X_PX, SCREEN_MARGIN_Y_PX

FITTED_PROPERTY = "wop_screen_fitted"  # set on a window the filter has looked at: it is looked at once, so the user may enlarge it afterwards


def scrolling(page: QWidget) -> QScrollArea:
    """`page` in a scroll area without a frame: the page keeps the size it needs when there is room, and scrolls when there is not."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(page)
    return area


def fit_to_screen(window: QWidget) -> None:
    """Make a window that is larger than the free part of its screen smaller, but never smaller than it can be."""
    screen = window.screen()
    if screen is None:
        return
    free = screen.availableGeometry()
    width = min(window.width(), free.width() - SCREEN_MARGIN_X_PX)
    height = min(window.height(), free.height() - SCREEN_MARGIN_Y_PX)
    hint = window.minimumSizeHint()
    width, height = max(width, hint.width(), window.minimumWidth()), max(height, hint.height(), window.minimumHeight())
    if (width, height) != (window.width(), window.height()):
        window.resize(width, height)


class ScreenFitFilter(QObject):
    """Installed on the application: every dialog and main window is fitted to the screen when it is shown for the first time."""

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        if event.type() == QEvent.Show and isinstance(watched, (QDialog, QMainWindow)) and watched.isWindow() and not watched.property(FITTED_PROPERTY):
            watched.setProperty(FITTED_PROPERTY, True)
            fit_to_screen(watched)
        return False
