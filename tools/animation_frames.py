"""The frames of a machining animation (round A of tools/make_animation.py).

`iter_frames(program, plan, ...)` walks the moves of a planned program in order and yields one
`AnimationFrame` per small step: the material left at that moment, the tool at that place and a
caption. A cutting move gives one frame for every `step_mm` of path; a rapid gives a few frames
(`rapid_frames`). The material is one running residual: each block starts from the material the
plan says it starts with, each tool position removes what the tool body passes, and the last frame
of a block shows exactly the material the plan has after the block.

No picture is made here: `draw_frame` turns a frame into SVG text with the same `render_svg` as the
window. Making PNG and video from the SVG is the job of tools/make_animation.py.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Container, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scene_svg

from wop.core.constants import PATH_CHECK_STEP_MM  # noqa: E402
from wop.core.geometry import ArcSegment, LineSegment, Point  # noqa: E402
from wop.core.program_model.operations import ArcMove, LinearMove, Rapid, SpindleMode, SpindleSetting, spindle_text  # noqa: E402
from wop.core.program_model.program import Program, ProgramPlan  # noqa: E402
from wop.core.reach import sample_segments  # noqa: E402
from wop.core.geometry.region import Region  # noqa: E402
from wop.ui.stepper import StepFrame, Stepper  # noqa: E402
from wop.ui.theme import LIGHT_COLORS  # noqa: E402
from wop.ui.svg_preview import StepView, render_svg  # noqa: E402
from wop.ui.view3d import build_scene  # noqa: E402

from scene_svg import scene_to_svg  # noqa: E402

DEFAULT_STEP_MM = 1.0
DEFAULT_RAPID_FRAMES = 6
MM_PER_M = 1000.0
SECONDS_PER_MINUTE = 60.0
MIN_RADIUS_MM = 0.1  # CSS: the radius is not taken smaller than this (the speed would be unlimited)
RAPID_MM_PER_MIN = 10000.0  # only for the time of a rapid in the time-true mode


@dataclass(frozen=True)
class AnimationFrame:
    number: int  # position in the animation, from 0
    step_index: int  # the Stepper step (one move) this frame belongs to
    block_index: int
    material: Region
    tool_body: Region
    holder_outlines: tuple[tuple[Point, ...], ...]
    moves_done: int  # moves of the block that are finished (StepView.moves_done)
    position: Point
    caption: str
    seconds: float  # machining time that this frame stands for (feed and RPM)
    spindle_on: bool = False


def spindle_rpm(spindle: SpindleSetting | None, radius_mm: float) -> float:
    """The RPM at this radius (0 = stopped)."""
    if spindle is None:
        return 0.0
    if spindle.mode is SpindleMode.CONSTANT_RPM:
        return spindle.value
    rpm = spindle.value * MM_PER_M / (2 * math.pi * max(radius_mm, MIN_RADIUS_MM))
    return rpm if spindle.rpm_limit is None else min(rpm, spindle.rpm_limit)


def move_positions(frame: StepFrame, step_mm: float, rapid_frames: int) -> list[Point]:
    """Where the tool tip is, in order, ending at the end of the move (a rapid: evenly spaced points)."""
    end = frame.end
    if frame.start is None:
        return [end]
    start = frame.start
    if isinstance(frame.move, Rapid):
        count = max(rapid_frames, 1)
        return [
            Point(start.x + (end.x - start.x) * i / count, start.z + (end.z - start.z) * i / count)
            for i in range(1, count + 1)
        ]
    if isinstance(frame.move, ArcMove):
        segment = ArcSegment(start, end, frame.move.center, frame.move.direction)
    else:
        segment = LineSegment(start, end)
    points = sample_segments([segment], step_mm)
    points = [p for p in points if p != start] or [end]
    if points[-1] != end:
        points.append(end)
    return points


def _path_length(points: list[Point], start: Point | None) -> float:
    total, last = 0.0, start
    for point in points:
        if last is not None:
            total += math.hypot(point.x - last.x, point.z - last.z)
        last = point
    return total


def position_seconds(frame: StepFrame, positions: list[Point]) -> list[float]:
    """The machining time (feed and RPM) that each position of a move stands for."""
    total = _path_length(positions, frame.start)
    feed = getattr(frame.move, "feed_mm_per_rev", None)
    result = []
    for point in positions:
        per_minute = RAPID_MM_PER_MIN if feed is None else feed * spindle_rpm(frame.spindle, point.x)
        result.append(total / len(positions) / per_minute * SECONDS_PER_MINUTE if total > 0 and per_minute > 0 else 0.0)
    return result


def _caption(frame: StepFrame, rpm: float) -> str:
    kind = "rapid" if isinstance(frame.move, Rapid) else "arc" if isinstance(frame.move, ArcMove) else "cut"
    parts = [f"Block {frame.block_number}", f"T{frame.tool_number}", kind, f"spindle {spindle_text(frame.spindle)}"]
    feed = getattr(frame.move, "feed_mm_per_rev", None)
    if feed is not None:
        parts.append(f"feed {feed:g} mm/rev")
        if rpm:
            parts.append(f"{feed * rpm:.0f} mm/min")
    return " | ".join(parts)


def iter_frames(
    program: Program,
    plan: ProgramPlan,
    step_mm: float = DEFAULT_STEP_MM,
    rapid_frames: int = DEFAULT_RAPID_FRAMES,
    blocks: range | None = None,
    first_number: int = 0,
    wanted: Container[int] | None = None,
) -> Iterator[AnimationFrame]:
    """All frames, in order. `blocks`: only these plan blocks (positions in plan.blocks); None = all.

    Numbering starts at `first_number` (for a worker that does the middle of the program). With `wanted`
    only frames with these numbers are yielded; the material is still worked out for every position.
    """
    if step_mm <= 0:
        raise ValueError("the step must be greater than zero")
    stepper = Stepper(program, plan)
    number = first_number
    residual: Region | None = None
    current_block = -1
    for frame in stepper.frames:
        if blocks is not None and frame.block_index not in blocks:
            continue
        block_plan = plan.blocks[frame.block_index]
        if frame.block_index != current_block:
            current_block = frame.block_index
            residual = block_plan.residual_before
        body = stepper.prepared_tool(frame.tool_number).body
        holders = stepper.prepared_tool(frame.tool_number).holder_outlines
        positions = move_positions(frame, step_mm, rapid_frames)
        times = position_seconds(frame, positions)
        last_index = len(positions) - 1
        for i, point in enumerate(positions):
            if frame.is_cutting:
                residual = residual.difference(body.translated(point.x, point.z))
            finished = i == last_index
            if finished and frame.move_number == frame.moves_in_block:
                residual = block_plan.residual_after  # exactly what the plan has
            if wanted is None or number in wanted:
                rpm = spindle_rpm(frame.spindle, point.x)
                yield AnimationFrame(
                    number, frame.index, frame.block_index, residual,
                    body.translated(point.x, point.z),
                    tuple(tuple(Point(p.x + point.x, p.z + point.z) for p in outline) for outline in holders),
                    frame.move_number if finished else frame.move_number - 1,
                    point, _caption(frame, rpm), times[i], frame.spindle_on,
                )
            number += 1


def timeline(program: Program, plan: ProgramPlan, step_mm: float = DEFAULT_STEP_MM,
             rapid_frames: int = DEFAULT_RAPID_FRAMES) -> list[tuple[int, float]]:
    """(plan block, machining seconds) of every position, in order, without cutting anything (cheap)."""
    result: list[tuple[int, float]] = []
    for frame in Stepper(program, plan).frames:
        positions = move_positions(frame, step_mm, rapid_frames)
        result.extend((frame.block_index, t) for t in position_seconds(frame, positions))
    return result


def draw_frame(plan: ProgramPlan, frame: AnimationFrame, findings=None, colors=None, view: str = "side",
               workholding=None, extra_points: tuple[Point, ...] = (), **options) -> str:
    """SVG text of one frame: view "side" is the window's step view (no legend), "3d" the 3D view."""
    shown = StepView(frame.material, frame.tool_body, frame.holder_outlines, frame.moves_done)
    extra = {} if colors is None else {"colors": colors}
    if view == "3d":
        scene = build_scene(plan, frame.block_index, step=shown, workholding=workholding, spindle_on=frame.spindle_on, **extra, **options)
        return scene_to_svg(scene, colors=extra.get("colors", LIGHT_COLORS))
    if view != "side":
        raise ValueError("the view is side or 3d")
    return render_svg(plan, frame.block_index, findings, with_legend=False, step=shown,
                      extra_points=extra_points, workholding=workholding, **extra, **options)


def count_frames(program: Program, plan: ProgramPlan, step_mm: float = DEFAULT_STEP_MM,
                 rapid_frames: int = DEFAULT_RAPID_FRAMES) -> int:
    """How many frames the animation will have (without cutting anything)."""
    stepper = Stepper(program, plan)
    return sum(len(move_positions(f, step_mm, rapid_frames)) for f in stepper.frames)
