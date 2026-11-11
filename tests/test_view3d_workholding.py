"""Chuck body and jaws in the 3D picture (WH4)."""

import unittest
from dataclasses import replace

from wop.core.lathe.workholding import CHUCK_KIND, JAWS_KIND, Workholding, place_workholding
from wop.core.workholding_types import example_item

from tests.reference_program import reference_program
from wop.core.program_model.program import plan_program
from wop.ui import view3d_constants as v
from wop.ui.view3d import _jaw_intervals, build_scene


class JawAngleTests(unittest.TestCase):
    def test_one_jaw_is_centred_in_the_plane_of_the_path(self):
        intervals = _jaw_intervals(3, 60)
        centred = [(a, b) for a, b in intervals if abs(b - v.PATH_PLANE_DEG) < 1e-9]
        self.assertEqual(len(centred), 1)  # clipped to the swept part: the half that is inside it
        self.assertAlmostEqual(centred[0][1] - centred[0][0], 30)

    def test_jaws_stay_inside_the_swept_range(self):
        for start, end in _jaw_intervals(4, 50):
            self.assertGreaterEqual(start, v.SWEEP_START_DEG)
            self.assertLessEqual(end, v.SWEEP_START_DEG + v.SWEEP_DEG)

    def test_a_jaw_in_the_removed_quarter_is_not_drawn(self):
        # two jaws of 20 degrees: the second one is opposite the first and lies in the swept part
        self.assertTrue(_jaw_intervals(2, 20))


class JawsIn3DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = reference_program()
        cls.plan = plan_program(cls.program)
        holding = Workholding(example_item(JAWS_KIND, "J"), example_item(CHUCK_KIND, "C"), "step 1")
        cls.placed = place_workholding(cls.program.raw_part, holding)

    def _scene(self, **kw):
        return build_scene(self.plan, steps_per_turn=24, **kw)

    def test_without_workholding_the_scene_is_as_before(self):
        plain, none = self._scene(), self._scene(workholding=None, spindle_on=False)
        self.assertEqual(plain.solid.count, none.solid.count)
        self.assertEqual(plain.glass.count, 0)

    def test_stopped_jaws_and_the_chuck_are_opaque_solids(self):
        plain, held = self._scene(), self._scene(workholding=self.placed)
        self.assertGreater(held.solid.count, plain.solid.count)
        self.assertEqual(held.glass.count, 0)  # nothing turns transparent while the spindle is off

    def test_a_running_spindle_makes_only_the_jaws_see_through(self):
        running = self._scene(workholding=self.placed, spindle_on=True)
        self.assertGreater(running.glass.count, 0)
        self.assertEqual(running.glass_opacity, v.JAWS_SPINDLE_OPACITY)
        # without the jaws the scene has exactly the triangles of the part and the chuck: all of them stay opaque
        chuck_only = place_workholding(self.program.raw_part, Workholding(None, example_item(CHUCK_KIND, "C")))
        self.assertEqual(running.solid.count, self._scene(workholding=chuck_only).solid.count)

    def test_the_model_turns_the_jaws_on_with_the_spindle(self):
        from wop.ui.app_model import AppModel
        from tests.reference_program import reference_program as ref

        model = AppModel()
        model.project = replace(model.project, program=replace(
            ref(), workholding=Workholding(example_item(JAWS_KIND, "J"), None, "step 1")))
        model._changed()
        self.assertGreater(model.scene3d(steps_per_turn=24).glass.count, 0)  # after the last block the spindle still runs
        self.assertEqual(model.scene3d(upto_block=None, steps_per_turn=24, step=0).glass.count, 0)  # first step: spindle off


if __name__ == "__main__":
    unittest.main()
