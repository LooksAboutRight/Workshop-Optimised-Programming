"""Relations and changes as a tool of the sketch editor: press the button, then click what it acts on."""

import unittest

from wop.core.geometry import Point
from wop.core.sketch.constants import ORIGIN
from wop.ui.sketch_constants import TOOL_ACTION, TOOL_LINE, TOOL_SELECT
from wop.core.sketch.modes import WORKHOLDING
from wop.core.lathe.workholding import JAWS_KIND
from wop.ui.point_kinds import WORKHOLDING_POINT_KINDS
from wop.ui.sketch_session import SketchSession
from wop.ui.sketch_target import SketchTarget

TOL = 0.5


def _click(session: SketchSession, x: float, z: float) -> None:
    session.move_hover(Point(x, z), TOL)
    session.press(Point(x, z), TOL)
    session.release(Point(x, z), TOL)


def _lines(*chains: tuple[tuple[float, float], ...]) -> SketchSession:
    session = SketchSession()
    session.snapping = False
    for chain in chains:
        session.set_tool(TOOL_LINE)
        for x, z in chain:
            _click(session, x, z)
        session.cancel()
    session.set_tool(TOOL_SELECT)
    return session


def _kinds(session: SketchSession) -> list[str]:
    return [c.kind for c in session.sketch.constraints.values()]


class ActionToolTests(unittest.TestCase):
    def test_one_selected_point_waits_for_a_second_pick_and_never_takes_the_origin_by_itself(self):
        for name, kind in (("horizontal", "horizontal"), ("vertical", "vertical")):
            with self.subTest(name):
                session = _lines(((3, 4), (8, 9)))
                _click(session, 3, 4)  # one point of the line
                self.assertEqual(len(session.selected_points), 1)
                session.use_relation(name)
                self.assertEqual((session.tool, session.armed), (TOOL_ACTION, name))
                self.assertEqual(len(session.selected_points), 1)  # still the first pick
                self.assertEqual(_kinds(session), [])  # nothing was made against the origin
                self.assertIn("second point", session.message)
                _click(session, 8, 9)
                self.assertEqual(_kinds(session), [kind])

    def test_the_origin_is_a_valid_second_pick(self):
        session = _lines(((3, 4), (8, 9)))
        _click(session, 3, 4)
        session.use_relation("horizontal")
        _click(session, 0, 0)
        constraint = next(iter(session.sketch.constraints.values()))
        self.assertEqual(constraint.kind, "horizontal")
        self.assertIn(ORIGIN, constraint.refs)

    def test_two_selected_points_still_make_the_relation_at_once(self):
        session = _lines(((3, 4), (8, 9)))
        _click(session, 3, 4)
        session.press(Point(8, 9), TOL, True)  # Ctrl adds
        session.release(Point(8, 9), TOL, True)
        session.use_relation("horizontal")
        self.assertEqual((_kinds(session), session.armed), (["horizontal"], ""))

    def test_ctrl_adds_a_thing_and_a_second_ctrl_click_takes_it_away(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (25, 10)))
        _click(session, 2.5, 5)
        for x, z in ((22.5, 5), (22.5, 5)):
            session.press(Point(x, z), TOL, True)
            session.release(Point(x, z), TOL, True)
            if x == 22.5 and len(session.selected_pieces) == 2:
                self.assertEqual(len(session.selected_pieces), 2)
        self.assertEqual(len(session.selected_pieces), 1)  # the second Ctrl click on the same line took it away

    def test_the_button_turns_the_tool_on_and_off(self):
        session = _lines(((0, 0), (5, 10)))
        session.use_relation("parallel")
        self.assertEqual((session.tool, session.armed), (TOOL_ACTION, "parallel"))
        self.assertIn("two lines", session.prompt)
        session.use_relation("parallel")
        self.assertEqual((session.tool, session.armed), (TOOL_SELECT, ""))

    def test_a_fitting_selection_is_used_at_once_and_the_tool_stays_off(self):
        session = _lines(((0, 0), (5, 10)))
        _click(session, 2.5, 5)
        session.use_relation("horizontal")
        self.assertEqual(_kinds(session), ["horizontal"])
        self.assertEqual(session.armed, "")

    def test_two_lines_picked_one_after_the_other_and_the_tool_stays_on(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)), ((40, 0), (47, 9)))
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        self.assertEqual(_kinds(session), [])
        self.assertEqual(len(session.selected_pieces), 1)  # picked, shown as selected
        _click(session, 25, 6)
        self.assertEqual(_kinds(session), ["parallel"])
        self.assertEqual(session.selected_pieces, set())  # ready for the next pair
        self.assertEqual(session.armed, "parallel")
        _click(session, 25, 6)
        _click(session, 43.5, 4.5)
        self.assertEqual(_kinds(session), ["parallel", "parallel"])

    def test_a_click_that_does_not_fit_is_ignored(self):
        session = _lines(((0, 0), (5, 10)))
        session.use_relation("parallel")
        _click(session, 100, 100)  # nothing there
        _click(session, 0, 0)  # a point: Parallel takes lines only
        self.assertEqual(session.selected_points, set())
        self.assertEqual(session.armed, "parallel")
        _click(session, 2.5, 5)
        _click(session, 2.5, 5)  # the same line again takes it back
        self.assertEqual(session.selected_pieces, set())

    def test_the_origin_levels_a_point(self):
        session = _lines(((3, 4), (8, 9)))
        session.use_relation("horizontal")
        _click(session, 3, 4)
        self.assertEqual(_kinds(session), [])  # one point waits for a second point
        _click(session, 0, 0)  # the origin
        self.assertEqual(_kinds(session), ["horizontal"])
        self.assertIn(ORIGIN, next(iter(session.sketch.constraints.values())).refs)
        self.assertNotIn(ORIGIN, session.selected_points)

    def test_a_line_levels_with_one_click(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.use_relation("vertical")
        _click(session, 2.5, 5)
        _click(session, 25, 6)
        self.assertEqual(_kinds(session), ["vertical", "vertical"])

    def test_a_relation_that_cannot_be_made_says_why_and_starts_again(self):
        session = _lines(((0, 0), (5, 10)))
        session.use_relation("point_on")
        _click(session, 0, 0)  # an end of the line
        _click(session, 2.5, 5)
        self.assertEqual(_kinds(session), [])
        self.assertIn("belongs", session.message)
        self.assertEqual((session.armed, session.selected_points, session.selected_pieces), ("point_on", set(), set()))

    def test_fix_and_the_marks_act_on_every_click(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.use_relation("fixed")
        _click(session, 2.5, 5)
        self.assertEqual(sorted(set(_kinds(session))), ["fixed"])
        session.set_tool(TOOL_SELECT)
        session.use_modify("construction")
        _click(session, 25, 6)
        self.assertEqual([line.construction for line in session.sketch.lines.values()], [False, True])
        _click(session, 25, 6)  # the same again turns it back
        self.assertEqual([line.construction for line in session.sketch.lines.values()], [False, False])

    def test_fillet_uses_the_size_asked_for_once_on_every_corner_clicked(self):
        session = _lines(((0, 0), (0, 10), (10, 10), (10, 20)))
        session.use_modify("fillet", 2)
        _click(session, 0, 10)
        self.assertEqual(len(session.sketch.arcs), 1)
        _click(session, 10, 10)
        self.assertEqual(len(session.sketch.arcs), 2)
        self.assertEqual(session.armed, "fillet")
        _click(session, 0, 0)  # an end, not a corner: nothing is made
        self.assertEqual(len(session.sketch.arcs), 2)

    def test_right_click_forgets_the_picks_then_turns_the_tool_off_and_escape_turns_it_off(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        session.cancel()
        self.assertEqual((session.armed, session.selected_pieces), ("parallel", set()))
        session.cancel()
        self.assertEqual(session.armed, "")
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        session.escape()
        self.assertEqual((session.armed, session.selected_pieces), ("", set()))

    def test_another_button_while_one_is_on_starts_that_one_without_using_the_picks(self):
        session = _lines(((0, 0), (5, 10)))
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        session.use_relation("fixed")
        self.assertEqual((session.armed, session.selected_pieces, _kinds(session)), ("fixed", set(), []))


class ConstraintMembersTests(unittest.TestCase):
    def test_a_chosen_relation_shows_what_it_acts_on_without_selecting_it(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        _click(session, 25, 6)
        session.set_tool(TOOL_SELECT)
        self.assertEqual(session.constraint_members(), (set(), set()))  # none chosen
        (constraint_id,) = session.sketch.constraints
        session.select_constraint(constraint_id)
        self.assertEqual(session.constraint_members(), (set(), set(session.sketch.lines)))
        self.assertEqual((session.selected_points, session.selected_pieces), (set(), set()))

    def test_a_dimension_from_the_origin_names_the_origin_and_a_point(self):
        session = _lines(((3, 4), (8, 9)))
        session.use_relation("horizontal")
        _click(session, 3, 4)
        _click(session, 0, 0)
        (constraint_id,) = session.sketch.constraints
        session.select_constraint(constraint_id)
        points, pieces = session.constraint_members()
        self.assertIn(ORIGIN, points)
        self.assertEqual(len(points), 2)
        self.assertEqual(pieces, set())


class SelectionDropTests(unittest.TestCase):
    def test_a_new_mode_and_escape_drop_the_selection_and_the_chosen_relation(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.use_relation("parallel")
        _click(session, 2.5, 5)
        _click(session, 25, 6)
        session.set_tool(TOOL_SELECT)
        (constraint_id,) = session.sketch.constraints
        session.select_constraint(constraint_id)
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session.set_tool(TOOL_LINE)
        self.assertEqual((session.selected_pieces, session.selected_constraint), (set(), None))
        session.select_constraint(constraint_id)
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session.escape()  # also while the select tool is on
        self.assertEqual((session.selected_pieces, session.selected_constraint), (set(), None))

    def test_the_mirror_tool_keeps_the_selection_it_is_started_with(self):
        session = _lines(((0, 0), (5, 10)), ((20, 0), (30, 12)))
        session.selected_pieces = {next(iter(session.sketch.lines))}
        session.set_tool("mirror")
        self.assertEqual(len(session.selected_pieces), 1)


class NamedPointTests(unittest.TestCase):
    def _jaws(self) -> SketchSession:
        session = SketchSession(target=SketchTarget(WORKHOLDING, "jaws", point_kinds=WORKHOLDING_POINT_KINDS[JAWS_KIND]))
        session.snapping = False
        session.set_tool(TOOL_LINE)
        for x, z in ((0, 0), (10, 0), (10, -10), (0, -10), (0, 0)):
            _click(session, x, z)
        session.cancel()
        session.set_tool(TOOL_SELECT)
        return session

    def test_a_name_button_names_a_point_and_the_same_click_again_takes_it_away(self):
        session = self._jaws()
        session.use_name("mount")
        self.assertEqual(session.armed, "name:mount")
        self.assertIn("Mount", session.prompt)
        _click(session, 10, 0)
        self.assertEqual(list(session.sketch.labels), ["mount"])
        self.assertEqual(session.armed, "name:mount")  # still on
        _click(session, 10, -10)  # another point: the name moves there
        self.assertEqual(session.sketch.labels["mount"], session.pickable_point(Point(10, -10), TOL))
        self.assertEqual(len(session.sketch.labels), 1)
        _click(session, 10, -10)  # the point that has the name: it is taken away
        self.assertEqual(session.sketch.labels, {})

    def test_steps_are_numbered_and_the_selected_point_is_named_at_once(self):
        session = self._jaws()
        for z in (-10, 0):
            session.selected_points = {session.pickable_point(Point(10, z), TOL)}
            session.use_name("step")
        self.assertEqual(sorted(session.sketch.labels), ["step 1", "step 2"])
        self.assertEqual(session.armed, "")  # a selected point: done at once, the tool did not turn on
        session.selected_points = {session.sketch.labels["step 1"]}
        session.use_name("step")  # the same button on a point with a step name takes it away
        self.assertEqual(sorted(session.sketch.labels), ["step 2"])
        session.selected_points = {session.pickable_point(Point(0, 0), TOL)}
        session.use_name("step")
        self.assertEqual(sorted(session.sketch.labels), ["step 1", "step 2"])  # the free number is used again


if __name__ == "__main__":
    unittest.main()
