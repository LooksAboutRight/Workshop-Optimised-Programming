"""The pictograms of the sketch editor buttons, drawn in code on a 24 x 24 grid (so they follow the theme and stay sharp).

Each pictogram is a small function that draws with an `Ink`: the main colour (the text colour of the button), an accent
(the part that the button acts on) and a muted colour (what is only a hint, like the sharp corner behind a fillet).
`make_icon` returns a QIcon; Qt greys it out by itself when the button is disabled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from .sketch_view_constants import CUTTING_COLOUR, LOOSE_COLOUR

GRID = 24
STROKE = 1.7
ICON_SIZES = (26, 52)  # the picture sizes put in the icon: normal and for a high resolution screen


@dataclass
class Ink:
    painter: QPainter
    main: QColor
    accent: QColor
    muted: QColor

    def pen(self, colour: QColor, width: float = STROKE, style=Qt.SolidLine) -> QPen:
        pen = QPen(colour, width, style, Qt.RoundCap, Qt.RoundJoin)
        return pen

    def line(self, x1: float, y1: float, x2: float, y2: float, colour: QColor | None = None, width: float = STROKE, style=Qt.SolidLine) -> None:
        self.painter.setPen(self.pen(colour or self.main, width, style))
        self.painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def lines(self, points: list, colour: QColor | None = None, width: float = STROKE, style=Qt.SolidLine, closed: bool = False) -> None:
        self.painter.setPen(self.pen(colour or self.main, width, style))
        self.painter.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        if closed:
            path.closeSubpath()
        self.painter.drawPath(path)

    def dot(self, x: float, y: float, radius: float = 2.2, colour: QColor | None = None) -> None:
        self.painter.setPen(Qt.NoPen)
        self.painter.setBrush(colour or self.accent)
        self.painter.drawEllipse(QPointF(x, y), radius, radius)

    def ring(self, x: float, y: float, radius: float, colour: QColor | None = None, width: float = STROKE) -> None:
        self.painter.setPen(self.pen(colour or self.main, width))
        self.painter.setBrush(Qt.NoBrush)
        self.painter.drawEllipse(QPointF(x, y), radius, radius)

    def arc(self, cx: float, cy: float, radius: float, start_deg: float, span_deg: float, colour: QColor | None = None, style=Qt.SolidLine) -> None:
        self.painter.setPen(self.pen(colour or self.main, STROKE, style))
        self.painter.setBrush(Qt.NoBrush)
        self.painter.drawArc(QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius), int(start_deg * 16), int(span_deg * 16))

    def arrow_head(self, tip: tuple[float, float], toward: tuple[float, float], size: float = 4.2, colour: QColor | None = None) -> None:
        """A filled arrow head at `tip`, pointing away from `toward`."""
        dx, dy = tip[0] - toward[0], tip[1] - toward[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        base = (tip[0] - ux * size, tip[1] - uy * size)
        wing = (-uy * size / 2.6, ux * size / 2.6)
        self.painter.setPen(Qt.NoPen)
        self.painter.setBrush(colour or self.main)
        self.painter.drawPolygon(QPolygonF([QPointF(*tip), QPointF(base[0] + wing[0], base[1] + wing[1]), QPointF(base[0] - wing[0], base[1] - wing[1])]))


# --- the tools ---------------------------------------------------------------------------------------------------------


def _line(ink: Ink) -> None:
    ink.line(5, 19, 19, 5)
    ink.dot(5, 19)
    ink.dot(19, 5)


def _circle(ink: Ink) -> None:
    ink.ring(12, 12, 8)
    ink.dot(12, 12, 1.6)


def _arc_centre(ink: Ink) -> None:
    ink.arc(7, 18, 12, 0, 90)
    ink.line(7, 18, 19, 18, ink.muted, 1.2, Qt.DotLine)
    ink.line(7, 18, 7, 6, ink.muted, 1.2, Qt.DotLine)
    ink.dot(7, 18, 2)
    ink.dot(19, 18, 1.6, ink.main)
    ink.dot(7, 6, 1.6, ink.main)


def _arc_three(ink: Ink) -> None:
    ink.arc(12, 18, 10, 20, 140)
    ink.dot(21.4, 14.6)
    ink.dot(2.6, 14.6)
    ink.dot(12, 8)


def _trim(ink: Ink) -> None:
    ink.line(3, 12, 12, 12)
    ink.line(12, 3, 12, 21)
    ink.line(12, 12, 21, 12, ink.accent, STROKE, Qt.DashLine)


def _point(ink: Ink) -> None:
    ink.ring(12, 12, 6)
    ink.dot(12, 12, 2)


def _dimension(ink: Ink) -> None:
    ink.line(4, 5, 4, 18, ink.muted, 1.2)
    ink.line(20, 5, 20, 18, ink.muted, 1.2)
    ink.line(4, 14, 20, 14)
    ink.arrow_head((4, 14), (10, 14))
    ink.arrow_head((20, 14), (14, 14))


# --- the relations -----------------------------------------------------------------------------------------------------


def _horizontal(ink: Ink) -> None:
    ink.line(4, 10, 20, 10)
    ink.dot(4, 10)
    ink.dot(20, 10)
    ink.line(8, 17, 16, 17, ink.accent, 2.2)


def _vertical(ink: Ink) -> None:
    ink.line(10, 4, 10, 20)
    ink.dot(10, 4)
    ink.dot(10, 20)
    ink.line(17, 8, 17, 16, ink.accent, 2.2)


def _parallel(ink: Ink) -> None:
    ink.line(4, 17, 14, 5)
    ink.line(10, 20, 20, 8)


def _perpendicular(ink: Ink) -> None:
    ink.line(4, 19, 20, 19)
    ink.line(8, 4, 8, 19)
    ink.lines([(8, 14.5), (12.5, 14.5), (12.5, 19)], ink.accent, 1.4)


def _equal(ink: Ink) -> None:
    ink.line(4, 7, 20, 7)
    ink.line(4, 17, 20, 17)
    ink.line(12, 4.5, 12, 9.5, ink.accent)
    ink.line(12, 14.5, 12, 19.5, ink.accent)


def _tangent(ink: Ink) -> None:
    ink.ring(12, 15, 6)
    ink.line(3, 9, 21, 9)
    ink.dot(12, 9)


def _fixed(ink: Ink) -> None:
    ink.line(12, 8, 12, 15)
    ink.dot(12, 6.5, 2.6)
    ink.line(5, 15, 19, 15)
    for x in (6, 10, 14, 18):
        ink.line(x, 15, x - 2.5, 20, ink.muted, 1.4)


def _point_on(ink: Ink) -> None:
    ink.line(4, 19, 20, 5)
    ink.ring(12, 12, 3.4, ink.accent, 2)


def _midpoint(ink: Ink) -> None:
    ink.line(3, 12, 21, 12)
    ink.line(3, 8, 3, 16)
    ink.line(21, 8, 21, 16)
    ink.dot(12, 12, 2.8)


def _join(ink: Ink) -> None:
    ink.line(4, 5, 12, 12)
    ink.line(20, 6, 12, 12)
    ink.line(12, 12, 8, 20)
    ink.dot(12, 12, 3.2)


# --- modify ------------------------------------------------------------------------------------------------------------


def _construction(ink: Ink) -> None:
    ink.line(4, 19, 20, 5, ink.main, STROKE, Qt.DashLine)


def _centre(ink: Ink) -> None:
    pen = ink.pen(ink.main, STROKE)
    pen.setDashPattern([6, 2, 1.2, 2])
    ink.painter.setPen(pen)
    ink.painter.drawLine(QPointF(1.5, 12), QPointF(22.5, 12))


def _cutting(ink: Ink) -> None:
    ink.line(4, 17, 20, 7, QColor(*CUTTING_COLOUR), 3.6)
    ink.line(4, 20, 14, 20, ink.muted, 1.2)


def _fillet(ink: Ink) -> None:
    ink.line(6, 4, 6, 20, ink.muted, 1.2, Qt.DashLine)
    ink.line(6, 20, 21, 20, ink.muted, 1.2, Qt.DashLine)
    ink.line(6, 4, 6, 13)
    ink.arc(12, 13, 6, 180, 90)
    ink.line(12, 19, 21, 19)


def _chamfer(ink: Ink) -> None:
    ink.line(6, 4, 6, 20, ink.muted, 1.2, Qt.DashLine)
    ink.line(6, 20, 21, 20, ink.muted, 1.2, Qt.DashLine)
    ink.lines([(6, 4), (6, 12), (13, 19), (21, 19)])


def _mirror_axis(ink: Ink, x1: float, y1: float, x2: float, y2: float) -> None:
    pen = ink.pen(ink.muted, 1.4)
    pen.setDashPattern([5, 2, 1, 2])
    ink.painter.setPen(pen)
    ink.painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _mirror(ink: Ink) -> None:
    _mirror_axis(ink, 12, 1.5, 12, 22.5)
    ink.lines([(9, 5), (3, 5), (9, 13)], ink.main, closed=True)
    ink.lines([(15, 5), (21, 5), (15, 13)], ink.accent, closed=True)


# --- the rest ----------------------------------------------------------------------------------------------------------


def _undo(ink: Ink) -> None:
    path = QPainterPath(QPointF(18, 19))
    path.cubicTo(QPointF(21.5, 12), QPointF(16, 8), QPointF(8.5, 9))
    ink.painter.setPen(ink.pen(ink.main, 1.9))
    ink.painter.setBrush(Qt.NoBrush)
    ink.painter.drawPath(path)
    ink.arrow_head((5, 9.3), (11, 9), 5)


def _redo(ink: Ink) -> None:
    path = QPainterPath(QPointF(6, 19))
    path.cubicTo(QPointF(2.5, 12), QPointF(8, 8), QPointF(15.5, 9))
    ink.painter.setPen(ink.pen(ink.main, 1.9))
    ink.painter.setBrush(Qt.NoBrush)
    ink.painter.drawPath(path)
    ink.arrow_head((19, 9.3), (13, 9), 5)


def _snap(ink: Ink) -> None:
    ink.ring(12, 12, 6)
    for a, b, c, d in ((12, 2, 12, 7), (12, 17, 12, 22), (2, 12, 7, 12), (17, 12, 22, 12)):
        ink.line(a, b, c, d)
    ink.dot(12, 12, 2)


def _show_relations(ink: Ink) -> None:
    ink.line(4, 7, 20, 7)
    ink.line(4, 17, 20, 17)
    ink.line(10, 10.5, 10, 13.5, ink.accent, 2.2)
    ink.line(14, 10.5, 14, 13.5, ink.accent, 2.2)


def _show_dimensions(ink: Ink) -> None:
    ink.line(4, 5, 4, 18, ink.muted, 1.2)
    ink.line(20, 5, 20, 18, ink.muted, 1.2)
    ink.line(4, 14, 8, 14)
    ink.line(16, 14, 20, 14)
    ink.arrow_head((4, 14), (8, 14))
    ink.arrow_head((20, 14), (16, 14))
    ink.line(9.5, 10, 14.5, 10, ink.accent, 2.2)


def _rapid(ink: Ink) -> None:
    ink.line(3, 17, 21, 7, ink.accent, 2.2, Qt.DashLine)
    ink.arrow_head((21, 7), (14, 10.5), 5, ink.accent)
    ink.dot(3, 17, 2, ink.muted)


def _name_mount(ink: Ink) -> None:
    ink.line(5, 3, 5, 21, ink.muted, 2.6)
    ink.lines([(5, 8), (19, 8), (19, 16), (5, 16)])
    ink.dot(5, 12, 2.4, ink.accent)


def _name_step(ink: Ink) -> None:
    ink.lines([(3, 19), (3, 15), (9, 15), (9, 10), (15, 10), (15, 5), (21, 5)])
    ink.dot(6, 15, 2.2, ink.accent)
    ink.dot(12, 10, 2.2, ink.accent)


def _name_face(ink: Ink) -> None:
    ink.lines([(3, 4), (9, 4), (9, 20), (3, 20)], ink.muted, 1.4, closed=True)
    ink.line(9, 4, 9, 20, ink.accent, 2.6)
    ink.line(9, 12, 20, 12, ink.muted, 1.2, Qt.DashLine)


def _import(ink: Ink) -> None:
    ink.lines([(5, 3), (14, 3), (19, 8), (19, 21), (5, 21)], closed=True)
    ink.lines([(14, 3), (14, 8), (19, 8)], ink.muted, 1.3)
    ink.line(12, 10, 12, 17, ink.accent, 2)
    ink.arrow_head((12, 18.5), (12, 13), 5, ink.accent)


PICTOGRAMS = (
    ("line", _line), ("circle", _circle), ("arc_centre", _arc_centre), ("arc_three", _arc_three), ("trim", _trim),
    ("point", _point), ("dimension", _dimension),
    ("horizontal", _horizontal), ("vertical", _vertical), ("parallel", _parallel), ("perpendicular", _perpendicular),
    ("equal", _equal), ("tangent", _tangent), ("fixed", _fixed), ("point_on", _point_on), ("midpoint", _midpoint),
    ("join", _join),
    ("construction", _construction), ("centre", _centre), ("cutting", _cutting), ("rapid", _rapid), ("fillet", _fillet), ("chamfer", _chamfer),
    ("mirror", _mirror),
    ("undo", _undo), ("redo", _redo), ("snap", _snap), ("show_relations", _show_relations), ("show_dimensions", _show_dimensions), ("import", _import),
    ("name_mount", _name_mount), ("name_step", _name_step), ("name_face", _name_face),
)


def icon_names() -> tuple[str, ...]:
    return tuple(name for name, _draw in PICTOGRAMS)


def pixmap(name: str, size: int, main: QColor) -> QPixmap:
    """The pictogram `name` as a picture of size x size pixels (transparent round it)."""
    draw = dict(PICTOGRAMS)[name]
    image = QPixmap(size, size)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / GRID, size / GRID)
    muted = QColor(main)
    muted.setAlphaF(0.55)
    draw(Ink(painter, main, QColor(*LOOSE_COLOUR), muted))
    painter.end()
    return image


def make_icon(name: str, main: QColor) -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(pixmap(name, size, main))
    return icon
