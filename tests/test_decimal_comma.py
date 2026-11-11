"""Every number the user types can use "," or "." as the decimal point.

The rule behind it: a decimal field is a `NumberBox` (or a text field read by `parse_text` / `number_from_text`), never a
plain `QDoubleSpinBox` or `QInputDialog.getDouble`, which follow the language of Windows and refuse the other sign."""

import os
import re
import sys
import unittest
from pathlib import Path

from wop.ui.block_forms import FieldKind, FieldSpec, parse_text
from wop.ui.number_text import number_from_text

ROOT = Path(__file__).parent.parent
QT_FOLDER = ROOT / "wop" / "ui" / "qt"
ALLOWED = {"number_boxes.py"}  # the file that makes the one decimal box
PLAIN_BOXES = re.compile(r"\bQDoubleSpinBox\s*\(|\bgetDouble\s*\(")

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog

    APP = QApplication.instance() or QApplication([])


class DecimalSignTests(unittest.TestCase):
    def test_no_window_makes_a_plain_decimal_box(self):
        found = []
        for path in sorted(QT_FOLDER.rglob("*.py")):
            if path.name not in ALLOWED and PLAIN_BOXES.search(path.read_text(encoding="utf-8")):
                found.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(found, [], "use NumberBox (wop/ui/qt/number_boxes.py) for a decimal field")

    def test_typed_text_in_a_form_field_takes_both_signs(self):
        spec = FieldSpec(path=("x",), label="X", kind=FieldKind.FLOAT)
        self.assertEqual(parse_text(spec, "2,5"), parse_text(spec, "2.5"))
        self.assertEqual(parse_text(spec, "2,5"), 2.5)

    def test_text_with_a_unit_takes_both_signs(self):
        self.assertEqual(number_from_text("12,5 mm"), number_from_text("12.5 mm"))

    @unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
    def test_a_number_box_takes_both_signs(self):
        from PySide6.QtGui import QValidator

        from wop.ui.qt.number_boxes import NumberBox

        for text in ("1,5", "1.5"):
            box = NumberBox()
            box.setRange(-100, 100)
            box.setDecimals(3)
            self.assertEqual(box.validate(text, 0)[0], QValidator.Acceptable, text)
            box.lineEdit().setText(text)
            box.interpretText()
            self.assertEqual(box.value(), 1.5, text)

    @unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
    def test_the_question_for_a_size_or_a_dimension_takes_both_signs(self):
        from unittest import mock

        from wop.ui.qt.number_boxes import NumberBox
        from wop.ui.qt.sketch_panel import ask_value

        for text in ("2,5", "2.5"):
            def answer(dialog, *_args, text=text):
                dialog.findChild(NumberBox).lineEdit().setText(text)
                return QDialog.Accepted

            with mock.patch.object(QDialog, "exec", answer):
                self.assertEqual(ask_value(None, "Fillet", "Radius (mm):", 1.0), 2.5, text)


if __name__ == "__main__":
    unittest.main()
