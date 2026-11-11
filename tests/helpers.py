"""Small helpers shared by the tests: assertions, a test tool, the plans shared by the whole run."""

import hashlib
import os
import pickle
import time
import unittest
from pathlib import Path

from wop.core.geometry import ArcSegment, Point

TOLERANCE_MM = 1e-6
PROJECTS_FOLDER = Path(__file__).parent / "data" / "projects"
EXAMPLES_FOLDER = Path(__file__).parent.parent / "examples"


def project_path(name: str) -> Path:
    """A project by its file name: the test projects first, then the shipped examples."""
    return PROJECTS_FOLDER / name if (PROJECTS_FOLDER / name).exists() else EXAMPLES_FOLDER / name


def distance_to_line(point: Point, a: Point, b: Point) -> float:
    """Distance from point to the infinite line through a and b."""
    cross = (b.x - a.x) * (point.z - a.z) - (b.z - a.z) * (point.x - a.x)
    return abs(cross) / a.distance_to(b)


def assert_chain_is_continuous(test: unittest.TestCase, segments) -> None:
    for first, second in zip(segments, segments[1:]):
        test.assertTrue(
            first.end.is_close(second.start, TOLERANCE_MM),
            f"gap between {first.end} and {second.start}",
        )


def assert_segments_close(test: unittest.TestCase, expected, actual) -> None:
    test.assertEqual(len(expected), len(actual))
    for want, got in zip(expected, actual):
        test.assertIs(type(want), type(got))
        test.assertTrue(want.start.is_close(got.start, TOLERANCE_MM), f"{want} != {got}")
        test.assertTrue(want.end.is_close(got.end, TOLERANCE_MM), f"{want} != {got}")
        if isinstance(want, ArcSegment):
            test.assertTrue(want.center.is_close(got.center, TOLERANCE_MM), f"{want} != {got}")
            test.assertIs(want.direction, got.direction)


def is_valid_outline(segments) -> bool:
    """The closed chain encloses an area and does not cross or touch itself (arcs as chords of 0.01 mm)."""
    from wop.core.geometry.region import Region
    from wop.core.geometry import segments_to_polyline
    from wop.core.geometry.region_types import RegionError

    points = segments_to_polyline(list(segments), 0.01)
    if len(points) > 1 and points[0].is_close(points[-1]):
        points = points[:-1]  # the outline closes itself
    try:
        return Region.from_points(points).area > 0
    except RegionError:
        return False


def simple_tool(number: int, side: int = 1):
    """Square test tool with its tip at the origin; side 1: body at larger X, -1: smaller X."""
    from wop.core.geometry import LineSegment
    from wop.core.tooling.tool import Tool, ToolSegment, ToolSegmentRole, ToolShape

    corners = [Point(0, 0), Point(8 * side, 0), Point(8 * side, 12), Point(0, 12), Point(0, 0)]
    roles = [
        ToolSegmentRole.CUTTER,
        ToolSegmentRole.HOLDER,
        ToolSegmentRole.HOLDER,
        ToolSegmentRole.CUTTER,
    ]
    pieces = tuple(
        ToolSegment(LineSegment(a, b), role)
        for (a, b), role in zip(zip(corners, corners[1:]), roles)
    )
    return Tool(number, f"test tool {number}", ToolShape(pieces))


_PLANS: dict = {}  # program -> plan, for the whole test run
SHARED_PLANS_VARIABLE = "WOP_TEST_PLANS"  # set by tools/run_tests.py: the folder where the processes of one run share their plans
SHARED_PLAN_WAIT_S = 600  # a process waits this long for a plan another process is making, then makes it itself
SHARED_PLAN_POLL_S = 0.1


def planned(program):
    """`plan_program(program)`, made once per program for the whole test run: many tests plan the same example project, and the analytic
    planner takes seconds per project. A plan is frozen data and a program compares by its values, so sharing the plan is safe. Run by
    `tools/run_tests.py`, the processes share their plans through files too (`_shared_plan`)."""
    from wop.core.program_model.program import plan_program  # late: importing the whole planner is slow

    if program not in _PLANS:
        _PLANS[program] = _shared_plan(program, plan_program)
    return _PLANS[program]


def _shared_plan(program, plan_program):
    """The plan from the shared folder: read when another process made it, else made here and written there (while it is being made, a
    `.planning` file tells the other processes to wait for it). Without the folder, or for a program that does not pickle, just made."""
    folder = os.environ.get(SHARED_PLANS_VARIABLE)
    try:
        key = hashlib.sha256(pickle.dumps(program)).hexdigest() if folder else None
    except (pickle.PicklingError, TypeError, AttributeError):
        key = None
    if key is None:
        return plan_program(program)
    done, busy = Path(folder) / f"{key}.pickle", Path(folder) / f"{key}.planning"
    waited = 0.0
    while True:
        if done.exists():
            return pickle.loads(done.read_bytes())
        try:
            os.close(os.open(busy, os.O_CREAT | os.O_EXCL))
            break  # this process makes it
        except FileExistsError:
            if waited >= SHARED_PLAN_WAIT_S:
                return plan_program(program)
            time.sleep(SHARED_PLAN_POLL_S)
            waited += SHARED_PLAN_POLL_S
    try:
        plan = plan_program(program)
        try:
            data = pickle.dumps(plan)
        except (pickle.PicklingError, TypeError, AttributeError):
            return plan  # the others make it themselves
        part = done.with_suffix(".part")
        part.write_bytes(data)
        os.replace(part, done)
        return plan
    finally:
        busy.unlink()
