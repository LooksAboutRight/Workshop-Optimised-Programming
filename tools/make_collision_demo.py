"""Write tests/data/projects/collision_demo.wop.json: a project whose verification reports findings (to see how they look).

Usage (project root):  python tools/make_collision_demo.py [file]
The turning block cuts CUT_BEHIND_CLAMP_MM further towards the chuck than the part sticks out (a new project has no
chuck, so the flat clamping plane is checked), so the verification reports it.
Also used by tests/test_collision_demo.py.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.model.helpers import new_project, with_starter_tools  # noqa: E402

DEFAULT_FILE = PROJECT_ROOT / "tests" / "data" / "projects" / "collision_demo.wop.json"
CUT_BEHIND_CLAMP_MM = 5


def demo_model() -> AppModel:
    model = AppModel(project=with_starter_tools(new_project()))
    index = model.add_block("turning")
    block = model.blocks[index]
    raw = model.project.program.raw_part
    end_z = raw.front_z_mm - raw.length_outside_mm - CUT_BEHIND_CLAMP_MM
    model.replace_block(index, replace(block, name="Cuts into the chuck", end_z_mm=end_z))
    return model


def main(argv: list[str]) -> None:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    demo_model().save(path, with_part=False)
    print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
