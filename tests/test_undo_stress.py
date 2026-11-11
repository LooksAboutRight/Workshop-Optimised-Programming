"""Undo / Redo with random edit sequences: every edit is exactly one step, and a refused edit leaves no trace."""

import random
import unittest
from dataclasses import replace

from wop.ui.app_model import AppModel, ModelError

SEEDS = (1, 2, 3)
EDITS_PER_RUN = 18


def feed_changed(block, rng):
    value = round(rng.uniform(0.05, 0.4), 2)
    if hasattr(block, "feed_mm_per_rev"):
        return replace(block, feed_mm_per_rev=value)
    return replace(block, name=f"n{rng.randint(0, 99)}")


class RandomEdits:
    def __init__(self, model, rng):
        self.model, self.rng = model, rng

    def one(self):
        """Do one random edit; returns its name. A refused edit (ModelError) is allowed."""
        model, rng = self.model, self.rng
        types = model.block_types()
        choices = ["add", "add", "delete", "move", "replace", "replace", "setup", "tool", "select", "contour", "ticked"]
        choice = rng.choice(choices)
        count = len(model.blocks)
        if choice == "add":
            model.add_block(rng.choice(types))
        elif choice == "delete" and count:
            model.delete_block(rng.randrange(count))
        elif choice == "move" and count:
            model.move_block(rng.randrange(count), rng.choice((-1, 1)))
        elif choice == "replace" and count:
            index = rng.randrange(count)
            model.replace_block(index, feed_changed(model.blocks[index], rng))
        elif choice == "setup":
            form = model.setup_form()
            if rng.random() < 0.5:
                form = replace(form, outer_diameter_mm=rng.choice((24, 30, 36, 40)))
            else:
                form = replace(form, front_z_mm=rng.choice((0, 1, 2)))
            model.set_setup_form(form)
        elif choice == "tool":
            kinds = [kind for kind, _label in model.tool_type_choices()]
            model.add_tool_of_type(rng.choice(kinds))
        elif choice == "select" and count:
            model.select(rng.randrange(count))
        elif choice == "contour":
            model.new_contour()
        elif choice == "ticked" and count:
            model.set_ticked(rng.randrange(count), rng.random() < 0.5)
        return choice


class UndoStressTests(unittest.TestCase):
    def run_sequence(self, seed):
        rng = random.Random(seed)
        model = AppModel()
        model.auto_check = False  # the history is what is tested, not the collision check
        edits = RandomEdits(model, rng)
        states = [model.project]
        for number in range(EDITS_PER_RUN):
            before = model._history_pos
            try:
                name = edits.one()
            except ModelError:
                name = "refused"
            self.assertEqual(model.project, model._history[model._history_pos],
                             f"seed {seed}, edit {number} ({name}): the project differs from its history entry")
            self.assertLessEqual(model._history_pos - before, 1, f"seed {seed}, edit {number} ({name}): more than one step")
            if model._history_pos > before:
                self.assertEqual(model._history[model._history_pos - 1], states[-1],
                                 f"seed {seed}, edit {number} ({name}): the step before is not the state before the edit")
                states.append(model.project)
        return model, states

    def test_undo_walks_back_through_every_state_and_redo_forward_again(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                model, states = self.run_sequence(seed)
                for expected in reversed(states[:-1]):
                    self.assertTrue(model.undo())
                    self.assertEqual(model.project, expected)
                self.assertFalse(model.can_undo)
                for expected in states[1:]:
                    self.assertTrue(model.redo())
                    self.assertEqual(model.project, expected)
                self.assertFalse(model.can_redo)

    def test_an_edit_after_undo_drops_the_redo_states(self):
        model, states = self.run_sequence(7)
        model.undo()
        model.undo()
        self.assertTrue(model.can_redo)
        model.add_block("turning")
        self.assertFalse(model.can_redo)
        model.undo()
        self.assertEqual(model.project, states[-3])


if __name__ == "__main__":
    unittest.main()
