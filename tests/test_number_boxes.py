"""Number boxes with the real PySide6 (offscreen): a click from one field into the next must not touch a box that the
form rebuild has deleted meanwhile (the console showed 'Internal C++ object (NumberBox) already deleted')."""

import io
import os
import sys
import unittest
from pathlib import Path


try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import shiboken6
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])

ROOT = Path(__file__).parent.parent


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class NumberBoxTests(unittest.TestCase):
    def test_the_select_all_of_a_box_that_is_gone_does_nothing(self):
        from wop.ui.qt.number_boxes import NumberBox, WholeNumberBox, _select_all_if_alive

        for kind in (NumberBox, WholeNumberBox):
            box = kind()
            _select_all_if_alive(box)  # alive: fine
            shiboken6.delete(box)
            _select_all_if_alive(box)  # gone: no RuntimeError

    def test_a_form_rebuild_between_the_click_and_the_select_all_is_harmless(self):
        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow
        from wop.ui.qt.number_boxes import NumberBox

        model = AppModel()
        model.open(ROOT / "examples" / "reference.wop.json")
        window = MainWindow(model)
        self.addCleanup(window.deleteLater)
        window.show()
        model.select(1)
        APP.processEvents()
        first, second = window.form.findChildren(NumberBox)[:2]
        first.setFocus()
        APP.processEvents()
        errors, old = io.StringIO(), sys.stderr
        sys.stderr = errors
        try:
            QTimer.singleShot(0, window._show_form)  # an edit that changes the fields asks for a rebuild after its handler
            second.setFocus()  # the click into the next field: its select-all waits behind the rebuild
            APP.processEvents()
            APP.processEvents()
        finally:
            sys.stderr = old
        self.assertNotIn("already deleted", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
