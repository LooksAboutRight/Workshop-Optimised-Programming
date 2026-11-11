"""The standard threading tool: a V point (pointed, or with a flat) on a body, outside or inside, right or left hand.

Everything is first drawn for a right-hand OUTSIDE tool in tool coordinates (u: from the point along the tool, z: across
it), then turned into the real coordinates (the same way as the grooving tool):

- the point has two flanks. `lead_angle_deg` is the angle of the flank that faces the cutting direction (the smaller Z),
  measured from the radial direction; the other flank has the included angle minus the lead angle. Equal flanks make a
  symmetric thread (60 degrees included, 30 and 30).
- the tip is pointed with a nose radius, or it has a flat (for trapezoidal threads, with sharp sides). A flat and a radius
  combine: the flat is the width of the tip between the flanks before rounding, the rounding of each corner takes away
  its tangent length (a 120 degree corner of a 60 degree tool: 0.58 of the radius), the rest stays straight.
- the flanks cut up to the cutting height, or until they meet the side of the body (the body is `width_mm` wide, its left
  side `tip_distance_mm` from the point). If they stop at the cutting height first, the tool steps out at a right angle to
  the body. A big cutting height lets the flanks run all the way to the body.
- inside, the tool is a bar along Z (the length from the left side of the body) and `width_mm` along X, and the point
  stands out of the bar's front: the flanks always end at the cutting height, and they must end on the bar.
- a left-hand tool is the mirror image in Z (outside) or in X (inside: the tool on the other side of the axis).

The touch-off point is the named point `tip`: the middle of the flat, or the lowest point of the nose.
"""

from __future__ import annotations

import math

from ..constants import (
    GEOMETRY_TOLERANCE_MM,
    HALF,
    RIGHT_ANGLE_DEG,
    THREAD_TOOL_FLANK_MAX_DEG,
    THREAD_TOOL_INCLUDED_MAX_DEG,
    THREAD_TOOL_INCLUDED_MIN_DEG,
    TIP_POINT,
    TOOL_SHAPE_DECIMALS,
)
from ..contour import NamedPoint
from ..geometry import LineSegment, Point
from .tool import Tool, ToolError, ToolSegment, ToolSegmentRole, ToolShape
from .tool_reference import arc_extremes
from .turning_tool_shape import nose_arc

Pair = tuple[float, float]  # (u, z)
Piece = tuple[Pair, Pair, "Pair | None", ToolSegmentRole]  # start, end, arc centre or None, role


def _flank_end(start: Pair, direction: Pair, height_u: float, face_z: float, meets_face: bool) -> tuple[Pair, bool]:
    """Where a flank from `start` ends: at the cutting height, or (outside) where it meets the side face of the body.

    Returns the end point and whether it is on the face."""
    to_height = (height_u - start[0]) / direction[0]
    if meets_face and abs(direction[1]) > GEOMETRY_TOLERANCE_MM:
        to_face = (face_z - start[1]) / direction[1]
        if 0 <= to_face < to_height:
            return (start[0] + to_face * direction[0], face_z), True
    return (start[0] + to_height * direction[0], start[1] + to_height * direction[1]), False


def thread_tool_shape(
    nose_radius_mm: float, flat_mm: float, included_angle_deg: float, lead_angle_deg: float, cutting_height_mm: float,
    tip_distance_mm: float, width_mm: float, length_mm: float, inside: bool,
) -> tuple[list[Piece], Pair, str]:
    """The outline of a right-hand tool with the lowest point of the tip at u = 0.

    Returns the pieces, the touch-off point (u is 0) and a text with the flank angles.
    Raises ToolError for dimensions that do not make a tool.
    """
    if min(cutting_height_mm, tip_distance_mm, width_mm, length_mm) <= 0 or nose_radius_mm < 0 or flat_mm < 0:
        raise ToolError("a threading tool needs a positive cutting height, tip distance, width and length, and a radius and flat of 0 or more")
    if not THREAD_TOOL_INCLUDED_MIN_DEG <= included_angle_deg <= THREAD_TOOL_INCLUDED_MAX_DEG:
        raise ToolError(f"the included angle must be between {THREAD_TOOL_INCLUDED_MIN_DEG} and {THREAD_TOOL_INCLUDED_MAX_DEG} degrees")
    trail_angle_deg = included_angle_deg - lead_angle_deg
    if not 0 <= lead_angle_deg <= THREAD_TOOL_FLANK_MAX_DEG or not 0 <= trail_angle_deg <= THREAD_TOOL_FLANK_MAX_DEG:
        raise ToolError(f"each flank must lean between 0 and {THREAD_TOOL_FLANK_MAX_DEG} degrees from the radial direction: change the lead angle")
    lead, trail = math.radians(lead_angle_deg), math.radians(trail_angle_deg)
    up_left, up_right = (math.cos(lead), -math.sin(lead)), (math.cos(trail), math.sin(trail))  # up the flanks (u, z)
    corner_left, corner_right = (0.0, -flat_mm * HALF), (0.0, flat_mm * HALF)
    cutter, holder = ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER

    # the tip: from the flank start on the left to the flank start on the right
    tip_pieces: list[tuple[Pair, Pair, Pair | None]] = []  # start, end, centre
    radius = nose_radius_mm
    if flat_mm > 0 and radius > 0:
        reach_left = radius / math.tan((math.radians(RIGHT_ANGLE_DEG) + lead) * HALF)
        reach_right = radius / math.tan((math.radians(RIGHT_ANGLE_DEG) + trail) * HALF)
        if reach_left + reach_right > flat_mm + GEOMETRY_TOLERANCE_MM:
            raise ToolError("the corner radius is too big for the flat")
        flank_left = (corner_left[0] + reach_left * up_left[0], corner_left[1] + reach_left * up_left[1])
        flank_right = (corner_right[0] + reach_right * up_right[0], corner_right[1] + reach_right * up_right[1])
        flat_left, flat_right = (0.0, corner_left[1] + reach_left), (0.0, corner_right[1] - reach_right)
        tip_pieces.append((flank_left, flat_left, (radius, flat_left[1])))
        tip_pieces.append((flat_left, flat_right, None))
        tip_pieces.append((flat_right, flank_right, (radius, flat_right[1])))
        touch_off_z = (flat_left[1] + flat_right[1]) * HALF
    elif flat_mm > 0:
        flank_left, flank_right = corner_left, corner_right
        tip_pieces.append((flank_left, flank_right, None))
        touch_off_z = 0.0
    elif radius > 0:
        between = math.acos(up_left[0] * up_right[0] + up_left[1] * up_right[1])
        reach = radius / math.tan(between * HALF)
        flank_left, flank_right = (reach * up_left[0], reach * up_left[1]), (reach * up_right[0], reach * up_right[1])
        bisector = (up_left[0] + up_right[0], up_left[1] + up_right[1])
        scale = radius / math.sin(between * HALF) / math.hypot(*bisector)
        tip_pieces.append((flank_left, flank_right, (bisector[0] * scale, bisector[1] * scale)))
        touch_off_z = 0.0
    else:
        flank_left = flank_right = (0.0, 0.0)
        touch_off_z = 0.0
    lowest = [flank_left[0], flank_right[0], 0.0 if flat_mm > 0 or radius == 0 else flank_left[0]]
    for start, end, centre in tip_pieces:
        if centre is not None:
            extremes = arc_extremes(nose_arc((start, end, centre)))
            lowest += [point.x for point in extremes]
            if flat_mm <= 0:  # a pointed tip: the touch-off point is the lowest point of the nose
                touch_off_z = min(extremes, key=lambda point: point.x).z
    deepest = min(lowest)
    height_u = deepest + cutting_height_mm
    if height_u <= max(flank_left[0], flank_right[0]) + GEOMETRY_TOLERANCE_MM:
        raise ToolError("the cutting height is too small for the rounded tip: make it bigger")

    # the flanks and the body
    face_left, face_right = -tip_distance_mm, (-tip_distance_mm + length_mm) if inside else (width_mm - tip_distance_mm)
    if flank_left[1] <= face_left or flank_right[1] >= face_right:
        raise ToolError("the point is not inside the body: make the tip distance bigger and the width (length inside) wider")
    end_left, on_face_left = _flank_end(flank_left, up_left, height_u, face_left, not inside)
    end_right, on_face_right = _flank_end(flank_right, up_right, height_u, face_right, not inside)
    if inside and (end_left[1] < face_left - GEOMETRY_TOLERANCE_MM or end_right[1] > face_right + GEOMETRY_TOLERANCE_MM):
        raise ToolError("the point stands out over the end of the bar: lower the cutting height, make the bar longer or the tip distance bigger")
    if inside:
        back = height_u + width_mm
        chain: list[tuple[Pair, ToolSegmentRole]] = [
            (end_right, holder), ((height_u, face_right), holder), ((back, face_right), holder), ((back, face_left), holder), ((height_u, face_left), holder),
        ]
    else:
        top = deepest + length_mm
        if top <= max(end_left[0], end_right[0]) + GEOMETRY_TOLERANCE_MM:
            raise ToolError("the tool is too short for its cutting height: make the length bigger")
        chain = [
            (end_right, holder), ((end_right[0], face_right), holder), ((top, face_right), holder), ((top, face_left), holder),
            ((end_left[0], face_left), holder),
        ]
    pieces: list[Piece] = [(end_left, flank_left, None, cutter)]
    pieces += [(start, end, centre, cutter) for start, end, centre in tip_pieces if centre is not None or math.dist(start, end) > GEOMETRY_TOLERANCE_MM]
    pieces.append((flank_right, end_right, None, cutter))
    pieces += [(start, end, None, role) for (start, role), (end, _next) in zip(chain, chain[1:] + [(end_left, holder)])]
    pieces = [piece for piece in pieces if piece[2] is not None or math.dist(piece[0], piece[1]) > GEOMETRY_TOLERANCE_MM]
    shifted = [
        ((s[0] - deepest, s[1]), (e[0] - deepest, e[1]), None if c is None else (c[0] - deepest, c[1]), role) for s, e, c, role in pieces
    ]
    text = f"Flank angles: {lead_angle_deg:g} deg on the smaller-Z side, {trail_angle_deg:g} deg on the other"
    return shifted, (0.0, touch_off_z), text


def thread_tool(
    number: int, name: str, left_hand: bool, inside: bool, nose_radius_mm: float, flat_mm: float, included_angle_deg: float,
    lead_angle_deg: float, cutting_height_mm: float, tip_distance_mm: float, width_mm: float, length_mm: float,
) -> Tool:
    """The threading tool; the reference point is the named point `tip`."""
    pieces, touch_off, _text = thread_tool_shape(
        nose_radius_mm, flat_mm, included_angle_deg, lead_angle_deg, cutting_height_mm, tip_distance_mm, width_mm, length_mm, inside,
    )
    side = -1 if inside and not left_hand else 1  # inside the point stands out of the bar (right hand); see groove_tool_shape
    hand = -1 if left_hand and not inside else 1

    def put(pair: Pair) -> Point:
        return Point(round(side * pair[0], TOOL_SHAPE_DECIMALS) + 0.0, round(hand * pair[1], TOOL_SHAPE_DECIMALS) + 0.0)

    segments: list[ToolSegment] = []
    for start, end, centre, role in pieces:
        if centre is None:
            segments.append(ToolSegment(LineSegment(put(start), put(end)), role))
        else:
            points = [put(start), put(end), put(centre)]
            segments.append(ToolSegment(nose_arc(tuple((p.x, p.z) for p in points)), role))
    tip = put(touch_off)
    return Tool(
        number, name, ToolShape(tuple(segments)),
        points=(NamedPoint(TIP_POINT, tip.x, tip.z),),
    )
