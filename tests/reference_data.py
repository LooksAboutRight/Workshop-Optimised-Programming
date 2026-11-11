"""Small reference data set with known results, shared by the tests.

Coordinates are (x = radius, z = axial position) in millimetres.
"""

import math

from wop.core.contour import Contour, ContourDefinition, LineStep, fillet
from wop.core.contour_solver import build_contour
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment

# --- Stepped shaft: radius 10 for 20 mm, radius 15 for 30 mm (half section) --
STEPPED_SHAFT_AREA_MM2 = 10 * 20 + 15 * 30
STEPPED_SHAFT_PERIMETER_MM = 10 + 20 + 5 + 30 + 15 + 50


def stepped_shaft_profile() -> list[Segment]:
    corners = [
        Point(0, 0),
        Point(10, 0),
        Point(10, -20),
        Point(15, -20),
        Point(15, -50),
        Point(0, -50),
        Point(0, 0),
    ]
    return [LineSegment(a, b) for a, b in zip(corners, corners[1:])]


# --- Rounded end: radius 10, length 20, R3 round on the outer corner at z=0 --
ROUND_RADIUS_MM = 3
ROUNDED_END_AREA_MM2 = 10 * 20 - (ROUND_RADIUS_MM**2 - math.pi * ROUND_RADIUS_MM**2 / 4)
ROUNDED_END_PERIMETER_MM = 7 + math.pi * ROUND_RADIUS_MM / 2 + 17 + 10 + 20


def rounded_end_profile() -> list[Segment]:
    return [
        LineSegment(Point(0, 0), Point(7, 0)),
        ArcSegment(Point(7, 0), Point(10, -3), Point(7, -3), ArcDirection.CW),
        LineSegment(Point(10, -3), Point(10, -20)),
        LineSegment(Point(10, -20), Point(0, -20)),
        LineSegment(Point(0, -20), Point(0, 0)),
    ]


# --- Five lines and three arcs (requirement C1): open contour, three R2 rounds --
FIVE_LINES_THREE_ARCS_LINE_COUNT = 5
FIVE_LINES_THREE_ARCS_ARC_COUNT = 3


def five_lines_three_arcs_definition() -> ContourDefinition:
    return ContourDefinition(
        Point(0, 0),
        (
            LineStep(Point(10, 0), fillet(2)),
            LineStep(Point(10, -20), fillet(2)),
            LineStep(Point(20, -30), fillet(2)),
            LineStep(Point(20, -50)),
            LineStep(Point(0, -50)),
        ),
    )


def five_lines_three_arcs_contour() -> Contour:
    return build_contour("ref-5l3a", "five lines three arcs", five_lines_three_arcs_definition())
