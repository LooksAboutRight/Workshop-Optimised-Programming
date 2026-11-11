"""A raw part drawn in the sketch editor (mode 'raw part'): the stock it makes and the numbers worked out from it.

The outline is a contour with the clamping plane as a named point. Solid: an open profile that starts and ends on the spindle
axis (the axis closes it). Hollow: a closed loop. Only what lies outside the jaws is stock. The old numbers of `RawPart` (diameter,
bore, stick-out, length, front Z) are kept in step with the drawing, so everything that reads them goes on working.
"""

from __future__ import annotations

from ..constants import CLAMP_PLANE_POINT, GEOMETRY_TOLERANCE_MM, RAW_OUTLINE_MARGIN_MM
from ..contour import Contour
from ..geometry import segments_to_polyline
from ..geometry.region import Region
from ..sketch.constants import ORIGIN
from ..sketch.model import Sketch
from .raw_part import RawPart, RawPartError


def outline_region(outline: Contour) -> Region:
    """The half section of the whole drawn piece (the axis closes an open profile)."""
    return Region.from_segments(list(outline.segments))


def clamp_z(outline: Contour) -> float:
    point = next((p for p in outline.points if p.name == CLAMP_PLANE_POINT), None)
    if point is None:
        raise RawPartError(f"the drawn raw part has no point named '{CLAMP_PLANE_POINT}'")
    return point.z


def outline_stock(raw_part: RawPart) -> Region:
    """The part of the drawn piece outside the jaws."""
    outline = raw_part.outline
    margin = RAW_OUTLINE_MARGIN_MM
    outside = Region.rectangle(-margin, clamp_z(outline), raw_part.outer_radius_mm + margin, raw_part.front_z_mm + margin)
    return outline_region(outline).intersection(outside)


def raw_part_from_outline(material: str, outline: Contour) -> RawPart:
    """A raw part whose numbers are worked out from the drawing."""
    if not outline.segments:
        raise RawPartError("the drawn raw part is empty")
    points = segments_to_polyline(list(outline.segments))
    high_x, front_z, back_z = max(p.x for p in points), max(p.z for p in points), min(p.z for p in points)
    low_x = min(p.x for p in points)
    hollow = outline.is_closed and low_x > GEOMETRY_TOLERANCE_MM
    clamp = clamp_z(outline)
    return RawPart(
        material, 2 * high_x, front_z - clamp, 2 * low_x if hollow else 0, front_z - back_z, front_z, outline,
    )


def starting_sketch(raw_part: RawPart, back_z: float) -> Sketch:
    """The sketch to start from for a raw part that is drawn for the first time: its bar or tube as a drawing, with the
    clamping plane named on the outer wall. `back_z` is where the drawn piece ends behind the jaws."""
    sketch = Sketch()
    front, clamp = raw_part.front_z_mm, raw_part.clamp_z_mm
    outer, inner = raw_part.outer_radius_mm, raw_part.inner_radius_mm
    corners = [(inner, front), (outer, front), (outer, clamp), (outer, back_z), (inner, back_z)]
    ids = [sketch.add_point(x, z) for x, z in corners]
    last = len(ids) if inner > 0 else len(ids) - 1
    for index in range(last):
        sketch.add_line(ids[index], ids[(index + 1) % len(ids)])
    sketch.label_point(ids[2], CLAMP_PLANE_POINT)
    sketch.add_constraint("vertical", (ids[0], ids[1]))  # the end faces lie across the axis
    sketch.add_constraint("vertical", (ids[3], ids[4]))
    sketch.add_constraint("horizontal", (ids[1], ids[2]))  # the outer wall runs along the axis
    sketch.add_constraint("horizontal", (ids[2], ids[3]))
    if inner > 0:
        sketch.add_constraint("horizontal", (ids[4], ids[0]))
    else:
        sketch.add_constraint("horizontal", (ids[0], ORIGIN))
        sketch.add_constraint("horizontal", (ids[4], ORIGIN))
    return sketch
