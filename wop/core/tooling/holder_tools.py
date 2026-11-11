"""Shapes of turning tools with an ISO holder (rectangular shank, ISO 5608) and of boring bars (ISO 6261).

Coordinates as everywhere in a tool shape: the programmed point (tip) is at (0, 0), X is the radial direction, Z the
axial one, the chuck is towards -Z. A right hand outside tool lies at +Z behind its tip and its shank runs away from the
axis (+X); a left hand tool is mirrored in Z; a boring bar is mirrored in X (its body is towards the axis) and its shank
runs along +Z.

The insert is a rhombus (square, triangle ...) of ISO 1832 with its acute corner at the tip: the main edge faces the
chuck at the cutting edge angle kappa of the holder style, the other edge leaves an end cutting edge angle of
180 - kappa - tip angle. The head of the holder (between the insert and the shank) is not standardised: it is drawn as a
plain envelope, a little larger than the real head (safe for collision checks). The shank is a rectangle (width b, from
the dimension f) or a cylinder (diameter d, axis at f from the tip).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ..constants import GEOMETRY_TOLERANCE_MM, HALF, HOLDER_HEAD_NECK_SLOPE, HOLDER_LEFT_HAND
from ..contour_check import find_crossings
from ..geometry import ArcDirection, ArcSegment, LineSegment, Point
from .holder_designation import (
    bar_row,
    length_mm,
    offset_f_mm,
    secondary_angle_deg,
    section_size,
    style_row,
)
from .insert_designation import InsertDesignation
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape

XZ = tuple[float, float]
Chain = Callable[[XZ, XZ], list[XZ]]  # (far end of the secondary edge, far end of the main edge) -> points between them


def _rect_chain(f_mm: float, width_mm: float, l1_mm: float) -> Chain:
    """Head and rectangular shank (width b, from f), as the points from the end of the main edge round to the secondary edge."""

    def chain(far_a: XZ, far_b: XZ) -> list[XZ]:
        far_c = (far_a[0] + far_b[0], far_a[1] + far_b[1])  # the fourth corner of the rhombus
        head_x = max(far_a[0], far_b[0], far_c[0])
        z_front = f_mm - width_mm
        z_back = max(f_mm, far_c[1], far_a[1])
        neck_x = head_x + abs(z_front - far_b[1]) * HOLDER_HEAD_NECK_SLOPE
        if l1_mm <= neck_x:
            raise ToolError("the holder is shorter than its head: take a longer length letter")
        return [(head_x, far_b[1]), (neck_x, z_front), (l1_mm, z_front), (l1_mm, z_back), (head_x, z_back)]

    return chain


def _bar_chain(f_mm: float, diameter_mm: float, l1_mm: float) -> Chain:
    """Head and round shank of a boring bar (seen from the side it is a rectangle of the diameter, axis at f)."""

    def chain(far_a: XZ, far_b: XZ) -> list[XZ]:
        far_c = (far_a[0] + far_b[0], far_a[1] + far_b[1])
        low, high = f_mm - diameter_mm * HALF, f_mm + diameter_mm * HALF
        if high < max(far_b[0], far_c[0]):
            raise ToolError("the insert is too big for this boring bar: take a smaller insert or a thicker bar")
        if l1_mm <= max(far_c[1], far_a[1]):
            raise ToolError("the boring bar is shorter than its head: take a longer length letter")
        return [(high, far_b[1]), (high, l1_mm), (low, l1_mm), (low, far_a[1])]

    return chain


def _build(
    number: int,
    name: str,
    designation: InsertDesignation,
    kappa_deg: float,
    chain: Chain,
    inside: bool,
    left_hand: bool,
) -> Tool:
    tip = designation.tip_angle_deg
    secondary = secondary_angle_deg(kappa_deg, tip)
    alpha, psi = math.radians(tip), math.radians(secondary)
    length, radius = designation.edge_length_mm, designation.nose_radius_mm
    tangent = radius / math.tan(alpha * HALF)
    if tangent >= length:
        raise ToolError("the corner radius is too big for this insert")
    along_a = (math.sin(psi), math.cos(psi))
    along_b = (math.sin(psi + alpha), math.cos(psi + alpha))
    side_x = -1 if inside else 1
    side_z = -1 if left_hand else 1

    def at(point: XZ) -> Point:
        return Point(point[0] * side_x, point[1] * side_z)

    def scaled(unit: XZ, distance: float) -> XZ:
        return (unit[0] * distance, unit[1] * distance)

    start_a, start_b = scaled(along_a, tangent), scaled(along_b, tangent)
    far_a, far_b = scaled(along_a, length), scaled(along_b, length)
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER
    pieces: list[ToolSegment] = []
    if radius > 0:
        bisector = (along_a[0] + along_b[0], along_a[1] + along_b[1])
        unit = scaled(bisector, 1 / math.hypot(*bisector))
        distance = radius / math.sin(alpha * HALF)
        centre, middle, first = at(scaled(unit, distance)), at(scaled(unit, distance - radius)), at(start_a)
        cross = (first.x - centre.x) * (middle.z - centre.z) - (first.z - centre.z) * (middle.x - centre.x)
        direction = ArcDirection.CCW if cross > 0 else ArcDirection.CW
        pieces.append(ToolSegment(ArcSegment(first, at(start_b), centre, direction), cutter))
    pieces.append(ToolSegment(LineSegment(at(start_b), at(far_b)), cutter))
    points: list[XZ] = []
    for point in [far_b, *chain(far_a, far_b), far_a]:
        if not points or math.dist(points[-1], point) > GEOMETRY_TOLERANCE_MM:
            points.append(point)
    pieces += [ToolSegment(LineSegment(at(a), at(b)), holder) for a, b in zip(points, points[1:])]
    pieces.append(ToolSegment(LineSegment(at(far_a), at(start_a)), cutter))
    shape = ToolShape(tuple(pieces))
    if find_crossings(shape.segments, True):
        raise ToolError("the insert does not fit this holder: its outline would cross the holder (take a smaller insert)")
    return Tool(number, name, shape)


def holder_tool(
    number: int,
    name: str,
    designation: InsertDesignation,
    style: str,
    hand: str,
    section: str,
    length_letter: str,
) -> Tool:
    """An outside turning tool: insert on a rectangular holder (ISO 5608 / 5610)."""
    _letter, kappa, offset, _cutting = style_row(style)
    height, width = section_size(section)
    f_mm = offset_f_mm(width, offset)
    if not height or not width:
        raise ToolError("a shank needs a height and a width")
    return _build(
        number, name, designation, kappa, _rect_chain(f_mm, width, length_mm(length_letter)),
        inside=False, left_hand=hand == HOLDER_LEFT_HAND,
    )


def bar_tool(
    number: int,
    name: str,
    designation: InsertDesignation,
    kappa_deg: float,
    hand: str,
    diameter_mm: int,
    length_letter: str,
) -> Tool:
    """A boring bar with an insert (ISO 6261 / 5609): the shank runs along +Z, the body is towards the axis."""
    _diameter, f_mm, _smallest_bore = bar_row(diameter_mm)
    return _build(
        number, name, designation, kappa_deg, _bar_chain(f_mm, diameter_mm, length_mm(length_letter)),
        inside=True, left_hand=hand == HOLDER_LEFT_HAND,
    )
