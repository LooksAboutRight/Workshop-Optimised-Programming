import unittest

from wop.ui.sketch_text_place import box_hits_segment, boxes_overlap, candidate_boxes, crossings, pick_box

SIZE = (20.0, 10.0)
GAP = 4.0


def _centre(box):
    return box[0] + box[2] / 2, box[1] + box[3] / 2


class BoxAndLineTests(unittest.TestCase):
    BOX = (10.0, 10.0, 20.0, 10.0)  # x 10..30, y 10..20

    def test_a_line_through_the_box_hits_it(self):
        self.assertTrue(box_hits_segment(self.BOX, (0, 15), (40, 15)))
        self.assertTrue(box_hits_segment(self.BOX, (20, 0), (20, 40)))
        self.assertTrue(box_hits_segment(self.BOX, (0, 0), (40, 30)))  # diagonally across
        self.assertTrue(box_hits_segment(self.BOX, (15, 12), (25, 18)))  # wholly inside

    def test_a_line_beside_or_short_of_the_box_does_not(self):
        self.assertFalse(box_hits_segment(self.BOX, (0, 25), (40, 25)))
        self.assertFalse(box_hits_segment(self.BOX, (0, 15), (8, 15)))  # stops before it
        self.assertFalse(box_hits_segment(self.BOX, (0, 0), (40, 5)))
        self.assertFalse(box_hits_segment(self.BOX, (10, 0), (10, 40)))  # along the edge only

    def test_boxes_overlap(self):
        self.assertTrue(boxes_overlap(self.BOX, (25, 15, 20, 10)))
        self.assertFalse(boxes_overlap(self.BOX, (30, 10, 20, 10)))  # they only touch


class CandidateTests(unittest.TestCase):
    def test_a_horizontal_line_has_its_number_above_the_middle_first(self):
        boxes = candidate_boxes((0, 100), (200, 100), SIZE, GAP)
        centre = _centre(boxes[0])
        self.assertEqual(centre[0], 100)  # in the middle along the line
        self.assertLess(centre[1], 100)  # above it (y grows downwards)
        self.assertFalse(box_hits_segment(boxes[0], (0, 100), (200, 100)))  # and clear of it

    def test_a_vertical_line_has_its_number_to_the_right_first(self):
        boxes = candidate_boxes((100, 0), (100, 200), SIZE, GAP)
        centre = _centre(boxes[0])
        self.assertEqual(centre[1], 100)
        self.assertGreater(centre[0], 100)
        self.assertFalse(box_hits_segment(boxes[0], (100, 0), (100, 200)))

    def test_every_candidate_is_clear_of_its_own_line(self):
        for start, end in (((0, 0), (100, 60)), ((100, 60), (0, 0)), ((0, 0), (0, 80)), ((0, 0), (90, 0))):
            for box in candidate_boxes(start, end, SIZE, GAP):
                self.assertFalse(box_hits_segment(box, start, end), (start, end, box))

    def test_the_number_never_leaves_its_side_or_the_span_of_the_line(self):
        for start, end in (((0, 100), (200, 100)), ((100, 0), (100, 200)), ((0, 0), (160, 90)), ((160, 90), (0, 0))):
            boxes = candidate_boxes(start, end, SIZE, GAP)
            for box in boxes:
                centre = _centre(box)
                self.assertTrue(min(start[0], end[0]) <= centre[0] <= max(start[0], end[0]) or abs(start[0] - end[0]) < 1)
                self.assertTrue(min(start[1], end[1]) - SIZE[1] <= centre[1] <= max(start[1], end[1]) + SIZE[1] or abs(start[1] - end[1]) < 1)
            sides = {round((_centre(b)[0] - start[0]) * (end[1] - start[1]) - (_centre(b)[1] - start[1]) * (end[0] - start[0]) > 0) for b in boxes}
            self.assertEqual(len(sides), 1)  # all on one side of the line

    def test_up_for_a_horizontal_or_slanted_line_and_right_for_a_vertical_one_whichever_way_it_was_drawn(self):
        for start, end in (((0, 100), (200, 100)), ((200, 100), (0, 100)), ((0, 0), (160, 90)), ((160, 90), (0, 0)), ((0, 0), (160, -90))):
            first = _centre(candidate_boxes(start, end, SIZE, GAP)[0])
            middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            self.assertLess(first[1], middle[1])  # above (y grows downwards)
        for start, end in (((100, 0), (100, 200)), ((100, 200), (100, 0))):
            first = _centre(candidate_boxes(start, end, SIZE, GAP)[0])
            self.assertGreater(first[0], 100)  # to the right
            self.assertAlmostEqual(first[1], 100)  # in the middle between the ends

    def test_a_point_has_places_all_round_it(self):
        boxes = candidate_boxes((50, 50), (50, 50), SIZE, GAP, along_a_line=False)
        self.assertTrue(any(_centre(b)[1] < 50 for b in boxes) and any(_centre(b)[1] > 50 for b in boxes))


class PickTests(unittest.TestCase):
    def setUp(self):
        self.line = ((0.0, 100.0), (200.0, 100.0))
        self.candidates = candidate_boxes(*self.line, SIZE, GAP)

    @staticmethod
    def _vertical_in(box):
        """A line that crosses this place and no other."""
        x = _centre(box)[0]
        return [((x, box[1] - 2), (x, box[1] + box[3] + 2))]

    @staticmethod
    def _horizontal_in(box):
        y = _centre(box)[1]
        return [((box[0] - 2, y), (box[0] + box[2] + 2, y))]

    def test_the_first_place_is_used_when_nothing_is_in_the_way(self):
        self.assertEqual(pick_box(self.candidates, [[self.line]], []), self.candidates[0])

    def test_a_line_through_the_first_place_slides_the_number_along_its_line(self):
        crossing = ((100.0, 60.0), (100.0, 100.0))  # a model line standing on the dimension line, where the number would be
        chosen = pick_box(self.candidates, [[self.line], [crossing]], [])
        self.assertNotEqual(chosen, self.candidates[0])
        self.assertFalse(box_hits_segment(chosen, *crossing))
        self.assertLess(_centre(chosen)[1], 100)  # still above the dimension line
        self.assertTrue(0 <= _centre(chosen)[0] <= 200)  # and between its ends

    def test_another_number_in_the_way_moves_it_too(self):
        chosen = pick_box(self.candidates, [[self.line]], [self.candidates[0]])
        self.assertNotEqual(chosen, self.candidates[0])
        self.assertLess(_centre(chosen)[1], 100)

    def test_when_every_place_is_crossed_it_ignores_one_line_and_still_avoids_the_others(self):
        # one line in the way in the middle, two lines in the way everywhere else: nowhere is free,
        # and the place where only a single line is in the way is the one to take
        middle = self.candidates[0]
        lines = [self._vertical_in(middle)]
        for box in self.candidates[1:]:
            lines += [self._vertical_in(box), self._horizontal_in(box)]
        self.assertEqual(crossings(middle, lines, []), 1)
        self.assertTrue(all(crossings(box, lines, []) == 2 for box in self.candidates[1:]))
        self.assertEqual(pick_box(self.candidates, lines, []), middle)

    def test_it_takes_the_place_with_fewest_lines_even_when_it_is_not_the_middle(self):
        middle, other = self.candidates[0], self.candidates[3]
        lines = [self._vertical_in(middle), self._horizontal_in(middle)]  # two lines on the middle place
        for box in self.candidates:
            if box not in (middle, other):
                lines += [self._vertical_in(box), self._horizontal_in(box)]
        lines.append(self._vertical_in(other))  # one line on the other place
        self.assertEqual(pick_box(self.candidates, lines, []), other)

    def test_a_curve_made_of_many_pieces_counts_as_one_line(self):
        centre = _centre(self.candidates[0])
        curve = [((centre[0], centre[1] - 8 + i), (centre[0], centre[1] - 7 + i)) for i in range(14)]  # 14 pieces, one line
        self.assertEqual(crossings(self.candidates[0], [curve], []), 1)

    def test_the_least_crossed_place_stays_on_its_side_and_between_the_ends(self):
        field = [[((x, 70.0), (x, 130.0))] for x in range(0, 201, 10)]  # lines across the whole length of the dimension line
        lines = [[self.line], *field]
        chosen = pick_box(self.candidates, lines, [])
        self.assertLess(_centre(chosen)[1], 100)
        self.assertTrue(0 <= _centre(chosen)[0] <= 200)
        self.assertEqual(crossings(chosen, lines, []), min(crossings(box, lines, []) for box in self.candidates))


if __name__ == "__main__":
    unittest.main()
