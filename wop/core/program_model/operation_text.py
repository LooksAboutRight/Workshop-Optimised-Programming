"""The neutral operations as plain text, one line each, for people who want to see what a block produces.

X is the radius, Z the axial position, feeds are mm per revolution (see operations.py). No dialect, no G-code.
"""

from __future__ import annotations

from .operations import (
    ArcMove,
    BlockBegin,
    BlockEnd,
    Comment,
    DrillOperation,
    LinearMove,
    FunctionCall,
    MachineFunction,
    MoveRole,
    Operation,
    RapidAxes,
    Rapid,
    SetCoolant,
    SetSpindle,
    StopSpindle,
    ThreadOperation,
    ThreadTaper,
    ToolChange,
    spindle_text,
)

HEADER = "X = radius, Z = axial position, feed in mm per revolution"


def _axes(x: float | None, z: float | None) -> str:
    return " ".join(part for part in (None if x is None else f"X{x:g}", None if z is None else f"Z{z:g}") if part)


def _compensation_text(move) -> str:
    """What a compensated finishing move adds: its role, the side of the tool and the contour point."""
    parts = []
    if move.role is not MoveRole.NORMAL:
        parts.append(move.role.value)
    if getattr(move, "side", None) is not None:
        parts.append(f"tool {move.side.value}")
    if move.contour_end is not None:
        parts.append(f"contour {_axes(move.contour_end.x, move.contour_end.z)}")
    return f"  [{', '.join(parts)}]" if parts else ""


def describe_operation(operation: Operation) -> str:
    """One line for one operation."""
    if isinstance(operation, Rapid):
        return f"RAPID    {_axes(operation.end.x, operation.end.z)}"
    if isinstance(operation, RapidAxes):
        return f"RAPID    {_axes(operation.x, operation.z)}"
    if isinstance(operation, LinearMove):
        return f"FEED     {_axes(operation.end.x, operation.end.z)}  feed {operation.feed_mm_per_rev:g}{_compensation_text(operation)}"
    if isinstance(operation, ArcMove):
        return (
            f"ARC      {_axes(operation.end.x, operation.end.z)}  centre {_axes(operation.center.x, operation.center.z)}"
            f"  {operation.direction.name.lower()}  feed {operation.feed_mm_per_rev:g}{_compensation_text(operation)}"
        )
    if isinstance(operation, DrillOperation):
        pecks = "" if operation.peck_depth_mm is None else f", pecks of {operation.peck_depth_mm:g}"
        dwell = f", dwell {operation.dwell_s:g} s" if operation.dwell_s > 0 else ""
        air = f", rapid in to Z{operation.air_z:g}" if operation.skips_air else ""
        return (
            f"DRILL    {operation.effective_mode.value}: from Z{operation.retract_z:g} to Z{operation.end_z:g}{air}, "
            f"feed {operation.feed_mm_per_rev:g}{pecks}{dwell}, out to Z{operation.end.z:g}"
        )
    if isinstance(operation, ThreadOperation):
        return (
            f"THREAD   start {_axes(operation.start_x, operation.start_z)} to Z{operation.end_z:g}, pitch {operation.pitch_mm:g}, "
            f"depth {operation.depth_mm:g}, first cut {operation.first_cut_mm:g}, {operation.spring_passes} spring passes"
            + ("" if operation.taper is ThreadTaper.NONE else f", {operation.taper.value} taper {operation.taper_distance_mm:g}")
        )
    if isinstance(operation, ToolChange):
        return f"TOOL     T{operation.tool_number}"
    if isinstance(operation, SetSpindle):
        return f"SPINDLE  {spindle_text(operation.setting)}"
    if isinstance(operation, StopSpindle):
        return "SPINDLE  off"
    if isinstance(operation, SetCoolant):
        return f"COOLANT  {operation.mode.value}"
    if isinstance(operation, MachineFunction):
        extra = f" {operation.seconds:g} s" if operation.seconds else ""
        return f"FUNCTION {operation.kind.value}{extra}"
    if isinstance(operation, FunctionCall):
        given = "".join(f" {name}={value:g}" if isinstance(value, float) else f" {name}={value}" for name, value in operation.values)
        return f"FUNCTION {operation.name}{given}"
    if isinstance(operation, BlockBegin):
        return f"BEGIN    block {operation.block_id} ({operation.type_name}) {operation.name}".rstrip()
    if isinstance(operation, BlockEnd):
        return f"END      block {operation.block_id}"
    if isinstance(operation, Comment):
        return f"COMMENT  {operation.text}"
    return repr(operation)


def describe_operations(operations: tuple[Operation, ...] | list[Operation], single_moves: bool = False) -> str:
    """The operations as text with a line of explanation on top. With `single_moves` a drill or thread operation
    is followed by the plain moves it stands for (what a controller without the cycle gets)."""
    lines = [HEADER, ""]
    for operation in operations:
        lines.append(describe_operation(operation))
        if single_moves and isinstance(operation, (DrillOperation, ThreadOperation)):
            lines += ["    " + describe_operation(move) for move in operation.explicit_moves()]
    return "\n".join(lines)
