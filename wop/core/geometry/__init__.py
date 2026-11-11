"""The fast geometry of the X/Z plane: points and pieces (`primitives.py`), where pieces cross and how far apart they are, offsets, the
areas as exact chains (`chains.py`, `region.py`), the tool as loops of edges and what it sweeps. It imports nothing of WOP but the
constants; the hot modules are compiled (`wop/core/compiled.py`)."""

from .primitives import (  # noqa: F401  (the points and pieces are imported from the package)
    ArcDirection,
    ArcSegment,
    Box,
    LineSegment,
    Point,
    Segment,
    arc_from_endpoints,
    polyline_length,
    segments_intersect,
    segments_to_polyline,
    signed_area,
)
