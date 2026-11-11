"""The marks on the pictures of the manual (tools/picture_marks.py): pointer, callouts, frames, popups pasted on a window."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HAVE_REAL_QT = False
try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    pass


def _load_marks():
    spec = importlib.util.spec_from_file_location("picture_marks", ROOT / "tools" / "picture_marks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class PictureMarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        cls.marks = _load_marks()
        cls.marks.disable_effects()

    def _window(self, width=240, height=160):
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QWidget

        window = QWidget()
        window.resize(width, height)
        palette = window.palette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        window.setPalette(palette)
        window.setAutoFillBackground(True)
        window.show()
        self.app.processEvents()
        return window

    @staticmethod
    def _pixel(picture, x, y):
        colour = picture.image.pixelColor(x, y)
        return colour.red(), colour.green(), colour.blue()

    def _any(self, picture, centre, test, radius=3):
        return any(test(*self._pixel(picture, centre[0] + dx, centre[1] + dy)) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1))

    def test_the_picture_is_the_window(self):
        window = self._window()
        picture = self.marks.Picture(window)
        self.assertEqual((picture.image.width(), picture.image.height()), (window.width(), window.height()))
        self.assertEqual(self._pixel(picture, 100, 80), (255, 255, 255))
        window.close()

    def test_the_pointer_is_white_with_a_black_edge_and_its_tip_is_where_it_was_put(self):
        from PySide6.QtCore import QPoint

        window = self._window()
        picture = self.marks.Picture(window)
        picture.pointer(QPoint(40, 30))
        self.assertTrue(self._any(picture, (40, 40), lambda r, g, b: r < 60 and g < 60 and b < 60, radius=2))  # the black edge
        self.assertTrue(self._any(picture, (43, 38), lambda r, g, b: r > 240 and g > 240 and b > 240, radius=1))  # the white inside
        self.assertEqual(self._pixel(picture, 200, 130), (255, 255, 255))  # nothing far from it
        window.close()

    def test_a_callout_is_a_red_circle_with_a_white_number(self):
        from PySide6.QtCore import QPoint

        window = self._window()
        picture = self.marks.Picture(window)
        picture.callout(7, QPoint(100, 60))
        self.assertTrue(self._any(picture, (100 + 8, 60), lambda r, g, b: r > 180 and g < 80 and b < 80, radius=1))  # the red disc
        inside = [self._pixel(picture, 100 + dx, 60 + dy) for dx in range(-6, 7) for dy in range(-6, 7)]
        self.assertTrue(any(r > 240 and g > 240 and b > 240 for r, g, b in inside))  # the number
        window.close()

    def test_a_callout_with_a_target_draws_an_arrow_to_it(self):
        from PySide6.QtCore import QPoint

        window = self._window()
        picture = self.marks.Picture(window)
        picture.callout(1, QPoint(40, 40), QPoint(160, 40))
        self.assertTrue(self._any(picture, (100, 40), lambda r, g, b: r > 180 and g < 90 and b < 90, radius=1))  # the line between
        self.assertTrue(self._any(picture, (156, 40), lambda r, g, b: r > 180 and g < 90 and b < 90, radius=2))  # the head
        window.close()

    def test_a_frame_is_red_round_a_rectangle_and_leaves_the_inside_alone(self):
        from PySide6.QtCore import QRect

        window = self._window()
        picture = self.marks.Picture(window)
        picture.frame(QRect(50, 40, 100, 50), margin=3)
        self.assertTrue(self._any(picture, (100, 37), lambda r, g, b: r > 180 and g < 90 and b < 90, radius=1))  # the top edge
        self.assertEqual(self._pixel(picture, 100, 65), (255, 255, 255))
        window.close()

    def test_a_popup_is_pasted_where_it_is_on_the_screen(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QWidget

        window = self._window()
        popup = QWidget(window, Qt.Tool | Qt.FramelessWindowHint)
        popup.resize(60, 30)
        palette = popup.palette()
        palette.setColor(QPalette.Window, QColor(0, 160, 0))
        popup.setPalette(palette)
        popup.setAutoFillBackground(True)
        popup.move(window.mapToGlobal(QPoint(50, 70)))
        popup.show()
        self.app.processEvents()
        picture = self.marks.Picture(window)
        # the picture of the window was taken with the popup open, but a grab does not hold a window of its own
        picture.add_popup(popup)
        self.assertEqual(self._pixel(picture, 80, 85), (0, 160, 0))
        self.assertEqual(self._pixel(picture, 49, 85), (255, 255, 255))
        self.assertEqual(picture.where(popup).topLeft(), QPoint(50, 70))
        popup.close()
        window.close()

    def test_crop_keeps_the_marks_in_the_right_place(self):
        from PySide6.QtCore import QPoint, QRect

        window = self._window()
        picture = self.marks.Picture(window)
        picture.crop(QRect(30, 20, 120, 100))
        self.assertEqual((picture.image.width(), picture.image.height()), (120, 100))
        self.assertEqual(picture.local(window.mapToGlobal(QPoint(30, 20))), QPoint(0, 0))  # the corner that was kept
        here = picture.local(window.mapToGlobal(QPoint(60, 50)))  # a place of the window, found again in the cropped picture
        self.assertEqual(here, QPoint(30, 30))
        picture.callout(1, here)
        self.assertTrue(self._any(picture, (30 + 8, 30), lambda r, g, b: r > 180 and g < 80 and b < 80, radius=1))
        window.close()

    def test_a_picture_can_be_saved_as_png(self):
        window = self._window()
        picture = self.marks.Picture(window)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sub" / "picture.png"
            picture.save(path)
            self.assertTrue(path.is_file() and path.stat().st_size > 0)
        window.close()

    def test_a_menu_a_dropdown_and_a_hover_text_open_from_code_and_are_found(self):
        from PySide6.QtWidgets import QComboBox, QMainWindow, QMenu, QPushButton, QVBoxLayout, QWidget

        window = QMainWindow()
        menu = QMenu("&File", window)
        menu.addAction("&Open...")
        menu.addAction("Export &G-code...")
        window.menuBar().addMenu(menu)
        body = QWidget()
        layout = QVBoxLayout(body)
        combo = QComboBox()
        combo.addItems(["Mild steel", "Aluminium", "Brass"])
        button = QPushButton("Go")
        button.setToolTip("Starts the program")
        layout.addWidget(combo)
        layout.addWidget(button)
        window.setCentralWidget(body)
        window.resize(400, 300)
        window.show()
        self.app.processEvents()
        marks = self.marks
        opened = marks.open_menu(window.menuBar(), window.menuBar().actions()[0])
        self.assertTrue(opened.isVisible())
        self.assertTrue(opened.rect().contains(opened.mapFromGlobal(marks.entry_point(opened, "Export G-code..."))))
        with self.assertRaises(KeyError):
            marks.entry_of(opened, "No such entry")
        picture = marks.Picture(window)
        picture.add_popup(opened)
        self.assertFalse(picture.image.isNull())
        marks.close_popups(opened)
        popup = marks.open_dropdown(combo)
        self.assertTrue(popup.isVisible())
        self.assertTrue(popup.rect().contains(popup.mapFromGlobal(marks.dropdown_item_point(combo, 1))))
        marks.close_popups(combo)
        tip = marks.show_hover_text(button)
        self.assertTrue(tip.isVisible())
        picture.add_popup(tip)
        marks.close_popups()
        window.close()


if __name__ == "__main__":
    unittest.main()
