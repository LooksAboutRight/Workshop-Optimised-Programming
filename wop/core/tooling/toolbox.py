"""Toolboxes (requirement T17): named lists of library tools with a tool number and an offset number each.

A toolbox lives in the tool library file next to the tools. It points at library tools by name; the numbers are the
toolbox's own (the library tool keeps no meaningful number). A new project gets a copy of the default toolbox.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .tool import Tool


class ToolboxError(ValueError):
    """The toolbox is not usable (a number twice, a tool the library does not have ...)."""


def _is_whole_number_from_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


@dataclass(frozen=True)
class ToolboxEntry:
    tool_name: str  # the name of a tool of the library
    number: int  # the tool number in the project
    offset_number: int | None = None  # the tool offset the post calls; None: the tool number


@dataclass(frozen=True)
class Toolbox:
    name: str
    entries: tuple[ToolboxEntry, ...] = ()  # kept in the order of the tool numbers

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolboxError("a toolbox needs a name")
        for entry in self.entries:
            if not _is_whole_number_from_one(entry.number):
                raise ToolboxError(f"toolbox {self.name!r}: the tool number of {entry.tool_name!r} must be a whole number from 1")
            if entry.offset_number is not None and not _is_whole_number_from_one(entry.offset_number):
                raise ToolboxError(f"toolbox {self.name!r}: the offset number of {entry.tool_name!r} must be a whole number from 1")
        numbers = [entry.number for entry in self.entries]
        if len(set(numbers)) != len(numbers):
            raise ToolboxError(f"toolbox {self.name!r}: a tool number is used twice")
        names = [entry.tool_name.casefold() for entry in self.entries]
        if len(set(names)) != len(names):
            raise ToolboxError(f"toolbox {self.name!r}: a tool is listed twice")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda entry: entry.number)))  # always in the order of the numbers


def check_toolboxes(boxes: tuple[Toolbox, ...], default: str | None, library_tools: tuple[Tool, ...]) -> None:
    """The toolboxes of a library: names unique, every entry names a tool of the library, the default is one of them."""
    names = [box.name.casefold() for box in boxes]
    if len(set(names)) != len(names):
        raise ToolboxError("a toolbox is listed twice")
    known = {tool.name.casefold() for tool in library_tools}
    for box in boxes:
        for entry in box.entries:
            if entry.tool_name.casefold() not in known:
                raise ToolboxError(f"toolbox {box.name!r} names the tool {entry.tool_name!r}, which the library does not have")
    if default is not None and default.casefold() not in names:
        raise ToolboxError(f"the default toolbox {default!r} does not exist")


def find_toolbox(boxes: tuple[Toolbox, ...], name: str) -> Toolbox | None:
    return next((box for box in boxes if box.name.casefold() == name.casefold()), None)


def toolboxes_using(boxes: tuple[Toolbox, ...], tool_name: str) -> tuple[str, ...]:
    """The names of the toolboxes that hold a library tool."""
    return tuple(box.name for box in boxes if any(entry.tool_name.casefold() == tool_name.casefold() for entry in box.entries))


def without_tool(boxes: tuple[Toolbox, ...], tool_name: str) -> tuple[Toolbox, ...]:
    """The toolboxes with a library tool taken out of every one of them."""
    return tuple(
        replace(box, entries=tuple(e for e in box.entries if e.tool_name.casefold() != tool_name.casefold())) for box in boxes
    )


def tools_of_toolbox(box: Toolbox, library_tools: tuple[Tool, ...]) -> tuple[Tool, ...]:
    """Copies of the library tools of a toolbox with the numbers of the box, in the order of the numbers."""
    by_name = {tool.name.casefold(): tool for tool in library_tools}
    result = []
    for entry in box.entries:
        tool = by_name.get(entry.tool_name.casefold())
        if tool is None:
            raise ToolboxError(f"toolbox {box.name!r} names the tool {entry.tool_name!r}, which the library does not have")
        result.append(replace(tool, number=entry.number, offset_number=entry.offset_number))
    return tuple(result)
