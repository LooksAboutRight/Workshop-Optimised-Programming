import sys
import tempfile
import unittest
from pathlib import Path

from wop.core.contour import ContourError

try:
    import ezdxf

    HAS_EZDXF = True
except ModuleNotFoundError:
    HAS_EZDXF = False

if HAS_EZDXF:
    from wop.adapters.dxf_files import read_dxf
    from wop.core.contour_solver import build_contour
    from wop.core.dxf_contour import DxfArc, DxfLine, contour_from_drawing

requires_ezdxf = unittest.skipUnless(HAS_EZDXF, "ezdxf is not installed")


@requires_ezdxf
class DxfFileTests(unittest.TestCase):
    def write(self, build) -> Path:
        document = ezdxf.new()
        build(document.modelspace())
        folder = Path(tempfile.mkdtemp())
        path = folder / "part.dxf"
        document.saveas(path)
        return path

    def test_lines_arcs_and_a_polyline_are_read_and_unsupported_things_are_named(self):
        def build(space):
            space.add_line((0, 10), (-5, 10))
            space.add_arc((-5, 5), 5, 90, 180)
            space.add_lwpolyline([(-10, 5), (-10, 0.5)])
            space.add_circle((0, 0), 1)
            space.add_text("hello")

        drawing = read_dxf(self.write(build))
        self.assertEqual(sum(isinstance(e, DxfLine) for e in drawing.entities), 2)
        self.assertEqual(sum(isinstance(e, DxfArc) for e in drawing.entities), 1)
        self.assertTrue(any("CIRCLE" in n for n in drawing.notes))
        self.assertTrue(any("TEXT" in n for n in drawing.notes))

    def test_a_file_becomes_a_valid_contour(self):
        def build(space):
            space.add_line((0, 10), (-5, 10))
            space.add_arc((-5, 5), 5, 90, 180)
            space.add_line((-10, 5), (-10, 0.5))

        result = contour_from_drawing(read_dxf(self.write(build)))
        build_contour("c", "dxf", result.definition)

    def test_a_polyline_with_a_bulge_gives_an_arc(self):
        def build(space):
            space.add_lwpolyline([(0, 10, 0.4142135623730951), (-5, 5, 0)], format="xyb")

        drawing = read_dxf(self.write(build))
        self.assertEqual(sum(isinstance(e, DxfArc) for e in drawing.entities), 1)

    def test_points_are_named_by_the_text_next_to_them(self):
        def build(space):
            space.add_line((0, 10), (-5, 10))
            space.add_point((-2.0, 4.0))
            space.add_text("shank seat", dxfattribs={"insert": (-1.0, 5.0)})
            space.add_point((-30.0, 30.0))  # no text beside it

        drawing = read_dxf(self.write(build))
        self.assertEqual([(p.name, p.position) for p in drawing.points], [("shank seat", (-2.0, 4.0)), ("point 1", (-30.0, 30.0))])
        self.assertFalse(any("TEXT" in n for n in drawing.notes))  # the text was used

    def test_a_missing_file_gives_a_readable_error(self):
        with self.assertRaises(ContourError):
            read_dxf(Path(tempfile.mkdtemp()) / "nothing.dxf")


class WithoutLibraryTests(unittest.TestCase):
    def test_a_missing_library_says_how_to_install_it(self):
        """Runs everywhere: a None entry in sys.modules makes `import ezdxf` fail as if it were not installed."""
        from unittest import mock

        from wop.adapters.dxf_files import read_dxf

        with mock.patch.dict(sys.modules, {"ezdxf": None}):
            with self.assertRaises(ContourError) as raised:
                read_dxf(Path("x.dxf"))
        self.assertIn("pip install ezdxf", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
