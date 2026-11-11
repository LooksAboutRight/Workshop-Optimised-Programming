"""The colour set of the pictures from the window's own palette (requirement V4)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from ..theme import ColorSet, color_set_for, mix_colors
from ..ui_constants import UNTOUCHED_TEXT_FADE


def color_set_from_palette(palette: QPalette) -> ColorSet:
    """Light or dark set, depending on the window colour; no background rectangle (the window shows through)."""
    window = palette.color(QPalette.Window).name()  # "#rrggbb"
    text = palette.color(QPalette.WindowText).name()
    return color_set_for(window, text)


def untouched_text_color(palette: QPalette) -> QColor:
    """The text colour of a field the user has not touched: the normal text faded towards the field colour."""
    text = palette.color(QPalette.Text).name()
    base = palette.color(QPalette.Base).name()
    return QColor(mix_colors(text, base, UNTOUCHED_TEXT_FADE))
