"""The finishing pass of the analytic planner (`analytic/cut_operations.finishing_pass`) and the test whether the nose can follow the contour
(`analytic/nose_follow.py`). The user's rule (2026-10-23): the pass follows the whole contour at the finishing feed, through the air too, never
shortened and never left; where the nose cannot follow, a note names the nose radius that would, and the checker reports what the tool does."""

import unittest
from pathlib import Path

from tests.helpers import planned
from tests.test_rough_follow import generate, holder_cnmg, path_of
from wop.adapters.project_files import load_project
from wop.core.analytic.nose_follow import largest_following_radius, misses
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point
from wop.core.nose_compensation import reference_path
from wop.core.program_model.operations import ArcMove, CompensationSide, LinearMove, MoveRole, Rapid
from wop.core.program_model.raw_part import RawPart

RAW = RawPart("steel", 40, 60)  # radius 20
SHAPE = [(10, 0), (14, -3), (14, -20)]
GROOVE = [(14, 0), (14, -10), (12, -10), (12, -11), (14, -11), (14, -20)]  # a groove 1 mm wide: a nose of 0.8 does not fit
BEYOND = [(10, 0), (10, -8), (25, -8), (25, -20)]  # the shoulder is drawn out to 25, beyond the bar (20)
NOSE = 0.8  # of `holder_cnmg`


def lines(points):
    return [LineSegment(Point(*a), Point(*b)) for a, b in zip(points, points[1:])]


def finishing_moves(operations, finish_feed):
    """The moves of the finishing pass: from the first to the last move at the finishing feed."""
    feeds = [i for i, op in enumerate(operations) if isinstance(op, (LinearMove, ArcMove)) and op.feed_mm_per_rev == finish_feed]
    return list(operations[feeds[0]:feeds[-1] + 1])


class FinishingPassTests(unittest.TestCase):
    FINISH_FEED = 0.07

    def pass_of(self, shape=SHAPE, **overrides):
        result, _shape = generate(shape, holder_cnmg(), RAW, finish_pass=True, finish_feed_mm_per_rev=self.FINISH_FEED, **overrides)
        return result

    def test_the_pass_is_the_whole_tool_path_at_the_finishing_feed_with_no_rapid(self):
        moves = finishing_moves(self.pass_of().operations, self.FINISH_FEED)
        self.assertFalse([move for move in moves if isinstance(move, Rapid)])
        pieces = reference_path(path_of(*SHAPE), holder_cnmg(), True)
        ends = [move.end for move in moves]
        for _index, piece in pieces[:-1]:  # the last piece of the shape is cut back by the wall the block adds up to the stock
            self.assertTrue(any(end.is_close(piece.end, 1e-6) for end in ends), piece.end)

    def test_a_wall_drawn_beyond_the_bar_is_followed_at_feed_through_the_air(self):
        moves = finishing_moves(self.pass_of(BEYOND).operations, self.FINISH_FEED)
        self.assertFalse([move for move in moves if isinstance(move, Rapid)])
        self.assertGreater(max(move.end.x for move in moves), 25 - 1e-6)

    def test_without_compensation_there_is_no_lead_in_or_out(self):
        roles = {getattr(op, "role", MoveRole.NORMAL) for op in self.pass_of().operations}
        self.assertEqual(roles, {MoveRole.NORMAL})

    def test_the_way_onto_the_contour_and_away_from_it_ends_and_begins_with_a_feed_move(self):
        operations = self.pass_of().operations
        moves = finishing_moves(operations, self.FINISH_FEED)
        first, last = operations.index(moves[0]), operations.index(moves[-1])
        self.assertIsInstance(next(op for op in operations[first + len(moves):] if hasattr(op, "end")), (Rapid, LinearMove))
        self.assertIsInstance(operations[first], LinearMove)  # the last stretch onto the material
        self.assertIsInstance(operations[last], (LinearMove, ArcMove))

    def test_a_contour_the_nose_follows_has_no_note(self):
        self.assertFalse([m for m in self.pass_of().messages if "nose" in m])

    def test_a_groove_narrower_than_the_nose_gets_a_note_with_the_radius_that_fits(self):
        notes = [m for m in self.pass_of(GROOVE).messages if "nose" in m]
        self.assertEqual(len(notes), 1)
        self.assertIn("needs a nose radius of 0.50 mm or smaller", notes[0])
        self.assertIn("between Z -10.", notes[0])

    def test_with_compensation_the_note_says_the_controller_may_refuse(self):
        notes = [m for m in self.pass_of(GROOVE, cutter_compensation=True).messages if "nose" in m]
        self.assertIn("controller may refuse", notes[0])

    def test_the_pass_is_not_shortened_where_the_nose_does_not_fit(self):
        moves = finishing_moves(self.pass_of(GROOVE).operations, self.FINISH_FEED)
        pieces = reference_path(lines(GROOVE), holder_cnmg(), True)
        self.assertGreaterEqual(len(moves), len(pieces) - 1)  # the tool path as it is: the checker reports where it cuts the part


class LeftHandToolTests(unittest.TestCase):
    def test_a_left_hand_tool_finishes_towards_the_front_with_the_compensation_on_its_left(self):
        program = load_project(Path(__file__).parent.parent / "examples" / "left_hand_rest_machining.wop.json").program
        operations = planned(program).blocks[4].operations  # block 5: the left-hand tool, with cutter compensation
        lead_in = next(op for op in operations if getattr(op, "role", None) is MoveRole.LEAD_IN)
        lead_out = next(op for op in operations if getattr(op, "role", None) is MoveRole.LEAD_OUT)
        self.assertIs(lead_in.side, CompensationSide.LEFT)
        self.assertLess(lead_in.end.z, lead_out.end.z)  # from the chuck side towards the front


class NoseFollowTests(unittest.TestCase):
    def test_a_sharp_inner_corner_is_followed(self):  # the nose leaves its own radius there: what a drawn sharp corner means
        self.assertEqual(misses(lines([(10, 0), (10, -10), (6, -10), (6, -20)]), True, NOSE), [])

    def test_a_groove_narrower_than_twice_the_nose_is_not(self):
        self.assertTrue(misses(lines(GROOVE), True, NOSE))
        self.assertEqual(misses(lines(GROOVE), True, 0.4), [])
        self.assertAlmostEqual(largest_following_radius(lines(GROOVE), True, NOSE), 0.5, delta=0.005)

    def test_a_concave_arc_smaller_than_the_nose_is_not(self):
        fillet = [
            LineSegment(Point(6, 0), Point(6, -9.7)), ArcSegment(Point(6, -9.7), Point(6.3, -10), Point(6.3, -9.7), ArcDirection.CCW),
            LineSegment(Point(6.3, -10), Point(10, -10)), LineSegment(Point(10, -10), Point(10, -20)),
        ]
        self.assertTrue(misses(fillet, True, NOSE))
        self.assertEqual(misses(fillet, True, 0.2), [])
        self.assertAlmostEqual(largest_following_radius(fillet, True, NOSE), 0.3, delta=0.01)

    def test_inside_the_free_side_is_towards_the_axis(self):
        bore = lines([(10, 0), (10, -10), (12, -10), (12, -11), (10, -11), (10, -20)])  # a groove 1 mm wide in the wall of a bore
        self.assertTrue(misses(bore, False, NOSE))
        self.assertEqual(misses(bore, False, 0.4), [])


if __name__ == "__main__":
    unittest.main()
