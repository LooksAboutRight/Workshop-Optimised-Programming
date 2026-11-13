"""Run a planned program through a postprocessor (requirements O2, O9, O11, B11).

find_issues() tells what the controller cannot do (or has not been confirmed
for), with a remedy where a safe one exists. generate_gcode() produces the
text. A remedy changes the output only, never the program. A block with an
issue the user has not accepted is left out and the result is marked
incomplete, with a clear comment in the code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from ..core.geometry import ArcSegment, Point
from ..core.program_model.operations import (
    ArcMove,
    BlockBegin,
    BlockEnd,
    Comment,
    CoolantMode,
    DrillOperation,
    FunctionCall,
    ThreadOperation,
    LinearMove,
    MachineFunction,
    Operation,
    Rapid,
    RapidAxes,
    SetCoolant,
    SetSpindle,
    SpindleMode,
    SpindleDirection,
    SpindleSetting,
    StopSpindle,
    ToolChange,
)
from ..core.program_model.program import ProgramPlan
from ..core.program_model.units import XInputMode
from .base import Feature, PostError, Postprocessor, PostInfo, PostSettings, function_feature
from .context import PostContext
from .variables import VariableError, check_values
from .post_constants import (
    ARC_AS_LINES_DEVIATION_MM,
    M_PER_MIN_TO_MM_PER_MIN,
)


class RemedyKind(Enum):
    FIXED_RPM = "fixed RPM instead of constant surface speed"
    OMIT_COOLANT = "leave the coolant command out"
    ARCS_AS_LINES = "replace arcs by short lines"
    RADIUS_MODE = "output radius values instead of diameters"
    OMIT_FUNCTION = "leave the machine function out"


# (block index or None for the whole program, remedy)
RemedyKey = tuple[int | None, RemedyKind]


@dataclass(frozen=True)
class Issue:
    block_index: int | None
    message: str
    remedy: RemedyKind | None  # None: no safe remedy, the block cannot be output
    remedy_text: str = ""

    @property
    def key(self) -> RemedyKey | None:
        return None if self.remedy is None else (self.block_index, self.remedy)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    complete: bool  # False if blocks had to be left out
    issues: tuple[Issue, ...]
    applied_remedies: tuple[str, ...]
    skipped_blocks: tuple[int, ...]


def _block_label(plan: ProgramPlan, index: int | None) -> str:
    """"block N" with the number the user sees (index counts the blocks of the plan, which may be a selection)."""
    return "the program" if index is None else f"block {plan.blocks[index].number}"


def _fixed_rpm(plan: ProgramPlan, index: int, setting: SpindleSetting) -> tuple[SpindleSetting, float]:
    """Constant RPM that gives the surface speed at the largest diameter of the block."""
    block_plan = plan.blocks[index]
    region = block_plan.result.removed
    if region.is_empty:
        region = block_plan.residual_before
    diameter = 2 * region.bounds.max_x
    rpm = setting.value * M_PER_MIN_TO_MM_PER_MIN / (math.pi * diameter)
    if setting.rpm_limit is not None:
        rpm = min(rpm, setting.rpm_limit)
    return replace(setting, mode=SpindleMode.CONSTANT_RPM, value=rpm, rpm_limit=None), diameter


def _groups(plan: ProgramPlan) -> list[tuple[int | None, tuple[Operation, ...]]]:
    groups: list[tuple[int | None, tuple[Operation, ...]]] = [
        (index, block_plan.operations) for index, block_plan in enumerate(plan.blocks)
    ]
    groups.append((None, plan.closing))
    return groups


def _has_moves(plan: ProgramPlan) -> bool:
    return any(isinstance(op, (Rapid, LinearMove, ArcMove)) for op in plan.operations)


def _operation_features(operation: Operation, settings: PostSettings) -> set[Feature]:
    """What a controller must be able to do for this operation."""
    if isinstance(operation, SetSpindle):
        used = set()
        if operation.setting.mode is SpindleMode.CONSTANT_SURFACE_SPEED:
            used.add(Feature.CONSTANT_SURFACE_SPEED)
        if operation.setting.direction is SpindleDirection.COUNTER_CLOCKWISE:
            used.add(Feature.SPINDLE_REVERSE)
        return used
    if isinstance(operation, SetCoolant):
        coolant = {CoolantMode.FLOOD: Feature.COOLANT_FLOOD, CoolantMode.MIST: Feature.COOLANT_MIST}.get(operation.mode)
        return set() if coolant is None else {coolant}
    if isinstance(operation, ArcMove):
        return {Feature.ARCS, Feature.ARCS_IN_DIAMETER_MODE} if settings.x_mode is XInputMode.DIAMETER else {Feature.ARCS}
    if isinstance(operation, ToolChange):
        return {Feature.TOOL_CHANGE}
    if isinstance(operation, ThreadOperation):
        return {Feature.THREAD_CYCLE}
    if isinstance(operation, MachineFunction):
        feature = function_feature(operation.kind)
        return set() if feature is None else {feature}
    return set()


def used_features(plan: ProgramPlan, settings: PostSettings) -> set[Feature]:
    used: set[Feature] = set()
    if settings.x_mode is XInputMode.DIAMETER and _has_moves(plan):
        used.add(Feature.DIAMETER_MODE)
    for operation in plan.operations:
        used |= _operation_features(operation, settings)
    return used


def _spindle_issues(operation: SetSpindle, plan: ProgramPlan, index: int, label: str, info: PostInfo) -> list[Issue]:
    setting = operation.setting
    issues = []
    if setting.mode is SpindleMode.CONSTANT_SURFACE_SPEED and Feature.CONSTANT_SURFACE_SPEED not in info.supported:
        fixed, diameter = _fixed_rpm(plan, index, setting)
        issues.append(Issue(
            index, f"{label}: {info.name} has no constant surface speed",
            RemedyKind.FIXED_RPM,
            f"fixed {fixed.value:.0f} RPM instead of {setting.value:g} m/min "
            f"(calculated for diameter {diameter:.1f} mm)",
        ))
    if setting.direction is SpindleDirection.COUNTER_CLOCKWISE and Feature.SPINDLE_REVERSE not in info.supported:
        issues.append(Issue(index, f"{label}: {info.name} cannot run the spindle counter-clockwise", None))
    return issues


def _coolant_issues(operation: SetCoolant, index: int, label: str, info: PostInfo) -> list[Issue]:
    needed = {CoolantMode.FLOOD: Feature.COOLANT_FLOOD, CoolantMode.MIST: Feature.COOLANT_MIST}.get(operation.mode)
    if needed is None or needed in info.supported:
        return []
    return [Issue(index, f"{label}: {info.name} has no {needed.value}", RemedyKind.OMIT_COOLANT, "leave the coolant command out; switch it by hand")]


def _arc_issue(settings: PostSettings, index: int, label: str, info: PostInfo) -> Issue | None:
    # a post without diameter mode writes radius values (the remedy in `find_issues`), so its arcs are not arcs in diameter mode
    diameters = settings.x_mode is XInputMode.DIAMETER and Feature.DIAMETER_MODE in info.supported
    missing = Feature.ARCS not in info.supported or (diameters and Feature.ARCS_IN_DIAMETER_MODE not in info.supported)
    if not missing:
        return None
    return Issue(index, f"{label}: {info.name} cannot do these arcs", RemedyKind.ARCS_AS_LINES, "replace the arcs by short straight lines")


def _machine_function_issues(operation: MachineFunction, index: int, label: str, info: PostInfo) -> list[Issue]:
    feature = function_feature(operation.kind)
    if feature is None or feature in info.supported:
        return []
    return [Issue(
        index, f"{label}: {info.name} cannot write {operation.kind.value}",
        RemedyKind.OMIT_FUNCTION, f"leave {operation.kind.value} out; do it by hand",
    )]


def _function_call_issues(operation: FunctionCall, index: int, label: str, info: PostInfo) -> list[Issue]:
    function = info.functions.get(operation.name)
    if function is None:
        return [Issue(index, f"{label}: {info.name} has no function {operation.name!r}", None)]
    try:
        check_values(function.variables, dict(operation.values))
    except VariableError as error:
        return [Issue(index, f"{label}: function {operation.name}: {error.message}", None)]
    return []


def _operation_issues(operation: Operation, plan: ProgramPlan, index: int, label: str, info: PostInfo) -> list[Issue]:
    """What the controller cannot do for one operation (an arc is left to `_arc_issue`: one report for the block)."""
    if isinstance(operation, SetSpindle):
        return _spindle_issues(operation, plan, index, label, info)
    if isinstance(operation, SetCoolant):
        return _coolant_issues(operation, index, label, info)
    if isinstance(operation, ThreadOperation) and Feature.THREAD_CYCLE not in info.supported:
        return [Issue(index, f"{label}: {info.name} has no thread cycle", None)]
    if isinstance(operation, ToolChange) and Feature.TOOL_CHANGE not in info.supported:
        return [Issue(index, f"{label}: {info.name} has no tool change", None)]
    if isinstance(operation, MachineFunction):
        return _machine_function_issues(operation, index, label, info)
    if isinstance(operation, StopSpindle) and Feature.SPINDLE_STOP not in info.supported:
        return [Issue(index, f"{label}: {info.name} has no spindle stop", None)]
    if isinstance(operation, FunctionCall):
        return _function_call_issues(operation, index, label, info)
    return []


def find_issues(plan: ProgramPlan, info: PostInfo, settings: PostSettings) -> list[Issue]:
    issues: list[Issue] = []
    if Feature.DIAMETER_MODE in used_features(plan, settings) and Feature.DIAMETER_MODE not in info.supported:
        issues.append(
            Issue(None, f"{info.name} has no diameter mode", RemedyKind.RADIUS_MODE,
                  "output radius values instead of diameters (the whole program)")
        )
    for index, operations in _groups(plan):
        if index is None:
            continue
        label = _block_label(plan, index)
        arcs_reported = False
        for operation in operations:
            if isinstance(operation, ArcMove):
                issue = None if arcs_reported else _arc_issue(settings, index, label, info)
                if issue is not None:
                    arcs_reported = True
                    issues.append(issue)
            else:
                issues += _operation_issues(operation, plan, index, label, info)
    return issues


def _rewrite(plan: ProgramPlan, index: int, operations: tuple[Operation, ...],
             accepted: set[RemedyKey]) -> list[Operation]:
    """Apply the accepted remedies of one block to its operations."""
    result: list[Operation] = []
    position: Point | None = None
    contour_position: Point | None = None  # the end of the last move on the nominal contour (the same as `position` without one)
    for operation in operations:
        if isinstance(operation, SetSpindle) and (index, RemedyKind.FIXED_RPM) in accepted:
            if operation.setting.mode is SpindleMode.CONSTANT_SURFACE_SPEED:
                operation = SetSpindle(_fixed_rpm(plan, index, operation.setting)[0])
        elif isinstance(operation, SetCoolant) and (index, RemedyKind.OMIT_COOLANT) in accepted:
            if operation.mode is not CoolantMode.NONE:
                result.append(Comment(f"coolant {operation.mode.value} not supported: switch by hand"))
                continue
        elif isinstance(operation, MachineFunction) and (index, RemedyKind.OMIT_FUNCTION) in accepted:
            result.append(Comment(f"{operation.kind.value} not supported: do it by hand"))
            continue
        elif isinstance(operation, ArcMove) and (index, RemedyKind.ARCS_AS_LINES) in accepted:
            arc = ArcSegment(position, operation.end, operation.center, operation.direction)
            points = arc.to_polyline(ARC_AS_LINES_DEVIATION_MM)[1:]
            contour_points = _contour_chords(operation, contour_position, len(points))
            for number, point in enumerate(points):
                result.append(LinearMove(
                    point, operation.feed_mm_per_rev, None if contour_points is None else contour_points[number], operation.role,
                ))
            position = operation.end
            contour_position = operation.contour_end or operation.end
            continue
        result.append(operation)
        end = getattr(operation, "end", None)
        if isinstance(end, Point):
            position = end
            contour_position = getattr(operation, "contour_end", None) or end
    return result


def _contour_chords(arc: ArcMove, start: Point | None, count: int) -> list[Point] | None:
    """The points of the contour arc that belong to the chords of the tool path arc (the same angles); None without a contour."""
    if arc.contour_end is None or arc.contour_center is None or start is None:
        return None
    try:
        contour = ArcSegment(start, arc.contour_end, arc.contour_center, arc.direction)
    except ValueError:
        return None
    return [contour.point_at((number + 1) / count) for number in range(count)]


def _machine_move(post, operation) -> bool:
    """The move to the tool change position, when the post writes it by itself: with its own [change_position], or in machine coordinates (the
    machine has that position). It is written every time, and the work position is not known after it."""
    if not (isinstance(operation, Rapid) and operation.at_change):
        return False
    if getattr(post, "has_change_position", False):
        return True
    context = getattr(post, "context", None)
    return context is not None and context.change_radius_mm is not None and context.change_z_mm is not None


def generate_gcode(
    plan: ProgramPlan,
    post: Postprocessor,
    settings: PostSettings,
    accepted: frozenset[RemedyKey] | set[RemedyKey] = frozenset(),
    header_notes: tuple[str, ...] = (),
    context: PostContext | None = None,
) -> GenerationResult:
    """The G-code of the plan from the postprocessor, with the accepted remedies applied; a block with an open issue is left out and the result is marked incomplete."""
    post = post.fresh()  # the postprocessor remembers modal values, so every run starts new
    if context is not None:
        post.start(context)
    info = post.info
    accepted = set(accepted)
    issues = find_issues(plan, info, settings)
    open_issues = [issue for issue in issues if issue.key is None or issue.key not in accepted]
    skipped = sorted({issue.block_index for issue in open_issues if issue.block_index is not None})
    applied = [
        f"{_block_label(plan, issue.block_index)}: {issue.remedy_text}"
        for issue in issues
        if issue.key is not None and issue.key in accepted
    ]
    if (None, RemedyKind.RADIUS_MODE) in accepted and any(i.remedy is RemedyKind.RADIUS_MODE for i in issues):
        settings = replace(settings, x_mode=XInputMode.RADIUS)
    program_level_open = [i for i in open_issues if i.block_index is None]
    if program_level_open:
        skipped = list(range(len(plan.blocks)))

    notes: list[str] = list(header_notes)  # for example what a partial output contains
    notes += [f"remedy, {text}" for text in applied]
    if skipped:
        notes.append("INCOMPLETE - DO NOT RUN: " + ", ".join(_block_label(plan, i) for i in skipped) + " not output")
    if plan.left_out:  # blocks with no usable contour (C10)
        notes.append("INCOMPLETE - DO NOT RUN: " + "; ".join(left.text for left in plan.left_out))

    lines = post.header(settings, notes)
    position: Point | None = None
    for index, operations in _groups(plan):
        if index is not None and index in skipped:
            reasons = "; ".join(i.message for i in open_issues if i.block_index in (index, None))
            lines += post.comment(f"{_block_label(plan, index)} NOT OUTPUT: {reasons}")
            continue
        for operation in _rewrite(plan, index, operations, accepted) if index is not None else operations:
            if isinstance(operation, Rapid) and operation.end == position and not _machine_move(post, operation):
                continue  # already there
            lines += _emit(post, operation, position, settings)
            end = getattr(operation, "end", None)
            if isinstance(end, Point):
                position = None if _machine_move(post, operation) else end  # a move in machine coordinates: the work position is not known
    lines += post.footer()
    lines = post.number_lines(lines)
    return GenerationResult(
        text=post.line_ending.join(lines) + post.line_ending,
        complete=not skipped and not plan.left_out,
        issues=tuple(issues),
        applied_remedies=tuple(applied),
        skipped_blocks=tuple(skipped),
    )


def _emit(post: Postprocessor, operation: Operation, position: Point | None, settings: PostSettings) -> list[str]:
    if isinstance(operation, BlockBegin):
        return post.block_begin(operation)
    if isinstance(operation, BlockEnd):
        return []
    if isinstance(operation, Rapid):
        return post.rapid(operation)
    if isinstance(operation, RapidAxes):
        return post.rapid_axes(operation)
    if isinstance(operation, LinearMove):
        return post.linear(operation)
    if isinstance(operation, ArcMove):
        if position is None:
            raise PostError("an arc needs a known start position")
        return post.arc(operation, position.x, position.z)
    if isinstance(operation, DrillOperation):
        return post.drill(operation, settings)
    if isinstance(operation, ThreadOperation):
        return post.thread(operation)
    if isinstance(operation, ToolChange):
        return post.tool_change(operation.tool_number)
    if isinstance(operation, SetSpindle):
        return post.set_spindle(operation.setting)
    if isinstance(operation, StopSpindle):
        return post.stop_spindle()
    if isinstance(operation, SetCoolant):
        return post.set_coolant(operation.mode)
    if isinstance(operation, Comment):
        return post.comment(operation.text)
    if isinstance(operation, MachineFunction):
        return post.machine_function(operation, settings)
    if isinstance(operation, FunctionCall):
        return post.function_call(operation)
    raise PostError(f"no postprocessor method for {type(operation).__name__}")
