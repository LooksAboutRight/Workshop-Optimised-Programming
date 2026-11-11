import json
import unittest
from dataclasses import replace

from tests.helpers import simple_tool
from wop.core.blocks.base import Safety
from wop.core.blocks.custom_path import CustomPathBlock, PathMove, PathStep
from wop.core.contour import CornerKind
from wop.core.files.dataclass_codec import from_data, to_data
from wop.core.geometry import ArcDirection, Point
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid, SpindleMode, SpindleSetting
from wop.core.program_model.program import Program, plan_program
from wop.core.program_model.raw_part import RawPart
from wop.core.sketch.sketch_io import sketch_from_dict

RPM = SpindleSetting(SpindleMode.CONSTANT_RPM, 1000)
SAFE = Point(25, 10)  # the safe point of the program below: every path starts there


def block(*steps, start=Point(20, 2), feed=0.1):
    """A path that goes from the safe point to `start` as a rapid line and then follows the steps."""
    empty = CustomPathBlock(block_id="p", tool_number=1, spindle=RPM, feed_mm_per_rev=feed)
    return empty.drawn_from(SAFE, start, tuple(steps)) if steps else empty


def program(*blocks):
    return Program(
        raw_part=RawPart("steel", 30, 60), tools=(simple_tool(1),),
        safety=Safety(safe_radius_mm=SAFE.x, safe_z_mm=SAFE.z, clearance_mm=1), blocks=tuple(blocks),
    )


def operations(path):
    plan = plan_program(program(path))
    return [op for op in plan.blocks[0].operations if isinstance(op, (Rapid, LinearMove, ArcMove))]


class CustomPathTests(unittest.TestCase):
    def test_two_rapids_two_feed_lines_and_an_arc_become_neutral_moves(self):
        path = block(
            PathStep(PathMove.RAPID, Point(20, 0)),
            PathStep(PathMove.FEED_LINE, Point(12, 0)),
            PathStep(PathMove.FEED_ARC, Point(10, -2), radius_mm=2, direction=ArcDirection.CW),
            PathStep(PathMove.FEED_LINE, Point(10, -10)),
            PathStep(PathMove.RAPID, Point(20, -10)),
        )
        moves = operations(path)
        kinds = [type(m) for m in moves if not (isinstance(m, Rapid) and m.end.x >= 25 and m.end.z == 10)]
        self.assertEqual(kinds[-5:], [Rapid, LinearMove, ArcMove, LinearMove, Rapid])
        arc = next(m for m in moves if isinstance(m, ArcMove))
        self.assertAlmostEqual(arc.end.x, 10)
        self.assertEqual(arc.feed_mm_per_rev, 0.1)

    def test_the_path_starts_at_the_safe_point_and_goes_to_where_it_was_drawn_to_start(self):
        moves = operations(block(PathStep(PathMove.FEED_LINE, Point(20, -5))))
        rapids = [m for m in moves if isinstance(m, Rapid)]
        self.assertEqual(rapids[-1].end, Point(20, 2))  # the first piece of the path: a rapid line from the safe point
        self.assertIn(SAFE, [m.end for m in rapids])

    def test_a_step_feed_overrides_the_block_feed(self):
        moves = operations(block(PathStep(PathMove.FEED_LINE, Point(20, -5), feed_mm_per_rev=0.3)))
        self.assertEqual([m.feed_mm_per_rev for m in moves if isinstance(m, LinearMove)], [0.3])

    def test_a_chamfer_between_two_feed_lines_adds_a_line_with_the_feed_of_the_corner_step(self):
        path = block(
            PathStep(PathMove.FEED_LINE, Point(20, -10), corner=CornerKind.CHAMFER, corner_size_mm=1, feed_mm_per_rev=0.2),
            PathStep(PathMove.FEED_LINE, Point(10, -10), feed_mm_per_rev=0.4),
        )
        lines = [m for m in operations(path) if isinstance(m, LinearMove)]
        self.assertEqual(len(lines), 3)
        self.assertEqual([m.feed_mm_per_rev for m in lines], [0.2, 0.2, 0.4])

    def test_a_fillet_makes_an_arc(self):
        path = block(
            PathStep(PathMove.FEED_LINE, Point(20, -10), corner=CornerKind.FILLET, corner_size_mm=1),
            PathStep(PathMove.FEED_LINE, Point(10, -10)),
        )
        self.assertEqual(len([m for m in operations(path) if isinstance(m, ArcMove)]), 1)

    def test_a_path_can_come_back_along_a_line(self):
        path = block(
            PathStep(PathMove.FEED_LINE, Point(20, -10)),
            PathStep(PathMove.RAPID, Point(20, 2)),  # the same line again, the other way, as a rapid
            PathStep(PathMove.FEED_LINE, Point(12, 2)),
        )
        self.assertEqual(path.own_problem(), "")
        self.assertEqual([type(m) for m in operations(path)][-3:], [LinearMove, Rapid, LinearMove])

    def test_a_path_that_is_not_drawn_is_a_problem_and_the_block_is_left_out(self):
        empty = block()
        self.assertEqual(empty.own_problem(), "the path is not drawn yet")
        plan = plan_program(program(empty))
        self.assertEqual(len(plan.blocks), 0)
        self.assertEqual(len(plan.left_out), 1)

    def test_a_piece_that_does_not_follow_the_path_is_named(self):
        path = block(PathStep(PathMove.FEED_LINE, Point(20, -5)))
        sketch = sketch_from_dict(path.sketch)
        far = sketch.add_point(5, 5)
        sketch.add_line(far, sketch.add_point(5, -5))
        from wop.core.sketch.sketch_io import sketch_to_dict

        self.assertIn("do not follow the path", replace(path, sketch=sketch_to_dict(sketch)).own_problem())

    def test_the_material_the_tool_passes_counts_as_removed(self):
        path = block(PathStep(PathMove.FEED_LINE, Point(13, -8)), start=Point(13, 2))
        plan = plan_program(program(path))
        self.assertGreater(plan.blocks[0].result.removed.area, 0)

    def test_a_new_block_has_nothing_drawn_and_the_sample_has_a_small_path(self):
        self.assertIsNone(CustomPathBlock.example("p", 1, RPM).sketch)
        self.assertEqual(CustomPathBlock.sample("p", 1, RPM).own_problem(), "")

    def test_the_example_works_and_survives_save_and_load(self):
        example = CustomPathBlock.sample("p", 1, RPM)
        self.assertEqual(example.own_problem(), "")
        self.assertEqual(from_data(CustomPathBlock, json.loads(json.dumps(to_data(example)))), example)
        plan = plan_program(program(example))
        self.assertEqual(len(plan.blocks), 1)
        self.assertEqual(plan.blocks[0].block.type_name, "custom_path")

    def test_a_path_that_is_not_fully_constrained_says_so(self):
        plan = plan_program(program(block(PathStep(PathMove.FEED_LINE, Point(20, -5)))))
        self.assertTrue(any("not fully constrained" in message for message in plan.blocks[0].result.messages))

    def test_the_safe_point_of_the_program_is_the_start_whatever_the_sketch_remembers(self):
        path = block(PathStep(PathMove.FEED_LINE, Point(20, -5)))
        other = Program(
            raw_part=RawPart("steel", 30, 60), tools=(simple_tool(1),),
            safety=Safety(safe_radius_mm=40, safe_z_mm=20, clearance_mm=1), blocks=(path,),
        )
        first = [op for op in plan_program(other).blocks[0].operations if isinstance(op, Rapid)][0]
        self.assertEqual(first.end, Point(40, 20))


class PathEditingTests(unittest.TestCase):
    def setUp(self):
        from wop.ui.app_model import AppModel

        self.model = AppModel()
        self.index = self.model.add_block("custom_path")

    def test_the_block_is_in_the_add_menu_and_its_form_has_a_draw_button(self):
        from wop.ui.block_forms import FieldKind, form_for

        self.assertIn("custom_path", self.model.block_types())
        specs = {spec.path[0]: spec for spec in form_for(self.model.selected_block(), self.model.form_context())}
        self.assertIn("feed_mm_per_rev", specs)
        self.assertIs(specs["draw_path"].kind, FieldKind.BUTTON)
        self.assertEqual(specs["draw_path"].button_text, "Draw the path...")
        self.assertNotIn("steps", specs)

    def test_deleting_everything_in_a_drawn_path_works_also_with_a_chamfer(self):
        from wop.ui.sketch_session import SketchSession

        sample = CustomPathBlock.sample("p", 1, RPM)
        self.model.replace_block(self.index, replace(self.model.blocks[self.index], sketch=sample.sketch))
        session = SketchSession(target=self.model.path_sketch_target(self.index))
        real = [i for i in session.sketch.lines if not session.sketch.is_locked_piece(i)]
        self.assertTrue(real)
        session.selected_pieces = set(session.sketch.lines) | set(session.sketch.arcs)  # a box round everything, the chamfer included
        session.selected_points = set(session.sketch.points)
        session.delete_selected()
        self.assertEqual([i for i in session.sketch.lines if not session.sketch.is_locked_piece(i)], [])
        self.assertTrue(session.sketch.locked_points)  # what is locked stays

    def test_a_rapid_move_has_no_feed(self):
        from wop.ui.sketch_session import SketchSession

        sample = CustomPathBlock.sample("p", 1, RPM)
        self.model.replace_block(self.index, replace(self.model.blocks[self.index], sketch=sample.sketch))
        session = SketchSession(target=self.model.path_sketch_target(self.index))
        rapid = next(iter(session.sketch.rapid_pieces))
        session.selected_pieces = {rapid}
        self.assertFalse(session.set_piece_feed(0.2))
        self.assertIn("no feed", session.message)
        self.assertEqual(session.sketch.piece_feeds, {})
        feed = next(i for i in session.sketch.lines if i not in session.sketch.rapid_pieces and not session.sketch.is_locked_piece(i))
        session.selected_pieces = {feed}
        session.set_piece_feed(0.2)
        session.toggle_rapid()  # now a rapid: its feed goes
        self.assertNotIn(feed, session.sketch.piece_feeds)

    def test_the_sketch_target_has_the_safe_point_and_the_part_as_locked_things(self):
        target = self.model.path_sketch_target(self.index)
        self.assertEqual(target.mode.key, "path")
        self.assertEqual(target.locked_points[0].key, "safe point")
        self.assertTrue(any(line.key.startswith("outline/") for line in target.locked_lines))
        safety = self.model.program.safety
        self.assertEqual((target.locked_points[0].x, target.locked_points[0].z), (safety.safe_radius_mm, safety.safe_z_mm))

    def test_a_drawing_is_stored_in_the_block_and_undo_takes_it_back(self):
        from wop.core.sketch.sketch_io import sketch_to_dict
        from wop.ui.sketch_session import SketchSession

        self.model.replace_block(self.index, replace(self.model.blocks[self.index], sketch=None))
        before = self.model.blocks[self.index]
        session = SketchSession(target=self.model.path_sketch_target(self.index))
        safe = session.sketch.locked_points["safe point"]
        end = session.sketch.add_point(20, -10)
        session.sketch.add_line(safe, end)
        self.model.path_sketch_target(self.index).commit(session.result())
        stored = self.model.blocks[self.index]
        self.assertNotEqual(stored.sketch, before.sketch)
        self.assertEqual(stored.own_problem(), "")
        self.model.undo()
        self.assertEqual(self.model.blocks[self.index].sketch, before.sketch)

    def test_a_dimension_to_the_part_follows_a_part_that_moves_and_is_dropped_when_it_changes_shape(self):
        from wop.ui.sketch_session import SketchSession

        self.model.replace_block(self.index, replace(self.model.blocks[self.index], sketch=None))
        session = SketchSession(target=self.model.path_sketch_target(self.index))
        sketch = session.sketch
        part = next(i for k, i in sketch.locked_lines.items() if k.startswith("outline/"))
        safe = sketch.locked_points["safe point"]
        end = sketch.add_point(20, -10)
        sketch.add_line(safe, end)
        sketch.add_constraint("point_on_line", (end, part))
        stored = self.model.path_sketch_target(self.index)
        stored.commit(session.result())
        self.assertFalse(self.model.blocks[self.index].own_problem())
        sketch_again = SketchSession(target=self.model.path_sketch_target(self.index))
        self.assertEqual(sketch_again.notes, [])
        self.assertTrue(any(c.kind == "point_on_line" for c in sketch_again.sketch.constraints.values()))
        # a part of another shape: a raw part with a step has more pieces
        from wop.core.constants import CLAMP_PLANE_POINT
        from wop.core.sketch.model import Sketch
        from wop.core.sketch.modes import RAW_PART, contour_from_sketch

        shaft = Sketch()
        ids = [shaft.add_point(x, z) for x, z in ((0, 0), (10, 0), (10, -20), (15, -20), (15, -30), (15, -50), (0, -50))]
        for first, second in zip(ids, ids[1:]):
            shaft.add_line(first, second)
        shaft.label_point(ids[4], CLAMP_PLANE_POINT)
        self.model.draw_raw_part(contour_from_sketch(shaft, RAW_PART, "raw", "Raw part"))
        changed = SketchSession(target=self.model.path_sketch_target(self.index))
        self.assertTrue(any("shape changed" in n or "removed" in n for n in changed.notes))
        self.assertFalse(any(c.kind == "point_on_line" for c in changed.sketch.constraints.values()))


if __name__ == "__main__":
    unittest.main()
