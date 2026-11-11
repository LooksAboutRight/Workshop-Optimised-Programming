"""The finished shape of a block, drawn in the picture for the block chosen in the flow list (Python 3.11 and later)."""

import unittest
import xml.etree.ElementTree as ET

from tests.helpers import simple_tool
from wop.core.geometry import Point
from wop.core.program_model.operations import SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart

SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"
SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
RAW = RawPart("steel", 30, 60)


def context(tool=None, residual=None):
    from wop.core.blocks.base import BlockContext, Safety
    from wop.core.program_model.stock import stock_region
    return BlockContext(RAW, tool or simple_tool(1), residual or stock_region(RAW), Safety(25, 10, 1))


def ends(outline):
    return [(round(s.start.x, 6), round(s.start.z, 6), round(s.end.x, 6), round(s.end.z, 6)) for s in outline]


class BlockOutlineTests(unittest.TestCase):
    def test_a_block_without_an_outline_gives_nothing(self):
        from wop.core.blocks.machine_function import MachineFunctionBlock
        block = MachineFunctionBlock.example("h1", 1, SPINDLE)
        self.assertEqual(block.target_outline(context()), ())

    def test_turning_shows_the_shoulder_from_the_form_values(self):
        from wop.core.blocks.turning import TurningBlock
        block = TurningBlock.example("t1", 1, SPINDLE)
        outline = block.target_outline(context())
        self.assertTrue(outline)
        self.assertTrue(any(abs(s.start.x - block.target_radius_mm) < 1e-6 and abs(s.end.z - block.end_z_mm) < 1e-6 for s in outline))

    def test_contour_turning_shows_the_contour(self):
        from wop.core.blocks.turning_contour import ContourTurningBlock
        from wop.core.contour import Contour, ContourDefinition, LineStep
        from wop.core.contour_solver import solve_contour
        from wop.core.blocks.base import BlockContext
        definition = ContourDefinition(Point(8, 0), (LineStep(Point(8, -10)), LineStep(Point(12, -10))))
        shape = Contour("c", "c", tuple(solve_contour(definition)), definition)
        block = ContourTurningBlock.example("c1", 1, SPINDLE)
        from dataclasses import replace
        block = replace(block, contour_id="c")
        base = context()
        full = BlockContext(base.raw_part, base.tool, base.residual, base.safety, contours=(shape,))
        self.assertEqual(block.target_outline(full), shape.segments)
        self.assertEqual(block.target_outline(base), ())  # no such contour: nothing, no error

    def test_facing_shows_the_finished_face(self):
        from wop.core.blocks.facing import FacingBlock
        block = FacingBlock.example("f1", 1, SPINDLE)
        outline = block.target_outline(context())
        self.assertEqual(len(outline), 1)
        self.assertEqual((outline[0].start.z, outline[0].end.z), (block.target_z_mm, block.target_z_mm))

    def test_drilling_shows_the_wall_and_the_point_of_the_hole(self):
        from wop.core.blocks.drilling import DrillingBlock
        from wop.core.tooling.tool_presets import drill_tool
        block = DrillingBlock.example("d1", 1, SPINDLE)
        outline = block.target_outline(context(drill_tool(1, "drill", diameter_mm=6)))
        self.assertEqual(len(outline), 2)
        self.assertEqual(outline[0].start.x, 3)  # the wall at the drill radius
        self.assertEqual(outline[1].end.x, 0)  # the point ends on the axis

    def test_grooving_shows_both_walls_and_the_bottom(self):
        from wop.core.blocks.grooving import GroovingBlock
        block = GroovingBlock.example("g1", 1, SPINDLE)
        outline = block.target_outline(context())
        self.assertEqual(len(outline), 3)
        self.assertEqual(outline[1].start.x, block.bottom_radius_mm)

    def test_threading_shows_crest_and_root(self):
        from wop.core.blocks.threading import ThreadingBlock
        block = ThreadingBlock.example("t1", 1, SPINDLE)
        crest, root = block.target_outline(context())
        self.assertEqual(crest.start.x, block.crest_radius_mm)
        self.assertLess(root.start.x, crest.start.x)  # an outside thread: the root is deeper


class PictureOutlineTests(unittest.TestCase):
    def test_the_outline_is_drawn_dashed_in_its_own_colour(self):
        from wop.ui.app_model import AppModel
        from wop.ui.theme import LIGHT_COLORS
        model = AppModel()
        model.add_block("turning")  # the new block is chosen
        root = ET.fromstring(model.picture(with_legend=False))
        lines = [e for e in root.iter(SVG_NAMESPACE + "polyline") if e.get("class") == "finished-outline"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get("stroke"), LIGHT_COLORS.finished_outline)

    def test_no_block_chosen_no_outline(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.add_block("turning")
        model.select(None)
        root = ET.fromstring(model.picture(with_legend=False))
        self.assertEqual([e for e in root.iter(SVG_NAMESPACE + "polyline") if e.get("class") == "finished-outline"], [])

    def test_only_the_chosen_block_is_drawn(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.add_block("turning")
        model.add_block("facing")
        model.select(0)
        root = ET.fromstring(model.picture(with_legend=False))
        self.assertEqual(len([e for e in root.iter(SVG_NAMESPACE + "polyline") if e.get("class") == "finished-outline"]), 1)

    def test_the_3d_view_draws_it_too(self):
        from wop.ui.app_model import AppModel
        model = AppModel()
        model.add_block("turning")
        colour = model.colors.finished_outline
        self.assertEqual(len([s for s in model.scene3d().strokes if s.color == colour]), 1)
        model.select(None)
        self.assertEqual([s for s in model.scene3d().strokes if s.color == colour], [])


if __name__ == "__main__":
    unittest.main()
