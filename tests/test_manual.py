"""The sources of the user manual (docs/manual) hang together: every file it reads and every picture it shows exists, and every
reference points at a label. (Building the PDF needs LaTeX and is done by tools/make_manual.py; this test needs nothing.)"""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "docs" / "manual"
SOURCES = [MANUAL / "main.tex", MANUAL / "preamble.tex", *sorted((MANUAL / "chapters").glob("*.tex"))]


def _text(files) -> str:
    return "".join(path.read_text(encoding="utf-8") for path in files)


def _shots() -> set[str]:
    chapters = [MANUAL / "main.tex", *sorted((MANUAL / "chapters").glob("*.tex"))]
    return set(re.findall(r"\\shot(?:\[[^\]]*\])?\{([^}]+)\}", _text(chapters)))


class ManualSourceTests(unittest.TestCase):
    def test_every_file_that_is_read_exists(self):
        missing = [
            name for name in re.findall(r"\\input\{([^}]+)\}", _text(SOURCES))
            if not (MANUAL / f"{name}.tex").is_file()
        ]
        self.assertEqual(missing, [])

    def test_every_chapter_file_is_used(self):
        used = set(re.findall(r"\\input\{chapters/([^}]+)\}", (MANUAL / "main.tex").read_text(encoding="utf-8")))
        on_disk = {path.stem for path in (MANUAL / "chapters").glob("*.tex")}
        self.assertEqual(on_disk - used, set())  # a chapter that nobody reads would be lost work

    def test_every_picture_is_in_the_images_folder(self):
        shots = _shots()
        self.assertTrue(shots)
        self.assertEqual([name for name in sorted(shots) if not (MANUAL / "images" / f"{name}.png").is_file()], [])

    def test_the_tool_makes_the_pictures_the_manual_shows(self):
        spec = importlib.util.spec_from_file_location("make_manual", ROOT / "tools" / "make_manual.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        made = {name for _source, name in tool.PICTURES} | set(tool.COMPOSED)
        self.assertEqual(sorted(_shots() - made), [])  # a picture that the tool does not make would go out of date

    def test_the_two_lists_of_composed_pictures_are_the_same(self):
        spec = importlib.util.spec_from_file_location("make_manual", ROOT / "tools" / "make_manual.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        scenes = (ROOT / "tools" / "manual_scenes.py").read_text(encoding="utf-8")
        listed = re.search(r"^COMPOSED = \(([^)]*)\)", scenes, flags=re.M).group(1)
        self.assertEqual(tuple(re.findall(r'"([^"]+)"', listed)), tool.COMPOSED)

    def test_every_reference_has_a_label_and_labels_are_not_used_twice(self):
        text = _text(SOURCES)
        labels = re.findall(r"\\label\{([^}]+)\}", text) + [f"fig:{name}" for name in _shots()]
        self.assertEqual(len(labels), len(set(labels)), "a label is used twice")
        refs = set(re.findall(r"\\(?:ref|pageref|autoref)\{([^}]+)\}", text))
        self.assertEqual(sorted(refs - set(labels)), [])

    def test_the_contents_has_the_parts_and_the_chapters_have_sections(self):
        main = (MANUAL / "main.tex").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"\\part\{([^}]+)\}", main), ["Getting started", "The menus", "Making a program", "Reference"])
        for path in (MANUAL / "chapters").glob("*.tex"):
            if path.stem not in ("preface", "appendix_glossary"):
                self.assertIn("\\section{", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
