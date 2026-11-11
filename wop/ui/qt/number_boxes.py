"""Number fields: select everything when entered, no trailing zeros, "." and "," both work as the decimal point."""

from __future__ import annotations

from PySide6.QtCore import QLocale, QTimer
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox
from shiboken6 import isValid

from ..number_text import number_from_text
from .qt_constants import SPIN_MIN_WIDTH_PX


def _select_all_if_alive(box) -> None:
    """Select the text of the box unless the form was rebuilt meanwhile and the box is gone (a click from one field into
    the next rebuilds the form while the selection is still waiting)."""
    if isValid(box):
        box.selectAll()


def _select_all_later(box) -> None:
    QTimer.singleShot(0, lambda: _select_all_if_alive(box))


class NumberBox(QDoubleSpinBox):
    def __init__(self) -> None:
        super().__init__()
        locale = QLocale(QLocale.C)  # the decimal point is "." whatever the system language
        locale.setNumberOptions(QLocale.OmitGroupSeparator | QLocale.RejectGroupSeparator)
        self.setLocale(locale)
        self.setMinimumWidth(SPIN_MIN_WIDTH_PX)  # the default minimum is wide enough for a million with four decimals

    def textFromValue(self, value: float) -> str:  # noqa: N802 (Qt name)
        text = f"{value:.{self.decimals()}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("", "-0") else text

    def validate(self, text: str, pos: int):
        return super().validate(text.replace(",", "."), pos)

    def valueFromText(self, text: str) -> float:  # noqa: N802 (Qt name)
        number = number_from_text(text)  # the text can carry the unit ("12.5 mm")
        return self.value() if number is None else number

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().focusInEvent(event)
        _select_all_later(self)


class WholeNumberBox(QSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(SPIN_MIN_WIDTH_PX)

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().focusInEvent(event)
        _select_all_later(self)
