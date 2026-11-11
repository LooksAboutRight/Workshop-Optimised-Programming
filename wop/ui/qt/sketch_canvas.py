"""The drawing area of the sketch editor: it paints the sketch and turns mouse and keys into session calls."""

from __future__ import annotations


from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ...core.constants import CLAMP_PLANE_POINT, SAFE_POINT_KEY
from ...core.geometry import ArcSegment, Point, Segment
from ...core.sketch.model import Sketch
from ...core.sketch.pick import piece_id, piece_points
from ...core.sketch.constants import ORIGIN
from ...core.sketch.relations import relation_for
from ..sketch_constants import AXIS_ID, TOOL_SELECT, RELATION_TAGS, SNAP_RADIUS_PX
from ..sketch_stepping import CURRENT, HIDDEN, OLD
from ..sketch_dimension_graphic import DimensionGraphic
from ..sketch_session import SketchSession
from ..sketch_text_place import candidate_boxes, pick_box
from .sketch_view_constants import (
    CANVAS_MIN_HEIGHT_PX,
    CANVAS_MIN_WIDTH_PX,
    ARROW_PX,
    MIRROR_LINE_WIDTH_PX,
    CUTTING_COLOUR,
    LOCKED_COLOUR,
    OLD_PIECE_ALPHA,
    ARROW_ALONG,
    STEP_ARROW_PX,
    DIM_TEXT_GAP_PX,
    ORIGIN_RADIUS_PX,
    CUTTING_WIDTH_PX,
    GRID_MIN_SPACING_PX,
    GRID_STEPS_MM,
    LOOSE_COLOUR,
    PIECE_WIDTH_PX,
    POINT_RADIUS_PX,
    SELECT_COLOUR,
    SELECT_WIDTH_PX,
    START_SCALE_PX_PER_MM,
    TAG_LINE_PX,
    TAG_OFFSET_PX,
    ZOOM_STEP,
)


class SketchCanvas(QWidget):
    """z runs to the right and x (the radius) up, as in the other pictures of the program."""

    dimension_edit_requested = Signal(int)  # double click on a dimension number: the id of the relation

    def __init__(self, session: SketchSession) -> None:
        super().__init__()
        self.session = session
        self.scale = START_SCALE_PX_PER_MM
        self.origin = QPointF(0, 0)
        self._placed = False
        self._panning_from: QPointF | None = None
        self._tag_rects: list[tuple[QRectF, int]] = []  # where the numbers and tags were drawn the last time
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(CANVAS_MIN_WIDTH_PX, CANVAS_MIN_HEIGHT_PX)
        session.subscribe(self.update)

    # --- coordinates --------------------------------------------------------------------------------------------------

    def to_world(self, screen: QPointF) -> Point:
        return Point((self.origin.y() - screen.y()) / self.scale, (screen.x() - self.origin.x()) / self.scale)

    def to_screen(self, point: Point) -> QPointF:
        return QPointF(self.origin.x() + point.z * self.scale, self.origin.y() - point.x * self.scale)

    @property
    def tolerance(self) -> float:
        return SNAP_RADIUS_PX / self.scale

    # --- mouse and keys -----------------------------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self._panning_from = event.position()
        elif event.button() == Qt.RightButton:
            self.session.cancel()
        elif event.button() == Qt.LeftButton:
            tag = self._tag_at(event.position())
            if tag is not None and self.session.tool == TOOL_SELECT:  # on a number: it is chosen, and moves with the mouse
                self.session.begin_dimension_drag(tag, self.to_world(event.position()))
                return
            self.session.press(self.to_world(event.position()), self.tolerance, bool(event.modifiers() & Qt.ControlModifier))

    def mouseMoveEvent(self, event) -> None:
        if self._panning_from is not None:
            self.origin += event.position() - self._panning_from
            self._panning_from = event.position()
            self.update()
        elif event.buttons() & Qt.LeftButton:
            self.session.drag(self.to_world(event.position()), self.tolerance)
        else:
            self.session.move_hover(self.to_world(event.position()), self.tolerance)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self._panning_from = None
        elif event.button() == Qt.LeftButton:
            self.session.release(self.to_world(event.position()), self.tolerance, bool(event.modifiers() & Qt.ControlModifier))

    def mouseDoubleClickEvent(self, event) -> None:
        tag = self._tag_at(event.position())
        if tag is not None and event.button() == Qt.LeftButton:
            self.dimension_edit_requested.emit(tag)

    def _tag_at(self, position: QPointF) -> int | None:
        return next((cid for rect, cid in reversed(self._tag_rects) if rect.contains(position)), None)

    def wheelEvent(self, event) -> None:
        before = self.to_world(event.position())
        self.scale *= ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        after = self.to_screen(before)
        self.origin += event.position() - after  # the point under the mouse stays where it is
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.session.escape()
        elif event.key() == Qt.Key_Right and self.session.can_step:
            self.session.step_forward()
        elif event.key() == Qt.Key_Left and self.session.can_step:
            self.session.step_back()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.session.selected_constraint is not None and not (self.session.selected_pieces or self.session.selected_points):
                self.session.remove_constraint(self.session.selected_constraint)
            else:
                self.session.delete_selected()
        else:
            super().keyPressEvent(event)

    # --- painting -----------------------------------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        """Draw the grid, the sketch and what is laid over it."""
        if not self._placed:  # first paint: the origin in the middle at the bottom: parts run to negative Z, up in X
            self.origin = QPointF(self.width() * 0.5, self.height() * 0.85)
            self._placed = True
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        text = palette.text().color()
        highlight = palette.highlight().color()
        self._paint_grid(painter, text, highlight)
        sketch = self.session.sketch
        drawings = self._dimension_drawings(text, highlight)
        for _id, drawing, _label, colour in drawings:  # under the sketch, so they never cover a contour or a helper line
            self._paint_dimension_lines(painter, drawing, colour)
        members = self.session.constraint_members()  # what the chosen relation acts on: drawn like the selection
        loose = QColor(*LOOSE_COLOUR)
        picked = QColor(*SELECT_COLOUR)
        fixed = self.session.analysis.fixed_points
        for piece in sketch.pieces():
            state = self.session.piece_state(piece_id(piece))
            if state == HIDDEN:
                continue
            selected = piece_id(piece) in self.session.selected_pieces or piece_id(piece) in members[1]
            colour = picked if selected else (text if piece_points(piece) <= fixed else loose)
            if piece.cutting and not selected:
                colour = QColor(*CUTTING_COLOUR)  # the cutting edges of a tool shape
            if sketch.is_locked_piece(piece_id(piece)) and not selected:
                colour = QColor(*LOCKED_COLOUR)
            thin = getattr(piece, "reference", False) or state == OLD  # the sharp corner a fillet or chamfer left, or an older piece of a path
            if state == OLD and not selected:
                colour = QColor(colour)
                colour.setAlphaF(OLD_PIECE_ALPHA)
            self._paint_segment(
                painter, sketch.segment(piece), colour, piece.construction or piece_id(piece) in sketch.rapid_pieces,
                SELECT_WIDTH_PX if selected else (1 if thin else (CUTTING_WIDTH_PX if piece.cutting else PIECE_WIDTH_PX)),
                getattr(piece, "centre_line", False),
            )
        for piece in sketch.pieces():  # the way the tool moves on the current piece of a path: an arrow at its end
            if self.session.piece_state(piece_id(piece)) == CURRENT:
                whole = sketch.segment(piece)
                tip, behind = (whole.end, whole.point_at(ARROW_ALONG)) if self.session.walked_forward(piece_id(piece)) else (whole.start, whole.point_at(1 - ARROW_ALONG))
                painter.setPen(QPen(QColor(*SELECT_COLOUR), 1))
                painter.setBrush(QColor(*SELECT_COLOUR))
                self._paint_arrow(painter, self.to_screen(tip), self.to_screen(behind), STEP_ARROW_PX)
        for segment in self.session.preview_segments():
            self._paint_segment(painter, segment, highlight, True)
        self._paint_mirror_line(painter, highlight)
        self._paint_points(painter, sketch, text, highlight, loose, fixed, members[0])
        self._paint_origin(painter, text, ORIGIN in members[0])
        self._paint_numbers(painter, drawings)
        self._paint_tags(painter, text)
        self._paint_band(painter, highlight)
        self._paint_trail(painter, highlight)
        painter.end()

    def _paint_grid(self, painter: QPainter, text: QColor, highlight: QColor) -> None:
        spacing = next((s for s in GRID_STEPS_MM if s * self.scale >= GRID_MIN_SPACING_PX), GRID_STEPS_MM[-1])
        faint = QColor(text)
        faint.setAlphaF(0.12)
        painter.setPen(QPen(faint, 1))
        low, high = self.to_world(QPointF(0, self.height())), self.to_world(QPointF(self.width(), 0))
        z = int(low.z // spacing) * spacing
        while z <= high.z:
            painter.drawLine(self.to_screen(Point(low.x, z)), self.to_screen(Point(high.x, z)))
            z += spacing
        x = int(low.x // spacing) * spacing
        while x <= high.x:
            painter.drawLine(self.to_screen(Point(x, low.z)), self.to_screen(Point(x, high.z)))
            x += spacing
        axis = QColor(text)
        axis.setAlphaF(0.45)
        painter.setPen(QPen(axis, 1))
        painter.drawLine(self.to_screen(Point(0, low.z)), self.to_screen(Point(0, high.z)))
        painter.drawLine(self.to_screen(Point(low.x, 0)), self.to_screen(Point(high.x, 0)))
        for name, point_id in self.session.sketch.labels.items():
            if name == CLAMP_PLANE_POINT:  # the clamping plane of a raw part: a line across the Z axis through its point
                z = self.session.sketch.point(point_id).z
                painter.setPen(QPen(QColor(*LOCKED_COLOUR), 1.5, Qt.DashLine))
                painter.drawLine(self.to_screen(Point(low.x, z)), self.to_screen(Point(high.x, z)))
        if self.session.mode.centre_line:  # the spindle axis of a turning contour: the centre line that is always there
            picked = any(kind == "centre" and ref == AXIS_ID for kind, ref in self.session.dim_picks)
            pen = QPen(QColor(*SELECT_COLOUR) if picked else text, 1.5, Qt.DashDotLine)
            painter.setPen(pen)
            painter.drawLine(self.to_screen(Point(0, low.z)), self.to_screen(Point(0, high.z)))

    def _paint_segment(
        self, painter: QPainter, segment: Segment, colour: QColor, dashed: bool, width: float = PIECE_WIDTH_PX, centre: bool = False
    ) -> None:
        pen = QPen(colour, width)
        if centre:
            pen.setStyle(Qt.DashDotLine)  # a centre line
        elif dashed:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        if isinstance(segment, ArcSegment):
            path = QPainterPath()
            points = segment.to_polyline()
            path.moveTo(self.to_screen(points[0]))
            for point in points[1:]:
                path.lineTo(self.to_screen(point))
            painter.drawPath(path)
        else:
            painter.drawLine(self.to_screen(segment.start), self.to_screen(segment.end))

    def _paint_mirror_line(self, painter: QPainter, colour: QColor) -> None:
        """While the Mirror tool is on: the line it would mirror about now, thick and in the colour of the selection."""
        axis = self.session.hover_axis
        if axis is None:
            return
        painter.setPen(QPen(colour, MIRROR_LINE_WIDTH_PX, Qt.SolidLine, Qt.RoundCap))
        if axis == "z":  # the spindle axis: the whole width of the picture
            level = self.to_screen(Point(0, 0)).y()
            painter.drawLine(QPointF(0, level), QPointF(self.width(), level))
        else:
            segment = self.session.sketch.segment(self.session.sketch.lines[axis])
            painter.drawLine(self.to_screen(segment.start), self.to_screen(segment.end))

    def _paint_trail(self, painter: QPainter, colour: QColor) -> None:
        """The path of the mouse while swiping with the Trim tool (it is not part of the sketch)."""
        if len(self.session.trail) < 2:
            return
        painter.setPen(QPen(colour, 1, Qt.DotLine))
        path = QPainterPath()
        path.moveTo(self.to_screen(self.session.trail[0]))
        for point in self.session.trail[1:]:
            path.lineTo(self.to_screen(point))
        painter.drawPath(path)

    def _paint_band(self, painter: QPainter, colour: QColor) -> None:
        if self.session.band is None:
            return
        corner, other = (self.to_screen(point) for point in self.session.band)
        fill = QColor(colour)
        fill.setAlphaF(0.15)
        painter.setPen(QPen(colour, 1, Qt.DashLine))
        painter.setBrush(fill)
        painter.drawRect(QRectF(corner, other).normalized())

    def _dimension_drawings(self, text: QColor, highlight: QColor) -> list:
        """(id or None, drawing, number, colour) of every placed dimension and of the one that follows the mouse."""
        found = []
        for constraint in self.session.sketch.constraints.values():
            if relation_for(constraint.kind).dimension and self.session.show_dimensions and self.session.constraint_visible(constraint):
                drawing, label = self.session.dimension_drawing(constraint)
                chosen = constraint.constraint_id == self.session.selected_constraint
                found.append((constraint.constraint_id, drawing, label, QColor(*SELECT_COLOUR) if chosen else text))
        draft = self.session.dimension_draft()
        if draft is not None:
            found.append((None, draft.drawing, draft.text, highlight))
        return found

    def _paint_dimension_lines(self, painter: QPainter, drawing: DimensionGraphic, colour: QColor) -> None:
        """Extension lines, dimension line, arc and arrows (the number is painted later, on top)."""
        painter.setPen(QPen(colour, 1))
        painter.setBrush(Qt.NoBrush)
        for start, end in drawing.lines:
            painter.drawLine(self.to_screen(start), self.to_screen(end))
        if drawing.curve:
            path = QPainterPath()
            path.moveTo(self.to_screen(drawing.curve[0]))
            for point in drawing.curve[1:]:
                path.lineTo(self.to_screen(point))
            painter.drawPath(path)
        painter.setBrush(colour)
        for tip, behind in drawing.arrows:
            self._paint_arrow(painter, self.to_screen(tip), self.to_screen(behind))
        painter.setBrush(Qt.NoBrush)

    def _obstacles(self, drawings: list) -> list:
        """Every line on the screen that a number should keep clear of: a list of lines, each a list of short pieces made of two
        (x, y) points (an arc is one line of many pieces, a whole dimension is one line)."""
        found = []

        def pieces(points: list) -> list:
            return [((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(points, points[1:])]

        for piece in self.session.sketch.pieces():
            segment = self.session.sketch.segment(piece)
            points = segment.to_polyline() if isinstance(segment, ArcSegment) else [segment.start, segment.end]
            found.append(pieces([self.to_screen(point) for point in points]))
        if self.session.mode.centre_line:  # the spindle axis
            level = self.to_screen(Point(0, 0)).y()
            found.append([((0.0, level), (float(self.width()), level))])
        for _id, drawing, _label, _colour in drawings:
            own = [piece for start, end in drawing.lines for piece in pieces([self.to_screen(start), self.to_screen(end)])]
            found.append(own + pieces([self.to_screen(point) for point in drawing.curve]))
        return found

    def _paint_numbers(self, painter: QPainter, drawings: list) -> None:
        """The numbers of the dimensions: on the usual side of the dimension line (right of one that runs up and down, above
        any other), between its ends, in the first place along it that no line runs through; if there is none, in the place where
        the fewest lines run through it (it ignores only as many lines as it must)."""
        self._tag_rects = []
        obstacles = self._obstacles(drawings)
        taken: list = []
        metrics = painter.fontMetrics()
        for constraint_id, drawing, label, colour in drawings:
            size = (metrics.horizontalAdvance(label), metrics.height())
            along_a_line = len(drawing.arrows) == 2 and not drawing.curve and bool(drawing.lines)
            if along_a_line:  # a dimension line: the number stays on its usual side of it, between its ends
                first, second = (self.to_screen(point) for point in drawing.lines[-1])
            else:  # an angle, a radius: round the place the number belongs
                first = second = self.to_screen(drawing.text_at)
            box = pick_box(
                candidate_boxes((first.x(), first.y()), (second.x(), second.y()), size, DIM_TEXT_GAP_PX, along_a_line),
                obstacles, taken,
            )
            taken.append(box)
            painter.setPen(QPen(colour, 1))
            painter.drawText(QPointF(box[0], box[1] + metrics.ascent()), label)
            if constraint_id is not None:
                self._tag_rects.append((QRectF(*box).adjusted(-2, -2, 2, 2), constraint_id))

    def _paint_tags(self, painter: QPainter, text: QColor) -> None:
        """A short tag for each relation that is not a dimension, next to the things it belongs to."""
        if not self.session.show_relations:
            return
        tags = dict(RELATION_TAGS)
        stacked: dict[tuple[int, int], int] = {}
        sketch = self.session.sketch
        for constraint in sketch.constraints.values():
            relation = relation_for(constraint.kind)
            if relation.dimension or not self.session.constraint_visible(constraint):
                continue
            label = tags.get(constraint.kind, "")
            x, z = relation.anchor(sketch.constraint_args(constraint))
            at = self.to_screen(Point(x, z))
            slot = stacked.get((round(at.x()), round(at.y())), 0)
            stacked[(round(at.x()), round(at.y()))] = slot + 1
            painter.setPen(QColor(*SELECT_COLOUR) if constraint.constraint_id == self.session.selected_constraint else text)
            place = at + QPointF(TAG_OFFSET_PX, -TAG_OFFSET_PX + slot * TAG_LINE_PX)
            painter.drawText(place, label)
            metrics = painter.fontMetrics()
            box = QRectF(place.x(), place.y() - metrics.ascent(), metrics.horizontalAdvance(label), metrics.height())
            self._tag_rects.append((box.adjusted(-2, -2, 2, 2), constraint.constraint_id))

    @staticmethod
    def _paint_arrow(painter: QPainter, tip: QPointF, behind: QPointF, size: float = ARROW_PX) -> None:
        dx, dy = tip.x() - behind.x(), tip.y() - behind.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        ux, uy = dx / length, dy / length
        base = QPointF(tip.x() - ux * size, tip.y() - uy * size)
        wing = QPointF(-uy * size / 3, ux * size / 3)
        painter.drawPolygon(QPolygonF([tip, base + wing, base - wing]))

    def _paint_origin(self, painter: QPainter, text: QColor, member: bool = False) -> None:
        """The origin: a small ring (the Dimension tool and Horizontal / Vertical can pick it)."""
        picked = any(i == ORIGIN for _kind, i in self.session.dim_picks) or ORIGIN in self.session.selected_points or member
        painter.setPen(QPen(QColor(*SELECT_COLOUR) if picked else text, SELECT_WIDTH_PX / 2 if picked else 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.to_screen(Point(0, 0)), ORIGIN_RADIUS_PX, ORIGIN_RADIUS_PX)

    def _paint_points(
        self, painter: QPainter, sketch: Sketch, text: QColor, highlight: QColor, loose: QColor, fixed: frozenset,
        members: set[int] = frozenset(),
    ) -> None:
        centres = {arc.centre for arc in sketch.arcs.values()}
        names = {point_id: name for name, point_id in sketch.labels.items()}
        hidden = self.session.hidden_points()
        for point_id, point in sketch.points.items():
            if point_id in hidden:
                continue
            chosen = point_id in self.session.selected_points or point_id in members
            hot = chosen or point_id == self.session.hover_point
            locked_key = next((k for k, i in sketch.locked_points.items() if i == point_id), None)
            colour = QColor(*SELECT_COLOUR) if chosen else (highlight if hot else (text if point_id in fixed else loose))
            if locked_key is not None and not chosen:
                colour = QColor(*LOCKED_COLOUR)
            painter.setPen(QPen(colour, SELECT_WIDTH_PX / 2 if chosen else 1))
            painter.setBrush(colour if hot else Qt.NoBrush)
            at = self.to_screen(point.position)
            if locked_key == SAFE_POINT_KEY:  # the safe point: a filled square with its name; the points of the part look like any other point
                painter.setBrush(colour)
                painter.drawRect(QRectF(at.x() - POINT_RADIUS_PX, at.y() - POINT_RADIUS_PX, 2 * POINT_RADIUS_PX, 2 * POINT_RADIUS_PX))
                painter.drawText(at + QPointF(POINT_RADIUS_PX + 2, -POINT_RADIUS_PX), locked_key)
                continue
            if point_id in centres:
                painter.drawLine(at + QPointF(-POINT_RADIUS_PX, 0), at + QPointF(POINT_RADIUS_PX, 0))
                painter.drawLine(at + QPointF(0, -POINT_RADIUS_PX), at + QPointF(0, POINT_RADIUS_PX))
            else:
                painter.drawEllipse(at, POINT_RADIUS_PX * (0.75 if chosen else 0.5), POINT_RADIUS_PX * (0.75 if chosen else 0.5))
            if point_id in names:  # a named point: ring and name
                painter.drawEllipse(at, POINT_RADIUS_PX, POINT_RADIUS_PX)
                painter.drawText(at + QPointF(POINT_RADIUS_PX + 2, -POINT_RADIUS_PX), names[point_id])
