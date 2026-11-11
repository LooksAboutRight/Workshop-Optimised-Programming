"""The Start Z of the simple turning block (requirement X15, the user's idea 2026-10-23): the outline begins where the material of the
block begins, so the finishing pass cuts no air over a step an earlier block turned and the start corner lies on the step. The field is
only shown (greyed, always): there is no typed Start Z (the user's decision, 2026-10-30)."""

import tempfile
import unittest
from pathlib import Path

from tests.helpers import simple_tool
from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.turning import TurningBlock, TurningSide
from wop.core.contour import chamfer
from wop.core.geometry import Point
from wop.core.program_model.operations import ArcMove, LinearMove, SpindleMode, SpindleSetting
from wop.core.program_model.raw_part import RawPart
from wop.core.geometry.region import Region
from wop.core.program_model.stock import stock_region

SAFETY = Safety(safe_radius_mm=30, safe_z_mm=10, clearance_mm=1)
SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
FINISH_FEED = 0.1
RAW = RawPart("steel", 40, 60)  # radius 20
STEP_Z = -30  # an earlier block turned the front down to radius 17 as far as this


def stepped_bar() -> Region:
    """The bar after an earlier block: radius 17 from the front to Z -30, the full bar behind it."""
    bar = stock_region(RAW)
    front = bar.bounds.max_z
    return bar.difference(Region.rectangle(17, STEP_Z, 21, front + 1))


def block(**overrides) -> TurningBlock:
    values = dict(
        block_id="t", tool_number=1, spindle=SPINDLE, side=TurningSide.OUTSIDE, target_radius_mm=18.5, end_z_mm=-42,
        feed_mm_per_rev=0.25, depth_of_cut_mm=2, finish_feed_mm_per_rev=FINISH_FEED, start_corner=chamfer(1),
    )
    values.update(overrides)
    return TurningBlock(**values)


def plan(turning: TurningBlock, residual: Region | None = None):
    return turning.generate(BlockContext(RAW, simple_tool(1), stepped_bar() if residual is None else residual, SAFETY))


def finishing(result):
    return [op for op in result.operations if isinstance(op, (LinearMove, ArcMove)) and op.feed_mm_per_rev == FINISH_FEED]


class StartTests(unittest.TestCase):
    def test_the_start_is_at_the_step_and_a_note_says_so(self):
        result = plan(block())
        self.assertIn("Start Z: -30.00, the edge of the material", " ".join(result.messages))

    def test_the_finishing_pass_cuts_no_air_in_front_of_the_step(self):
        self.assertLessEqual(max(op.end.z for op in finishing(plan(block()))), STEP_Z + 1e-6)

    def test_the_start_chamfer_lies_on_the_step(self):
        ends = [op.end for op in finishing(plan(block()))]
        self.assertTrue(any(end.is_close(Point(17.5, STEP_Z), 1e-6) for end in ends))
        self.assertTrue(any(end.is_close(Point(18.5, STEP_Z - 1), 1e-6) for end in ends))

    def test_the_cylinder_of_the_earlier_block_is_not_touched(self):
        removed = plan(block()).removed
        self.assertLess(removed.intersection(Region.rectangle(0, STEP_Z + 0.01, 17.5, 1)).area, 1e-6)

    def test_a_bar_nobody_turned_starts_at_its_front(self):
        result = plan(block(), stock_region(RAW))
        self.assertIn(f"Start Z: {stock_region(RAW).bounds.max_z:.2f}", " ".join(result.messages))

    def test_nothing_beyond_the_target_is_said(self):
        result = plan(block(target_radius_mm=21))
        self.assertIn("already at or beyond the target radius", " ".join(result.messages))


class ShownValueTests(unittest.TestCase):
    """The greyed Start Z shows the value auto worked out (the user, 2026-10-25): the block's result carries it, the model puts it into
    the block the form shows."""

    def test_the_result_carries_the_start_auto_worked_out(self):
        self.assertEqual(plan(block()).shown_values, (("start_z_mm", STEP_Z),))

    def test_the_model_shows_it_in_the_greyed_field(self):
        model = reference_model()
        shown = model.shown_block(2)  # block 3: behind the step of block 2 at Z -30
        self.assertAlmostEqual(shown.start_z_mm, -30)
        self.assertEqual(model.blocks[2].start_z_mm, 0)  # the project keeps what it had


def reference_model():
    from wop.ui.app_model import AppModel

    folder = tempfile.TemporaryDirectory()
    model = AppModel(settings_path=Path(folder.name) / "settings.json")
    model.open(Path(__file__).parent.parent / "examples" / "reference.wop.json")
    model.refresh()
    model.folder = folder  # kept as long as the model
    return model


class FormTests(unittest.TestCase):
    def test_the_field_is_always_greyed(self):
        self.assertIn("start_z_mm", block().form_disabled())
        self.assertIn("start_z_mm", block(finish_pass=False).form_disabled())

    def test_there_is_no_auto_box(self):
        self.assertNotIn("start_z_auto", block().form_fields())


if __name__ == "__main__":
    unittest.main()
