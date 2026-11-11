"""What the sketch editor is opened for: the mode, the contour to start from and what happens with the result."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..core.contour import Contour
from ..core.sketch.locked import LockedArc, LockedLine, LockedPoint
from ..core.sketch.model import Sketch
from ..core.sketch.modes import FREE, SketchMode
from .point_kinds import PointKind


@dataclass(frozen=True)
class SketchTarget:
    """`commit` stores the finished contour in the program (it raises `ModelError` with the reason if it cannot);
    a target without it is a free sketch that is only looked at."""

    mode: SketchMode
    title: str
    contour: Contour | None = None  # the outline to start from (None: an empty sketch)
    point_kinds: tuple[PointKind, ...] = ()  # the names a point can be given (tip ...)
    x_scale: float = 1  # 2 when the project is typed in diameters: "along X" dimensions are shown as diameters
    commit: Callable[[Contour], None] | None = None
    start_sketch: Sketch | None = None  # the sketch to start from, when the contour cannot hold it (a path that comes back to a place)
    locked_points: tuple[LockedPoint, ...] = ()  # what the program supplies: the user can dimension to it but not change it
    locked_lines: tuple[LockedLine, ...] = ()
    locked_arcs: tuple[LockedArc, ...] = ()


FREE_TARGET = SketchTarget(FREE, "Sketch editor (experimental)")
