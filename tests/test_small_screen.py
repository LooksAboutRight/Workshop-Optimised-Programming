"""The windows fit a small screen (the lathe PC may be 1024 x 768): the smallest size of the main window and of every dialog
(`tools/check_small_screen.py`, run in a process of its own: it needs the Windows font, which only a new Qt application can be given),
a window that opens larger than the screen is made smaller, and a shut side panel counts as nothing in the width of the window."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QSizePolicy, QVBoxLayout, QWidget

    APP = QApplication.instance() or QApplication([])


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class SmallScreenTests(unittest.TestCase):
    def test_every_window_fits_a_screen_of_1024_by_768(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "check_small_screen.py")], capture_output=True, text=True, cwd=ROOT, timeout=300)
        if "SKIPPED" in done.stdout:
            self.skipTest("the Windows font Segoe UI is not here: the sizes would be those of another font")
        self.assertEqual(done.returncode, 0, "a window is too large for a small screen (tools/check_small_screen.py):\n" + done.stdout + done.stderr)

    def test_a_dialog_larger_than_the_screen_is_made_smaller_when_it_is_shown(self):
        from wop.ui.qt.small_screens import ScreenFitFilter

        fit = ScreenFitFilter(APP)
        APP.installEventFilter(fit)
        self.addCleanup(APP.removeEventFilter, fit)
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("a small dialog"))
        dialog.resize(5000, 5000)
        dialog.show()
        APP.processEvents()
        free = dialog.screen().availableGeometry()
        self.assertLess(dialog.width(), free.width())
        self.assertLess(dialog.height(), free.height())
        dialog.resize(900, 300)  # the user may enlarge it afterwards: it is looked at once only
        self.assertEqual(dialog.size().toTuple(), (900, 300))
        dialog.close()

    def test_a_shut_side_panel_counts_as_nothing_in_the_width_of_the_window(self):
        from wop.ui.qt.panel_splitter import PanelSplitter

        def panel(minimum: int) -> QWidget:
            widget = QWidget()
            widget.setMinimumWidth(minimum)
            QVBoxLayout(widget).addWidget(QLabel("a panel with a text that wants some room"))
            return widget

        splitter = PanelSplitter()
        for part in (panel(200), panel(0), panel(300)):
            splitter.addWidget(part)
        splitter.resize(1000, 300)
        splitter.setSizes([200, 500, 300])
        splitter.show()
        APP.processEvents()
        open_width = splitter.minimumSizeHint().width()
        splitter.close_panel(0)
        splitter.close_panel(2)
        APP.processEvents()
        self.assertEqual((splitter.widget(0).minimumWidth(), splitter.widget(2).minimumWidth()), (0, 0))
        self.assertEqual(splitter.widget(0).sizePolicy().horizontalPolicy(), QSizePolicy.Ignored)
        self.assertLess(splitter.minimumSizeHint().width(), open_width - 400)
        splitter.open_panel(0)
        splitter.open_panel(2)
        APP.processEvents()
        self.assertEqual((splitter.widget(0).minimumWidth(), splitter.widget(2).minimumWidth()), (200, 300))
        self.assertNotEqual(splitter.widget(0).sizePolicy().horizontalPolicy(), QSizePolicy.Ignored)
        self.assertGreaterEqual(splitter.sizes()[0], 200)
        splitter.close()


    def test_the_border_between_the_picture_and_the_messages_can_be_dragged(self):
        import tempfile

        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow
        from wop.ui.qt.qt_constants import MESSAGE_PANEL_HEIGHT_PX, MESSAGE_PANEL_MIN_HEIGHT_PX

        with tempfile.TemporaryDirectory() as folder:
            model = AppModel(settings_path=Path(folder) / "settings.json")
            window = MainWindow(model)
            window.resize(1400, 800)
            window.show()
            for _ in range(5):
                APP.processEvents()
            split = window.centre_split
            self.assertEqual(split.sizes()[1], MESSAGE_PANEL_HEIGHT_PX)  # it opens at its usual height
            split.setSizes([split.height() - 300, 300])
            self.assertEqual(split.sizes()[1], 300)
            split.setSizes([split.height() - 5, 5])
            self.assertEqual(split.sizes()[1], MESSAGE_PANEL_MIN_HEIGHT_PX)  # not smaller than its minimum
            split.setSizes([split.height() - MESSAGE_PANEL_HEIGHT_PX, MESSAGE_PANEL_HEIGHT_PX])
            before = split.sizes()
            window.resize(1400, 1000)
            APP.processEvents()
            self.assertEqual(split.sizes()[1], before[1])  # a taller window gives its room to the picture
            window.close()


if __name__ == "__main__":
    unittest.main()
