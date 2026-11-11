import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wop.ui.crash_log import MAX_CRASH_BYTES, install

ROOT = Path(__file__).parent.parent


def run_child(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)


class CrashLogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "crash.log"

    def test_a_crash_without_a_message_leaves_the_stack_of_the_thread_in_the_file(self):
        child = run_child(
            f"import faulthandler\nfrom pathlib import Path\nfrom wop.ui.crash_log import install\n"
            f"install(Path({str(self.path)!r}))\n\ndef work():\n    faulthandler._sigsegv()\n\nwork()\n"
        )
        self.assertNotEqual(child.returncode, 0)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("Fatal Python error", text)
        self.assertIn("in work", text)  # the stack names the function that was running
        self.assertNotIn(" end ---", text)  # a normal end writes a marker; this one has none

    def test_a_slow_program_writes_no_dump_and_a_normal_end_leaves_a_marker(self):
        child = run_child(
            f"import time\nfrom pathlib import Path\nfrom wop.ui.crash_log import install\n"
            f"log = install(Path({str(self.path)!r}))\ntime.sleep(2.5)\nlog.stop()\n"
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("Timeout", text)  # no watchdog: a freeze is not dumped (the dump from a second thread could crash the program)
        self.assertIn(" end ---", text)

    def test_a_big_file_is_kept_as_old_and_a_new_one_started(self):
        self.path.write_text("x" * (MAX_CRASH_BYTES + 1), encoding="utf-8")
        child = run_child(
            f"from pathlib import Path\nfrom wop.ui.crash_log import CrashLog\nCrashLog(Path({str(self.path)!r})).stop()\n"
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertTrue(self.path.with_name("crash.log.old").exists())
        self.assertLess(self.path.stat().st_size, 1000)

    def test_a_file_that_cannot_be_opened_changes_nothing(self):
        self.assertIsNone(install(Path(self.folder.name)))  # a folder is not a file


if __name__ == "__main__":
    unittest.main()
