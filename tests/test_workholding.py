"""Workholding: types, placement of jaws and chuck, files, library, and the collision surface (WH1)."""

import unittest
from dataclasses import replace

from wop.core.files.app_settings import AppSettings, settings_from_dict, settings_to_dict
from wop.core.constants import CHUCK_FACE_POINT, JAWS_MOUNT_POINT
from wop.core.geometry import Point
from wop.core.program_model.raw_part import RawPart
from wop.core.lathe.workholding import (
    CHUCK_KIND,
    JAWS_KIND,
    GripMode,
    Workholding,
    WorkholdingError,
    WorkholdingItem,
    library_find,
    library_with,
    library_without,
    place_workholding,
    placement_target,
    workholding_problem,
    _z_range,
)
from wop.core.files.workholding_io import item_from_dict, item_to_dict, workholding_from_dict, workholding_to_dict
from wop.core.workholding_types import WORKHOLDING_TYPES, example_item

BAR = RawPart("Mild steel", 50, 40)  # radius 25, clamping plane at z = -40, runs through
SHORT = RawPart("Mild steel", 50, 40, length_mm=52)  # stock ends 12 mm behind the clamping plane
TUBE = RawPart("Mild steel", 60, 40, inner_diameter_mm=40)


def jaws() -> WorkholdingItem:
    return example_item(JAWS_KIND, "Soft jaws")


def chuck() -> WorkholdingItem:
    return example_item(CHUCK_KIND, "Chuck 3-jaw")


class TypeTests(unittest.TestCase):
    def test_both_types_are_registered_and_make_valid_items(self):
        self.assertEqual({t.type_name for t in WORKHOLDING_TYPES.types()}, {JAWS_KIND, CHUCK_KIND})
        self.assertTrue(jaws().outline.is_closed)
        self.assertIsNotNone(jaws().point("step 1"))
        self.assertIsNotNone(chuck().point(CHUCK_FACE_POINT))

    def test_item_checks(self):
        item = jaws()
        with self.assertRaises(WorkholdingError):
            replace(item, jaw_count=1)
        with self.assertRaises(WorkholdingError):
            replace(item, jaw_width_deg=130)  # 3 x 130 is more than a full turn
        with self.assertRaises(WorkholdingError):
            replace(item, name=" ")


class PlacementTests(unittest.TestCase):
    def test_target_on_a_bar_that_runs_through(self):
        self.assertEqual(placement_target(BAR, GripMode.OUTSIDE), Point(25, -40))

    def test_target_when_the_stock_ends_inside_is_its_back_end(self):
        self.assertEqual(placement_target(SHORT, GripMode.OUTSIDE), Point(25, -52))

    def test_inside_grip_needs_a_tube_and_uses_the_bore(self):
        with self.assertRaises(WorkholdingError):
            placement_target(BAR, GripMode.INSIDE)
        self.assertEqual(placement_target(TUBE, GripMode.INSIDE), Point(20, -40))

    def test_jaw_step_corner_lands_on_the_part(self):
        # "step 1" is the corner at (25, -12) of the example jaws: shoulder 12 mm behind the jaw front.
        placed = place_workholding(SHORT, Workholding(jaws(), None, "step 1"))
        corner = next(p for p in placed.jaws_points if p.name == "step 1")
        self.assertEqual((corner.x, corner.z), (25, -52))
        # the jaw front face is then exactly at the clamping plane of the Setup (stick-out 40, inside 12)
        self.assertAlmostEqual(_z_range(placed.jaws)[1], SHORT.clamp_z_mm)

    def test_smaller_part_closes_the_jaws_radially(self):
        small = RawPart("Mild steel", 30, 40, length_mm=64)
        placed = place_workholding(small, Workholding(jaws(), None, "step 2"))
        corner = next(p for p in placed.jaws_points if p.name == "step 2")
        self.assertEqual((corner.x, corner.z), (15, -64))

    def test_inside_grip_on_a_tube(self):
        placed = place_workholding(TUBE, Workholding(jaws(), None, "step 1", GripMode.INSIDE))
        corner = next(p for p in placed.jaws_points if p.name == "step 1")
        self.assertEqual(corner.x, 20)

    def test_chuck_meets_the_jaws_in_z_only(self):
        placed = place_workholding(SHORT, Workholding(jaws(), chuck(), "step 1"))
        mount = next(p for p in placed.jaws_points if p.name == JAWS_MOUNT_POINT)
        face = next(p for p in placed.chuck_points if p.name == CHUCK_FACE_POINT)
        self.assertEqual(face.z, mount.z)
        self.assertEqual(face.x, 20)  # not moved radially

    def test_chuck_alone_has_its_face_at_the_clamping_plane(self):
        placed = place_workholding(BAR, Workholding(None, chuck()))
        face = next(p for p in placed.chuck_points if p.name == CHUCK_FACE_POINT)
        self.assertEqual(face.z, BAR.clamp_z_mm)

    def test_no_anchor_leaves_the_jaws_where_they_are_drawn(self):
        placed = place_workholding(BAR, Workholding(jaws(), None, ""))
        self.assertEqual(placed.jaws, jaws().outline.segments)

    def test_problems_are_named(self):
        self.assertIn("step 9", workholding_problem(BAR, Workholding(jaws(), None, "step 9")))
        self.assertIn("tube", workholding_problem(BAR, Workholding(jaws(), None, "step 1", GripMode.INSIDE)))
        self.assertEqual(workholding_problem(BAR, None), "")
        self.assertEqual(place_workholding(BAR, Workholding()).is_empty, True)


class FileTests(unittest.TestCase):
    def test_item_and_workholding_round_trip(self):
        item = replace(jaws(), jaw_count=4, jaw_width_deg=40)
        self.assertEqual(item_from_dict(item_to_dict(item)), item)
        holding = Workholding(item, chuck(), "step 2", GripMode.INSIDE)
        self.assertEqual(workholding_from_dict(workholding_to_dict(holding)), holding)

    def test_damaged_data_is_an_error(self):
        data = item_to_dict(jaws())
        with self.assertRaises(WorkholdingError):
            item_from_dict({**data, "format": 99})
        with self.assertRaises(WorkholdingError):
            item_from_dict({"format": data["format"]})

    def test_library_helpers(self):
        a, b = jaws(), chuck()
        items = library_with(library_with((), a), b)
        replaced = library_with(items, replace(a, name="SOFT JAWS", jaw_count=2))
        self.assertEqual(len(replaced), 2)  # same name, not case sensitive: replaced
        self.assertEqual(library_find(replaced, "soft jaws").jaw_count, 2)
        self.assertEqual(library_without(replaced, "Chuck 3-jaw"), (replaced[0],))

    def test_settings_keep_the_library_and_old_files_stay_as_they_were(self):
        self.assertNotIn("workholding", settings_to_dict(AppSettings()))
        settings = AppSettings(workholding=(jaws(), chuck()))
        self.assertEqual(settings_from_dict(settings_to_dict(settings, include_content=True)), settings)
        data = settings_to_dict(settings, include_content=True)
        data["workholding"] = data["workholding"] + [data["workholding"][0]]
        from wop.core.files.app_settings import SettingsError

        with self.assertRaises(SettingsError):
            settings_from_dict(data)


class CollisionSurfaceTests(unittest.TestCase):
    def test_none_is_the_flat_clamping_plane(self):
        from wop.core.reach import jaws_region, program_jaws

        region, problem = program_jaws(BAR, None)
        self.assertEqual(problem, "")
        self.assertEqual(region.bounds, jaws_region(BAR).bounds)

    def test_jaws_and_chuck_replace_the_plane(self):
        from wop.core.reach import program_jaws

        region, problem = program_jaws(SHORT, Workholding(jaws(), chuck(), "step 1"))
        self.assertEqual(problem, "")
        self.assertTrue(region.contains_point(Point(35, -45)))  # inside the jaw body
        self.assertTrue(region.contains_point(Point(60, -100)))  # inside the chuck body
        self.assertFalse(region.contains_point(Point(60, -20)))  # beside the stock, in front of the jaws

    def test_a_workholding_that_cannot_be_placed_falls_back_and_says_so(self):
        from wop.core.reach import jaws_region, program_jaws

        region, problem = program_jaws(BAR, Workholding(jaws(), None, "step 1", GripMode.INSIDE))
        self.assertIn("flat clamping plane", problem)
        self.assertEqual(region.bounds, jaws_region(BAR).bounds)

    def test_project_file_and_plan_carry_the_workholding(self):
        from wop.core.files.project_io import project_from_json, project_to_json
        from wop.core.program_model.program import plan_program
        from tests.reference_program import reference_program
        from wop.core.program_model.project import Project

        project = Project(reference_program())
        plain = project_to_json(project)
        self.assertNotIn("workholding", plain)  # no workholding: the file looks as before
        holding = Workholding(jaws(), chuck(), "step 1")
        with_holding = replace(project, program=replace(project.program, workholding=holding))
        text = project_to_json(with_holding)
        self.assertEqual(project_from_json(text).program.workholding, holding)
        self.assertEqual(project_to_json(project_from_json(text)), text)
        broken = replace(holding, anchor="nowhere")
        plan = plan_program(replace(project.program, workholding=broken))
        self.assertTrue(any("nowhere" in message for message in plan.messages))


if __name__ == "__main__":
    unittest.main()
