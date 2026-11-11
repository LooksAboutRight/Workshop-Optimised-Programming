"""The check of a move as a whole (the area the tool sweeps).

`verify_plan` looks at a straight move as one swept area first and follows it in steps only where the tool may touch something. (The
check that followed every move in steps was removed on 2026-10-23: the program never used it, and it reported false alarms.)
"""

import unittest
from pathlib import Path

from tests.helpers import planned, simple_tool
from wop.core.geometry import LineSegment, Point

ROOT = Path(__file__).resolve().parent.parent


class SweptAreaTests(unittest.TestCase):
    def test_the_area_a_square_sweeps(self):
        from wop.core.geometry.region import Region

        square = Region.rectangle(0, 0, 1, 1)
        self.assertAlmostEqual(square.swept(3, 0).area, 4)
        self.assertAlmostEqual(square.swept(3, 4).area, 8)  # the square, and the strip it draws: 3 + 4 wide edges
        self.assertAlmostEqual(square.swept(0, 0).area, 1)

    def test_an_l_shape_sweeps_its_hollow_too(self):
        from wop.core.geometry.region import Region

        shape = Region.from_points([Point(0, 0), Point(2, 0), Point(2, 1), Point(1, 1), Point(1, 2), Point(0, 2)])
        self.assertAlmostEqual(shape.swept(0, -1).area, shape.area + 2)  # the two bottom edges draw 2 x 1

    def test_edges_that_move_along_themselves_still_have_an_area(self):
        import numpy as np

        from wop.core.geometry.region import Region

        a, b = np.array([[0.0, 0.0]]), np.array([[0.0, 2.0]])
        along = Region.swept_edges(a, b, 0, 1, 0.01)
        across = Region.swept_edges(a, b, 3, 0, 0.01)
        self.assertGreater(along.area, 0)
        self.assertGreater(across.area, 6)
        self.assertTrue(Region.swept_edges(np.zeros((0, 2)), np.zeros((0, 2)), 1, 1, 0.01).is_empty)


class HolderEdgeTests(unittest.TestCase):
    def test_the_edges_of_a_holder_and_the_way_they_face(self):
        from wop.core.reach import prepare_tool
        from wop.core.verify import _HolderEdges

        edges = _HolderEdges(prepare_tool(simple_tool(1, side=1)))
        self.assertEqual(len(edges.starts), 2)  # the side and the end of the square holder
        self.assertEqual([tuple(map(float, n)) for n in edges.normals], [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(list(edges.facing(1, 0)), [True, False])
        self.assertEqual(list(edges.facing(0, 1)), [False, True])
        self.assertEqual(list(edges.facing(0, -1)), [False, False])  # into the material: nothing faces that way
        self.assertEqual(list(edges.facing(-1, 0)), [False, False])

    def test_a_tool_on_the_other_side_of_the_axis_faces_the_other_way(self):
        from wop.core.reach import prepare_tool
        from wop.core.verify import _HolderEdges

        edges = _HolderEdges(prepare_tool(simple_tool(2, side=-1)))
        self.assertEqual(list(edges.facing(-1, 0)), [True, False])


class SweepCheckTests(unittest.TestCase):
    def setUp(self):
        from wop.core.reach import prepare_tool
        from wop.core.geometry.region import Region
        from wop.core.verify import _HolderEdges

        self.Region = Region
        self.prepared = prepare_tool(simple_tool(1, side=1))  # 8 wide, 12 high, tip at the origin
        self.edges = (_HolderEdges(self.prepared), None)
        self.nothing = Region.empty()

    def clean(self, start, end, rapid=True, protected=None, jaws=None, current=None):
        from wop.core.verify import _sweep_is_clean

        protected = (protected or self.nothing).shrunk_for_collision()
        jaws = None if jaws is None else jaws.shrunk_for_collision()
        return _sweep_is_clean(self.prepared, self.edges, start, end, rapid, protected, jaws, current or self.nothing, -1000)

    def test_a_move_through_the_air_is_clean(self):
        self.assertTrue(self.clean(Point(20, 5), Point(20, -20)))
        self.assertTrue(self.clean(Point(20, 5), Point(20, -20), rapid=False))

    def test_a_move_across_the_finished_part_is_not(self):
        part = self.Region.rectangle(5, -10, 30, 0)
        self.assertFalse(self.clean(Point(40, -5), Point(0, -5), protected=part))  # the tool passes through it
        self.assertTrue(self.clean(Point(40, -5), Point(0, -5)))
        self.assertTrue(self.clean(Point(40, 5), Point(0, 5), protected=part))  # above it

    def test_the_jaws_are_noticed(self):
        jaws = self.Region.rectangle(0, -30, 40, -20)
        self.assertFalse(self.clean(Point(20, 0), Point(20, -25), jaws=jaws))

    def test_a_rapid_move_through_material_is_noticed(self):
        material = self.Region.rectangle(0, -10, 15, 0)
        self.assertFalse(self.clean(Point(30, -5), Point(0, -5), current=material))

    def test_a_cutting_move_through_material_with_the_holder_in_the_air_is_clean(self):
        material = self.Region.rectangle(0, -20, 10, 0)
        # the tool body (8 wide, tip down) cuts the material at radius 2 to 10 and the holder is above it, in the air
        self.assertTrue(self.clean(Point(2, 5), Point(2, -15), rapid=False, current=material))

    def test_a_holder_edge_that_runs_into_material_ahead_of_it_is_noticed(self):
        wall = self.Region.rectangle(10, 0, 12, 20)  # above the cutter, beside the holder: the holder side runs into it
        self.assertFalse(self.clean(Point(0, 3), Point(6, 3), rapid=False, current=wall))

    def test_a_thin_obstacle_between_two_steps_is_found_by_the_sweep_only(self):
        from wop.core.geometry import Point as P
        from wop.core.reach import CollisionContext, check_prepared, prepare_tool, sample_segments
        from wop.core.tooling.tool import Tool, ToolSegment, ToolSegmentRole, ToolShape
        from wop.core.verify import _HolderEdges, _first_contact, _sweep_is_clean, _sweep_verdict

        width = 0.3  # a blade thinner than the step
        corners = [P(0, 0), P(width, 0), P(width, 12), P(0, 12), P(0, 0)]
        roles = [ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER, ToolSegmentRole.HOLDER, ToolSegmentRole.CUTTER]
        pieces = tuple(ToolSegment(LineSegment(a, b), role) for (a, b), role in zip(zip(corners, corners[1:]), roles))
        prepared = prepare_tool(Tool(1, "blade", ToolShape(pieces)))
        rib = self.Region.rectangle(2.35, -5, 2.40, 20)  # 0.05 thick, between the steps at 2.0 and 2.5
        context = CollisionContext(rib, self.nothing, None)
        start, end = P(0, 5), P(5, 5)
        steps = sample_segments([LineSegment(start, end)], 0.5)
        self.assertEqual([c for point in steps for c in check_prepared(prepared, point, context)], [])  # the steps miss it
        edges = (_HolderEdges(prepared), None)
        self.assertFalse(_sweep_is_clean(prepared, edges, start, end, True, rib.shrunk_for_collision(), None, self.nothing, -1000))
        proved, doubt = _sweep_verdict(prepared, edges, start, end, True, rib.shrunk_for_collision(), None, self.nothing, -1000)
        self.assertEqual([contact.kind.name for contact in proved], ["GOUGE"])
        point = _first_contact(proved[0], start, end)  # the blade touches the rib when its right edge reaches x = 2.35
        self.assertAlmostEqual(point.x, 2.35 - width + 0.005, delta=0.01)
        self.assertAlmostEqual(point.z, 5)


class ProjectTests(unittest.TestCase):
    def test_the_first_step_of_a_drill_plunge_is_not_reported(self):
        from wop.core.verify import verify_plan
        from wop.ui.app_model import AppModel

        model = AppModel()
        model.add_block("drilling")  # tool 1, a plain stub of 8 x 12 mm: the steps compared it with the material the cutter had not removed yet
        self.assertEqual(verify_plan(model.program, planned(model.program)), [])

    def test_the_collision_of_the_demo_is_found(self):
        from wop.core.files.project_io import project_from_json
        from wop.core.verify import verify_plan

        program = project_from_json((ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json").read_text(encoding="utf-8")).program
        self.assertIn("JAWS", {finding.kind.name for finding in verify_plan(program, planned(program))})  # the tool runs into the jaws


if __name__ == "__main__":
    unittest.main()
