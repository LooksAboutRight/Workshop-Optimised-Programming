"""Zoom and pan of a picture, without any GUI toolkit (the 2D view of the part and the toolpaths).

The picture is drawn into a rectangle. Without zoom that is the `base` rectangle (the picture fitted into the window,
aspect ratio kept). `zoom` makes the rectangle bigger; `origin` is where its top left corner lies, as a fraction of the
base size, so the view survives a change of the window size and of the picture. Rectangles are (x, y, width, height).
"""

from __future__ import annotations

from dataclasses import dataclass

from .ui_constants import PAN_KEEP_VISIBLE_FRACTION, ZOOM_MAX, ZOOM_MIN

Rect = tuple[float, float, float, float]


@dataclass
class ZoomPan:
    zoom: float = ZOOM_MIN
    origin: tuple[float, float] = (0.0, 0.0)  # top left corner of the picture relative to the base rectangle, in base sizes

    @property
    def is_default(self) -> bool:
        return self.zoom == ZOOM_MIN and self.origin == (0.0, 0.0)

    def reset(self) -> None:
        self.zoom, self.origin = ZOOM_MIN, (0.0, 0.0)

    def view_rect(self, base: Rect) -> Rect:
        x, y, width, height = base
        return (x + self.origin[0] * width, y + self.origin[1] * height, width * self.zoom, height * self.zoom)

    def zoom_at(self, cursor: tuple[float, float], base: Rect, factor: float, window: Rect | None = None) -> None:
        """Zoom by `factor` keeping the point of the picture under `cursor` where it is."""
        new_zoom = min(max(self.zoom * factor, ZOOM_MIN), ZOOM_MAX)
        if new_zoom == self.zoom:
            return
        x, y, width, height = self.view_rect(base)
        ratio = new_zoom / self.zoom
        left, top = cursor[0] - (cursor[0] - x) * ratio, cursor[1] - (cursor[1] - y) * ratio
        self.zoom = new_zoom
        self.origin = ((left - base[0]) / base[2], (top - base[1]) / base[3])
        self._keep_in_window(base, window)

    def pan_by(self, dx: float, dy: float, base: Rect, window: Rect | None = None) -> None:
        """Move the picture by (dx, dy) window pixels."""
        self.origin = (self.origin[0] + dx / base[2], self.origin[1] + dy / base[3])
        self._keep_in_window(base, window)

    def _keep_in_window(self, base: Rect, window: Rect | None) -> None:
        """Do not lose the picture: a part of it always stays inside the window; unzoomed it sits at its base place."""
        if self.zoom <= ZOOM_MIN:
            self.reset()
            return
        if window is None:
            return
        x, y, width, height = self.view_rect(base)
        keep_x, keep_y = width * PAN_KEEP_VISIBLE_FRACTION, height * PAN_KEEP_VISIBLE_FRACTION
        left = min(max(x, window[0] + keep_x - width), window[0] + window[2] - keep_x)
        top = min(max(y, window[1] + keep_y - height), window[1] + window[3] - keep_y)
        self.origin = ((left - base[0]) / base[2], (top - base[1]) / base[3])
