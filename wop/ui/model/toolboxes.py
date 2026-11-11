"""The toolboxes of the tool library (T17)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...core.constants import NO_TOOL_NUMBER
from ...core.program_model.project import Project
from ...core.tooling.toolbox import Toolbox, ToolboxEntry, ToolboxError, check_toolboxes, find_toolbox, tools_of_toolbox, toolboxes_using
from .helpers import ModelError, TOOL_SAME_AS_LIBRARY


@dataclass(frozen=True)
class ToolboxChange:
    """What a change of the toolbox does to a project (T19)."""

    toolbox: str
    unhooked: tuple[int, ...] = ()  # the blocks (0 = first) that lose their tool: "no tool chosen"
    renumbered: tuple[int, ...] = ()  # the blocks that keep their tool, which has another number in the toolbox
    kept: tuple[int, ...] = ()  # the blocks that keep their tool under the same number

    @property
    def changes_blocks(self) -> bool:
        return bool(self.unhooked or self.renumbered)


class ToolboxesMixin:
    """The toolboxes of the active tool library. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    @property
    def toolboxes(self) -> tuple[Toolbox, ...]:
        return self.app_settings.toolboxes

    @property
    def default_toolbox(self) -> str | None:
        return self.app_settings.default_toolbox

    def toolboxes_using_tool(self, tool_name: str) -> tuple[str, ...]:
        """The toolboxes of the library that hold a library tool (to warn before the tool is deleted)."""
        return toolboxes_using(self.toolboxes, tool_name)

    def save_toolbox(self, box: Toolbox, old_name: str | None = None) -> None:
        """Add a toolbox to the library, or replace the one called `old_name` (also when it is renamed)."""
        previous = old_name if old_name is not None else box.name
        clash = find_toolbox(self.toolboxes, box.name)
        if clash is not None and box.name.casefold() != previous.casefold():
            raise ModelError(f"there is already a toolbox called {box.name!r}")
        kept = tuple(b for b in self.toolboxes if b.name.casefold() != previous.casefold())
        default = box.name if self.default_toolbox is not None and self.default_toolbox.casefold() == previous.casefold() else self.default_toolbox
        self._set_toolboxes(kept + (box,), default)

    def delete_toolbox(self, name: str) -> None:
        if find_toolbox(self.toolboxes, name) is None:
            raise ModelError(f"there is no toolbox {name!r}")
        kept = tuple(b for b in self.toolboxes if b.name.casefold() != name.casefold())
        default = None if self.default_toolbox is not None and self.default_toolbox.casefold() == name.casefold() else self.default_toolbox
        self._set_toolboxes(kept, default)

    def set_default_toolbox(self, name: str | None) -> None:
        """The toolbox a new project starts with; None: a new project has no tools."""
        if name is not None and find_toolbox(self.toolboxes, name) is None:
            raise ModelError(f"there is no toolbox {name!r}")
        self._set_toolboxes(self.toolboxes, None if name is None else find_toolbox(self.toolboxes, name).name)

    def save_project_tools_as_toolbox(self, name: str, update: bool = False) -> None:
        """Make a toolbox of the tools of the project, with their numbers and offsets (`update`: replace the toolbox of that name).
        Every tool must be in the library as it is (a toolbox points at library tools), else the user is told which ones to save first."""
        tools = self.program.tools
        loose = [t.name for t in tools if self.tool_library_state(t.number) != TOOL_SAME_AS_LIBRARY]
        if not tools:
            raise ModelError("the project has no tools")
        if not update and find_toolbox(self.toolboxes, name) is not None:
            raise ModelError(f"there is already a toolbox called {name!r}")
        if loose:
            raise ModelError(f"save these tools to the library first (they are not in it, or differ from it): {', '.join(loose)}")
        self.save_toolbox(Toolbox(name, tuple(ToolboxEntry(t.name, t.number, t.offset_number) for t in tools)))
        self._remember_toolbox(name)
        self._changed()

    def current_toolbox(self) -> Toolbox | None:
        """The toolbox the tools of the project came from, when the active library still has it."""
        program = self.program
        if not program.toolbox_name or program.toolbox_library.casefold() != self.active_library_name("tools").casefold():
            return None
        return find_toolbox(self.toolboxes, program.toolbox_name)

    def toolbox_line(self) -> str:
        """The line of the Tools view: which toolbox the project has, and whether its tools were changed since."""
        program = self.program
        if not program.toolbox_name:
            return "Toolbox: none"
        box = self.current_toolbox()
        if box is None:
            return f"Toolbox: {program.toolbox_name} (library {program.toolbox_library}; not in the library in use)"
        now = sorted((t.number, t.origin_name.casefold(), t.offset_number) for t in program.tools)
        wanted = sorted((e.number, e.tool_name.casefold(), e.offset_number) for e in box.entries)
        marks = []
        if self.default_toolbox is not None and box.name.casefold() == self.default_toolbox.casefold():
            marks.append("default")
        if now != wanted:
            marks.append("tools changed since")
        return f"Toolbox: {box.name}" + (f" ({', '.join(marks)})" if marks else "")

    def make_current_toolbox_default(self) -> None:
        box = self.current_toolbox()
        if box is None:
            raise ModelError("the project has no toolbox of the library in use")
        self.set_default_toolbox(box.name)

    def _remember_toolbox(self, name: str) -> None:
        self.project = replace(self.project, program=replace(
            self.program, toolbox_library=self.active_library_name("tools"), toolbox_name=name,
        ))

    def toolbox_tools(self, name: str):
        """Copies of the library tools of a toolbox, numbered as the box says, marked with the library they come from."""
        box = find_toolbox(self.toolboxes, name)
        if box is None:
            raise ModelError(f"there is no toolbox {name!r}")
        library = self.active_library_name("tools")
        return tuple(replace(tool, origin_library=library, origin_name=entry.tool_name)
                     for tool, entry in zip(tools_of_toolbox(box, self.app_settings.tools), box.entries))

    def _with_default_toolbox(self, project: Project) -> Project:
        """A new project gets the tools of the default toolbox of the active library; without one it has none."""
        if self.default_toolbox is None:
            return project
        return replace(project, program=replace(
            project.program, tools=self.toolbox_tools(self.default_toolbox),
            toolbox_library=self.active_library_name("tools"), toolbox_name=self.default_toolbox,
        ))

    def _new_numbers(self, name: str) -> dict[int, int]:
        """For every tool of the project that the toolbox holds (the same tool of the same library): its number in the toolbox.
        Two tools with one name in two libraries are not known to be the same, so a tool of another library is not found."""
        library = self.active_library_name("tools").casefold()
        by_name = {entry.tool_name.casefold(): entry.number for entry in find_toolbox(self.toolboxes, name).entries}
        return {
            tool.number: by_name[tool.origin_name.casefold()]
            for tool in self.program.tools
            if tool.origin_library.casefold() == library and tool.origin_name.casefold() in by_name
        }

    def toolbox_change(self, name: str) -> ToolboxChange:
        """What putting a toolbox into the project would do to the blocks (the window tells the user before it is done)."""
        if find_toolbox(self.toolboxes, name) is None:
            raise ModelError(f"there is no toolbox {name!r}")
        numbers = self._new_numbers(name)
        unhooked, renumbered, kept = [], [], []
        for index, block in enumerate(self.blocks):
            if not block.needs_tool or block.tool_number == NO_TOOL_NUMBER:
                continue
            if block.tool_number not in numbers:
                unhooked.append(index)
            elif numbers[block.tool_number] != block.tool_number:
                renumbered.append(index)
            else:
                kept.append(index)
        return ToolboxChange(find_toolbox(self.toolboxes, name).name, tuple(unhooked), tuple(renumbered), tuple(kept))

    def apply_toolbox(self, name: str) -> ToolboxChange:
        """Replace the tools of the project by those of a toolbox. A block keeps its tool when the box holds the same tool of the
        same library (it follows the tool to its new number); every other block gets "no tool chosen"."""
        change = self.toolbox_change(name)
        numbers = self._new_numbers(name)
        blocks = tuple(
            replace(b, tool_number=numbers.get(b.tool_number, NO_TOOL_NUMBER)) if b.tool_number != NO_TOOL_NUMBER else b
            for b in self.blocks
        )
        tools = self.toolbox_tools(name)
        self.project = replace(self.project, program=replace(self.program, tools=tools, blocks=blocks))
        self._remember_toolbox(change.toolbox)
        self.selected_tool = tools[0].number if tools else None
        self._changed()
        return change

    def _set_toolboxes(self, boxes: tuple[Toolbox, ...], default: str | None) -> None:
        try:
            check_toolboxes(boxes, default, self.app_settings.tools)
        except ToolboxError as error:
            raise ModelError(str(error)) from error
        self._set_app_settings(replace(self.app_settings, toolboxes=boxes, default_toolbox=default))
        self._changed(dirty=False)
