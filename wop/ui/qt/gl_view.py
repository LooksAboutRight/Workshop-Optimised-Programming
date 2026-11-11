"""The 3D view with OpenGL (requirements Z1, V5): `GLSceneView` draws a `Scene` (wop/ui/view3d.py).

The triangles of the part, the chuck and the jaws are drawn by the graphics card with a depth buffer. The lines of the
path, the finished outline and the tool, and the tool's fill, are drawn over them with QPainter, so they stay thin and
dashed on every system. Drag with the left or middle mouse button moves the picture (in `turns` mode it turns it), the
wheel zooms, a double click or "Reset view" comes back to the start.

`opengl_works` says whether this computer can open an OpenGL context at all; the window falls back to the 2D picture when
it cannot.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QMatrix4x4,
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QPen,
    QPolygonF,
    QSurfaceFormat,
    QVector3D,
)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMenu, QWidget

from .. import view3d_constants as v
from ..view3d import Camera, Scene, Stroke, _Projection, view_matrix
from . import gl_constants as gl
from .qt_constants import OVERLAY_MARGIN_PX

WHEEL_STEP_DEGREES = 120  # one notch of a mouse wheel
ZOOM_PER_NOTCH = 1.15
DEGREES_PER_PIXEL = 0.5
RESET_VIEW_TEXT = "Reset view"
TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT = "top-left", "top-right", "bottom-left", "bottom-right"

_probe: tuple[bool, str] | None = None


def opengl_works() -> tuple[bool, str]:
    """(works, the reason when it does not): can an OpenGL 2 context be made and used on this computer? Asked once."""
    global _probe
    if _probe is None:
        _probe = _try_context()
    return _probe


def _try_context() -> tuple[bool, str]:
    context = QOpenGLContext()
    if not context.create():
        return False, "this computer cannot open an OpenGL context"
    surface = QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    if not context.makeCurrent(surface):
        return False, "the OpenGL context cannot be used"
    try:
        version = context.format().majorVersion()
        if version < gl.MIN_GL_MAJOR and not context.isOpenGLES():
            return False, f"OpenGL {version} is too old (2.0 is needed)"
        return True, ""
    finally:
        context.doneCurrent()


def _color(text: str) -> QColor:
    return QColor(text)


class GLSceneView(QOpenGLWidget):
    """Draws a `Scene`. The camera is kept by the widget; `set_scene` shows another scene."""

    def __init__(self, turns: bool = False) -> None:
        super().__init__()
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(gl.DEPTH_BITS)
        fmt.setSamples(gl.MULTISAMPLES)
        self.setFormat(fmt)
        self.turns = turns  # dragging turns the part instead of moving the picture
        self.camera = Camera()
        self.scene: Scene | None = None
        self._dirty = False
        self._program: QOpenGLShaderProgram | None = None
        self._buffers: dict[str, tuple[QOpenGLBuffer, int]] = {}
        self._last: QPointF | None = None
        self._overlays: list[tuple[QWidget, str]] = []

    # --- the scene --------------------------------------------------------------------------------------------------

    def set_scene(self, scene: Scene | None) -> None:
        self.scene = scene
        self._dirty = True
        self.update()

    def reset_view(self) -> None:
        self.camera = Camera()
        self.update()

    def image(self):
        """The picture as a QImage (needs a computer that can run OpenGL)."""
        return self.grabFramebuffer()

    # --- OpenGL -----------------------------------------------------------------------------------------------------

    def initializeGL(self) -> None:  # noqa: N802 (Qt name)
        header = gl.DESKTOP_HEADER if not self.context().isOpenGLES() else ""
        fragment_header = header + (gl.ES_HEADER if self.context().isOpenGLES() else "")
        program = QOpenGLShaderProgram(self)
        program.addShaderFromSourceCode(QOpenGLShader.Vertex, header + gl.VERTEX_SHADER)
        program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment_header + gl.FRAGMENT_SHADER)
        program.link()
        self._program = program

    def _upload(self, name: str, positions: np.ndarray, normals: np.ndarray, colors: np.ndarray) -> None:
        old = self._buffers.pop(name, None)
        if old is not None:
            old[0].destroy()
        if not len(positions):
            return
        data = np.concatenate([positions, normals, colors], axis=1).astype(np.float32)
        buffer = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        buffer.create()
        buffer.bind()
        buffer.allocate(data.tobytes(), data.nbytes)
        buffer.release()
        self._buffers[name] = (buffer, len(data))

    def _upload_scene(self) -> None:
        scene = self.scene
        for name in ("solid", "glass", "axis"):
            self._upload(name, *(np.zeros((0, 3)),) * 3)
        if scene is None:
            return
        self._upload("solid", scene.solid.positions, scene.solid.normals, scene.solid.colors)
        self._upload("glass", scene.glass.positions, scene.glass.normals, scene.glass.colors)
        if len(scene.axis):
            colour = _color(scene.axis_color)
            rgb = np.tile([colour.redF(), colour.greenF(), colour.blueF()], (len(scene.axis), 1))
            self._upload("axis", scene.axis, np.zeros_like(scene.axis), rgb)
        self._dirty = False

    def _background(self) -> QColor:
        return self.palette().window().color()

    def paintGL(self) -> None:  # noqa: N802 (Qt name)
        functions = self.context().functions()
        background = self._background()
        functions.glClearColor(background.redF(), background.greenF(), background.blueF(), 1.0)
        functions.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        scene = self.scene
        if scene is None or self._program is None:
            return
        if self._dirty:
            self._upload_scene()
        width, height = max(1, self.width()), max(1, self.height())
        projection = _Projection(self.camera, scene.centre, scene.radius, width, height)
        mvp, normal = view_matrix(projection, width, height, scene.radius)
        program = self._program
        program.bind()
        program.setUniformValue(program.uniformLocation("u_mvp"), QMatrix4x4(*mvp.ravel().tolist()))
        normal4 = np.eye(4)
        normal4[:3, :3] = normal
        program.setUniformValue(program.uniformLocation("u_normal"), QMatrix4x4(*normal4.ravel().tolist()))
        light = np.array(v.LIGHT_DIRECTION, dtype=float)
        light /= np.linalg.norm(light)
        program.setUniformValue(program.uniformLocation("u_light"), QVector3D(*light.tolist()))
        self._ambient = float(v.AMBIENT_LIGHT)
        functions.glEnable(gl.GL_DEPTH_TEST)
        self._draw("solid", functions, gl.GL_TRIANGLES, lit=1.0, alpha=1.0)
        self._draw("axis", functions, gl.GL_LINES, lit=0.0, alpha=1.0)
        functions.glEnable(gl.GL_BLEND)
        functions.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        functions.glDepthMask(gl.GL_FALSE)
        self._draw("glass", functions, gl.GL_TRIANGLES, lit=1.0, alpha=float(scene.glass_opacity))
        functions.glDepthMask(gl.GL_TRUE)
        functions.glDisable(gl.GL_BLEND)
        functions.glDisable(gl.GL_DEPTH_TEST)
        program.release()
        self._paint_overlays(scene, projection)

    def _draw(self, name: str, functions, mode: int, lit: float, alpha: float) -> None:
        entry = self._buffers.get(name)
        if entry is None:
            return
        buffer, count = entry
        program = self._program
        program.setUniformValue(program.uniformLocation("u_params"), QVector3D(self._ambient, lit, alpha))
        buffer.bind()
        stride = gl.FLOATS_PER_VERTEX * gl.BYTES_PER_FLOAT
        for index, attribute in enumerate(("a_position", "a_normal", "a_color")):
            location = program.attributeLocation(attribute)
            program.enableAttributeArray(location)
            program.setAttributeBuffer(location, gl.GL_FLOAT, index * 3 * gl.BYTES_PER_FLOAT, 3, stride)
        functions.glDrawArrays(mode, 0, count)
        for attribute in ("a_position", "a_normal", "a_color"):
            program.disableAttributeArray(program.attributeLocation(attribute))
        buffer.release()

    # --- the lines and the tool over the solids -----------------------------------------------------------------------

    def _paint_overlays(self, scene: Scene, projection: _Projection) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for stroke in scene.strokes:
            self._stroke(painter, projection, stroke)
        for fill in scene.fills:
            polygon = QPolygonF([QPointF(x, y) for x, y in projection.pixels_of(fill.points)])
            colour = _color(fill.color)
            colour.setAlphaF(fill.opacity)
            painter.setBrush(colour)
            painter.setPen(QPen(_color(fill.stroke_color), fill.stroke_width))
            painter.drawPolygon(polygon)
        painter.setBrush(Qt.NoBrush)
        for stroke in scene.top_strokes:
            self._stroke(painter, projection, stroke)
        painter.end()

    @staticmethod
    def _stroke(painter: QPainter, projection: _Projection, stroke: Stroke) -> None:
        if len(stroke.points) < 2:
            return
        pen = QPen(_color(stroke.color), stroke.width)
        if stroke.dash:
            pen.setDashPattern([length / stroke.width for length in stroke.dash])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        points = [QPointF(x, y) for x, y in projection.pixels_of(stroke.points)]
        painter.drawPolygon(QPolygonF(points)) if stroke.closed else painter.drawPolyline(QPolygonF(points))

    # --- corners ------------------------------------------------------------------------------------------------------

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

    # --- moving, turning and zooming ----------------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._last = event.position()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if self._last is None:
            return
        position = event.position()
        dx, dy = position.x() - self._last.x(), position.y() - self._last.y()
        self.camera = self.camera.turned(dx * DEGREES_PER_PIXEL, dy * DEGREES_PER_PIXEL) if self.turns else self.camera.panned(dx, dy)
        self._last = position
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self._last = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self.reset_view()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt name)
        menu = QMenu(self)
        reset = QAction(RESET_VIEW_TEXT, menu)
        reset.triggered.connect(self.reset_view)
        menu.addAction(reset)
        menu.exec(event.globalPos())

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt name)
        self.camera = self.camera.zoomed(ZOOM_PER_NOTCH ** (event.angleDelta().y() / WHEEL_STEP_DEGREES))
        self.update()
