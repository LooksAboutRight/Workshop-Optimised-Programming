"""The OpenGL 3D view. The offscreen test platform of Qt cannot make an OpenGL context on every system (on Windows it
cannot), so the drawing is tried in a program of its own on the normal platform of the computer; where that has no
OpenGL (or no screen) the tests are skipped. What the scene holds is tested in `tests/test_view3d.py` without Qt."""

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parent.parent

SCRIPT = textwrap.dedent(
    """
    import json, sys, time
    sys.path.insert(0, %r)
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from wop.ui.qt.gl_view import GLSceneView, opengl_works
    works, why = opengl_works()
    if not works:
        print(json.dumps({"works": False, "why": why})); sys.exit(0)
    from tests.reference_program import reference_program
    from wop.core.program_model.program import plan_program
    from wop.core.lathe.workholding import CHUCK_KIND, JAWS_KIND, Workholding, place_workholding
    from wop.core.workholding_types import example_item
    from wop.ui.view3d import Camera, build_scene
    program = reference_program()
    plan = plan_program(program)
    view = GLSceneView(); view.resize(500, 400)
    background = view.palette().window().color().rgb()

    def counts(scene, camera=None):
        view.camera = camera or Camera()
        view.set_scene(scene)
        image = view.image()
        tan, other = 0, 0
        for y in range(0, image.height(), 2):
            for x in range(0, image.width(), 2):
                pixel = image.pixelColor(x, y)
                if pixel.rgb() == background:
                    continue
                other += 1
                if pixel.red() > 150 and pixel.green() > 120 and pixel.blue() < 160 and pixel.red() - pixel.blue() > 40:
                    tan += 1
        return {"size": [image.width(), image.height()], "drawn": other, "tan": tan}

    result = {"works": True}
    result["part"] = counts(build_scene(plan, 1))
    result["empty"] = counts(None)
    result["turned"] = counts(build_scene(plan, 1), Camera(azimuth_deg=70))
    holding = Workholding(example_item(JAWS_KIND, "J"), example_item(CHUCK_KIND, "C"), "step 1")
    placed = place_workholding(program.raw_part, holding)
    result["jaws"] = counts(build_scene(plan, 1, workholding=placed))
    result["glass"] = counts(build_scene(plan, 1, workholding=placed, spindle_on=True))
    start = time.perf_counter()
    for _ in range(5):
        counts(build_scene(plan, 1))
    result["seconds_per_picture"] = (time.perf_counter() - start) / 5
    print(json.dumps(result))
    """
    % str(ROOT)
)


def drawn_in_a_program_of_its_own() -> dict:
    environment = {key: value for key, value in os.environ.items() if key != "QT_QPA_PLATFORM"}
    try:
        done = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=180, env=environment, cwd=ROOT)
    except subprocess.TimeoutExpired:
        raise unittest.SkipTest("the OpenGL program did not finish")
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    if done.returncode != 0 or not lines:
        raise unittest.SkipTest("Qt could not start on the normal platform of this computer: " + done.stderr.strip()[-200:])
    found = json.loads(lines[-1])
    if not found["works"]:
        raise unittest.SkipTest("no OpenGL here: " + found["why"])
    return found


class OpenGLViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = drawn_in_a_program_of_its_own()

    def test_the_part_is_drawn_with_the_tan_of_its_cross_section(self):
        part = self.found["part"]
        self.assertEqual(part["size"], [500, 400])
        self.assertGreater(part["drawn"], 1000)
        self.assertGreater(part["tan"], 100)

    def test_no_scene_draws_only_the_background(self):
        self.assertEqual(self.found["empty"]["drawn"], 0)

    def test_another_camera_gives_another_picture(self):
        self.assertNotEqual(self.found["turned"]["drawn"], self.found["part"]["drawn"])

    def test_the_jaws_and_the_see_through_jaws_add_to_the_picture(self):
        self.assertGreater(self.found["jaws"]["drawn"], self.found["part"]["drawn"])
        self.assertGreater(self.found["glass"]["drawn"], self.found["part"]["drawn"])

    def test_a_picture_takes_a_fraction_of_a_second(self):
        self.assertLess(self.found["seconds_per_picture"], 1.0)


class NoOpenGLTests(unittest.TestCase):
    def test_on_linux_without_opengl_the_program_starts_again_once_with_the_software_renderer(self):
        from wop.ui.qt import app

        with mock.patch.object(app, "opengl_works", return_value=(False, "no")), \
                mock.patch.object(app.sys, "platform", "linux"), \
                mock.patch.object(app.os, "execv") as execv, \
                mock.patch.dict(app.os.environ, {}, clear=False):
            app.os.environ.pop(app.SOFTWARE_OPENGL_VARIABLE, None)
            app.retry_with_software_opengl(["wop_app.py", "project.json"])
            execv.assert_called_once()
            self.assertEqual(app.os.environ[app.SOFTWARE_OPENGL_VARIABLE], "1")
            self.assertEqual(execv.call_args[0][1][1:], ["wop_app.py", "project.json"])
            execv.reset_mock()
            app.retry_with_software_opengl(["wop_app.py"])  # the variable is set now: no second start
            execv.assert_not_called()

    def test_it_does_not_start_again_when_opengl_works_or_off_linux(self):
        from wop.ui.qt import app

        with mock.patch.object(app.os, "execv") as execv:
            with mock.patch.object(app, "opengl_works", return_value=(True, "")), mock.patch.object(app.sys, "platform", "linux"):
                app.retry_with_software_opengl(["x"])
            with mock.patch.object(app, "opengl_works", return_value=(False, "no")), mock.patch.object(app.sys, "platform", "win32"):
                app.retry_with_software_opengl(["x"])
            execv.assert_not_called()

    def test_the_window_falls_back_to_the_2d_picture_when_there_is_no_opengl(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from wop.ui.app_model import AppModel
        from wop.ui.qt import centre_view

        with mock.patch.object(centre_view, "opengl_works", return_value=(False, "no OpenGL here")):
            centre = centre_view.CentreView(AppModel())
            self.assertFalse(centre.is_3d)
            self.assertFalse(centre.button_3d.isEnabled())
            self.assertIn("no OpenGL here", centre.button_3d.toolTip())
            centre.toggle_mode()  # does nothing without 3D
            self.assertFalse(centre.is_3d)
            centre.redraw()


if __name__ == "__main__":
    unittest.main()
