"""Common parts of all blocks (requirements B1, B5, B6, B10).

A block type is one class in one file. It needs a unique `type_name` and a
`generate(context)` method, and is registered with the decorator
`@BLOCK_TYPES.register`. Nothing else has to change to add a block type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import BLOCK_MENU_ORDER
from ..contour import NO_CONTOUR, Contour  # noqa: F401  (NO_CONTOUR is used through this module)
from ..geometry import Segment
from ..program_model.operations import CoolantMode, Operation, SpindleSetting
from ..geometry.region import Region
from ..program_model.raw_part import RawPart
from ..tooling.tool import Tool


class BlockError(ValueError):
    """A block has unusable parameters."""


@dataclass(frozen=True)
class Safety:
    """Safe positions and the gap kept when approaching material."""

    safe_radius_mm: float  # the safe position: blocks travel at this radius, and the tool waits at it between blocks
    safe_z_mm: float  # ... and at this axial position
    clearance_mm: float  # the distance kept to the material inside a block (the same for X and Z)
    change_radius_mm: float | None = None  # the tool change position; None: the same as the safe position
    change_z_mm: float | None = None

    @property
    def change_point_x(self) -> float:
        return self.safe_radius_mm if self.change_radius_mm is None else self.change_radius_mm

    @property
    def change_point_z(self) -> float:
        return self.safe_z_mm if self.change_z_mm is None else self.change_z_mm


@dataclass(frozen=True)
class BlockContext:
    """What a block needs to know to generate its operations."""

    raw_part: RawPart
    tool: Tool
    residual: Region  # material still there before this block
    safety: Safety
    contours: tuple[Contour, ...] = ()  # the program's contours, for blocks that refer to one
    jaws: Region | None = None  # what the tool must not touch behind the work (workholding); None: flat clamping plane
    front_z: float | None = None  # where the material this block works on begins (the Start Z of the simple turning block); None: the front of the residual

    def contour(self, contour_id: str) -> Contour:
        for contour in self.contours:
            if contour.contour_id == contour_id:
                return contour
        raise BlockError(f"contour {contour_id!r} does not exist")


@dataclass(frozen=True)
class BlockResult:
    operations: tuple[Operation, ...]
    removed: Region  # material this block removes
    messages: tuple[str, ...] = ()  # things the user should know (for example unreachable areas)
    protected: Region | None = None  # what the tool must never touch; None: everything this block leaves standing
    shown_values: tuple[tuple[str, object], ...] = ()  # values the block worked out for fields its form shows greyed (the Start Z of auto)


@dataclass(frozen=True, kw_only=True)
class Block:
    """Fields every block has. Block types add their own after these."""

    type_name = ""  # set by each block type
    # What the machine must be able to do for this block type (checked against the machine definition, M10).
    required_capabilities = frozenset()  # of Capability (not a field: no annotation)
    label = ""  # the name shown to the user; empty: the type name
    # False for blocks that need no tool, spindle or coolant of their own (a machine function): the
    # program then adds no tool change or spindle start before them and keeps its idea of the state.
    needs_tool = True
    stops_spindle = False  # the spindle is off after this block

    def works_on_far_side(self, tool: Tool) -> bool:
        """True when `tool` (its tip at the origin) works on the far side of the axis in this block: the program plans the block with the tool
        turned over the axis and turns the moves back (`analytic/far_side.py`). Only blocks that can be planned that way say yes."""
        return False

    # Fields whose preset depends on the tool (names of fields); `with_tool_defaults` gives them their value for a tool.
    # The program applies them when a block is added or its tool changes, but only to fields the user never touched.
    tool_default_fields = ()  # of str (not a field: no annotation)

    block_id: str
    tool_number: int
    spindle: SpindleSetting
    coolant: CoolantMode = CoolantMode.NONE
    name: str = ""
    comment: str = field(default="", compare=False)

    @classmethod
    def example(cls, block_id: str, tool_number: int, spindle: SpindleSetting) -> "Block":
        """A block with sensible values, used when the user adds a new block."""
        raise NotImplementedError

    def with_tool_defaults(self, tool: Tool) -> "Block":
        """The block with the tool-dependent fields (`tool_default_fields`) at their preset for this tool."""
        return self

    def follower_values(self) -> dict[str, object]:
        """Fields that follow other fields of the block until the user types a value of his own (name -> value now).

        The program puts these values into the fields the user never touched, when the block is added and after every
        edit of another field. The default follows nothing."""
        return {}

    def with_derived_fields(self, previous: "Block | None") -> "Block":
        """The block after an edit: fields that follow from other fields (a thread designation, say) are brought in step.

        `previous` is the block as it was before the edit (None for a new block). The default does nothing.
        """
        return self

    def example_with_default(self, name: str, example: "Block") -> "Block":
        """The fresh example whose field `name` is the one to reset to default; a block whose default of one field
        depends on another field of the block (as it is now) brings that in. The default does nothing."""
        return example

    @property
    def title(self) -> str:
        """The name shown for the block; a block type may fall back on something else when the name is empty."""
        return self.name

    def own_problem(self) -> str:
        """Why the block cannot be planned although its contours are fine (for example a path that does not work out); empty if all is well."""
        return ""

    @classmethod
    def display_label(cls) -> str:
        return cls.label or cls.type_name.replace("_", " ")

    @property
    def contour_ids(self) -> tuple[str, ...]:
        """Contours this block refers to (a program refuses to delete them)."""
        return ()

    def generate(self, context: BlockContext) -> BlockResult:
        raise NotImplementedError

    def wanted_plan(self, context: BlockContext):
        """Experimental (analytic planner): the region to remove and the lines to cut, as `analytic.wanted_lines.WantedPlan`;
        None for a block that has none. Made from the form values and the material only: no tool is looked at."""
        return None

    def target_outline(self, context: BlockContext) -> tuple[Segment, ...]:
        """The finished shape this block aims at, as lines and arcs in the picture (empty: nothing to show).

        Made from the form values only: the picture draws it for the block chosen in the flow list.
        """
        return ()


class BlockRegistry:
    """Known block types by name."""

    def __init__(self) -> None:
        self._types: dict[str, type[Block]] = {}

    def register(self, block_class: type[Block]) -> type[Block]:
        name = block_class.type_name
        if not name:
            raise BlockError(f"{block_class.__name__} has no type_name")
        if name in self._types:
            raise BlockError(f"block type {name!r} is already registered")
        self._types[name] = block_class
        return block_class

    def get(self, name: str) -> type[Block]:
        if name not in self._types:
            raise BlockError(f"unknown block type {name!r}")
        return self._types[name]

    def names(self) -> list[str]:
        """The type names in menu order (BLOCK_MENU_ORDER first, any other type after them by name)."""
        rank = {name: index for index, name in enumerate(BLOCK_MENU_ORDER)}
        return sorted(self._types, key=lambda name: (rank.get(name, len(rank)), name))


BLOCK_TYPES = BlockRegistry()
