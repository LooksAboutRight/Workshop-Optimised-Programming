"""Reflections of the plane (x -> -x, z -> -z, x <-> z) applied to points, pieces and loops. Every arc turns the other way round; a
reflected loop is travelled the other way, so it keeps its sense of turning."""

from __future__ import annotations

from .primitives import ArcDirection, ArcSegment, LineSegment, Point, Segment


def other_way(direction: ArcDirection) -> ArcDirection:
    return ArcDirection.CW if direction is ArcDirection.CCW else ArcDirection.CCW


def turned_round(piece: Segment) -> Segment:
    if isinstance(piece, LineSegment):
        return LineSegment(piece.end, piece.start)
    return ArcSegment(piece.end, piece.start, piece.center, other_way(piece.direction))


class Reflection:
    """One reflection of the plane (it is its own inverse: applied twice it gives the original)."""

    def __init__(self, swap: bool, in_x: bool = False) -> None:
        self.swap = swap  # True: x <-> z
        self.in_x = in_x  # True: x -> -x; both False: z -> -z

    def point(self, at: Point) -> Point:
        if self.swap:
            return Point(at.z, at.x)
        return Point(-at.x, at.z) if self.in_x else Point(at.x, -at.z)

    def segment(self, piece: Segment) -> Segment:
        """The piece reflected, the same way round (from its reflected start to its reflected end)."""
        if isinstance(piece, LineSegment):
            return LineSegment(self.point(piece.start), self.point(piece.end))
        return ArcSegment(self.point(piece.start), self.point(piece.end), self.point(piece.center), other_way(piece.direction))

    def moves(self, pieces) -> tuple[Segment, ...]:
        """Moves of the tool reflected: the same order, each one reflected."""
        return tuple(self.segment(piece) for piece in pieces)

    def path(self, pieces: list[Segment]) -> list[Segment]:
        """A contour reflected so it keeps its order of travel (from the front to the chuck): travelled the other way, but the same way
        under x -> -x (Z stays as it is)."""
        if self.in_x:
            return list(self.moves(pieces))
        return [turned_round(self.segment(piece)) for piece in reversed(pieces)]

    def loop(self, ring: tuple[Segment, ...]) -> tuple[Segment, ...]:
        """A closed loop reflected and travelled the other way: its sense of turning is kept (a counter-clockwise loop stays counter-clockwise)."""
        return tuple(turned_round(self.segment(piece)) for piece in reversed(ring))

    def loops(self, rings) -> list[tuple[Segment, ...]]:
        return [self.loop(ring) for ring in rings]


ACROSS_AXIS = Reflection(False, True)  # x -> -x: the far side of a round part
ACROSS_FACE = Reflection(False)  # z -> -z: front and chuck side change places
