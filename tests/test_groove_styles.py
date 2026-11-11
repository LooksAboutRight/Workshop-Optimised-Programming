"""Styles of the grooving block: the standard and the layers style (both part of the program), the contract of a style."""

import unittest

from wop.adapters.style_samples import SAMPLES, samples_for
from wop.core.blocks.base import BlockError
from wop.core.blocks.groove_style import GrooveInput, GrooveStyleError, Plunge, check_plunges, standard_plan
from wop.core.blocks.styles import DEFAULT_STYLE_KEY, STYLES
from wop.core.program_model.operations import LinearMove

def groove(**overrides):
    values = dict(
        blade_mm=3, wall_low_z=-19, wall_high_z=-5, rough_low_z=-19, rough_high_z=-5, surface_radius=15, rough_bottom_radius=12,
        final_radius=12, one_sided_mm=1, peck_depth_mm=None, finishing=False, finish_stop_early_mm=1.5,
    )
    values.update(overrides)
    return GrooveInput(**values)


class ContractTests(unittest.TestCase):
    def test_the_standard_style_is_the_default_and_comes_first(self):
        self.assertEqual(STYLES.styles_for("grooving")[0].key, DEFAULT_STYLE_KEY)
        self.assertTrue(STYLES.supports("grooving"))
        self.assertFalse(STYLES.supports("facing"))

    def test_a_plunge_outside_the_groove_is_refused_with_the_style_and_the_number(self):
        for plunge, text in (
            (Plunge(-30, 12), "Z -30 is outside the groove"),
            (Plunge(-10, 5), "is not between the final radius and the surface"),
            (Plunge(-10, 12, sweep_to=-40), "ends at Z -40"),
        ):
            with self.subTest(text=text), self.assertRaises(GrooveStyleError) as caught:
                check_plunges(groove(), [Plunge(-10, 12), plunge], "mine")
            self.assertIn("'mine'", str(caught.exception))
            self.assertIn("plunge 2", str(caught.exception))
            self.assertIn(text, str(caught.exception))

    def test_no_plunge_and_far_too_many_are_refused(self):
        with self.assertRaises(GrooveStyleError):
            check_plunges(groove(), [], "mine")
        with self.assertRaises(GrooveStyleError):
            check_plunges(groove(), [Plunge(-10, 12)] * 5000, "mine")

    def test_the_standard_plan_is_what_the_numbers_say(self):
        plunges = standard_plan(groove())
        self.assertEqual(plunges[0], Plunge(-9, 12))  # one one-sided cut away from the front wall
        self.assertEqual(plunges[-1].z, -19)
        finishing = standard_plan(groove(finishing=True, rough_bottom_radius=12.2))
        self.assertEqual([p.finishing for p in finishing].count(True), 2)
        self.assertTrue(all(p.radius == 12 for p in finishing if p.finishing))


class LayersStyleTests(unittest.TestCase):
    def sample(self, name, style):
        sample = next(s for s in samples_for("grooving") if s.name == name)
        block, context = sample.build(style)
        return block, block.generate(context)

    def test_the_layers_style_is_offered(self):
        self.assertEqual([s.key for s in STYLES.styles_for("grooving")][:2], [DEFAULT_STYLE_KEY, "layers"])

    def test_it_removes_what_the_standard_style_removes_but_plunges_more_often(self):
        for sample in samples_for("grooving"):
            with self.subTest(sample=sample.name):
                _, standard = self.sample(sample.name, DEFAULT_STYLE_KEY)
                _, layers = self.sample(sample.name, "layers")
                self.assertAlmostEqual(standard.removed.area, layers.removed.area, delta=0.05)
                self.assertEqual(layers.messages, standard.messages)
        _, standard = self.sample("outside, wide groove, finishing", DEFAULT_STYLE_KEY)
        _, layers = self.sample("outside, wide groove, finishing", "layers")
        count = lambda result: len([op for op in result.operations if isinstance(op, LinearMove)])
        self.assertGreater(count(layers), count(standard))

    def test_the_layers_are_opened_one_after_the_other(self):
        _, layers = self.sample("outside, wide groove, finishing", "layers")
        depths = [round(op.end.x, 3) for op in layers.operations if isinstance(op, LinearMove) and op.feed_mm_per_rev == 0.05]
        self.assertEqual(depths, sorted(depths, reverse=True))  # outside: deeper means a smaller radius, and never back up
        self.assertGreater(len(set(depths)), 1)


class UnavailableStyleTests(unittest.TestCase):
    def test_a_block_whose_style_is_gone_is_refused_with_a_reason_and_still_shows_it(self):
        sample = samples_for("grooving")[0]
        block, context = sample.build("gone")
        with self.assertRaises(BlockError) as caught:
            block.generate(context)
        self.assertIn("'gone' is not available", str(caught.exception))
        keys = [key for key, _label in block.field_choices()["style"]]
        self.assertEqual(keys[-1], "gone")
        self.assertIn("not available in this program", block.form_notes()["style"])

    def test_the_form_has_the_dropdown_with_the_hint_of_the_chosen_style_as_its_note(self):
        from wop.ui.block_forms import FieldKind, form_for

        block, _context = samples_for("grooving")[0].build("layers")
        spec = next(s for s in form_for(block) if s.path == ("style",))
        self.assertEqual(spec.kind, FieldKind.CHOICE)
        self.assertEqual([c.value for c in spec.choices][:2], [DEFAULT_STYLE_KEY, "layers"])
        self.assertIn("layer by layer", spec.note)


class SampleTests(unittest.TestCase):
    def test_the_samples_cover_outside_inside_wide_and_narrow(self):
        names = [sample.name for sample in SAMPLES["grooving"]]
        self.assertEqual(len(names), 4)
        self.assertTrue(any("inside" in n for n in names) and any("narrow" in n for n in names) and any("wide" in n for n in names))


if __name__ == "__main__":
    unittest.main()
