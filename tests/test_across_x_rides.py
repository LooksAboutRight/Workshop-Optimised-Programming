"""The ride up at the end of a line across X (the user, 2026-10-25: "the ride-up that normally goes to the previous line seems to go all the
way, a massive amount of double cutting the contour"). Across X the column above the end of a line runs along Z beside the part: through a part
that is wider towards the front, and past what stands under it. The ride now counts only the material to rough that is connected to the line
(not the part) and ends where it no longer cuts."""

import unittest

from tests.test_rough_follow import block, generate, holder_cnmg
from wop.core.blocks.base import BlockContext, Safety
from wop.core.blocks.turning_common import PassDirection
from wop.core.contour import Contour, ContourDefinition, LineStep
from wop.core.contour_solver import solve_contour
from wop.core.geometry import Point
from wop.core.program_model.raw_part import RawPart
from wop.core.program_model.stock import stock_region

RAW = RawPart("steel", 40, 60)
CONE = [(16, 0), (16, -4), (10, -14), (10, -30)]  # wider towards the front: the cone narrows towards the chuck
DEPTH_OF_CUT = 2  # of `tests.test_rough_follow.block`


def roughing_cuts(points):
    definition = ContourDefinition(Point(*points[0]), tuple(LineStep(Point(x, z)) for x, z in points[1:]))
    shape = Contour("c", "test", tuple(solve_contour(definition)), definition)
    context = BlockContext(RAW, holder_cnmg(), stock_region(RAW), Safety(30, 10, 1), contours=(shape,))
    return block(finish_pass=False, pass_direction=PassDirection.ALONG_X).roughing_cuts(context)


class AcrossXRideTests(unittest.TestCase):
    def test_no_ride_goes_far_beyond_the_line_before(self):
        for listed in roughing_cuts(CONE).cuts:
            if listed.kind.name == "LINE" and listed.ride:
                with self.subTest(line=listed.start):
                    self.assertLessEqual(abs(listed.ride[-1].end.x - listed.end.x), 2 * DEPTH_OF_CUT)  # across X the rise is along Z (x of the planner)
                    self.assertLessEqual(sum(piece.length for piece in listed.ride), 3 * DEPTH_OF_CUT)

    def test_the_shorter_rides_remove_as_much_as_before(self):
        result, _shape = generate(CONE, holder_cnmg(), RAW, finish_pass=False, pass_direction=PassDirection.ALONG_X)
        self.assertGreater(result.removed.area, 142.1)  # the long rides removed 142.14 mm2


if __name__ == "__main__":
    unittest.main()
