"""Move the tool along a line, cut what it passes, stop before a collision."""

from __future__ import annotations

from ..geometry import LineSegment, Point
from ..reach import CollisionContext, check_prepared, far_side_tip, jaws_region, placed_shrunk, prepare_tool, sample_segments
from ..geometry.region import Region
from .base import BlockContext
from ..constants import CONTACT_SEARCH_STEPS, PATH_CHECK_STEP_MM, STRAIGHT_WAY_STEP_MM


class Sweeper:
    """Follows the tool through the material of one block.

    `keep` is what must stay. `current` is the material as it is while the block
    runs: every position the tool reaches removes the tool body's area from it.
    """

    def __init__(self, context: BlockContext, keep: Region) -> None:
        self.keep = keep
        self.current = context.residual
        self._prepared = prepare_tool(context.tool)
        self._jaws = context.jaws if context.jaws is not None else jaws_region(context.raw_part, None)

    def collides(self, point: Point) -> bool:
        return bool(
            check_prepared(self._prepared, point, CollisionContext(self.keep, self.current, self._jaws))
        )

    def cut_line(self, start: Point, end: Point) -> list[Point]:
        """The positions from start towards end that the tool can reach (then it stops)."""
        safe: list[Point] = []
        for point in sample_segments([LineSegment(start, end)], PATH_CHECK_STEP_MM):
            if self.collides(point):
                break
            self.current = self.current.difference(self._prepared.body.translated(point.x, point.z))
            safe.append(point)
        return safe

    def follow_line(self, start: Point, end: Point) -> tuple[list[Point], Point | None]:
        """The positions from start to end, all of them: the tool goes the whole way as asked and cuts what its body
        passes (the whole way between two positions). Returns them with the first position where the tool collides, or
        None. The block writes the way as drawn; the checks of the program report the collision."""
        points = sample_segments([LineSegment(start, end)], PATH_CHECK_STEP_MM)
        first: Point | None = None
        previous: Point | None = None
        for point in points:
            if first is None and self.collides(point):
                first = point
            if previous is None:
                cut_away = self._prepared.body.translated(point.x, point.z)
            else:
                cut_away = self._prepared.body.swept(point.x - previous.x, point.z - previous.z).translated(previous.x, previous.z)
            self.current = self.current.difference(cut_away)
            previous = point
        return points, first

    def air_line(self, start: Point, end: Point) -> Point:
        """How far the tool can go from start towards end before its body touches material: the last position
        in the air (the end itself when it never touches). The tool does not cut on the way."""
        previous = start
        for point in sample_segments([LineSegment(start, end)], PATH_CHECK_STEP_MM):
            if not self._touches(point):
                previous = point
                continue
            low = previous
            high = point
            for _ in range(CONTACT_SEARCH_STEPS):  # halve the gap between the last free and the first touching position
                middle = Point((low.x + high.x) / 2, (low.z + high.z) / 2)
                if self._touches(middle):
                    high = middle
                else:
                    low = middle
            return low
        return end

    def _touches(self, point: Point) -> bool:
        if placed_shrunk(self._prepared, point).overlaps(self.current):
            return True
        far = far_side_tip(self._prepared, point)  # a tool that reaches past the axis touches the far side too
        return far is not None and placed_shrunk(self._prepared.mirror, far).overlaps(self.current)

    def line_is_free(self, a: Point, b: Point) -> bool:
        """True when no material (as it is now) is on the straight line from a to b (tool tip only)."""
        steps = max(1, int(a.distance_to(b) / STRAIGHT_WAY_STEP_MM) + 1)
        return not any(
            self.current.strictly_contains_point(Point(a.x + (b.x - a.x) * i / steps, a.z + (b.z - a.z) * i / steps))
            for i in range(steps + 1)
        )
