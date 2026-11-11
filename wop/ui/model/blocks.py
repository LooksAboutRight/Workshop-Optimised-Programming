"""Blocks and the untouched marks of fields."""

from __future__ import annotations

from dataclasses import replace

from ...core.blocks import BLOCK_TYPES
from ...core.blocks.base import Block
from ...core.constants import NO_TOOL_NUMBER
from ...core.program_model.operation_text import describe_operations
from ...core.program_model.operations import SpindleDirection, SpindleMode, SpindleSetting
from ...core.program_model.touched import block_owner, copy_owner, forget_owner, is_touched, mark_touched, mark_untouched, SETUP_OWNER
from ..app_constants import DEFAULT_NEW_BLOCK_RPM
from ..setup_form import safe_positions, setup_from_program
from .helpers import ModelError, new_project


class BlocksMixin:
    """Blocks and the untouched marks of fields. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def _next_block_id(self) -> str:
        used = {block.block_id for block in self.blocks}
        number = len(used) + 1
        while f"b{number}" in used:
            number += 1
        return f"b{number}"

    def add_block(self, type_name: str) -> int:
        """Add a block of the given type after the selected one (or at the end)."""
        block_class = BLOCK_TYPES.get(type_name)
        previous = self.selected_block() or (self.blocks[-1] if self.blocks else None)
        spindle = replace(previous.spindle, direction=SpindleDirection.CLOCKWISE) if previous else SpindleSetting(
            SpindleMode.CONSTANT_RPM, DEFAULT_NEW_BLOCK_RPM
        )  # a new block turns clockwise, whatever the block before did
        tools = self.program.tools
        tool_number = previous.tool_number if previous else min((t.number for t in tools), default=NO_TOOL_NUMBER)
        block = block_class.example(self._next_block_id(), tool_number, spindle)
        block = self._with_tool_defaults(block, block.tool_default_fields)
        block = self._with_followers(block)
        program = self.program  # a new block never gets a contour of its own (C10)
        position = len(program.blocks) if self.selected is None else self.selected + 1
        blocks = program.blocks[:position] + (block,) + program.blocks[position:]
        self.project = replace(self.project, program=replace(program, blocks=blocks))
        self.selected = position
        self.selected_contour = None
        self.tools_view = False
        self.workholding_view = False
        self._changed()
        return position

    def delete_block(self, index: int) -> None:
        self._check_index(index)
        blocks = self.blocks[:index] + self.blocks[index + 1 :]
        self._unticked.discard(self.blocks[index].block_id)  # an id may be used again
        touched = forget_owner(self.project.touched, block_owner(self.blocks[index].block_id))
        self.project = replace(self.project, program=replace(self.program, blocks=blocks), touched=touched)
        self.selected = min(index, len(blocks) - 1) if blocks else None
        self._changed()

    def copy_block(self, index: int) -> int:
        """Put an exact copy of a block right after it (new id, title with " copy", same touched marks). Returns its position."""
        self._check_index(index)
        source = self.blocks[index]
        copy = replace(source, block_id=self._next_block_id(), name=f"{source.name} copy" if source.name else "")
        position = index + 1
        blocks = self.blocks[:position] + (copy,) + self.blocks[position:]
        touched = copy_owner(self.project.touched, block_owner(source.block_id), block_owner(copy.block_id))
        self._unticked.discard(copy.block_id)
        self.project = replace(self.project, program=replace(self.program, blocks=blocks), touched=touched)
        self.selected = position
        self.selected_contour = None
        self._changed()
        return position

    def move_block(self, index: int, step: int) -> int:
        """Move a block up (-1) or down (+1). Returns its new position."""
        self._check_index(index)
        target = index + step
        if not 0 <= target < len(self.blocks):
            return index
        blocks = list(self.blocks)
        blocks[index], blocks[target] = blocks[target], blocks[index]
        self.project = replace(self.project, program=replace(self.program, blocks=tuple(blocks)))
        self.selected = target
        self._changed()
        return target

    def replace_block(self, index: int, block: Block) -> None:
        """Put a changed block in its place. Raises ModelError if the block is not valid."""
        self._check_index(index)
        if block.tool_number != self.blocks[index].tool_number:  # another tool: the fields the user never touched follow it
            block = self._with_tool_defaults(block, self._untouched(block, block.tool_default_fields))
        old = self.blocks[index]
        if getattr(block, "function", None) != getattr(old, "function", None) and hasattr(block, "values"):  # another function: its default values
            block = replace(block, values=self.function_defaults(block.function))
        block = self._with_followers(block, self.blocks[index])  # the plunge feed follows the feed until it is typed
        block = block.with_derived_fields(self.blocks[index])  # for example the numbers of a thread designation
        blocks = self.blocks[:index] + (block,) + self.blocks[index + 1 :]
        self.project = replace(self.project, program=replace(self.program, blocks=blocks))
        self._changed()

    def shown_block(self, index: int) -> Block:
        """The block as its form shows it: its greyed fields with the values the last plan worked out for them (`BlockResult.shown_values`,
        the Start Z of auto). An edit of another field keeps them, so unticking auto starts from the last value auto used."""
        block = self.blocks[index]
        plan = self.analysis.plan
        found = None if plan is None else next((b for b in plan.blocks if b.program_index == index), None)
        if found is None or not found.result.shown_values:
            return block
        disabled = getattr(block, "form_disabled", None)  # an optional hook of the forms
        greyed = disabled() if callable(disabled) else frozenset()
        values = {name: value for name, value in found.result.shown_values if name in greyed}
        return replace(block, **values) if values else block

    def _with_followers(self, block: Block, previous: Block | None = None) -> Block:
        """The block with the fields that follow other fields (`Block.follower_values`) set, but only those the user never
        touched and did not just edit (a field that differs from `previous` is the one being edited)."""
        values = block.follower_values()
        edited = set() if previous is None else {name for name in values if getattr(block, name) != getattr(previous, name, None)}
        names = self._untouched(block, tuple(name for name in values if name not in edited))
        return replace(block, **{name: values[name] for name in names}) if names else block

    def _untouched(self, block: Block, names: tuple[str, ...]) -> tuple[str, ...]:
        owner = block_owner(block.block_id)
        return tuple(name for name in names if not self.is_touched(owner, (name,)))

    def _with_tool_defaults(self, block: Block, names: tuple[str, ...]) -> Block:
        """The block with the given tool-dependent fields set to their preset for the block's tool."""
        if not names or not block.needs_tool or block.tool_number == NO_TOOL_NUMBER:
            return block
        try:
            fresh = block.with_tool_defaults(self.program.equipped_tool(block.tool_number))
        except (KeyError, ValueError):  # no such tool: the block keeps what it has (the plan says so)
            return block
        return replace(block, **{name: getattr(fresh, name) for name in names})

    def _refresh_tool_defaults(self, tool_number: int) -> None:
        """After a tool changed: the untouched tool-dependent fields of the blocks that use it follow."""
        blocks = tuple(
            self._with_tool_defaults(b, self._untouched(b, b.tool_default_fields)) if b.tool_number == tool_number else b
            for b in self.blocks
        )
        if blocks != self.blocks:
            self.project = replace(self.project, program=replace(self.program, blocks=blocks))

    def block_operations_text(self, index: int, single_moves: bool = False) -> str:
        """The neutral operations of one block as text (what a postprocessor receives), or why there are none.
        With `single_moves` the drilling and threading operations are written out as the moves they stand for."""
        self._check_index(index)
        plan = self.analysis.plan
        for block_plan in () if plan is None else plan.blocks:
            if block_plan.program_index == index:
                return describe_operations(block_plan.operations, single_moves)
        return "This block is not part of the plan (no contour, an error, or not ticked)."

    def block_owner(self, index: int) -> str:
        self._check_index(index)
        return block_owner(self.blocks[index].block_id)

    def is_touched(self, owner: str, path: tuple[str, ...]) -> bool:
        return is_touched(self.project.touched, owner, path)

    def set_touched(self, owner: str, path: tuple[str, ...], touched: bool = True) -> None:
        """Remember that the user edited a field (or, with False, that it is a preset again).

        Not a change of the program: nothing is replanned and the pictures stay.
        """
        mark = mark_touched if touched else mark_untouched
        new = mark(self.project.touched, owner, path)
        if new != self.project.touched:
            self.project = replace(self.project, touched=new)
            self._history[self._history_pos] = self.project  # the mark belongs to the edit just recorded
            self.dirty = True

    def default_object(self, owner: str, field: str | None = None) -> object | None:
        """A fresh object of the kind `owner` names, whose values are the defaults of its fields (`field`: the one about to be reset)."""
        fresh = new_project()
        if owner == SETUP_OWNER:  # the safe positions are those that follow the present part
            current = self.setup_form()
            radius, z = safe_positions(current.outer_diameter_mm, current.front_z_mm)
            machine = self.project.machine
            change_radius = radius if machine is None or machine.change_radius_mm is None else machine.change_radius_mm
            change_z = z if machine is None or machine.change_z_mm is None else machine.change_z_mm
            return replace(
                setup_from_program(fresh.program), safe_radius_mm=radius, change_radius_mm=change_radius,
                safe_z_mm=z, change_z_mm=change_z, title=fresh.settings.title, x_mode=fresh.settings.x_mode,
                machine=current.machine,
            )
        for index, block in enumerate(self.blocks):
            if block_owner(block.block_id) == owner:
                example = type(block).example(block.block_id, block.tool_number, block.spindle)
                if field is not None:
                    example = block.example_with_default(field, example)
                return self._with_followers(self._with_tool_defaults(example, example.tool_default_fields))
        return None

    def _check_index(self, index: int) -> None:
        if not 0 <= index < len(self.blocks):
            raise ModelError(f"there is no block {index + 1}")
