"""The small types of the areas (`region.py`), in a module of their own so that the callers can import them alone."""

from __future__ import annotations

from dataclasses import dataclass

from .primitives import Point


class RegionError(ValueError):
    """The given points do not describe a valid area."""


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_z: float
    max_x: float
    max_z: float


@dataclass(frozen=True)
class PolygonRings:
    """One polygon: outer boundary and the boundaries of its holes."""

    exterior: tuple[Point, ...]
    holes: tuple[tuple[Point, ...], ...]
