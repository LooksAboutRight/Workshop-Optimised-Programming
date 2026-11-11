"""The square buttons with pictograms of the sketch editor."""

import os
import sys
import unittest

from wop.core.geometry import Point
from wop.core.sketch.modes import TOOL, TURNING
from wop.ui.point_kinds import TOOL_POINT_KINDS
from wop.ui.sketch_constants import MODIFY_ITEMS, RELATION_ITEMS, TOOL_LINE, TOOL_NAMES, TOOL_SELECT
from wop.ui.sketch_target import SketchTarget

HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass

TOL = 0.5


def _everything_with_a_button() -> list[str]:
    return [name for name, _label in TOOL_NAMES if name != TOOL_SELECT] + [n for n, _l in RELATION_ITEMS] + [n for n, _l in MODIFY_ITEMS]


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_every_button_has_a_pictogram(self):
        from wop.ui.qt.sketch_icons import icon_names

        known = set(icon_names())
        missing = [name for name in _everything_with_a_button() if name not in known]
        self.assertEqual(missing, [])
        self.assertTrue({"undo", "redo", "snap", "import", "name_mount", "name_step", "name_face", "show_relations", "show_dimensions"} <= known)

    def test_the_pictograms_are_drawn_and_all_different(self):
        from PySide6.QtGui import QColor

        from wop.ui.qt.sketch_icons import icon_names, pixmap

        seen = {}
        for name in icon_names():
            image = pixmap(name, 52, QColor(20, 20, 20)).toImage()
            painted = sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 40)
            self.assertGreater(painted, 40, name)  # something is there
            self.assertLess(painted, image.width() * image.height() * 0.6, name)  # and it is not a block
            data = bytes(image.constBits())
            self.assertNotIn(data, seen, f"{name} looks like {seen.get(data)}")
            seen[data] = name

    def test_the_pictograms_follow_the_colour_of_the_text(self):
        from PySide6.QtGui import QColor

        from wop.ui.qt.sketch_icons import pixmap

        dark_on_light = pixmap("line", 52, QColor(10, 10, 10)).toImage()
        light_on_dark = pixmap("parallel", 52, QColor(240, 240, 240)).toImage()
        coloured = [dark_on_light.pixelColor(x, y) for x in range(52) for y in range(52) if dark_on_light.pixelColor(x, y).alpha() > 200]
        bright = [light_on_dark.pixelColor(x, y) for x in range(52) for y in range(52) if light_on_dark.pixelColor(x, y).alpha() > 200]
        self.assertTrue(any(c.red() < 60 and c.green() < 60 for c in coloured))
        self.assertTrue(any(c.red() > 200 and c.green() > 200 for c in bright))

    def _dialog(self, target=None):
        from wop.ui.qt.sketch_dialog import SketchDialog

        dialog = SketchDialog(target=target)
        dialog.show()
        return dialog

    def test_the_buttons_are_square_with_a_picture_and_a_hover_text_and_no_words(self):
        dialog = self._dialog(SketchTarget(TOOL, "tool", point_kinds=TOOL_POINT_KINDS))
        buttons = [
            *dialog.tool_buttons.values(), *dialog.relation_buttons.values(), *dialog.modify_buttons.values(),
            *dialog.name_buttons.values(), dialog.toolbox.import_button, dialog.toolbox.undo_button, dialog.toolbox.redo_button,
            dialog.toolbox.snap_button, dialog.toolbox.relations_button, dialog.toolbox.dimensions_button,
        ]
        self.assertGreaterEqual(len(buttons), 28)
        for button in buttons:
            self.assertEqual(button.width(), button.height())
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.text(), "")
            self.assertTrue(button.toolTip().strip())
        tips = [b.toolTip() for b in buttons]
        self.assertEqual(len(set(tips)), len(tips))  # every hover text says something different
        dialog.close()

    def test_the_hover_texts_are_the_names_the_menus_had(self):
        dialog = self._dialog()
        self.assertEqual(dialog.relation_buttons["horizontal"].toolTip(), "Horizontal")
        self.assertIn("Fillet", dialog.modify_buttons["fillet"].toolTip())
        self.assertIn("Line", dialog.tool_buttons[TOOL_LINE].toolTip())
        dialog.close()

    def test_a_relation_button_acts_on_a_fitting_selection_and_is_always_enabled(self):
        dialog = self._dialog()
        session = dialog.session
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (3, 10)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        self.assertTrue(dialog.relation_buttons["horizontal"].isEnabled())  # nothing selected: it turns the tool on
        self.assertTrue(dialog.modify_buttons["fillet"].isEnabled())
        session.selected_pieces = set(session.sketch.lines)
        session.refresh()
        self.assertTrue(session.available_relation("horizontal"))
        self.assertFalse(session.available_relation("parallel"))  # needs two lines
        self.assertFalse(session.available_modify("fillet"))  # needs a corner point
        dialog.relation_buttons["horizontal"].click()
        self.assertTrue(session.sketch.constraints)
        self.assertEqual(session.armed, "")  # it acted on the selection, the tool did not turn on
        dialog.close()

    def test_a_relation_button_without_a_fitting_selection_turns_the_tool_on_and_off(self):
        dialog = self._dialog()
        session = dialog.session
        button = dialog.relation_buttons["parallel"]
        button.click()
        self.assertEqual(session.armed, "parallel")
        self.assertTrue(button.isChecked())
        button.click()
        self.assertEqual(session.armed, "")
        self.assertFalse(button.isChecked())
        dialog.close()

    def test_undo_and_redo_are_enabled_when_there_is_something_to_undo_or_redo(self):
        dialog = self._dialog()
        session = dialog.session
        self.assertFalse(dialog.toolbox.undo_button.isEnabled())
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (3, 10)):
            session.press(Point(x, z), TOL)
        self.assertTrue(dialog.toolbox.undo_button.isEnabled())
        self.assertFalse(dialog.toolbox.redo_button.isEnabled())
        dialog.toolbox.undo_button.click()
        self.assertTrue(dialog.toolbox.redo_button.isEnabled())
        dialog.toolbox.redo_button.click()
        self.assertTrue(session.sketch.lines)
        dialog.close()

    def test_the_snap_button_switches_snapping(self):
        dialog = self._dialog()
        self.assertTrue(dialog.toolbox.snap_button.isChecked() and dialog.session.snapping)
        dialog.toolbox.snap_button.click()
        self.assertFalse(dialog.session.snapping)
        dialog.close()

    def test_the_relations_and_the_dimensions_can_be_hidden_and_are_shown_when_the_window_opens(self):
        dialog = self._dialog()
        session = dialog.session
        self.assertTrue(session.show_relations and session.show_dimensions)
        self.assertTrue(dialog.toolbox.relations_button.isChecked() and dialog.toolbox.dimensions_button.isChecked())
        dialog.toolbox.relations_button.click()
        self.assertFalse(session.show_relations)
        self.assertTrue(session.show_dimensions)  # separate switches
        dialog.toolbox.dimensions_button.click()
        self.assertFalse(session.show_dimensions)
        dialog.canvas.grab()  # paints without the tags and the dimensions
        dialog.close()

    def test_the_cutting_button_is_only_there_for_tool_shapes_and_names_for_shapes_with_names(self):
        free = self._dialog()
        self.assertNotIn("cutting", free.modify_buttons)
        self.assertEqual(free.name_buttons, {})
        free.close()
        tool = self._dialog(SketchTarget(TOOL, "tool", point_kinds=TOOL_POINT_KINDS))
        self.assertIn("cutting", tool.modify_buttons)
        self.assertEqual(list(tool.name_buttons), [])  # the tip is the origin: no button
        tool.close()
        turning = self._dialog(SketchTarget(TURNING, "part"))
        self.assertNotIn("cutting", turning.modify_buttons)
        turning.close()

    def test_the_mirror_button_waits_for_a_selection_and_stays_pressed_while_it_waits_for_the_line(self):
        from wop.ui.sketch_constants import TOOL_MIRROR

        dialog = self._dialog()
        session = dialog.session
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((5, 0), (5, -20)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        mirror = dialog.tool_buttons[TOOL_MIRROR]
        self.assertFalse(mirror.isEnabled())  # nothing is selected yet
        session.selected_pieces = set(session.sketch.lines)
        session.refresh()
        self.assertTrue(mirror.isEnabled())
        mirror.click()
        self.assertEqual(session.tool, TOOL_MIRROR)
        self.assertTrue(mirror.isChecked())
        mirror.click()  # the button of the tool that is on turns it off
        self.assertEqual(session.tool, TOOL_SELECT)
        self.assertNotIn("mirror_line", dialog.modify_buttons)  # one mirror only
        self.assertEqual([n for n in dialog.modify_buttons if n.startswith("mirror")], [])
        dialog.close()

    def test_the_tray_of_relations_and_dimensions_starts_folded_and_opens_and_shuts_with_its_handle(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        dialog = self._dialog()
        splitter = dialog.splitter
        self.assertEqual(splitter.count(), 2)
        self.assertTrue(splitter.is_collapsed(1))  # folded to begin with
        width_of_picture = splitter.sizes()[0]
        handle = splitter.handle(1)
        QTest.mouseClick(handle, Qt.LeftButton, Qt.NoModifier, handle.rect().center())  # a click on the handle opens it
        self.assertFalse(splitter.is_collapsed(1))
        self.assertGreaterEqual(splitter.sizes()[1], dialog.panel.minimumWidth())
        self.assertLess(splitter.sizes()[0], width_of_picture)  # the drawing gave up the room
        QTest.mouseClick(handle, Qt.LeftButton, Qt.NoModifier, handle.rect().center())  # and a click shuts it again
        self.assertTrue(splitter.is_collapsed(1))
        self.assertTrue(dialog.canvas.isVisible())
        dialog.close()

    def test_the_tray_keeps_working_while_it_is_folded(self):
        dialog = self._dialog()
        self.assertTrue(dialog.splitter.is_collapsed(1))
        session = dialog.session
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (3, 10)):
            session.press(Point(x, z), TOL)
        session.cancel()
        session.selected_pieces = set(session.sketch.lines)
        session.apply_relation("horizontal")
        self.assertEqual(dialog.panel.list.count(), 1)  # the list is kept up to date although nobody sees it
        dialog.splitter.open_panel(1)
        self.assertTrue(dialog.splitter.sizes()[1] > 0)
        self.assertEqual(dialog.panel.list.count(), 1)
        dialog.close()

    def test_the_buttons_are_in_sections_with_headings(self):
        dialog = self._dialog(SketchTarget(TOOL, "tool", point_kinds=TOOL_POINT_KINDS))
        toolbox = dialog.toolbox
        self.assertEqual([heading for heading, _names in toolbox.sections], ["Draw", "Edit", "Constraints", "Mark", "General"])
        self.assertEqual([label.text() for label in toolbox.headings], ["Draw", "Edit", "Constraints", "Mark", "General"])
        sections = dict(toolbox.sections)
        self.assertEqual(sections["Draw"], ["line", "circle", "arc_centre", "arc_three", "point"])  # what makes geometry
        self.assertEqual(sections["Edit"], ["trim", "mirror", "fillet", "chamfer"])  # what changes what is there
        self.assertEqual(sections["Constraints"][0], "dimension")  # the dimension first
        self.assertIn("horizontal", sections["Constraints"])
        self.assertEqual(sections["Mark"], ["construction", "centre", "cutting"])
        self.assertEqual(sections["General"], ["import", "undo", "redo", "snap", "show_relations", "show_dimensions"])
        every = [name for _heading, names in toolbox.sections for name in names]
        self.assertEqual(len(every), len(set(every)))  # a button is in one section only
        for label in toolbox.headings:
            self.assertTrue(label.isVisible())
        dialog.close()

    def test_a_heading_is_above_its_buttons_and_the_sections_follow_each_other(self):
        dialog = self._dialog(SketchTarget(TOOL, "tool", point_kinds=TOOL_POINT_KINDS))
        toolbox = dialog.toolbox
        every = {**toolbox.tool_buttons, **toolbox.relation_buttons, **toolbox.modify_buttons}
        every.update({"import": toolbox.import_button, "undo": toolbox.undo_button,
                      "redo": toolbox.redo_button, "snap": toolbox.snap_button, **{"name:" + k: b for k, b in toolbox.name_buttons.items()},
                      "show_relations": toolbox.relations_button, "show_dimensions": toolbox.dimensions_button})
        last_bottom = -1
        for label, (_heading, names) in zip(toolbox.headings, toolbox.sections):
            tops = [every[name].mapTo(toolbox, every[name].rect().topLeft()).y() for name in names]
            bottoms = [every[name].mapTo(toolbox, every[name].rect().bottomLeft()).y() for name in names]
            self.assertLess(label.mapTo(toolbox, label.rect().bottomLeft()).y(), min(tops) + 1)
            self.assertGreater(label.y(), last_bottom)
            last_bottom = max(bottoms)
        dialog.close()

    def test_a_window_without_cutting_edges_or_names_leaves_those_buttons_out_of_the_sections(self):
        dialog = self._dialog()
        sections = dict(dialog.toolbox.sections)
        self.assertEqual(sections["Mark"], ["construction", "centre"])
        dialog.close()

    def test_the_window_is_painted_with_the_strip(self):
        dialog = self._dialog()
        self.assertFalse(dialog.grab().isNull())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
