"""The collision demo project really provokes a finding (so it stays a useful recipe)."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


class CollisionDemoTests(unittest.TestCase):
    def test_the_demo_has_findings_and_a_plain_new_project_has_none(self):
        from make_collision_demo import demo_model
        from wop.ui.app_model import AppModel

        found = demo_model().verify_now()
        self.assertTrue(found.findings, "the demo should provoke at least one finding")
        plain = AppModel()
        plain.add_block("turning")
        self.assertFalse(plain.verify_now().findings)


if __name__ == "__main__":
    unittest.main()
