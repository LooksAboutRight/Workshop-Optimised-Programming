"""Where the number of a dimension goes so that no line runs through it, in screen coordinates (pixels), without a toolkit.

`candidate_boxes` lists places for the number in order of preference. For a dimension line the number always stays on
the same side of it (to the right of a line that runs up and down, above any other) and between its two ends; it may
slide along the line to find a free place, but it never jumps to the other side or past an end: being understood is
worth more than being clear of every line. `pick_box` takes the first place that touches no line and no other number;
when none is free it takes the place that is crossed by the fewest separate lines (a line counts once, however many
pieces it is drawn in; ties go to the place nearest the middle), so it ignores as few lines as it has to.
"""

from __future__ import annotations

import math

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # left, top, width, height
Segment = tuple[Point, Point]
Line = list[Segment]  # everything that is one line to the eye: a straight piece, or an arc drawn as many short pieces

ALONG_THE_LINE = (0.5, 0.3, 0.7, 0.15, 0.85)  # where along the dimension line the number is tried, as fractions of its length
BEYOND_GAP_FACTOR = 3  # a number round a point (no line) stays this many gaps clear of it


def _support(direction: Point, width: float, height: float) -> float:
    """How far a box reaches from its centre in a direction."""
    return abs(direction[0]) * width / 2 + abs(direction[1]) * height / 2


def _box_at(centre: Point, width: float, height: float) -> Box:
    return centre[0] - width / 2, centre[1] - height / 2, width, height


def candidate_boxes(start: Point, end: Point, size: tuple[float, float], gap: float, along_a_line: bool = True) -> list[Box]:
    """Places for a number of this size next to the line from `start` to `end`: on the preferred side, along the line.
    Without a line (`along_a_line` False: an angle, a radius) round the point `start`: above, below and to both sides."""
    width, height = size
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    along = (1.0, 0.0) if length < 1e-9 else ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
    across = (-along[1], along[0])
    if across[1] > 1e-9 or (abs(across[1]) <= 1e-9 and across[0] < 0):  # the side that is up, or else to the right, first
        across = (-across[0], -across[1])
    boxes: list[Box] = []
    sides = (1,) if along_a_line else (1, -1)
    for fraction in ALONG_THE_LINE:
        point = (start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction)
        for side in sides:
            reach = gap + _support(across, width, height)
            boxes.append(_box_at((point[0] + across[0] * side * reach, point[1] + across[1] * side * reach), width, height))
        if not along_a_line:
            break  # one point: the fractions would all be the same place
    if not along_a_line:
        for direction in (along, (-along[0], -along[1])):  # and to the sides of it
            reach = gap * BEYOND_GAP_FACTOR + _support(direction, width, height)
            boxes.append(_box_at((start[0] + direction[0] * reach, start[1] + direction[1] * reach), width, height))
    return boxes


def box_hits_segment(box: Box, a: Point, b: Point) -> bool:
    """Does the line from a to b pass through the box (touching the edge does not count)?"""
    left, top, width, height = box
    right, bottom = left + width, top + height
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - left), (dx, right - a[0]), (-dy, a[1] - top), (dy, bottom - a[1])):
        if p == 0:
            if q <= 0:
                return False  # parallel to this edge and outside it (or on it)
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
    return True


def boxes_overlap(first: Box, second: Box) -> bool:
    return (
        first[0] < second[0] + second[2] and second[0] < first[0] + first[2]
        and first[1] < second[1] + second[3] and second[1] < first[1] + first[3]
    )


def crossings(box: Box, lines: list[Line], taken: list[Box]) -> int:
    """How many of the lines and of the other numbers are in the way of a number placed in this box."""
    in_the_way = sum(any(box_hits_segment(box, a, b) for a, b in line) for line in lines)
    return in_the_way + sum(boxes_overlap(box, other) for other in taken)


def pick_box(candidates: list[Box], lines: list[Line], taken: list[Box]) -> Box:
    """The first candidate with nothing in the way; if every one is crossed, the one with the fewest lines in the way
    (the first of those: the one nearest the middle)."""
    best, fewest = candidates[0], None
    for box in candidates:
        count = crossings(box, lines, taken)
        if count == 0:
            return box
        if fewest is None or count < fewest:
            best, fewest = box, count
    return best
