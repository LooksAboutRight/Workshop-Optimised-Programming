import unittest

from wop.core.geometry import LineSegment, Point
from wop.core.program_model.raw_part import RawPart
from wop.core.tooling.tool import Tool, ToolSegment, ToolSegmentRole, ToolShape

from wop.core.reach import (
    CollisionKind,
    build_context,
    check_position,
    sample_segments,
    jaws_region,
)
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region

CUTTER = ToolSegmentRole.CUTTER
HOLDER = ToolSegmentRole.HOLDER
RAW_PART = RawPart("steel", 30, 50)


def rectangle_shape(x0, z0, x1, z1, roles) -> ToolShape:
    corners = [Point(x0, z0), Point(x1, z0), Point(x1, z1), Point(x0, z1), Point(x0, z0)]
    return ToolShape(
        tuple(ToolSegment(LineSegment(a, b), r) for (a, b), r in zip(zip(corners, corners[1:]), roles))
    )


# Outside tool, tip at the origin, body towards larger x and larger z.
# Edges: front (z=0) and bottom (x=0) cut; the other two edges are holder.
TOOL = Tool(1, "square", rectangle_shape(0, 0, 10, 10, [CUTTER, HOLDER, HOLDER, CUTTER]))


def stepped_shaft_part() -> "Region":
    return Region.from_points(
        [Point(0, 0), Point(10, 0), Point(10, -20), Point(15, -20), Point(15, -50), Point(0, -50)]
    )


def roughing_context():
    """Whole bar still there, flat jaws at the clamping plane."""
    return build_context(stepped_shaft_part(), stock_region(RAW_PART), jaws_region(RAW_PART))


def kinds(collisions):
    return {c.kind for c in collisions}


class PositionTests(unittest.TestCase):
    def setUp(self):
        self.context = roughing_context()

    def test_tool_beside_the_part_is_free(self):
        self.assertEqual(check_position(TOOL, Point(12, -10), self.context), [])

    def test_touching_the_part_is_free(self):
        self.assertEqual(check_position(TOOL, Point(10, -10), self.context), [])

    def test_tool_in_the_part_gouges(self):
        found = check_position(TOOL, Point(8, -5), self.context)
        self.assertIn(CollisionKind.GOUGE, kinds(found))

    def test_holder_in_the_material(self):
        found = check_position(TOOL, Point(12, -20), self.context)
        self.assertEqual(kinds(found), {CollisionKind.HOLDER_IN_MATERIAL})

    def test_cutter_edge_may_be_in_the_material(self):
        # Tip at x=12 puts the bottom (cutter) edge into the bar from x=12 to 15.
        self.assertEqual(check_position(TOOL, Point(12, -10), self.context), [])

    def test_jaws(self):
        found = check_position(TOOL, Point(20, -55), self.context)
        self.assertEqual(kinds(found), {CollisionKind.JAWS})

    def test_no_jaws_given_means_no_jaw_check(self):
        context = build_context(stepped_shaft_part(), stock_region(RAW_PART))
        self.assertEqual(check_position(TOOL, Point(20, -55), context), [])

    def test_finishing_allowance_protects_more_material(self):
        context = build_context(
            stepped_shaft_part(), stock_region(RAW_PART), allowance_mm=0.5
        )
        found = check_position(TOOL, Point(10, -10), context)
        self.assertIn(CollisionKind.GOUGE, kinds(found))



class JawsTests(unittest.TestCase):
    def test_default_jaws_are_a_plane_at_the_clamping_position(self):
        jaws = jaws_region(RAW_PART)
        self.assertEqual(jaws.bounds.max_z, RAW_PART.clamp_z_mm)
        self.assertTrue(jaws.contains_point(Point(5, -60)))
        self.assertFalse(jaws.contains_point(Point(5, -40)))

    def test_given_jaw_outline_is_used(self):
        outline = [
            LineSegment(Point(16, -50), Point(30, -50)),
            LineSegment(Point(30, -50), Point(30, -30)),
            LineSegment(Point(30, -30), Point(16, -30)),
            LineSegment(Point(16, -30), Point(16, -50)),
        ]
        jaws = jaws_region(RAW_PART, outline)
        self.assertTrue(jaws.contains_point(Point(20, -40)))
        self.assertFalse(jaws.contains_point(Point(5, -60)))


def collisions_along(path, context, step_mm=0.5):
    """(position, collision) for every collision of the tool with its tip on the positions along a straight path."""
    segments = [LineSegment(a, b) for a, b in zip(path, path[1:])]
    positions = sample_segments(segments, step_mm) if segments else list(path)
    return [(position, collision) for position in positions for collision in check_position(TOOL, position, context)]


def reach_along(outline, context, step_mm=0.5):
    """(position, collisions) for the positions along the machined part of an outline, tip on the outline."""
    return [(point, check_position(TOOL, point, context)) for point in sample_segments(list(outline), step_mm)]


class PathTests(unittest.TestCase):
    def setUp(self):
        self.context = roughing_context()

    def test_clear_path(self):
        self.assertEqual(collisions_along([Point(20, -5), Point(11, -5)], self.context), [])

    def test_path_into_the_part_reports_the_first_position(self):
        found = collisions_along([Point(20, -5), Point(8, -5)], self.context)
        self.assertTrue(found)
        point, collision = found[0]
        self.assertEqual(collision.kind, CollisionKind.GOUGE)
        self.assertLess(point.x, 10)
        self.assertGreater(point.x, 9)

    def test_single_point_path(self):
        self.assertEqual(collisions_along([Point(20, -5)], self.context), [])


class ReachTests(unittest.TestCase):
    def finishing_context(self):
        part = stepped_shaft_part()
        return build_context(part, part)

    def test_outer_profile_of_a_stepped_shaft_is_reachable(self):
        outline = [
            LineSegment(Point(10, 0), Point(10, -20)),
            LineSegment(Point(10, -20), Point(15, -20)),
            LineSegment(Point(15, -20), Point(15, -50)),
        ]
        results = reach_along(outline, self.finishing_context())
        self.assertTrue(all(not collisions for _point, collisions in results))
        self.assertGreater(len(results), len(outline))

    def test_neck_next_to_a_shoulder_is_not_reachable(self):
        # Large radius for z -20..0, small radius below. The tool body is 10 mm
        # long, so it cannot get into the neck closer than 10 mm to the shoulder.
        part = Region.from_points(
            [Point(0, 0), Point(15, 0), Point(15, -20), Point(10, -20), Point(10, -50), Point(0, -50)]
        )
        outline = [
            LineSegment(Point(10, -50), Point(10, -20)),
            LineSegment(Point(10, -20), Point(15, -20)),
            LineSegment(Point(15, -20), Point(15, 0)),
        ]
        results = reach_along(outline, build_context(part, part))
        unreachable = [point for point, collisions in results if collisions]
        reachable = [point for point, collisions in results if not collisions]
        self.assertTrue(unreachable)
        for point in unreachable:
            self.assertGreaterEqual(point.z, -30)
            self.assertLess(point.x, 15)
        self.assertTrue(any(p.is_close(Point(10, -40)) for p in reachable))
        self.assertTrue(any(p.is_close(Point(15, -10)) for p in reachable))


if __name__ == "__main__":
    unittest.main()
