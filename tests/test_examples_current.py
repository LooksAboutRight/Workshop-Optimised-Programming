"""The example projects in examples/ are what the tools that make them write today.

A change of the model (a new field, another default) changes what `tools/make_*.py` write. The committed examples must
follow: run the tools again (see tools/TOOLS.md) and commit the result. The files still load when they are older, but an
old example hides what a project looks like now.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SINGLE_FILES = (
    ("make_example_project.py", "examples/reference.wop.json"),
    ("make_collision_demo.py", "tests/data/projects/collision_demo.wop.json"),
    ("make_compensation_test.py", "tests/data/projects/compensation_test.wop.json"),
    ("make_example_machine.py", "examples/example.machine.json"),
    ("make_example_post.py", "examples/posts/linuxcnc_custom_function.post.ini"),
)


def same_text(a: Path, b: Path) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def run(tool: str, target: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / tool), str(target)], check=True, capture_output=True, cwd=ROOT)


class ExamplesAreCurrentTests(unittest.TestCase):
    def test_the_single_example_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            for tool, committed in SINGLE_FILES:
                with self.subTest(example=committed):
                    made = Path(folder) / Path(committed).name
                    run(tool, made)
                    self.assertTrue(same_text(made, ROOT / committed), f"run tools/{tool} and commit {committed}")

    def test_the_block_examples(self):
        with tempfile.TemporaryDirectory() as folder:
            run("make_block_examples.py", Path(folder))
            for made in sorted(Path(folder).glob("*.wop.json")):
                with self.subTest(example=made.name):
                    self.assertTrue(same_text(made, ROOT / "examples" / "blocks" / made.name), f"run tools/make_block_examples.py and commit {made.name}")

    def test_every_shipped_project_loads_and_plans_with_its_post_in_place(self):
        """The pawn and the rest-machining example are saved from the window (no tool writes them): after a change of the model they must
        still open without a notice, plan every block and find the post of their machine."""
        from wop.adapters.post_library import load_post_library
        from wop.adapters.project_files import load_project
        from wop.core.files.project_io import program_problems
        from wop.core.program_model.program import plan_program

        library = load_post_library()
        for path in sorted((ROOT / "examples").rglob("*.wop.json")):
            with self.subTest(example=path.relative_to(ROOT).as_posix()):
                project = load_project(path)
                self.assertEqual(program_problems(project.program), [])
                self.assertEqual(plan_program(project.program).left_out, ())
                if project.machine is not None:
                    self.assertEqual(library.choose(project.machine.postprocessor)[1], "", "the post of the machine of the project is not there")

    def test_the_machine_tests_are_made_on_demand_and_load(self):
        """They are not kept in the repository: the tool makes them for the day on the lathe (`tools/make_machine_tests.py`)."""
        from wop.adapters.project_files import load_project

        with tempfile.TemporaryDirectory() as folder:
            run("make_machine_tests.py", Path(folder))
            made_files = sorted(Path(folder).glob("*.*"))
            self.assertEqual(len(made_files), 8)  # eight projects
            for made in made_files:
                if made.name.endswith(".wop.json"):
                    with self.subTest(example=made.name):
                        load_project(made)


if __name__ == "__main__":
    unittest.main()
