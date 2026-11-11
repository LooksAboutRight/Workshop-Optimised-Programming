"""The tools of the program and the tool library."""

from __future__ import annotations

from dataclasses import replace

from ...core.contour import Contour
from ...core.tooling.tool import Tool
from ...core.tooling.toolbox import without_tool
from ...core.tooling.tool_shape import tool_from_contour
from ...core.tool_types import definition_of, info_of, make_tool, TOOL_TYPES
from .helpers import ModelError, ShapeToolForm, TOOL_DIFFERS_FROM_LIBRARY, TOOL_NOT_IN_LIBRARY, TOOL_SAME_AS_LIBRARY, starter_tools, tool_core


class ToolsMixin:
    """The tools of the program and the tool library. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def tool_type_choices(self) -> tuple[tuple[str, str], ...]:
        """(type name, label) of the tool types for the Add menu (T8)."""
        return tuple((tool_type.type_name, tool_type.label) for tool_type in TOOL_TYPES.types())

    def add_tool_of_type(self, type_name: str) -> int:
        """Add a tool of a type with the default values of its form, under the next free number, and choose it."""
        used = {t.number for t in self.program.tools}
        number = max(used, default=0) + 1
        try:
            tool = make_tool(type_name, number, TOOL_TYPES.get(type_name).default())
        except ValueError as error:
            raise ModelError(str(error)) from error
        self.project = replace(self.project, program=replace(self.program, tools=self.program.tools + (tool,)))
        self.selected, self.selected_contour = None, None
        self.tools_view, self.selected_tool = True, number
        self.workholding_view = False
        self._changed()
        return number

    def tool_form(self, number: int) -> object:
        """What the form of a tool shows: its definition, or name and material for a tool that is only a shape."""
        tool = self.program.tool(number)
        try:
            definition = definition_of(tool)
        except ValueError as error:
            raise ModelError(str(error)) from error
        return ShapeToolForm(number, tool.name, tool.material) if definition is None else replace(definition, number=number)

    def tool_info(self, number: int) -> tuple[str, ...]:
        """Lines that explain the definition of a tool (an insert designation decoded); a wrong definition gives its problem."""
        try:
            return info_of(self.program.tool(number))
        except ValueError as error:
            return (str(error),)

    def edit_tool(self, number: int, form: object) -> None:
        """Apply the form of a tool (the same form as when it was added). Raises ModelError for impossible values."""
        tool = self.program.tool(number)
        new_number = form.number
        if new_number != number:
            if new_number < 1:
                raise ModelError("a tool number must be 1 or more")
            if any(t.number == new_number for t in self.program.tools):
                raise ModelError(f"tool T{new_number} already exists")
        try:
            if isinstance(form, ShapeToolForm):
                new = replace(tool, number=new_number, name=form.name.strip() or tool.name, material=form.material)
            else:
                old = definition_of(tool)
                form = TOOL_TYPES.get(tool.kind).reconcile(old, form)
                new = replace(make_tool(tool.kind, new_number, form), offset_number=tool.offset_number,
                              origin_library=tool.origin_library, origin_name=tool.origin_name)
        except ValueError as error:
            raise ModelError(str(error)) from error
        tools = tuple(new if t.number == number else t for t in self.program.tools)
        program = replace(self.program, tools=tools)
        if new_number != number:  # the blocks that use the tool follow its new number
            blocks = tuple(
                replace(b, tool_number=new_number) if getattr(b, "tool_number", None) == number else b for b in program.blocks
            )
            program = replace(program, blocks=blocks)
            if self.selected_tool == number:
                self.selected_tool = new_number
        self.project = replace(self.project, program=program)
        self._refresh_tool_defaults(new_number)
        self._changed()

    def set_tool_offset(self, number: int, offset: int | None) -> None:
        """Set the tool offset the post calls after the tool change (G43 H..); None: the offset is the tool number. Raises ModelError."""
        self.program.tool(number)
        if offset is not None and offset < 1:
            raise ModelError("a tool offset number must be 1 or more")
        tools = tuple(replace(t, offset_number=offset) if t.number == number else t for t in self.program.tools)
        self.project = replace(self.project, program=replace(self.program, tools=tools))
        self._changed()

    def set_tool_shape(self, number: int, contour: Contour) -> None:
        """Give a tool the outline and the named points of an edited contour. The tool then has no type form any more."""
        try:
            new = tool_from_contour(self.program.tool(number), contour)
        except ValueError as error:
            raise ModelError(str(error)) from error
        tools = tuple(new if t.number == number else t for t in self.program.tools)
        self.project = replace(self.project, program=replace(self.program, tools=tools))
        self._changed()

    @property
    def tool_library(self) -> tuple[Tool, ...]:
        return self.app_settings.tools

    def tool_library_state(self, number: int) -> str:
        """How a tool of the project stands to the library: "new" (no tool of that name), "same" or "differs"."""
        tool = self.program.tool(number)
        found = next((t for t in self.tool_library if t.name.casefold() == tool.name.casefold()), None)
        if found is None:
            return TOOL_NOT_IN_LIBRARY
        return TOOL_SAME_AS_LIBRARY if tool_core(found) == tool_core(tool) else TOOL_DIFFERS_FROM_LIBRARY

    def tools_differing_from_library(self) -> tuple[int, ...]:
        """Numbers of the project's tools that have a tool of the same name in the library with other values."""
        return tuple(t.number for t in self.program.tools if self.tool_library_state(t.number) == TOOL_DIFFERS_FROM_LIBRARY)

    def tools_new_to_library(self) -> tuple[int, ...]:
        """Numbers of the project's tools that the library does not have yet (no tool of that name).

        A tool exactly as its type makes it, or as a new project starts with it (name and values), is not offered.
        """
        factory = [tool_core(t) for t in starter_tools()]  # the tools of the example projects
        for tool_type in TOOL_TYPES.types():
            try:
                factory.append(tool_core(make_tool(tool_type.type_name, 1, tool_type.default())))
            except ValueError:
                continue
        return tuple(
            t.number for t in self.program.tools
            if self.tool_library_state(t.number) == TOOL_NOT_IN_LIBRARY and tool_core(t) not in factory
        )

    def add_tool_from_library(self, name: str) -> int:
        """Copy a tool of the library into the project. It keeps its library number when that is free, else it gets the
        next free one. Returns the number."""
        found = next((t for t in self.tool_library if t.name.casefold() == name.casefold()), None)
        if found is None:
            raise ModelError(f"there is no tool {name!r} in the library")
        used = {t.number for t in self.program.tools}
        number = found.number if found.number not in used and found.number >= 1 else max(used, default=0) + 1
        tool = replace(found, number=number, origin_library=self.active_library_name("tools"), origin_name=found.name)
        self.project = replace(self.project, program=replace(self.program, tools=self.program.tools + (tool,)))
        self.selected, self.selected_contour = None, None
        self.tools_view, self.selected_tool = True, number
        self.workholding_view = False
        self._changed()
        return number

    def save_tool_to_library(self, number: int, replace_existing: bool = False) -> str:
        """Write a tool of the project to the library. A tool of the same name there is only replaced when
        `replace_existing` is set (the window asks first). Returns what happened."""
        tool = self.program.tool(number)
        state = self.tool_library_state(number)
        if state == TOOL_SAME_AS_LIBRARY:
            return f"{tool.name} is already in the library"
        if state == TOOL_DIFFERS_FROM_LIBRARY and not replace_existing:
            raise ModelError(f"the library has another tool called {tool.name!r}")
        kept = tuple(t for t in self.tool_library if t.name.casefold() != tool.name.casefold())
        self._set_app_settings(replace(self.app_settings, tools=kept + (tool,)))
        self._changed(dirty=False)
        where = self.library_file_path("tools")
        return f"{tool.name} saved to the {self.active_library_name('tools')} library" + ("" if where is None else f" ({where})")

    def remove_tool_from_library(self, name: str, from_toolboxes: bool = False) -> None:
        """Delete a tool of the library. A tool that toolboxes hold is only deleted with `from_toolboxes` (it leaves them too);
        the window asks first (`toolboxes_using_tool`)."""
        kept = tuple(t for t in self.tool_library if t.name.casefold() != name.casefold())
        if len(kept) == len(self.tool_library):
            raise ModelError(f"there is no tool {name!r} in the library")
        users = self.toolboxes_using_tool(name)
        if users and not from_toolboxes:
            raise ModelError(f"the tool {name!r} is in the toolbox {', '.join(users)}")
        self._set_app_settings(replace(self.app_settings, tools=kept, toolboxes=without_tool(self.toolboxes, name)))
        self._changed(dirty=False)

    def x_mode(self):
        """How X values are typed in the forms of the project (radius or diameter)."""
        return self.project.settings.x_mode

    def show_tools(self, number: int | None = None) -> None:
        """Show the Tools view in the centre (T8) with a tool chosen (the first one if none is given)."""
        self.selected = None
        self.selected_contour = None
        self.tools_view = True
        self.workholding_view = False
        numbers = sorted(t.number for t in self.program.tools)
        self.selected_tool = number if number in numbers else (numbers[0] if numbers else None)
        self._notify()

    def remove_tool(self, number: int) -> None:
        self._refuse_if_used(number)
        tools = tuple(t for t in self.program.tools if t.number != number)
        self.project = replace(self.project, program=replace(self.program, tools=tools))
        if self.selected_tool == number:
            self.selected_tool = tools[0].number if tools else None
        self._changed()

    def select_tool(self, number: int | None) -> None:
        self.selected_tool = number
        self._notify()

    def _refuse_if_used(self, number: int) -> None:
        users = [b.name or b.block_id for b in self.blocks if b.tool_number == number]
        if users:
            raise ModelError(f"tool T{number} is used by: {', '.join(users)}")
