"""Tool types (requirement T8): each type has its own definition form and builds the tool shape.

A type is one file in this package. It declares a definition dataclass (its form is made from the
type hints, like the block forms) and builds the `Tool` from it. `make_tool` adds the common parts: the
tool material, the type name and the definition as plain data, so the tool can be edited later with the
same form.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..constants import TOOL_TYPE_ORDER
from ..files.dataclass_codec import CodecError, from_data, to_data
from ..tooling.tool import Tool, ToolError


class ToolType:
    """Base of a tool type. Set the class attributes and write `build`; register with TOOL_TYPES.register."""

    type_name: str = ""  # stored in the project file
    label: str = ""  # shown in the Add menu
    definition_class: type  # a dataclass with at least `name` and `material`

    def default(self) -> Any:
        return self.definition_class()

    def build(self, number: int, definition: Any) -> Tool:
        """The tool shape for a definition. Raises ToolError for impossible values."""
        raise NotImplementedError

    def reconcile(self, old: Any, new: Any) -> Any:
        """The new definition after a form edit, with dependent fields brought in step (codes and dropdowns); unchanged by default."""
        return new

    def info(self, definition: Any) -> tuple[str, ...]:
        """Lines of text that explain the definition (shown under the form); none by default."""
        return ()


class ToolTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, ToolType] = {}

    def register(self, tool_class: type[ToolType]) -> type[ToolType]:
        instance = tool_class()
        if not instance.type_name or not instance.label:
            raise ToolError(f"{tool_class.__name__} has no type_name or label")
        if instance.type_name in self._types:
            raise ToolError(f"tool type {instance.type_name!r} is already registered")
        self._types[instance.type_name] = instance
        return tool_class

    def get(self, type_name: str) -> ToolType:
        if type_name not in self._types:
            raise ToolError(f"unknown tool type {type_name!r}")
        return self._types[type_name]

    def types(self) -> list[ToolType]:
        order = {name: place for place, name in enumerate(TOOL_TYPE_ORDER)}
        return sorted(self._types.values(), key=lambda t: (order.get(t.type_name, len(order)), t.label))


TOOL_TYPES = ToolTypeRegistry()


def make_tool(type_name: str, number: int, definition: Any) -> Tool:
    """The tool of a type for a definition, with the definition kept for editing."""
    tool_type = TOOL_TYPES.get(type_name)
    if hasattr(definition, "number"):
        definition = replace(definition, number=number)
    tool = tool_type.build(number, definition)
    return replace(tool, material=definition.material, kind=type_name, definition=to_data(definition))


def definition_of(tool: Tool) -> Any | None:
    """The definition a tool was made from; None for a tool without type (a shape only)."""
    if not tool.kind or tool.definition is None:
        return None
    tool_type = TOOL_TYPES.get(tool.kind)
    try:
        return from_data(tool_type.definition_class, tool.definition)
    except CodecError as error:
        raise ToolError(f"tool T{tool.number}: {error}") from error


def info_of(tool: Tool) -> tuple[str, ...]:
    """The explaining lines of a tool's definition (for an insert: the designation decoded)."""
    definition = definition_of(tool)
    return () if definition is None else TOOL_TYPES.get(tool.kind).info(definition)
