"""Postprocessor interface and capability flags (O1, O2, O4).

A postprocessor says which features it supports and has one method per neutral operation. The only implementation is the
template engine (`engine.py`), which reads a post file; a new controller is a new file, nothing in the core changes.
There is no record of what was verified on a real machine: the user checks what a post writes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from ..core.program_model.operations import (
    ArcMove,
    BlockBegin,
    CoolantMode,
    DrillOperation,
    ThreadOperation,
    LinearMove,
    FunctionCall,
    MachineFunction,
    MachineFunctionKind,
    Rapid,
    RapidAxes,
    SpindleSetting,
)
from ..core.program_model.units import UnitSystem, XInputMode


class PostError(ValueError):
    """A postprocessor problem (unknown name, bad registration)."""


class Feature(Enum):
    """Things a program can use that a controller may or may not support."""

    CONSTANT_SURFACE_SPEED = "constant surface speed"
    DIAMETER_MODE = "diameter mode"
    ARCS = "arcs"
    ARCS_IN_DIAMETER_MODE = "arcs in diameter mode"
    COOLANT_FLOOD = "flood coolant"
    COOLANT_MIST = "mist coolant"
    TOOL_CHANGE = "tool change"
    THREAD_CYCLE = "thread cycle"
    PROGRAM_STOP = "program stop"
    OPTIONAL_STOP = "optional stop"
    DWELL = "dwell"
    SPINDLE_STOP = "spindle stop"
    SPINDLE_REVERSE = "reversed spindle"
    # later: DRILL_CYCLE, SUB_SPINDLE, LIVE_TOOLING


@dataclass(frozen=True)
class PostInfo:
    controller_id: str  # also used to mark hand-written blocks
    name: str
    supported: frozenset[Feature]
    functions: dict = field(default_factory=dict, hash=False, compare=False)  # the custom concepts of the post: name -> variables.Function


@dataclass(frozen=True)
class PostSettings:
    x_mode: XInputMode  # G-code mode of the whole program (B11)
    unit: UnitSystem = UnitSystem.METRIC  # the unit of the numbers in the G-code (the unit of the machine); the program itself is in mm


def function_feature(kind: MachineFunctionKind) -> Feature | None:
    """The feature a postprocessor needs to write a machine function."""
    if kind is MachineFunctionKind.PROGRAM_STOP:
        return Feature.PROGRAM_STOP
    if kind is MachineFunctionKind.OPTIONAL_STOP:
        return Feature.OPTIONAL_STOP
    if kind is MachineFunctionKind.DWELL:
        return Feature.DWELL
    return Feature.SPINDLE_STOP


class Postprocessor(ABC):
    """One controller dialect. An instance is used for one generation run."""

    @property
    @abstractmethod
    def info(self) -> PostInfo: ...

    def fresh(self) -> "Postprocessor":
        """A new instance with no memory of earlier output (feed, modal state)."""
        return type(self)()

    def start(self, context) -> None:
        """What the post may know besides the operations (tools, blocks, project, clock: `PostContext`). The Python posts ignore it."""

    @property
    def line_ending(self) -> str:
        return "\n"

    def block_begin(self, operation: BlockBegin) -> list[str]:
        """The start of a block of the program."""
        return self.comment(f"Block {operation.index + 1}: {operation.type_name} {operation.name}".strip())

    @abstractmethod
    def header(self, settings: PostSettings, notes: list[str]) -> list[str]:
        """Start of the program. `notes` are lines the user must see (remedies, what is incomplete)."""

    @abstractmethod
    def footer(self) -> list[str]: ...

    def number_lines(self, lines: list[str]) -> list[str]:
        """The finished lines with line numbers, when the post wants them."""
        return lines

    @abstractmethod
    def comment(self, text: str) -> list[str]: ...

    @abstractmethod
    def rapid(self, move: Rapid) -> list[str]: ...

    @abstractmethod
    def rapid_axes(self, move: RapidAxes) -> list[str]: ...

    @abstractmethod
    def linear(self, move: LinearMove) -> list[str]: ...

    @abstractmethod
    def arc(self, move: ArcMove, start_x: float, start_z: float) -> list[str]: ...

    def drill(self, operation: DrillOperation, settings: PostSettings) -> list[str]:
        """Drill operation. The default is explicit moves (and the dwell); a controller with a cycle overrides it."""
        lines: list[str] = []
        for move in operation.explicit_moves():
            if isinstance(move, Rapid):
                lines += self.rapid(move)
            elif isinstance(move, LinearMove):
                lines += self.linear(move)
            else:
                lines += self.machine_function(move, settings)
        return lines

    def thread(self, operation: ThreadOperation) -> list[str]:
        """Thread cutting needs the controller's synchronised cycle; there is no plain-move version."""
        raise PostError("this postprocessor has no thread cycle")

    def machine_function(self, operation: MachineFunction, settings: PostSettings) -> list[str]:
        """A machine function (stop, dwell). A controller that has them overrides this."""
        raise PostError(f"this postprocessor cannot write {operation.kind.value}")

    def function_call(self, operation: FunctionCall) -> list[str]:
        """A custom function of the post. A controller that has them overrides this."""
        raise PostError(f"this postprocessor has no function {operation.name!r}")

    @abstractmethod
    def tool_change(self, tool_number: int) -> list[str]: ...

    @abstractmethod
    def set_spindle(self, setting: SpindleSetting) -> list[str]: ...

    @abstractmethod
    def stop_spindle(self) -> list[str]: ...

    @abstractmethod
    def set_coolant(self, mode: CoolantMode) -> list[str]: ...
