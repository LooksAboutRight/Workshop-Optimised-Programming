"""The named points the sketch editor offers depend on who opened it."""

import unittest

from wop.core.constants import CHUCK_FACE_POINT, JAWS_MOUNT_POINT, TIP_POINT
from wop.core.lathe.workholding import CHUCK_KIND, JAWS_KIND
from wop.ui.point_kinds import TOOL_POINT_KINDS, WORKHOLDING_POINT_KINDS


def names(kinds):
    return [kind.name for kind in kinds]


class PointKindsTests(unittest.TestCase):
    def test_a_tool_offers_the_touch_off_point(self):
        self.assertIn(TIP_POINT, names(TOOL_POINT_KINDS))

    def test_only_the_touch_off_point_can_be_worked_out_from_the_shape(self):
        self.assertEqual([k.name for k in TOOL_POINT_KINDS if k.automatic], [TIP_POINT])

    def test_chuck_and_jaws_offer_their_own_points(self):
        self.assertEqual(names(WORKHOLDING_POINT_KINDS[JAWS_KIND]), [JAWS_MOUNT_POINT, "step"])
        self.assertEqual(names(WORKHOLDING_POINT_KINDS[CHUCK_KIND]), [CHUCK_FACE_POINT])



if __name__ == "__main__":
    unittest.main()
