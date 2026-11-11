"""The sketch editor on the program's own shapes and contours: every one must open and give back the same outline."""

import unittest
from pathlib import Path

from wop.core.sketch.modes import TURNING, WORKHOLDING, contour_from_sketch, sketch_from_contour
from wop.core.lathe.workholding import CHUCK_KIND, JAWS_KIND
from wop.ui.sketch_session import SketchSession

from wop.ui.app_model import AppModel

ROOT = Path(__file__).parent.parent


def _same(first, second) -> bool:
    def key(segment):
        parts = [type(segment).__name__, segment.start.x, segment.start.z, segment.end.x, segment.end.z]
        if hasattr(segment, "center"):
            parts += [segment.center.x, segment.center.z]
        return tuple(p if isinstance(p, str) else round(p, 6) for p in parts)

    return sorted(map(key, first)) == sorted(map(key, second))


class RealShapeTests(unittest.TestCase):
    def test_every_tool_type_opens_and_gives_its_outline_back(self):
        model = AppModel()
        for type_name, label in model.tool_type_choices():
            with self.subTest(label):
                number = model.add_tool_of_type(type_name)
                tool = model.program.tool(number)
                session = SketchSession(target=model.tool_sketch_target(number))
                self.assertEqual(session.problems, [])
                back = session.result()
                self.assertTrue(_same([p.segment for p in tool.shape.pieces], back.segments))
                self.assertEqual(sum(back.cutting), sum(p.role.name == "CUTTER" for p in tool.shape.pieces))
                self.assertEqual({p.name for p in back.points}, {p.name for p in tool.points})
                session.target.commit(back)
                self.assertTrue(_same([p.segment for p in model.program.tool(number).shape.pieces], back.segments))

    def test_every_workholding_type_opens(self):
        model = AppModel()
        model.new_library("workholding", "Test")
        for kind in (JAWS_KIND, CHUCK_KIND):
            with self.subTest(kind):
                name = model.add_workholding_item(kind)
                target = model.workholding_sketch_target(name)
                session = SketchSession(target=target)
                self.assertEqual(session.problems, [])
                self.assertTrue(_same(target.contour.segments, session.result().segments))

    def test_every_contour_of_the_examples_opens(self):
        from wop.adapters.project_files import load_project  # only the contours are needed: the file, not the window model (which plans every block)

        found = 0
        for path in sorted((ROOT / "examples").glob("*.wop.json")) + sorted((ROOT / "tests" / "data" / "projects").glob("*.wop.json")):
            for contour in load_project(path).program.contours:
                if not contour.is_valid:
                    continue
                with self.subTest(f"{path.name} {contour.name}"):
                    found += 1
                    sketch = sketch_from_contour(contour)
                    mode = WORKHOLDING if contour.is_closed else TURNING
                    again = contour_from_sketch(sketch, mode, contour.contour_id, contour.name)
                    self.assertTrue(_same(contour.segments, again.segments))
        self.assertGreater(found, 0)


if __name__ == "__main__":
    unittest.main()
