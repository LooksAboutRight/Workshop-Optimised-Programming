"""Write the air-cut test projects for the first day on the LinuxCNC lathe (by default wop_output/machine_tests/; nothing of them is kept in the repository).

Usage (project root):  python tools/make_machine_tests.py [folder]
Four small projects with a custom path (known points, nothing is cut), a thread and drilling cycles; the fourth test, cutter
compensation, is tests/data/projects/compensation_test.wop.json (tools/make_compensation_test.py); the shipped LinuxCNC post writes G41 / G42.

  test_1_basics   T1 and T2 (the same square at the same points: the tool offsets must bring both tips to the same corners)
  test_2_arcs     T1, four quarter arcs: all four combinations of direction and Z direction (G2 / G3, I and K)
  test_3_thread   T4, an outside thread M36x3, 15 mm long, 100 rpm, G76
  test_5a..5d_drill_*   T5, one hole each, drilled in the air: G81, G82, G83 and G73 (cycles in the plane G17, written by the shipped post)
  test_6_back_boring    T6, a left-hand boring bar in a bore of 36 mm: the far wall, X below the axis, the spindle counter-clockwise (M4)
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from wop.core.blocks.custom_path import CustomPathBlock, PathMove, PathStep  # noqa: E402
from wop.core.blocks.turning_common import TurningSide  # noqa: E402
from wop.core.geometry import ArcDirection, Point  # noqa: E402
from wop.core.program_model.operations import DrillMode, SpindleDirection, SpindleMode, SpindleSetting  # noqa: E402
from wop.core.tool_types.hand import ToolHand  # noqa: E402
from wop.ui.app_model import AppModel  # noqa: E402
from wop.ui.model.helpers import new_project, with_starter_tools  # noqa: E402

DEFAULT_FOLDER = PROJECT_ROOT / "wop_output" / "machine_tests"
STOCK_DIAMETER_MM = 30  # the paths stay at 40 mm and more: nothing is touched, also with a bar in the chuck
SPINDLE = SpindleSetting(SpindleMode.CONSTANT_RPM, 200)
FEED_MM_PER_REV = 0.5  # 100 mm/min at 200 rpm: slow enough to watch
ARC_RADIUS_MM = 5
THREAD_RPM = 100
THREAD_DESIGNATION = "M36x3"
THREAD_START_Z_MM = 3  # in front of the part: the cycle starts before the first thread turn
THREAD_LENGTH_MM = 15  # from Z3 to Z-12
THREAD_TOOL_NUMBER = 4  # T3 is the tool of the compensation test
DRILL_TOOL_NUMBER = 5
BORING_TOOL_NUMBER = 6
BORING_RPM = 200
BORING_FEED_MM_PER_REV = 0.1
TUBE_DIAMETER_MM = 60
TUBE_BORE_MM = 30  # the hole of the tube
BORED_DIAMETER_MM = 36
BORED_DEPTH_MM = 15
DRILL_RPM = 300
DRILL_FEED_MM_PER_REV = 0.1
DRILL_DEPTH_MM = 12  # from the front face Z0 to Z-12 (the point of the drill goes deeper)
DRILL_PECK_MM = 4
DRILL_DWELL_S = 2


def new_model(title: str, diameter_mm: float = STOCK_DIAMETER_MM) -> AppModel:
    model = AppModel(project=with_starter_tools(new_project()))
    for tool in tuple(model.program.tools):  # a new project comes with two tools; the tests make their own
        model.remove_tool(tool.number)
    model.set_setup_form(replace(model.setup_form(), title=title, outer_diameter_mm=diameter_mm))
    return model


def numbered_tool(model: AppModel, type_name: str, number: int) -> int:
    """Add a tool of a type and give it a number (the tests use T1, T2 and T3)."""
    first = model.add_tool_of_type(type_name)
    model.edit_tool(first, replace(model.tool_form(first), number=number))
    return number


def path_block(model: AppModel, name: str, tool: int, start: tuple[float, float], steps: tuple[PathStep, ...]) -> None:
    index = model.add_block("custom_path")
    safety = model.program.safety
    block = replace(
        model.blocks[index], name=name, tool_number=tool, spindle=SPINDLE, feed_mm_per_rev=FEED_MM_PER_REV,
    ).drawn_from(Point(safety.safe_radius_mm, safety.safe_z_mm), Point(*start), steps)
    model.replace_block(index, block)


def rapid(x: float, z: float) -> PathStep:
    return PathStep(PathMove.RAPID, Point(x, z))


def line(x: float, z: float) -> PathStep:
    return PathStep(PathMove.FEED_LINE, Point(x, z))


def arc(x: float, z: float, direction: ArcDirection) -> PathStep:
    return PathStep(PathMove.FEED_ARC, Point(x, z), radius_mm=ARC_RADIUS_MM, direction=direction)


def basics() -> AppModel:
    """The same square for T1 and T2 (radius, Z): diameter 50 and 40, Z 5 and -10. X, Z moves alone and together."""
    model = new_model("Machine test 1: basics")
    square = (rapid(25, -10), line(20, -10), line(20, 5), rapid(25, 5))
    first = numbered_tool(model, "turning", 1)
    second = numbered_tool(model, "turning", 2)
    path_block(model, "square with T1", first, (25, 5), square)
    path_block(model, "square with T2", second, (25, 5), square)
    return model


def arcs() -> AppModel:
    """Four quarter arcs, radius 5: counter-clockwise and clockwise, each towards smaller and towards larger Z."""
    model = new_model("Machine test 2: arcs")
    tool = numbered_tool(model, "turning", 1)
    ccw, cw = ArcDirection.CCW, ArcDirection.CW
    steps = (
        arc(20, -5, ccw), arc(25, -10, cw),  # towards smaller Z: counter-clockwise, then clockwise
        rapid(25, -25),
        arc(20, -20, cw), arc(25, -15, ccw),  # towards larger Z: clockwise, then counter-clockwise
        rapid(25, 5),
    )
    path_block(model, "four arcs", tool, (25, 5), (rapid(25, 0),) + steps)
    return model


def thread() -> AppModel:
    """An outside thread M36x3 on a bar of 36 mm: a big pitch and a short length, 100 rpm."""
    model = new_model("Machine test 3: thread", diameter_mm=36)
    tool = numbered_tool(model, "thread", THREAD_TOOL_NUMBER)
    index = model.add_block("threading")
    block = replace(
        model.blocks[index], name=THREAD_DESIGNATION, tool_number=tool, side=TurningSide.OUTSIDE,
        designation=THREAD_DESIGNATION, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, THREAD_RPM),
        start_z_mm=THREAD_START_Z_MM, end_z_mm=THREAD_START_Z_MM - THREAD_LENGTH_MM,
    )
    model.replace_block(index, block.with_derived_fields(None))
    return model


def back_boring() -> AppModel:
    """A left-hand boring bar in a bore of 36 mm, 15 mm deep: it works on the far wall, below the axis (X negative), with the spindle
    counter-clockwise. The tube has a hole of 30 mm; nothing is cut if there is no tube in the chuck."""
    model = new_model("Machine test 6: back boring", diameter_mm=TUBE_DIAMETER_MM)
    form = model.setup_form()
    model.set_setup_form(replace(form, inner_diameter_mm=TUBE_BORE_MM))
    first = model.add_tool_of_type("boring")
    definition = replace(model.tool_form(first), number=BORING_TOOL_NUMBER, hand=ToolHand.LEFT)
    model.edit_tool(first, definition)
    index = model.add_block("turning")
    block = replace(
        model.blocks[index], name="far wall", tool_number=BORING_TOOL_NUMBER, side=TurningSide.INSIDE,
        spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, BORING_RPM, direction=SpindleDirection.COUNTER_CLOCKWISE),
        target_radius_mm=BORED_DIAMETER_MM / 2, end_z_mm=-BORED_DEPTH_MM, feed_mm_per_rev=BORING_FEED_MM_PER_REV, depth_of_cut_mm=1,
        finish_allowance_mm=0.2, finish_pass=True,
    )
    model.replace_block(index, block)
    return model


def drill_cycle(title: str, mode: DrillMode, peck: float | None, dwell: float) -> AppModel:
    """One hole on the axis, drilled in the air. (One project per hole: a second drilling block on the axis finds the hole made.)"""
    model = new_model(f"Machine test 5: {title}")
    tool = numbered_tool(model, "drill", DRILL_TOOL_NUMBER)
    index = model.add_block("drilling")
    block = replace(
        model.blocks[index], name=title, tool_number=tool, spindle=SpindleSetting(SpindleMode.CONSTANT_RPM, DRILL_RPM),
        depth_z_mm=-DRILL_DEPTH_MM, feed_mm_per_rev=DRILL_FEED_MM_PER_REV, drill_mode=mode, peck_depth_mm=peck, dwell_s=dwell,
    )
    model.replace_block(index, block)
    return model


PROJECTS = (
    ("test_1_basics", basics), ("test_2_arcs", arcs), ("test_3_thread", thread),
    ("test_5a_drill_g81", lambda: drill_cycle("G81 plain hole", DrillMode.DRILL, None, 0)),
    ("test_5b_drill_g82", lambda: drill_cycle("G82 dwell", DrillMode.DRILL, None, DRILL_DWELL_S)),
    ("test_5c_drill_g83", lambda: drill_cycle("G83 peck", DrillMode.PECK_FULL_RETRACT, DRILL_PECK_MM, 0)),
    ("test_5d_drill_g73", lambda: drill_cycle("G73 chip break", DrillMode.PECK, DRILL_PECK_MM, 0)),
    ("test_6_back_boring", back_boring),
)


def main(argv: list[str]) -> None:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for name, make in PROJECTS:
        path = folder / f"{name}.wop.json"
        make().save(path, with_part=False)
        print(f"written {path}")


if __name__ == "__main__":
    main(sys.argv)
