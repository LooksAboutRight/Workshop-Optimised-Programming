"""The flow list drawn as cards (usability, touch).

Every entry is a rounded card: a strip in the colour of the block on the left, a big tick box for export, and up to
three lines of text: "N: Type" (bold), the name of the block, and a note (smaller, dimmer). The text wraps and the
card grows downwards when the panel is narrow, so nothing is cut off.

The list stays a normal QListWidget (selection, keyboard, Up/Down): only the drawing and the size of the rows are
done here. The data of a row sits in item roles (see the ROLE_ constants).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QFrame, QListWidget, QStyle, QStyledItemDelegate

from .qt_constants import (
    FLOW_CARD_GAP_PX,
    FLOW_CARD_MIN_HEIGHT_PX,
    FLOW_CARD_PAD_PX,
    FLOW_CARD_RADIUS_PX,
    FLOW_CHECK_BOX_PX,
    FLOW_CHECK_HIT_PX,
    FLOW_DIM_ALPHA,
    FLOW_LINE_GAP_PX,
    FLOW_NOTE_SIZE_FACTOR,
    FLOW_SELECTED_BORDER_PX,
    FLOW_SELECTED_FILL_ALPHA,
    FLOW_STRIP_PX,
    FLOW_WARNING_COLOR,
)

ROLE_KIND = Qt.UserRole + 1  # one of the KIND_ values
ROLE_COLOR = Qt.UserRole + 2  # colour of the strip, "#rrggbb" ("" = neutral)
ROLE_TITLE = Qt.UserRole + 3  # line 1
ROLE_NAME = Qt.UserRole + 4  # line 2 (may be empty)
ROLE_NOTE = Qt.UserRole + 5  # line 3 (may be empty)
ROLE_WARN = Qt.UserRole + 6  # True: the note is a warning

KIND_SETUP = "setup"
KIND_BLOCK = "block"
KIND_CONTOUR = "contour"
KIND_HEADER = "header"

TEXT_FLAGS = Qt.AlignLeft.value | Qt.AlignTop.value | Qt.TextWordWrap.value  # as plain numbers (mixed flag types)
HEADER_FLAGS = Qt.AlignLeft.value | Qt.AlignVCenter.value
CHECKED = Qt.Checked.value
UNCHECKED = Qt.Unchecked.value


def _is_checked(value) -> bool:
    return getattr(value, "value", value) == CHECKED  # a number or an enum, depending on the PySide6 version


class FlowDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.width = 0  # width of the list's viewport; the list keeps this up to date

    # --- geometry -----------------------------------------------------------------------

    def _fonts(self, base: QFont) -> tuple[QFont, QFont, QFont]:
        title, name, note = QFont(base), QFont(base), QFont(base)
        title.setBold(True)
        if base.pointSizeF() > 0:
            note.setPointSizeF(base.pointSizeF() * FLOW_NOTE_SIZE_FACTOR)
        elif base.pixelSize() > 0:
            note.setPixelSize(max(1, int(base.pixelSize() * FLOW_NOTE_SIZE_FACTOR)))
        return title, name, note

    def _card_rect(self, row: QRect) -> QRect:
        return row.adjusted(FLOW_CARD_GAP_PX, FLOW_CARD_GAP_PX, -FLOW_CARD_GAP_PX, -FLOW_CARD_GAP_PX)

    def _text_left(self, kind: str) -> int:
        """Distance from the left edge of the card to the text."""
        left = FLOW_STRIP_PX
        left += FLOW_CHECK_HIT_PX if kind == KIND_BLOCK else FLOW_CARD_PAD_PX
        return left

    def _text_width(self, card_width: int, kind: str) -> int:
        return max(1, card_width - self._text_left(kind) - FLOW_CARD_PAD_PX)

    def _lines(self, index, base: QFont, text_width: int) -> list[tuple[str, QFont, int, bool]]:
        """The lines to draw: (text, font, height of the wrapped text, is the note)."""
        title_font, name_font, note_font = self._fonts(base)
        entries = (
            (index.data(ROLE_TITLE), title_font, False),
            (index.data(ROLE_NAME), name_font, False),
            (index.data(ROLE_NOTE), note_font, True),
        )
        lines = []
        for text, font, is_note in entries:
            if not text:
                continue
            height = QFontMetrics(font).boundingRect(0, 0, text_width, 0x7FFFFF, TEXT_FLAGS, text).height()
            lines.append((text, font, height, is_note))
        return lines

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt name)
        kind = index.data(ROLE_KIND)
        if kind == KIND_HEADER:
            return QSize(self.width, QFontMetrics(option.font).height() + 2 * FLOW_CARD_PAD_PX)
        card_width = max(1, self.width - 2 * FLOW_CARD_GAP_PX)
        lines = self._lines(index, option.font, self._text_width(card_width, kind))
        text_height = sum(height for _t, _f, height, _n in lines) + FLOW_LINE_GAP_PX * max(0, len(lines) - 1)
        card_height = max(FLOW_CARD_MIN_HEIGHT_PX, text_height + 2 * FLOW_CARD_PAD_PX)
        return QSize(self.width, card_height + 2 * FLOW_CARD_GAP_PX)

    # --- drawing ------------------------------------------------------------------------

    def paint(self, painter: QPainter, option, index) -> None:
        """Draw one row of the flow list (a header or a block)."""
        kind = index.data(ROLE_KIND)
        palette = option.palette
        text_colour = palette.color(QPalette.Text)
        dim_colour = QColor(text_colour)
        dim_colour.setAlpha(FLOW_DIM_ALPHA)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if kind == KIND_HEADER:
            title_font, _name, _note = self._fonts(option.font)
            painter.setFont(title_font)
            painter.setPen(dim_colour)
            area = option.rect.adjusted(FLOW_CARD_PAD_PX, 0, -FLOW_CARD_PAD_PX, 0)
            painter.drawText(area, HEADER_FLAGS, index.data(ROLE_TITLE) or "")
            painter.restore()
            return
        card = self._card_rect(option.rect)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(card), FLOW_CARD_RADIUS_PX, FLOW_CARD_RADIUS_PX)
        selected = bool(option.state & QStyle.State_Selected)
        painter.fillPath(shape, palette.color(QPalette.Base))
        if selected:
            tint = QColor(palette.color(QPalette.Highlight))
            tint.setAlpha(FLOW_SELECTED_FILL_ALPHA)
            painter.fillPath(shape, tint)
        # the strip in the colour of the block, cut to the rounded corners of the card
        strip_colour = QColor(index.data(ROLE_COLOR) or palette.color(QPalette.Mid))
        painter.save()
        painter.setClipPath(shape)
        painter.fillRect(QRect(card.left(), card.top(), FLOW_STRIP_PX, card.height()), strip_colour)
        painter.restore()
        border = palette.color(QPalette.Highlight if selected else QPalette.Mid)
        pen = QPen(border)
        pen.setWidth(FLOW_SELECTED_BORDER_PX if selected else 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(shape)
        if kind == KIND_BLOCK:
            self._paint_check(painter, option, index, card)
        # text
        text_left = card.left() + self._text_left(kind)
        text_width = self._text_width(card.width(), kind)
        lines = self._lines(index, option.font, text_width)
        warn = bool(index.data(ROLE_WARN))
        y = card.top() + FLOW_CARD_PAD_PX
        for text, font, height, is_note in lines:
            painter.setFont(font)
            painter.setPen(QColor(FLOW_WARNING_COLOR) if (is_note and warn) else (dim_colour if is_note else text_colour))
            painter.drawText(QRect(text_left, y, text_width, height), TEXT_FLAGS, text)
            y += height + FLOW_LINE_GAP_PX
        painter.restore()

    def _check_hit_rect(self, option_rect: QRect) -> QRect:
        """The area that toggles the tick: the full height of the card, FLOW_CHECK_HIT_PX wide, after the strip."""
        card = self._card_rect(option_rect)
        return QRect(card.left() + FLOW_STRIP_PX, card.top(), FLOW_CHECK_HIT_PX, card.height())

    def _paint_check(self, painter: QPainter, option, index, card: QRect) -> None:
        hit = self._check_hit_rect(option.rect)
        box = QRectF(0, 0, FLOW_CHECK_BOX_PX, FLOW_CHECK_BOX_PX)
        box.moveCenter(QPointF(hit.center().x() + 0.5, hit.center().y() + 0.5))
        palette = option.palette
        ticked = _is_checked(index.data(Qt.CheckStateRole))
        painter.setBrush(palette.color(QPalette.Highlight) if ticked else palette.color(QPalette.Base))
        pen = QPen(palette.color(QPalette.Highlight if ticked else QPalette.Mid))
        pen.setWidth(FLOW_SELECTED_BORDER_PX)
        painter.setPen(pen)
        painter.drawRoundedRect(box, FLOW_CARD_RADIUS_PX / 2, FLOW_CARD_RADIUS_PX / 2)
        if ticked:
            tick = QPen(palette.color(QPalette.HighlightedText))
            tick.setWidth(FLOW_SELECTED_BORDER_PX)
            tick.setCapStyle(Qt.RoundCap)
            tick.setJoinStyle(Qt.RoundJoin)
            painter.setPen(tick)
            painter.setBrush(Qt.NoBrush)
            size = box.width()
            painter.drawPolyline([
                QPointF(box.left() + size * 0.22, box.top() + size * 0.52),
                QPointF(box.left() + size * 0.42, box.top() + size * 0.72),
                QPointF(box.left() + size * 0.78, box.top() + size * 0.30),
            ])

    # --- clicks on the tick box ---------------------------------------------------------

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802 (Qt name)
        if index.data(ROLE_KIND) == KIND_BLOCK and event.type() == QEvent.MouseButtonRelease:
            flags = model.flags(index)
            if (flags & Qt.ItemIsUserCheckable) and (flags & Qt.ItemIsEnabled):
                if self._check_hit_rect(option.rect).contains(event.position().toPoint()):
                    now = _is_checked(index.data(Qt.CheckStateRole))
                    model.setData(index, UNCHECKED if now else CHECKED, Qt.CheckStateRole)
                    return True
        return super().editorEvent(event, model, option, index)


class FlowList(QListWidget):
    """A QListWidget that draws its rows as cards and re-wraps them when the panel changes its width."""

    def __init__(self) -> None:
        super().__init__()
        self._card_delegate = FlowDelegate(self)
        self.setItemDelegate(self._card_delegate)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(False)
        self.viewport().setBackgroundRole(QPalette.Window)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        width = self.viewport().width()
        if width != self._card_delegate.width:
            self._card_delegate.width = width
            self.scheduleDelayedItemsLayout()  # the rows are measured again for the new width
