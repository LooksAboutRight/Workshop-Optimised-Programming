"""Write one small example project per block type (examples/blocks/<type>.wop.json), except the custom path: its example (trepanning with a custom tool) is saved from the window.

Usage (project root):  python tools/make_block_examples.py [folder]
Each project is a new project with one block of that type (a drilling, grooving or threading block with a tool of its own type) with the cutting values of `example_values.py`. A turning contour block
gets a stepped shaft contour (small at the free end, bigger towards the chuck: a right-hand tool can cut it). The files are also used by tests/test_block_examples.py.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from wop.core.contour import ContourDefinition, LineStep  # noqa: E402
from wop.core.contour_solver import build_contour  # noqa: E402
from wop.core.geometry import Point  # noqa: E402
from wop.core.blocks import BLOCK_TYPES  # noqa: E402
from wop.core.blocks.custom_path import CustomPathBlock  # noqa: E402
from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.model.helpers import new_project, with_starter_tools  # noqa: E402
from example_values import CUSTOM_PATH, DRILLING, FACING, GROOVING, ROUGHING, THREADING, with_values  # noqa: E402

DEFAULT_FOLDER = PROJECT_ROOT / "examples" / "blocks"
SHAFT_POINTS = ((8, 0), (8, -10), (12, -10), (12, -25), (14, -25), (14, -40))  # small at the free end, bigger towards the chuck
CONTOUR_BLOCK = "turning_contour"
SAVED_FROM_THE_WINDOW = ("custom_path",)  # a project of two blocks and a tool of its own: no tool writes it
VALUES = {"facing": FACING, "turning": ROUGHING, "turning_contour": ROUGHING, "grooving": GROOVING, "drilling": DRILLING, "threading": THREADING, "custom_path": CUSTOM_PATH}  # what a lathe does, not what a new block gets
TOOL_OF_BLOCK = {"drilling": "drill", "grooving": "groove", "threading": "thread"}  # the tool type these blocks are made for


def example_model(type_name: str) -> AppModel:
    model = AppModel(project=with_starter_tools(new_project()))
    index = model.add_block(type_name)
    if type_name in TOOL_OF_BLOCK:
        number = model.add_tool_of_type(TOOL_OF_BLOCK[type_name])
        model.replace_block(index, replace(model.blocks[index], tool_number=number))
        model.select(index)
    if type_name == "custom_path":  # a new block has nothing drawn; the example project shows a small path
        block = model.blocks[index]
        model.replace_block(index, replace(block, sketch=CustomPathBlock.sample(block.block_id, block.tool_number, block.spindle).sketch))
    if type_name == CONTOUR_BLOCK:
        steps = tuple(LineStep(Point(x, z)) for x, z in SHAFT_POINTS[1:])
        shaft = build_contour("shaft", "stepped shaft", ContourDefinition(Point(*SHAFT_POINTS[0]), steps))
        model.set_contour(shaft)
        model.replace_block(index, replace(model.blocks[index], contour_id="shaft"))
    if type_name in VALUES:
        model.replace_block(index, with_values(model.blocks[index], VALUES[type_name]))
    return model


def main(argv: list[str]) -> None:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for type_name in BLOCK_TYPES.names():
        if type_name in SAVED_FROM_THE_WINDOW:
            continue
        model = example_model(type_name)
        path = folder / f"{type_name}.wop.json"
        model.save(path, with_part=False)
        print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
