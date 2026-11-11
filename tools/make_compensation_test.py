"""Write the project for the air-cut test of cutter compensation (tests/data/projects/compensation_test.wop.json).

Usage (project root):  python tools/make_compensation_test.py [file]
The project: facing, turning along a contour (roughing, 0.3 mm left), and the same contour as a finishing pass with
"Cutter compensation" ticked. The contour has a 45 degree chamfer at the front, a round corner, a long cylinder and a
taper, so a wrong reference point shows at the slope and at the arc, not only on the straight pieces.

Run it on the machine without material, once with a post that has cutter_compensation = yes and once with it set to no
(or untick the box), and compare the position of the tool at the points of the contour.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from wop.core.blocks.turning_common import PassDirection  # noqa: E402
from wop.core.contour import ArcCenterStep, ContourDefinition, LineStep  # noqa: E402
from wop.core.contour_solver import build_contour  # noqa: E402
from wop.core.geometry import ArcDirection, Point  # noqa: E402
from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.model.helpers import new_project, with_starter_tools  # noqa: E402

DEFAULT_FILE = PROJECT_ROOT / "tests" / "data" / "projects" / "compensation_test.wop.json"
CONTOUR_ID = "test"
START = (8, 0)  # (radius, Z)
STEPS = (
    LineStep(Point(10, -2)),  # a 45 degree chamfer
    LineStep(Point(10, -10)),  # a cylinder
    ArcCenterStep(Point(13, -13), Point(10, -13), ArcDirection.CW),  # a round corner of radius 3
    LineStep(Point(13, -25)),  # a long cylinder
    LineStep(Point(16, -30)),  # a taper
    LineStep(Point(16, -38)),  # the last cylinder
)
ALLOWANCE_MM = 0.3


def compensation_test() -> AppModel:
    model = AppModel(project=with_starter_tools(new_project()))
    model.set_contour(build_contour(CONTOUR_ID, "compensation test", ContourDefinition(Point(*START), STEPS)))
    tool = model.add_tool_of_type("holder")  # an ISO turning tool with a nose radius: without one nothing is compensated
    facing = model.add_block("facing")
    model.replace_block(facing, replace(model.blocks[facing], tool_number=tool))
    rough = model.add_block("turning_contour")
    model.replace_block(rough, replace(
        model.blocks[rough], name="rough", tool_number=tool, contour_id=CONTOUR_ID, pass_direction=PassDirection.ALONG_Z,
        finish_allowance_mm=ALLOWANCE_MM, finish_pass=False,
    ))
    finish = model.add_block("turning_contour")
    model.replace_block(finish, replace(
        model.blocks[finish], name="finish with cutter compensation", tool_number=tool, contour_id=CONTOUR_ID,
        pass_direction=PassDirection.ALONG_Z, finish_allowance_mm=ALLOWANCE_MM, finish_pass=True, cutter_compensation=True,
    ))
    return model


def main(argv: list[str]) -> None:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    compensation_test().save(path, with_part=False)
    print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
