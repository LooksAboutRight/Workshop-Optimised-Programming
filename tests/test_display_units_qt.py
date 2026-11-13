"""The form panel with the real PySide6 shows inches and hands the model millimetres (skipped without PySide6)."""

import os
import unittest
from unittest import mock

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])
except ImportError:  # no PySide6 here
    APP = None

from dataclasses import dataclass

from wop.core.program_model.units import XInputMode
from wop.ui import app_constants
from wop.ui.block_forms import form_for


@dataclass(frozen=True)
class Sample:
    length_mm: float = 25.4
    feed_mm_per_rev: float = 0.254
    tilt_deg: float = 30.0


@unittest.skipIf(APP is None, "needs PySide6")
class InchFormTests(unittest.TestCase):
    def test_boxes_show_inches_and_edits_arrive_in_millimetres(self):
        from wop.ui.qt.form_panel import FormPanel

        with mock.patch.object(app_constants, "DISPLAY_UNITS", "inch"):
            panel = FormPanel()
            sample = Sample()
            panel.set_form(sample, form_for(sample), XInputMode.RADIUS)
            boxes = {path[0]: widget for path, widget in panel._widgets.items()}
            self.assertAlmostEqual(boxes["length_mm"].value(), 1)
            self.assertEqual(boxes["length_mm"].suffix(), " in")
            self.assertAlmostEqual(boxes["feed_mm_per_rev"].value(), 0.01)
            self.assertEqual(boxes["feed_mm_per_rev"].suffix(), " in/rev")
            self.assertEqual(boxes["tilt_deg"].suffix(), " deg")
            seen = []
            panel.edited.connect(lambda spec, value: seen.append((spec.path[0], value)))
            boxes["length_mm"].setValue(2)
            self.assertAlmostEqual(seen[-1][1], 50.8)


if __name__ == "__main__":
    unittest.main()
