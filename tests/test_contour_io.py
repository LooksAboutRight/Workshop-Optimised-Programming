import json
import unittest

from tests import reference_data
from wop.core.contour import (
    ArcCenterStep,
    ArcRadiusStep,
    Contour,
    ContourDefinition,
    ContourError,
    LineStep,
    chamfer,
    fillet,
)
from wop.core.files.contour_io import contour_from_dict, contour_to_dict
from wop.core.contour_solver import build_contour
from wop.core.geometry import ArcDirection, ArcSegment, LineSegment, Point


def round_trip(contour: Contour) -> Contour:
    """Through real JSON text, as the project file will do it."""
    return contour_from_dict(json.loads(json.dumps(contour_to_dict(contour))))


class RoundTripTests(unittest.TestCase):
    def test_five_lines_three_arcs_reload_unchanged(self):
        """Requirement C1: a prepared contour is created, saved and reloaded unchanged."""
        original = reference_data.five_lines_three_arcs_contour()
        lines = [s for s in original.segments if isinstance(s, LineSegment)]
        arcs = [s for s in original.segments if isinstance(s, ArcSegment)]
        self.assertEqual(len(lines), reference_data.FIVE_LINES_THREE_ARCS_LINE_COUNT)
        self.assertEqual(len(arcs), reference_data.FIVE_LINES_THREE_ARCS_ARC_COUNT)
        self.assertEqual(round_trip(original), original)

    def test_contour_without_definition_reloads_unchanged(self):
        """Contours from a DXF file have no definition."""
        original = Contour(
            "dxf-1", "from dxf", tuple(reference_data.rounded_end_profile()), None
        )
        reloaded = round_trip(original)
        self.assertEqual(reloaded, original)
        self.assertIsNone(reloaded.definition)

    def test_every_kind_of_step_reloads_unchanged(self):
        definition = ContourDefinition(
            Point(0, 0),
            (
                LineStep(Point(10, 0), chamfer(1)),
                LineStep(Point(10, -10), fillet(0.5)),
                LineStep(Point(5, -12)),
                ArcRadiusStep(Point(0, -20), 10, ArcDirection.CW, large_arc=True),
                ArcCenterStep(Point(0, -30), Point(0, -25), ArcDirection.CCW),
            ),
        )
        original = build_contour("steps", "all step kinds", definition)
        self.assertEqual(round_trip(original), original)

    def test_saved_data_is_plain_and_versioned(self):
        data = contour_to_dict(reference_data.five_lines_three_arcs_contour())
        self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertIn("format", data)

    def test_save_load_save_gives_identical_data(self):
        original = reference_data.five_lines_three_arcs_contour()
        first = json.dumps(contour_to_dict(original), sort_keys=True)
        second = json.dumps(contour_to_dict(round_trip(original)), sort_keys=True)
        self.assertEqual(first, second)


class InvalidDataTests(unittest.TestCase):
    def valid_data(self):
        return contour_to_dict(reference_data.five_lines_three_arcs_contour())

    def assert_rejected(self, data):
        with self.assertRaises(ContourError):
            contour_from_dict(data)

    def test_missing_key(self):
        data = self.valid_data()
        del data["segments"]
        self.assert_rejected(data)

    def test_not_a_dict(self):
        self.assert_rejected([1, 2, 3])

    def test_unknown_format_version(self):
        data = self.valid_data()
        data["format"] = data["format"] + 1
        self.assert_rejected(data)

    def test_unknown_segment_type(self):
        data = self.valid_data()
        data["segments"][0]["type"] = "spline"
        self.assert_rejected(data)

    def test_unknown_step_type(self):
        data = self.valid_data()
        data["definition"]["steps"][0]["type"] = "spline"
        self.assert_rejected(data)

    def test_bad_direction(self):
        data = self.valid_data()
        arc = next(item for item in data["segments"] if item["type"] == "arc")
        arc["direction"] = "sideways"
        self.assert_rejected(data)

    def test_arc_end_not_on_the_circle(self):
        data = self.valid_data()
        arc = next(item for item in data["segments"] if item["type"] == "arc")
        arc["end"] = [arc["end"][0] + 1, arc["end"][1]]
        self.assert_rejected(data)

    def test_coordinate_is_not_a_number(self):
        data = self.valid_data()
        data["segments"][0]["start"] = ["a", "b"]
        self.assert_rejected(data)

    def test_unknown_corner_kind(self):
        data = self.valid_data()
        data["definition"]["steps"][0]["corner"]["kind"] = "bevel"
        self.assert_rejected(data)


if __name__ == "__main__":
    unittest.main()
