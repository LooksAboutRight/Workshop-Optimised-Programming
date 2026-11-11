"""The rule of a drawn raw part (the mode 'raw part' of the sketch editor).

A raw part is a solid or a hollow piece. Solid: an open profile that starts and ends on the spindle axis (the axis closes it).
Hollow: a closed loop wholly at X > 0. A closed loop that touches the axis is a solid one. One point has the name
`CLAMP_PLANE_POINT`; its Z is where the jaws begin, and it lies inside the length of the piece.
"""

from __future__ import annotations

from ..constants import CLAMP_PLANE_POINT, GEOMETRY_TOLERANCE_MM
from ..geometry import Segment, segments_to_polyline
from .model import Sketch


def raw_part_problems(sketch: Sketch, segments: list[Segment], closed: bool) -> list[str]:
    """What is wrong with the outline of a raw part, in plain words (empty: it is one)."""
    found = []
    if not closed:
        for place, point in (("starts", segments[0].start), ("ends", segments[-1].end)):
            if abs(point.x) > GEOMETRY_TOLERANCE_MM:
                found.append(f"An open outline starts and ends on the spindle axis (X = 0): this one {place} at X = {point.x:g}")
    if CLAMP_PLANE_POINT not in sketch.labels:
        found.append(f"Name one point '{CLAMP_PLANE_POINT.capitalize()}': it marks where the jaws begin")
    else:
        z = sketch.point(sketch.labels[CLAMP_PLANE_POINT]).z
        heights = [point.z for point in segments_to_polyline(segments)]
        if not min(heights) + GEOMETRY_TOLERANCE_MM < z < max(heights) - GEOMETRY_TOLERANCE_MM:
            found.append("The clamping plane must lie inside the length of the piece")
    return found
