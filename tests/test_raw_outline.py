import unittest
from dataclasses import replace

from wop.core.analytic.material import stock_chains
from wop.core.constants import CLAMP_PLANE_POINT
from wop.core.files.project_io import project_from_dict, project_to_dict
from wop.core.program_model.raw_outline import raw_part_from_outline, starting_sketch
from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.stock import stock_region
from wop.core.sketch.model import Sketch
from wop.core.sketch.modes import RAW_PART, contour_from_sketch, problems
from wop.core.sketch.solver import solve
from wop.core.program_model.project import Project


def _profile(points, clamp_index=None, closed=False):
    sketch = Sketch()
    ids = [sketch.add_point(x, z) for x, z in points]
    count = len(ids) if closed else len(ids) - 1
    for index in range(count):
        sketch.add_line(ids[index], ids[(index + 1) % len(ids)])
    if clamp_index is not None:
        sketch.label_point(ids[clamp_index], CLAMP_PLANE_POINT)
    return sketch


# a shaft: 10 radius from the front (z 0) to z -20, then 15 radius to z -50; the jaws begin at z -30
SHAFT = [(0, 0), (10, 0), (10, -20), (15, -20), (15, -30), (15, -50), (0, -50)]


def _shaft():
    return _profile(SHAFT, clamp_index=4)


class RuleTests(unittest.TestCase):
    def test_a_solid_profile_that_starts_and_ends_on_the_axis_is_a_raw_part(self):
        self.assertEqual(problems(_shaft(), RAW_PART), [])

    def test_an_open_profile_must_start_and_end_on_the_axis(self):
        sketch = _profile([(2, 0), (10, 0), (10, -30), (0, -30)], clamp_index=2)
        found = problems(sketch, RAW_PART)
        self.assertTrue(any("starts" in p and "spindle axis" in p for p in found))
        sketch = _profile([(0, 0), (10, 0), (10, -30), (2, -30)], clamp_index=2)
        self.assertTrue(any("ends" in p for p in problems(sketch, RAW_PART)))

    def test_a_closed_loop_above_the_axis_is_a_hollow_part(self):
        sketch = _profile([(5, 0), (10, 0), (10, -20), (10, -40), (5, -40)], clamp_index=2, closed=True)
        self.assertEqual(problems(sketch, RAW_PART), [])

    def test_a_closed_loop_that_touches_the_axis_is_a_solid_part(self):
        sketch = _profile([(0, 0), (10, 0), (10, -20), (10, -40), (0, -40)], clamp_index=2, closed=True)
        self.assertEqual(problems(sketch, RAW_PART), [])

    def test_a_loop_below_the_axis_is_refused(self):
        sketch = _profile([(-5, 0), (10, 0), (10, -20), (10, -40), (-5, -40)], clamp_index=2, closed=True)
        self.assertTrue(problems(sketch, RAW_PART))

    def test_the_clamping_plane_must_be_named_and_inside_the_piece(self):
        self.assertTrue(any("Clamping plane" in p for p in problems(_profile(SHAFT), RAW_PART)))
        sketch = _profile([(0, 0), (10, 0), (10, -40), (0, -40)], clamp_index=1)  # the front corner: no stock outside the jaws
        self.assertTrue(any("inside the length" in p for p in problems(sketch, RAW_PART)))

    def test_a_profile_that_crosses_itself_is_refused(self):
        sketch = _profile([(0, 0), (10, 0), (10, -30), (5, -30), (5, 5), (0, 5)], clamp_index=2)
        self.assertTrue(any("itself" in p for p in problems(sketch, RAW_PART)))


class StockTests(unittest.TestCase):
    def setUp(self):
        self.outline = contour_from_sketch(_shaft(), RAW_PART, "raw", "Raw part")
        self.raw = raw_part_from_outline("steel", self.outline)

    def test_the_numbers_come_from_the_drawing(self):
        self.assertEqual(self.raw.outer_diameter_mm, 30)
        self.assertEqual(self.raw.inner_diameter_mm, 0)
        self.assertEqual(self.raw.front_z_mm, 0)
        self.assertEqual(self.raw.length_outside_mm, 30)  # from the front to the clamping plane
        self.assertEqual(self.raw.length_mm, 50)
        self.assertEqual(self.raw.clamp_z_mm, -30)

    def test_only_the_part_outside_the_jaws_is_stock(self):
        # a half section: radius 10 for 20 mm, radius 15 for the 10 mm up to the jaws
        self.assertAlmostEqual(stock_region(self.raw).area, 10 * 20 + 15 * 10)

    def test_the_exact_chains_describe_the_same_area(self):
        loops = stock_chains(self.raw)
        self.assertEqual(len(loops), 1)
        self.assertEqual(len(loops[0]), 6)  # front, step, shoulder, wall, jaws, axis: exact lines

    def test_a_hollow_part_has_a_bore(self):
        sketch = _profile([(5, 0), (10, 0), (10, -20), (10, -40), (5, -40)], clamp_index=2, closed=True)
        raw = raw_part_from_outline("steel", contour_from_sketch(sketch, RAW_PART, "raw", "Raw part"))
        self.assertEqual((raw.outer_diameter_mm, raw.inner_diameter_mm), (20, 10))
        self.assertAlmostEqual(stock_region(raw).area, 5 * 20)

    def test_a_raw_part_without_a_drawing_is_the_same_as_before(self):
        plain = RawPart("steel", 30, 30, front_z_mm=0)
        self.assertEqual(stock_region(plain).area, 15 * 30)

    def test_the_drawing_is_saved_with_the_project(self):
        from wop.core.program_model.program import Program
        from wop.core.blocks.base import Safety
        program = Program(self.raw, (), Safety(0, 0, 0, 0, 0), (), ())
        project = Project(program, project_settings())
        again = project_from_dict(project_to_dict(project))
        self.assertEqual(again.program.raw_part, self.raw)
        self.assertEqual(stock_region(again.program.raw_part).area, stock_region(self.raw).area)


def project_settings():
    from wop.core.program_model.project import ProjectSettings
    return ProjectSettings()


class StartingSketchTests(unittest.TestCase):
    def _round_trip(self, raw, back_z):
        sketch = starting_sketch(raw, back_z)
        self.assertTrue(solve(sketch).converged)
        self.assertEqual(problems(sketch, RAW_PART), [])
        return raw_part_from_outline(raw.material, contour_from_sketch(sketch, RAW_PART, "raw", "Raw part"))

    def test_a_bar_starts_as_its_own_drawing(self):
        raw = RawPart("steel", 30, 40, front_z_mm=2)
        again = self._round_trip(raw, -60)
        self.assertEqual((again.outer_diameter_mm, again.inner_diameter_mm), (30, 0))
        self.assertEqual((again.front_z_mm, again.length_outside_mm, again.clamp_z_mm), (2, 40, -38))
        self.assertAlmostEqual(stock_region(again).area, stock_region(replace(raw, outline=None)).area)

    def test_a_tube_starts_as_its_own_drawing(self):
        raw = RawPart("steel", 40, 30, inner_diameter_mm=20, front_z_mm=0)
        again = self._round_trip(raw, -50)
        self.assertEqual((again.outer_diameter_mm, again.inner_diameter_mm), (40, 20))
        self.assertAlmostEqual(stock_region(again).area, stock_region(replace(raw, outline=None)).area)


if __name__ == "__main__":
    unittest.main()
