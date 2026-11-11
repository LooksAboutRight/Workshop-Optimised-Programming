"""Write an example project file (requirement B4).

Usage (project root):  python tools/make_example_project.py [file]
Writes examples/reference.wop.json: the reference program (with generated tools: an ISO holder with an insert, and a boring bar)
plus a contour-form turning block with a shaft contour. Open it with tools/wop_app.py or tools/wop_run.py.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from example_values import BORING, FACING, ROUGHING, with_values  # noqa: E402
from tests.reference_program import RPM, reference_program  # noqa: E402
from wop.adapters.project_files import save_project  # noqa: E402
from wop.core.blocks.turning_common import TurningSide  # noqa: E402
from wop.core.blocks.turning_contour import ContourTurningBlock  # noqa: E402
from wop.core.contour import ContourDefinition, LineStep  # noqa: E402
from wop.core.contour_solver import build_contour  # noqa: E402
from wop.core.geometry import Point  # noqa: E402
from wop.core.program_model.project import Project, ProjectSettings  # noqa: E402
from wop.core.tool_types import make_tool  # noqa: E402
from wop.core.tool_types.boring import BoringDefinition  # noqa: E402
from wop.core.tool_types.holder import HolderDefinition  # noqa: E402
from wop.core.tooling.tool import ToolMaterial  # noqa: E402

DEFAULT_FILE = PROJECT_ROOT / "examples" / "reference.wop.json"
SHAFT_POINTS = [(14, 0), (14, -20), (16, -20), (16, -30)]  # clear of the bore (radius 10)
SMALL_BORING_BAR = BoringDefinition(number=2, nose_radius_mm=0.2, wall_edge_length_mm=10, front_width_mm=11, bar_width_mm=8, length_mm=60)  # fits the bore of 14 mm
TURNING_HOLDER = HolderDefinition(  # a right-hand ISO holder with a VNMG insert, made from its codes (the tools of the tests are drawn by hand)
    number=1, material=ToolMaterial.COATED_CARBIDE, insert_code="VNMG 160408", holder_code="MVJNR 2020 K16", clamping="M", shape="V",
    style="J", clearance="N", hand="R", section="2020", length="K", insert_size="16", tolerance="M", insert_type="G", thickness="04", corner_radius="08",
)


def example_project() -> Project:
    steps = tuple(LineStep(Point(x, z)) for x, z in SHAFT_POINTS[1:])
    shaft = build_contour("shaft", "stepped shaft", ContourDefinition(Point(*SHAFT_POINTS[0]), steps))
    program = replace(reference_program(), tools=(make_tool("holder", 1, TURNING_HOLDER), make_tool("boring", 2, SMALL_BORING_BAR))).with_contour(shaft)
    values = {"r1": FACING, "r4": BORING}  # the other blocks: turning outside
    program = replace(program, blocks=tuple(with_values(block, values.get(block.block_id, ROUGHING)) for block in program.blocks))
    block = ContourTurningBlock(
        block_id="r6", name="stepped shaft from a contour", tool_number=1, spindle=RPM,
        contour_id="shaft", side=TurningSide.OUTSIDE, feed_mm_per_rev=0.2, depth_of_cut_mm=1,
        finish_allowance_mm=0.2, finish_feed_mm_per_rev=0.1,
    )
    block = with_values(block, ROUGHING)
    program = replace(program, blocks=program.blocks[:4] + (block,) + program.blocks[4:])
    return Project(program, ProjectSettings(title="WOP example"))


def main(argv: list[str]) -> None:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    save_project(path, example_project())
    print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
