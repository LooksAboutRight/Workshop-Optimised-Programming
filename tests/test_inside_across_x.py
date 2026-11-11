"""Inside turning across X (ALONG_X) on a solid bar: the step down from one plane to the next goes into material, so it is a
feed move (the tool must cut at the centre), never a rapid. A bore and all other cases keep their rapids.
`tests/data/projects/inside_across_x_solid_bar.wop.json` is the user's project 'rapid problem'; the contour block uses the
same planner and has its own case."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from wop.adapters.project_files import load_project
from wop.core.program_model.operations import LinearMove, Rapid
from wop.core.program_model.program import plan_program
from wop.core.verify import FindingKind, plain_moves, verify_plan

PROJECT = Path(__file__).parent / "data" / "projects" / "inside_across_x_solid_bar.wop.json"
TOLERANCE = 1e-3
NEAR_AXIS_MM = 0.5  # the line starts a little past the axis (the analytic planner: the far side of the bar is cut too)
BORE_RADIUS_MM = 10.0


def planned(data: dict):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "case.wop.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        program = load_project(path).program
    return program, plan_program(program)


def moves(plan, block=0):
    return [move for operation in plan.blocks[block].operations for move in plain_moves(operation) if hasattr(move, "end")]


def plunges_on_the_axis(plan):
    """The feed moves down in Z near the axis (the way into a plane of a solid bar), longer than a few hundredths (the pass along the
    bottom begins with one of 0.01 mm)."""
    everything = moves(plan)
    return [
        m for before, m in zip(everything, everything[1:])
        if isinstance(m, LinearMove) and abs(m.end.x) <= NEAR_AXIS_MM and abs(m.end.x - before.end.x) <= TOLERANCE and m.end.z < before.end.z - 0.05
    ]


def rapids_into_uncut_material_on_the_axis(plan):
    """Rapids on the axis that end deeper (smaller Z) than any cut has been so far: they go into uncut material."""
    deepest = 0.0  # the front face of the material
    found = []
    for move in moves(plan):
        if isinstance(move, LinearMove):
            deepest = min(deepest, move.end.z)
        elif isinstance(move, Rapid) and abs(move.end.x) <= NEAR_AXIS_MM and move.end.z < deepest - TOLERANCE:
            found.append(move)
    return found


def contour_variant(data: dict) -> dict:
    """The same bar with a turning contour block inside across X: a blind bore of radius 20 and depth 20."""
    data = copy.deepcopy(data)
    contour = {
        "format": 1, "id": "bore", "name": "Bore",
        "segments": [
            {"type": "line", "start": [20.0, 0.0], "end": [20.0, -20.0]},
            {"type": "line", "start": [20.0, -20.0], "end": [0.0, -20.0]},
        ],
        "definition": {
            "start": [20.0, 0.0],
            "steps": [
                {"type": "line", "end": [20.0, -20.0], "corner": {"kind": "none", "size_mm": 0}},
                {"type": "line", "end": [0.0, -20.0], "corner": {"kind": "none", "size_mm": 0}},
            ],
        },
    }
    block = {
        "type": "turning_contour",
        "parameters": {
            "block_id": "b2", "tool_number": 2, "spindle": data["blocks"][0]["parameters"]["spindle"], "coolant": "NONE",
            "name": "Bore", "comment": "", "contour_id": "bore", "side": "INSIDE", "feed_mm_per_rev": 0.2,
            "depth_of_cut_mm": 2.0, "pass_direction": "ALONG_X", "finish_allowance_mm": 0.2, "finish_pass": True,
            "cutter_compensation": False, "finish_feed_mm_per_rev": 0.1, "finish_spindle_value": 1000,
            "plunge_feed_mm_per_rev": 0.07, "plunge_depth_of_cut_mm": 1.0, "min_free_angle_deg": 5,
        },
    }
    data["contours"] = [contour]
    data["blocks"] = [block]
    return data


class InsideAcrossXTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(PROJECT.read_text(encoding="utf-8"))

    def test_the_project_has_no_finding_any_more(self):
        program, plan = planned(self.data)
        self.assertEqual(plan.left_out, ())
        findings = verify_plan(program, plan)
        self.assertEqual([f for f in findings if f.kind is FindingKind.RAPID_IN_MATERIAL], [])
        self.assertEqual(findings, [])

    def test_the_way_down_to_every_plane_is_a_feed_move_with_the_feed_of_the_block(self):
        _program, plan = planned(self.data)
        self.assertEqual(rapids_into_uncut_material_on_the_axis(plan), [])
        feed = self.data["blocks"][0]["parameters"]["feed_mm_per_rev"]
        plunges = plunges_on_the_axis(plan)
        self.assertGreaterEqual(len(plunges), 20)  # one plunge per plane
        self.assertTrue(all(abs(m.feed_mm_per_rev - feed) < TOLERANCE for m in plunges))

    def test_the_first_plane_starts_with_a_feed_from_just_above_the_front_face(self):
        program, plan = planned(self.data)
        everything = moves(plan)
        first = next(m for m in everything if isinstance(m, LinearMove))
        before = everything[everything.index(first) - 1]
        self.assertIsInstance(before, Rapid)
        self.assertGreater(before.end.z, TOLERANCE)  # the rapid stops in front of the face

    def test_a_bore_keeps_its_rapids(self):
        data = copy.deepcopy(self.data)
        data["raw_part"]["inner_diameter_mm"] = 2 * BORE_RADIUS_MM  # a hole through the bar: the way down is air
        program, plan = planned(data)
        everything = moves(plan)
        plunges = [  # feed moves down in Z in the bore, longer than the last stretch to the plane (X12: under a clearance at feed)
            m for before, m in zip(everything, everything[1:])
            if isinstance(m, LinearMove) and m.end.x < BORE_RADIUS_MM and abs(m.end.x - before.end.x) <= TOLERANCE and before.end.z - m.end.z > 0.05
        ]
        self.assertEqual(plunges, [])
        self.assertEqual([f for f in verify_plan(program, plan) if f.kind is FindingKind.RAPID_IN_MATERIAL], [])

    def test_along_Z_is_not_changed(self):
        data = copy.deepcopy(self.data)
        data["blocks"][0]["parameters"]["pass_direction"] = "ALONG_Z"
        _program, plan = planned(data)
        self.assertEqual([m for m in moves(plan) if isinstance(m, LinearMove) and abs(m.end.x) <= TOLERANCE], [])

    def test_the_contour_block_plunges_with_its_plunge_feed(self):
        data = contour_variant(self.data)
        program, plan = planned(data)
        self.assertEqual(plan.left_out, ())
        self.assertEqual(rapids_into_uncut_material_on_the_axis(plan), [])
        plunges = plunges_on_the_axis(plan)
        self.assertTrue(plunges)
        self.assertTrue(all(abs(m.feed_mm_per_rev - 0.07) < TOLERANCE for m in plunges))
        self.assertEqual([f for f in verify_plan(program, plan) if f.kind is FindingKind.RAPID_IN_MATERIAL], [])


if __name__ == "__main__":
    unittest.main()
