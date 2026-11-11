"""The pictures show a block that cut into the part as it really left it; the plan and the files keep the part as drawn (the user's
idea, 2026-10-30)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def model_of(project: Path):
    from wop.ui.app_model import AppModel

    folder = tempfile.TemporaryDirectory()
    model = AppModel(settings_path=Path(folder.name) / "settings.json")
    model.open(project)
    model.refresh()
    model.folder = folder  # kept as long as the model
    return model


class DamageViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = model_of(ROOT / "tests" / "data" / "projects" / "gouge_steep_contour.wop.json")
        cls.analysis = cls.model.verify_now()

    def test_the_block_that_gouges_shows_less_material_than_planned(self):
        gouged = {f.block_index for f in self.analysis.findings}
        self.assertTrue(gouged)
        first = min(gouged)
        block_plan = self.analysis.plan.blocks[first]
        self.assertIsNotNone(block_plan.shown_after)
        self.assertLess(block_plan.material_after.area, block_plan.residual_after.area - 0.01)

    def test_the_damage_is_a_notch_in_the_outline_not_a_hole_in_the_part(self):
        # the 3D surface is the revolve of the outer ring: a damage that let go of the outline would show in the cut plane only
        for block_plan in self.analysis.plan.blocks:
            for polygon in block_plan.material_after.polygons():
                self.assertEqual(len(polygon.holes), 0)
        first = min(f.block_index for f in self.analysis.findings)
        ring = self.analysis.plan.blocks[first].material_after.polygons()[0].exterior
        area = abs(sum(a.x * b.z - b.x * a.z for a, b in zip(ring, [*ring[1:], ring[0]]))) / 2
        self.assertAlmostEqual(area, self.analysis.plan.blocks[first].material_after.area, places=3)

    def test_what_comes_before_is_as_planned_and_the_plan_itself_is_not_changed(self):
        gouged = min(f.block_index for f in self.analysis.findings)
        for block_plan in self.analysis.plan.blocks[:gouged]:
            self.assertIsNone(block_plan.shown_after)
        self.assertEqual(self.analysis.plan.final_residual.area, self.analysis.plan.blocks[-1].residual_after.area)

    def test_the_stepper_ends_a_block_with_what_the_pictures_show(self):
        stepper = self.model.stepper()
        gouged = min(f.block_index for f in self.analysis.findings)
        last = stepper.block_end(stepper.first_step_of_block(gouged))
        self.assertAlmostEqual(stepper.material(last).area, self.analysis.plan.blocks[gouged].material_after.area, places=6)

    def test_a_plan_without_findings_is_not_touched(self):
        from wop.ui.damage import with_damage

        clean = model_of(ROOT / "examples" / "reference.wop.json")
        plan = clean.analysis.plan
        self.assertIs(with_damage(clean.program, plan, []), plan)


if __name__ == "__main__":
    unittest.main()
