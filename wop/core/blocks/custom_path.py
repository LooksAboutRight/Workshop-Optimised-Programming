"""Custom path block (requirement B12): a path drawn in the sketch editor, rapid lines, feed lines and feed arcs.

The path starts at the safe point and goes piece after piece in the order they were drawn (`sketch/path_walk.py`). Each line is a feed
move unless it is marked as rapid; each piece can have a feed of its own, otherwise the feed of the block is used. A rapid arc cannot be
made. The sketch is stored in the block; when the block is planned, the safe point and the part before the block are put into it, it
is solved, and the pieces become `PathStep`s that make neutral operations only, so the block is drawn, collision-checked and written
like any other block. The path may cross itself or start inside the material; the material the tool passes through while feeding
counts as removed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from enum import Enum

from ..constants import (
    DEFAULT_PATH_ARC_RADIUS_MM,
    EXAMPLE_PATH_CHAMFER_MM,
    EXAMPLE_PATH_END_Z_MM,
    EXAMPLE_PATH_FEED_MM_PER_REV,
    EXAMPLE_PATH_INNER_X_MM,
    EXAMPLE_PATH_SAFE_X_MM,
    EXAMPLE_PATH_SAFE_Z_MM,
    EXAMPLE_PATH_START_X_MM,
    EXAMPLE_PATH_START_Z_MM,
    PATH_CHECK_STEP_MM,
    SAFE_POINT_KEY,
)
from ..contour import ArcRadiusStep, Corner, ContourDefinition, ContourError, CornerKind, LineStep
from ..contour_solver import solve_contour_tagged
from ..geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment
from ..program_model.operations import ArcMove, BlockBegin, BlockEnd, LinearMove, Operation, Rapid, SpindleSetting
from ..reach import prepare_tool, sample_segments
from ..sketch.corners import chamfer_corner
from ..sketch.loops import reversed_segment
from ..sketch.locked import sync_locked
from ..sketch.model import Sketch, SketchError
from ..sketch.modes import PATH, problems
from ..sketch.path_walk import walk_path
from ..sketch.pick import piece_id
from ..sketch.solver import analyse
from ..sketch.sketch_io import sketch_from_dict, sketch_to_dict
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult
from .path_locked import OUTLINE_GROUP, path_locked_items


class PathMove(Enum):
    RAPID = "rapid line"
    FEED_LINE = "feed line"
    FEED_ARC = "feed arc"


@dataclass(frozen=True)
class PathStep:
    """One step of the path, ending at `end`. Only the fields that belong to the move are used."""

    move: PathMove = PathMove.FEED_LINE
    end: Point = Point(0, 0)
    radius_mm: float = DEFAULT_PATH_ARC_RADIUS_MM  # arc
    direction: ArcDirection = ArcDirection.CCW  # arc
    large_arc: bool = False  # arc: the long way round
    corner: CornerKind = CornerKind.NONE  # feed line: treatment of the end, towards the next feed line
    corner_size_mm: float = 0
    feed_mm_per_rev: float | None = None  # feed moves; None: the feed of the block

    def __post_init__(self) -> None:
        if self.feed_mm_per_rev is not None and self.feed_mm_per_rev <= 0:
            raise BlockError("the feed of a step must be greater than zero")

    @property
    def is_feed(self) -> bool:
        return self.move is not PathMove.RAPID


_STEP_WORD = re.compile(r"step (\d+)")


def _shift_step_numbers(message: str, offset: int) -> str:
    return _STEP_WORD.sub(lambda match: f"step {int(match.group(1)) + offset}", message)


def _contour_step(step: PathStep):
    if step.move is PathMove.FEED_ARC:
        return ArcRadiusStep(step.end, step.radius_mm, step.direction, step.large_arc)
    return LineStep(step.end, Corner(step.corner, step.corner_size_mm))


def step_segments(start: Point, steps: tuple[PathStep, ...]) -> list[tuple[PathStep, Segment]]:
    """Every piece of the path with the step it belongs to (a corner treatment adds a piece to its step). Raises BlockError naming the step."""
    found: list[tuple[PathStep, Segment]] = []
    position, index = start, 0
    while index < len(steps):
        step = steps[index]
        if not step.is_feed:
            found.append((step, LineSegment(position, step.end)))
            position, index = step.end, index + 1
            continue
        run = []
        while index + len(run) < len(steps) and steps[index + len(run)].is_feed:
            run.append(steps[index + len(run)])
        try:
            solved = solve_contour_tagged(ContourDefinition(position, tuple(_contour_step(s) for s in run)))
        except ContourError as error:
            raise BlockError(_shift_step_numbers(str(error), index)) from error
        found += [(run[tag], segment) for tag, segment in solved]
        position, index = run[-1].end, index + len(run)
    return found


def path_moves(start: Point, steps: tuple[PathStep, ...], default_feed: float) -> list[tuple[Operation, bool]]:
    """The operations of a path, each with whether it cuts."""
    moves: list[tuple[Operation, bool]] = [(Rapid(start), False)]
    for step, segment in step_segments(start, steps):
        feed = step.feed_mm_per_rev or default_feed
        if not step.is_feed:
            moves.append((Rapid(segment.end), False))
        elif isinstance(segment, ArcSegment):
            moves.append((ArcMove(segment.end, segment.center, segment.direction, feed), True))
        else:
            moves.append((LinearMove(segment.end, feed), True))
    return moves


def path_sketch_from_steps(safe: Point, start: Point, steps: tuple[PathStep, ...]) -> Sketch:
    """A sketch of a path that starts at the safe point, goes to `start` (a rapid line when that is somewhere else) and then follows the
    steps. For the example block, the tools that make example projects and the tests."""
    sketch = Sketch()
    here = sketch.add_point(safe.x, safe.z)
    sketch.locked_points[SAFE_POINT_KEY] = here
    if not start.is_close(safe):
        there = sketch.add_point(start.x, start.z)
        sketch.rapid_pieces.add(sketch.add_line(here, there))
        here = there
    for step, segment in step_segments(start, steps):
        end = sketch.add_point(segment.end.x, segment.end.z)
        if isinstance(segment, ArcSegment):
            centre = sketch.add_point(segment.center.x, segment.center.z)
            piece = sketch.add_arc(centre, here, end, segment.direction)
        else:
            piece = sketch.add_line(here, end)
            if not step.is_feed:
                sketch.rapid_pieces.add(piece)
        if step.feed_mm_per_rev is not None and step.is_feed:
            sketch.piece_feeds[piece] = step.feed_mm_per_rev
        here = end
    return sketch


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class CustomPathBlock(Block):
    type_name = "custom_path"
    label = "Custom path"

    feed_mm_per_rev: float
    sketch: dict | None = field(default=None, hash=False)  # the drawing of the path (plain data); None: not drawn yet
    draw_path: str = field(default="", init=False, compare=False)  # not a value: the form shows a button that opens the sketch editor

    def form_fields(self) -> tuple[str, ...]:
        """Tool and spindle, the default feed and the button that opens the drawing of the path."""
        return ("name", "tool_number", "spindle", "feed_mm_per_rev", "coolant", "draw_path")

    def form_labels(self) -> dict[str, str]:
        return {"feed_mm_per_rev": "Feed (pieces without their own)"}

    def form_buttons(self) -> dict[str, str]:
        return {"draw_path": "Draw the path..."}

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "CustomPathBlock":
        """A new block: nothing is drawn yet (the safe point and the part are put in when the sketch editor opens)."""
        return cls(
            block_id=block_id, name="Custom path", tool_number=tool_number, spindle=spindle, feed_mm_per_rev=EXAMPLE_PATH_FEED_MM_PER_REV,
        )

    @classmethod
    def sample(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "CustomPathBlock":
        """A block with a small path drawn: a cut along Z with a chamfer, and out (for the example projects and the tests)."""
        x, z = EXAMPLE_PATH_START_X_MM, EXAMPLE_PATH_START_Z_MM
        steps = (
            PathStep(PathMove.FEED_LINE, Point(x, EXAMPLE_PATH_END_Z_MM)),
            PathStep(PathMove.FEED_LINE, Point(EXAMPLE_PATH_INNER_X_MM, EXAMPLE_PATH_END_Z_MM)),
            PathStep(PathMove.RAPID, Point(EXAMPLE_PATH_INNER_X_MM, z)),
        )
        sketch = path_sketch_from_steps(Point(EXAMPLE_PATH_SAFE_X_MM, EXAMPLE_PATH_SAFE_Z_MM), Point(x, z), steps)
        corner = next(i for i, p in sketch.points.items() if p.position.is_close(Point(x, EXAMPLE_PATH_END_Z_MM)))
        chamfer_corner(sketch, corner, EXAMPLE_PATH_CHAMFER_MM)
        return replace(cls.example(block_id, tool_number, spindle), sketch=sketch_to_dict(sketch))

    def drawn_from(self, safe: Point, start: Point, steps: tuple[PathStep, ...]) -> "CustomPathBlock":
        """The block with the path of these steps drawn in its sketch (see `path_sketch_from_steps`)."""
        return replace(self, sketch=sketch_to_dict(path_sketch_from_steps(safe, start, steps)))

    def __post_init__(self) -> None:
        if self.feed_mm_per_rev <= 0:
            raise BlockError("feed must be greater than zero")

    def own_problem(self) -> str:
        if self.sketch is None:
            return "the path is not drawn yet"
        try:
            return "; ".join(problems(sketch_from_dict(self.sketch), PATH))
        except SketchError as error:
            return str(error)

    def resolved(self, context: BlockContext) -> tuple[Point, tuple[PathStep, ...], list[str]]:
        """The start and the steps of the path for this part and these safe positions, and the notes for the user. The part before the
        block is only put into the sketch when a relation refers to it."""
        if self.sketch is None:
            raise BlockError("the path is not drawn yet")
        try:
            sketch = sketch_from_dict(self.sketch)
        except SketchError as error:
            raise BlockError(str(error)) from error
        safe = Point(context.safety.safe_radius_mm, context.safety.safe_z_mm)
        uses_part = any(
            self._touches_part(sketch, constraint) for constraint in sketch.constraints.values()
        )
        notes = sync_locked(sketch, *path_locked_items(safe, context.residual if uses_part else None))
        walked, found = walk_path(sketch)
        if found:
            raise BlockError("; ".join(found))
        steps: list[PathStep] = []
        start: Point | None = None
        for piece, forward in walked:
            segment = sketch.segment(piece)
            segment = segment if forward else reversed_segment(segment)
            start = segment.start if start is None else start
            feed = sketch.piece_feeds.get(piece_id(piece))
            if isinstance(segment, ArcSegment):
                steps.append(PathStep(
                    PathMove.FEED_ARC, segment.end, radius_mm=segment.radius, direction=segment.direction,
                    large_arc=segment.sweep > math.pi, feed_mm_per_rev=feed,
                ))
            elif piece_id(piece) in sketch.rapid_pieces:
                steps.append(PathStep(PathMove.RAPID, segment.end))
            else:
                steps.append(PathStep(PathMove.FEED_LINE, segment.end, feed_mm_per_rev=feed))
        free = analyse(sketch).free_directions
        if free:
            notes.append(f"The path is not fully constrained ({free} free directions): its points can still move; add dimensions or relations")
        return start, tuple(steps), notes

    @staticmethod
    def _touches_part(sketch: Sketch, constraint) -> bool:
        part = {i for key, i in sketch.locked_points.items() if key.startswith(OUTLINE_GROUP + "/")}
        return bool(part & set(sketch.constraint_points(constraint)))

    def generate(self, context: BlockContext) -> BlockResult:
        start, steps, notes = self.resolved(context)
        moves = path_moves(start, steps, self.feed_mm_per_rev)
        prepared = prepare_tool(context.tool)
        current = context.residual
        position = start
        for operation, cuts in moves:
            end = operation.end
            if cuts:
                segment = _segment_of(position, operation)
                for point in sample_segments([segment], PATH_CHECK_STEP_MM):
                    current = current.difference(prepared.body.translated(point.x, point.z))
            position = end
        operations = (BlockBegin(0, self.block_id, self.type_name, self.title), *(op for op, _cuts in moves), BlockEnd(self.block_id))
        return BlockResult(operations, context.residual.difference(current), messages=tuple(notes))


def _segment_of(start: Point, operation):
    if isinstance(operation, ArcMove):
        return ArcSegment(start, operation.end, operation.center, operation.direction)
    return LineSegment(start, operation.end)
