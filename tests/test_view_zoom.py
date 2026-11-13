import unittest

from wop.ui.ui_constants import ZOOM_MAX, ZOOM_MIN
from wop.ui.view_zoom import ZoomPan

BASE = (0.0, 100.0, 800.0, 400.0)  # the picture fitted in a window of 800 x 600
WINDOW = (0.0, 0.0, 800.0, 600.0)


def point_under(view, base, cursor):
    """The point of the picture under the cursor as a fraction of the picture."""
    x, y, width, height = view.view_rect(base)
    return ((cursor[0] - x) / width, (cursor[1] - y) / height)


class ZoomPanTests(unittest.TestCase):
    def test_without_zoom_the_picture_is_the_base_rectangle(self):
        self.assertEqual(ZoomPan().view_rect(BASE), BASE)

    def test_zooming_keeps_the_point_under_the_cursor(self):
        view = ZoomPan()
        cursor = (300.0, 250.0)
        before = point_under(view, BASE, cursor)
        view.zoom_at(cursor, BASE, 2.0, WINDOW)
        after = point_under(view, BASE, cursor)
        self.assertAlmostEqual(before[0], after[0])
        self.assertAlmostEqual(before[1], after[1])
        self.assertEqual(view.zoom, 2.0)

    def test_zoom_has_limits_and_zooming_out_fully_resets(self):
        view = ZoomPan()
        view.zoom_at((100, 200), BASE, 1e6, WINDOW)
        self.assertEqual(view.zoom, ZOOM_MAX)
        view.zoom_at((100, 200), BASE, 1e-6, WINDOW)
        self.assertEqual((view.zoom, view.origin), (ZOOM_MIN, (0.0, 0.0)))
        self.assertTrue(view.is_default)

    def test_a_picture_with_more_than_its_home_view_zooms_out_past_home_and_snaps_at_home(self):
        view = ZoomPan()
        view.zoom_at((400, 300), BASE, 1.2, WINDOW, 0.25)
        self.assertEqual(view.zoom, 1.2)
        view.zoom_at((400, 300), BASE, 1 / 1.2, WINDOW, 0.25)
        self.assertTrue(view.is_default)  # back at home exactly
        view.zoom_at((400, 300), BASE, 0.1, WINDOW, 0.25)
        self.assertEqual(view.zoom, 0.25)  # as far out as the whole picture
        view.pan_by(30, 10, BASE, WINDOW, 0.25)
        self.assertNotEqual(view.origin, (0.0, 0.0))  # it can be moved while it is smaller than home

    def test_panning_moves_the_picture_but_not_out_of_the_window(self):
        view = ZoomPan()
        view.zoom_at((400, 300), BASE, 4.0, WINDOW)
        x_before = view.view_rect(BASE)[0]
        view.pan_by(-50, 0, BASE, WINDOW)
        self.assertAlmostEqual(view.view_rect(BASE)[0], x_before - 50)
        view.pan_by(-1e6, -1e6, BASE, WINDOW)
        x, y, width, height = view.view_rect(BASE)
        self.assertGreater(x + width, 0)  # still a piece of the picture in the window
        self.assertGreater(y + height, 0)
        view.pan_by(1e6, 1e6, BASE, WINDOW)
        x, y, _w, _h = view.view_rect(BASE)
        self.assertLess(x, 800)
        self.assertLess(y, 600)

    def test_the_view_follows_a_bigger_window(self):
        view = ZoomPan()
        view.zoom_at((400, 300), BASE, 2.0, WINDOW)
        bigger = (0.0, 200.0, 1600.0, 800.0)
        x, y, width, height = view.view_rect(bigger)
        self.assertAlmostEqual(width, 3200)


if __name__ == "__main__":
    unittest.main()
