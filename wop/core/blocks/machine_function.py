"""Machine function block (requirement B13): a function of the post that is not a motion.

The function is chosen from a list that follows the post: the stops, the dwell and the spindle stop (each offered when the post has its
code) and the custom concepts of the post file (`[functions]`). The values of the variables of a custom concept are stored by name. The
block never guesses a code: the post writes the function. An empty name takes the name of the function.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..constants import EXAMPLE_DWELL_S, FIXED_FUNCTION_NAMES
from ..program_model.operations import (
    BlockBegin,
    BlockEnd,
    FunctionCall,
    MachineFunction,
    MachineFunctionKind,
    SpindleSetting,
    StopSpindle,
)
from ..geometry.region import Region
from .base import BLOCK_TYPES, Block, BlockContext, BlockError, BlockResult


@dataclass(frozen=True)
class FunctionValue:
    """The value of one variable of a custom function: a number, a flag or a text (the one that is set)."""

    name: str
    number: float | None = None
    flag: bool | None = None
    text: str = ""

    @property
    def value(self) -> "float | bool | str":
        if self.number is not None:
            return self.number
        if self.flag is not None:
            return self.flag
        return self.text


def fixed_kind(function: str) -> MachineFunctionKind | None:
    """The kind of a function every post knows, or None for a custom function."""
    return MachineFunctionKind[function.upper()] if function in FIXED_FUNCTION_NAMES else None


def function_label(function: str) -> str:
    """The name of a function as the user reads it: "program stop", "Bar feed"."""
    kind = fixed_kind(function)
    return kind.value if kind is not None else function.replace("_", " ").capitalize()


@BLOCK_TYPES.register
@dataclass(frozen=True, kw_only=True)
class MachineFunctionBlock(Block):
    type_name = "machine_function"
    label = "Machine function"
    needs_tool = False

    function: str = FIXED_FUNCTION_NAMES[0]  # the name of a fixed function or of a custom concept of the post
    dwell_s: float = EXAMPLE_DWELL_S  # only for a dwell
    values: tuple[FunctionValue, ...] = ()  # the variables of a custom function

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "MachineFunctionBlock":
        return cls(block_id=block_id, tool_number=tool_number, spindle=spindle)

    def __post_init__(self) -> None:
        if not self.function:
            raise BlockError("a machine function block needs a function")
        if self.function == "dwell" and self.dwell_s <= 0:
            raise BlockError("a dwell needs a time greater than zero")

    def form_fields(self) -> tuple[str, ...]:
        """Name and function first; the dwell time only for a dwell, the variables of a custom function after them (built by the form)."""
        return ("name", "function") + (("dwell_s",) if self.function == "dwell" else ())

    def form_function_field(self) -> str:
        """The field that holds the function; the form adds the variables of that function as fields (`variable_value`, `with_variable`)."""
        return "function"

    def form_key(self) -> str:
        return self.function  # the form is built again when the function changes

    def variable_value(self, name: str) -> "float | bool | str | None":
        found = next((item for item in self.values if item.name == name), None)
        return None if found is None else found.value

    def with_variable(self, name: str, value: "float | bool | str | None") -> "MachineFunctionBlock":
        """The block with the value of a variable set (None takes it away)."""
        others = tuple(item for item in self.values if item.name != name)
        if value is None:
            return replace(self, values=others)
        if isinstance(value, bool):
            item = FunctionValue(name, flag=value)
        elif isinstance(value, (int, float)):
            item = FunctionValue(name, number=float(value))
        else:
            item = FunctionValue(name, text=str(value))
        return replace(self, values=(*others, item))

    @property
    def title(self) -> str:
        return self.name or function_label(self.function)

    @property
    def stops_spindle(self) -> bool:  # type: ignore[override]
        return fixed_kind(self.function) is MachineFunctionKind.SPINDLE_STOP

    def generate(self, context: BlockContext) -> BlockResult:
        kind = fixed_kind(self.function)
        if kind is MachineFunctionKind.SPINDLE_STOP:
            action = StopSpindle()
        elif kind is not None:
            action = MachineFunction(kind, self.dwell_s if kind is MachineFunctionKind.DWELL else 0)
        else:
            action = FunctionCall(self.function, tuple((item.name, item.value) for item in self.values))
        operations = (BlockBegin(0, self.block_id, self.type_name, self.title), action, BlockEnd(self.block_id))
        return BlockResult(operations, Region.empty())
