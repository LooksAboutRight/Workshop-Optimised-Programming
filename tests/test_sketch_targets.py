"""The sketch editor opened for real things: a contour of the part, a tool shape, workholding, tool holding."""

import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from wop.core.dxf_contour import DxfAxes, DxfDrawing, DxfLine
from wop.core.geometry import Point
from wop.core.sketch.model import SketchError
from wop.core.lathe.workholding import JAWS_KIND
from wop.ui.sketch_constants import TOOL_LINE, TOOL_POINT, TOOL_SELECT
from wop.ui.sketch_session import SketchSession

from wop.ui.app_model import AppModel

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


def _draw(session: SketchSession, *points: tuple[float, float]) -> None:
    session.snapping = False
    session.set_tool(TOOL_LINE)
    for x, z in points:
        _click(session, x, z)
    session.cancel()
    session.set_tool(TOOL_SELECT)


class ContourTargetTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.contour_id = self.model.new_contour()

    def test_draw_and_store_a_part_contour(self):
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        self.assertTrue(session.problems)  # nothing drawn yet
        _draw(session, (20, 0), (20, -30), (30, -40))
        self.assertEqual(session.problems, [])
        session.target.commit(session.result())
        stored = next(c for c in self.model.program.contours if c.contour_id == self.contour_id)
        self.assertTrue(stored.is_valid)
        self.assertEqual(len(stored.segments), 2)
        self.assertIsNotNone(stored.sketch)

    def test_edit_again_keeps_the_relations(self):
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        _draw(session, (20, 0), (20, -30))
        session.selected_pieces = set(session.sketch.lines)
        session.add_dimension(session.plan_dimension("length"), 35)
        session.target.commit(session.result())
        again = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        self.assertEqual(len(again.sketch.constraints), 1)
        self.assertAlmostEqual(self.model.program.contours[0].segments[0].length, 35)

    def test_undo_of_the_store_goes_back(self):
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        _draw(session, (20, 0), (20, -30))
        session.target.commit(session.result())
        self.model.undo()
        self.assertFalse(self.model.program.contours[0].is_valid)

    def test_diameter_mode_shows_along_x_as_a_diameter(self):
        from wop.core.program_model.units import XInputMode

        self.model.project = replace(self.model.project, settings=replace(self.model.project.settings, x_mode=XInputMode.DIAMETER))
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        _draw(session, (20, 0), (20, -30))
        point = min(session.sketch.points)
        session.selected_points = {point}
        plan = session.plan_dimension("along_x")
        self.assertAlmostEqual(plan.shown, 40)  # the point is at radius 20, its diameter is 40
        self.assertIn("diameter", plan.label)
        self.assertTrue(session.add_dimension(plan, 50))
        self.assertAlmostEqual(session.sketch.point(point).x, 25)

    def test_a_new_contour_opens_as_an_empty_sketch(self):
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        self.assertEqual(session.sketch.pieces(), [])

    def test_a_contour_made_from_steps_opens_as_a_sketch(self):
        from wop.core.contour import ContourDefinition, LineStep
        from wop.core.contour_solver import build_contour
        from wop.core.geometry import Point

        definition = ContourDefinition(Point(10, 0), (LineStep(Point(10, -20)), LineStep(Point(15, -20))), False)
        self.model.set_contour(build_contour(self.contour_id, "From steps", definition))
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        self.assertEqual(len(session.sketch.lines), 2)
        self.assertEqual(session.problems, [])

    def test_drawing_import_replaces_the_sketch(self):
        session = SketchSession(target=self.model.contour_sketch_target(self.contour_id))
        drawing = DxfDrawing((DxfLine((0, 10), (-20, 10)), DxfLine((-20, 10), (-20, 15))), (), ())
        with mock.patch("wop.ui.sketch_modify.read_dxf", return_value=drawing):
            session.load_drawing(Path("part.dxf"), DxfAxes.HORIZONTAL)
        self.assertEqual(len(session.sketch.lines), 2)
        self.assertEqual(session.problems, [])
        session.undo()
        self.assertEqual(session.sketch.pieces(), [])


class ToolTargetTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.number = self.model.add_tool_of_type("turning")

    def test_the_tool_opens_with_its_cutting_edges(self):
        session = SketchSession(target=self.model.tool_sketch_target(self.number))
        self.assertEqual(session.problems, [])
        self.assertTrue(any(piece.cutting for piece in session.sketch.pieces()))

    def test_the_drawing_of_a_right_hand_cutter_is_imported_as_drawn_and_the_tool_becomes_a_free_shape(self):
        drawing = Path(__file__).parent / "data" / "right_hand_cutter.dxf"
        session = SketchSession(target=self.model.tool_sketch_target(self.number))
        session.load_drawing(drawing, DxfAxes.HORIZONTAL)
        self.assertEqual(session.problems, [])
        contour = session.result()
        self.assertTrue(contour.is_valid and contour.is_closed)
        self.assertAlmostEqual(min(s.start.x for s in contour.segments), 0, delta=0.01)  # the tip stays at the origin
        self.assertAlmostEqual(max(s.start.x for s in contour.segments), 102.069, delta=0.01)
        session.target.commit(contour)
        self.assertEqual(self.model.program.tool(self.number).kind, "")

    def test_change_a_dimension_and_store_the_tool(self):
        session = SketchSession(target=self.model.tool_sketch_target(self.number))
        before = self.model.program.tool(self.number)
        line = next(l for l in session.sketch.lines.values() if not l.construction)
        session.selected_pieces = {line.line_id}
        session.add_dimension(session.plan_dimension("length"), 33)
        session.target.commit(session.result())
        tool = self.model.program.tool(self.number)
        self.assertEqual(tool.kind, "")  # a free shape now
        self.assertIsNotNone(tool.sketch)
        self.assertNotEqual(tool.shape, before.shape)
        again = SketchSession(target=self.model.tool_sketch_target(self.number))
        self.assertEqual(len(again.sketch.constraints), 1)

    def test_cutting_edge_and_names(self):
        session = SketchSession(target=self.model.tool_sketch_target(self.number))
        piece = next(iter(session.sketch.lines))
        session.selected_pieces = {piece}
        was = session.sketch.lines[piece].cutting
        session.toggle_cutting()
        self.assertNotEqual(session.sketch.lines[piece].cutting, was)
        session.selected_pieces = set()
        session.set_tool(TOOL_POINT)
        _click(session, 50, 50)
        (new_point,) = session.selected_points
        self.assertTrue(session.name_point("mark"))
        self.assertEqual(session.sketch.labels["mark"], new_point)
        session.name_point("")
        self.assertNotIn("mark", session.sketch.labels)
        self.assertNotIn(new_point, session.sketch.points)  # a point on its own with no name is gone
        session.undo()
        self.assertIn("mark", session.sketch.labels)

    def test_an_open_outline_cannot_be_used(self):
        session = SketchSession(target=self.model.tool_sketch_target(self.number))
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session.delete_selected()
        self.assertTrue(any("not closed" in p or "separate" in p for p in session.problems))
        with self.assertRaises(SketchError):
            session.result()


class WorkholdingTargetTests(unittest.TestCase):
    def setUp(self):
        self.model = AppModel()
        self.model.new_library("workholding", "Test")
        self.jaws = self.model.add_workholding_item(JAWS_KIND)

    def test_the_outline_opens_and_is_stored(self):
        target = self.model.workholding_sketch_target(self.jaws)
        session = SketchSession(target=target)
        self.assertEqual(session.problems, [])
        self.assertTrue(target.point_kinds)  # mount point
        before = self.model.workholding_library[0].outline
        piece = next(iter(session.sketch.lines))
        session.selected_pieces = {piece}
        session.add_dimension(session.plan_dimension("length"), 77)
        target.commit(session.result())
        after = self.model.workholding_library[0].outline
        self.assertNotEqual(before.segments, after.segments)
        self.assertIsNotNone(after.sketch)

    def test_the_sketch_survives_the_files(self):
        import json

        from wop.core.files.workholding_io import item_from_dict, item_to_dict

        target = self.model.workholding_sketch_target(self.jaws)
        session = SketchSession(target=target)
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session.add_dimension(session.plan_dimension("length"), 77)
        target.commit(session.result())
        item = self.model.workholding_library[0]
        again = item_from_dict(json.loads(json.dumps(item_to_dict(item))))
        self.assertEqual(again.outline.sketch, item.outline.sketch)
        self.assertEqual(len(SketchSession(target=target.__class__(target.mode, "x", again.outline)).sketch.constraints), 1)

    def test_a_project_file_keeps_the_sketch_of_a_contour(self):
        import tempfile

        model = AppModel()
        contour_id = model.new_contour()
        session = SketchSession(target=model.contour_sketch_target(contour_id))
        _draw(session, (20, 0), (20, -30))
        session.target.commit(session.result())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "part.wop.json"
            model.save(path)
            loaded = AppModel()
            loaded.open(path)
        stored = loaded.program.contours[0]
        self.assertIsNotNone(stored.sketch)
        self.assertEqual(len(SketchSession(target=loaded.contour_sketch_target(stored.contour_id)).sketch.lines), 1)



HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class DialogTargetTests(unittest.TestCase):
    def test_ok_stores_and_is_blocked_while_the_outline_is_not_usable(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.sketch_dialog import SketchDialog

        app = QApplication.instance() or QApplication([])
        model = AppModel()
        contour_id = model.new_contour()
        dialog = SketchDialog(target=model.contour_sketch_target(contour_id))
        self.assertFalse(dialog.ok_button.isEnabled())  # empty
        self.assertIn("Draw the outline", dialog.problems.text())
        _draw(dialog.session, (20, 0), (20, -30))
        self.assertTrue(dialog.ok_button.isEnabled())
        dialog._accept()
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        self.assertTrue(model.program.contours[0].is_valid)
        dialog.grab()
        # a tool: names and cutting edges are drawn, and the Names menu lists the kinds
        number = model.add_tool_of_type("turning")
        tool_dialog = SketchDialog(target=model.tool_sketch_target(number))
        self.assertEqual(list(tool_dialog.name_buttons), [])  # the tip is the origin: no button
        tool_dialog.show()
        tool_dialog.grab()
        tool_dialog.close()
        del app

    def test_the_part_contour_button_opens_the_dialog(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from wop.ui.qt.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        model = AppModel()
        model.new_contour()
        window = MainWindow(model)
        with mock.patch("wop.ui.qt.window_parts.actions.SketchDialog") as dialog:
            window._sketch_for_contour()
        dialog.assert_called_once()
        self.assertIn("target", dialog.call_args.kwargs)
        del window, app


if __name__ == "__main__":
    unittest.main()
