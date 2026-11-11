"""The error log: what goes to the error output is kept in a file and a traceback is counted and shown to the user."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wop.ui.error_log import MAX_LOG_BYTES, TRACEBACK_MARK, ErrorLog, install

try:
    import PySide6  # noqa: F401
    HAVE_REAL_QT = not hasattr(sys.modules["PySide6"], "_fake")
except ImportError:
    HAVE_REAL_QT = False

if HAVE_REAL_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    APP = QApplication.instance() or QApplication([])


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "sub" / "wop.log"

    def test_text_goes_to_the_file_and_to_the_console(self):
        console = io.StringIO()
        log = ErrorLog(self.path, console)
        self.addCleanup(log.close)
        log.write("hello\n")
        self.assertIn("hello", self.path.read_text(encoding="utf-8"))
        self.assertEqual(console.getvalue(), "hello\n")
        self.assertEqual(log.errors, 0)

    def test_a_traceback_is_counted(self):
        log = ErrorLog(self.path, None)
        self.addCleanup(log.close)
        log.write(f"{TRACEBACK_MARK}:\n  File x\nRuntimeError: boom\n")
        self.assertEqual(log.errors, 1)

    def test_no_console_is_fine(self):
        log = ErrorLog(self.path, None)  # a windowed .exe has no error output
        self.addCleanup(log.close)
        self.assertEqual(log.write("x"), 1)

    def test_a_big_old_log_is_kept_aside(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"x" * (MAX_LOG_BYTES + 1))
        log = ErrorLog(self.path, None)
        self.addCleanup(log.close)
        self.assertTrue(self.path.with_name("wop.log.old").exists())
        self.assertLess(self.path.stat().st_size, MAX_LOG_BYTES)

    def test_install_replaces_the_error_output_and_a_bad_path_changes_nothing(self):
        before = sys.stderr
        self.addCleanup(setattr, sys, "stderr", before)
        with mock.patch("wop.ui.error_log.ErrorLog", side_effect=OSError("no")):
            self.assertIsNone(install(self.path))
        self.assertIs(sys.stderr, before)
        log = install(self.path)
        self.addCleanup(log.close)
        self.assertIs(sys.stderr, log)


@unittest.skipUnless(HAVE_REAL_QT, "needs the real PySide6")
class WindowTellsTheUserTests(unittest.TestCase):
    def test_a_printed_error_is_shown_in_the_window_once(self):
        import traceback

        from wop.ui.app_model import AppModel
        from wop.ui.qt.main_window import MainWindow

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        before = sys.stderr
        self.addCleanup(setattr, sys, "stderr", before)
        log = install(Path(folder.name) / "wop.log")
        self.addCleanup(log.close)
        log.console = None  # the test prints a traceback on purpose: keep it out of the test output
        window = MainWindow(AppModel(), log)
        self.addCleanup(window.deleteLater)
        window._check_error_log()
        self.assertEqual(window._notice, "")  # nothing happened yet
        try:
            raise RuntimeError("boom in a handler")
        except RuntimeError:
            traceback.print_exc()  # what Qt does with an error inside a handler: print it
        self.assertEqual(log.errors, 1)
        self.assertIn("boom in a handler", (Path(folder.name) / "wop.log").read_text(encoding="utf-8"))
        window._check_error_log()
        self.assertIn("internal error", window._notice)
        window._notice = ""
        window._check_error_log()
        self.assertEqual(window._notice, "")  # told once


if __name__ == "__main__":
    unittest.main()
