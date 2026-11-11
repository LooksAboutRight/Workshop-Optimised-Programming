"""Types, small functions and constants shared by the parts of the application model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from ...core.blocks.base import Safety
from ...core.constants import RIGHT_ANGLE_DEG, STARTER_TOOL_HEIGHT_MM, STARTER_TOOL_WIDTH_MM
from ...core.contour import Contour, ContourDefinition, LineStep
from ...core.contour_solver import build_contour
from ...core.geometry import Point
from ...core.material import MaterialLibrary
from ...core.lathe.power import PowerEstimate
from ...core.program_model.program import Program, ProgramPlan
from ...core.program_model.project import Project, ProjectSettings
from ...core.program_model.raw_part import RawPart
from ...core.tooling.tool import ToolMaterial
from ...core.tool_types import make_tool
from ...core.tool_types.boring import BoringDefinition
from ...core.tool_types.turning import TurningDefinition
from ...core.verify import Finding
from ..app_constants import DEFAULT_CLEARANCE_MM, DEFAULT_CONTOUR_LENGTH_MM, DEFAULT_NEW_PART_DIAMETER_MM, DEFAULT_NEW_PART_LENGTH_MM, DEFAULT_NEW_PART_MATERIAL
from ..setup_form import NEW_SAFE_RADIUS_MM, NEW_SAFE_Z_MM


Listener = Callable[[], None]


class ModelError(ValueError):
    """An action cannot be done; the message is for the user."""


@dataclass
class Analysis:
    """What the program turned out to be after the last change."""

    plan: ProgramPlan | None = None
    findings: list[Finding] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    error: str = ""  # set when the program could not be planned at all
    power: PowerEstimate | None = None  # only when a machine is set
    checked: bool = True  # False: collisions and power were not looked at (the user switched the automatic check off)
    working: str = ""  # in the window: WORKING_PLANNING (this is the result of an older program) or WORKING_CHECKING (the check follows)
    program: object = field(default=None, compare=False, repr=False)  # the program it belongs to (an export never uses an older one)
    preview: object = field(default=None, compare=False, repr=False)  # the finished part saved in the file (a Region): drawn until the plan is there (V9)


@dataclass(frozen=True)
class ExportReport:
    """What the window needs to know before the G-code leaves."""

    checked: bool  # the collision and power checks have been run for it
    problems: tuple[str, ...] = ()  # what they found (only when checked) and the blocks that are left out (always)


@dataclass(frozen=True)
class ShapeToolForm:
    """The form of a tool that has no type (a shape that was drawn or loaded): only name and material can change."""

    number: int
    name: str
    material: ToolMaterial


TOOL_NOT_IN_LIBRARY = "new"


TOOL_SAME_AS_LIBRARY = "same"


TOOL_DIFFERS_FROM_LIBRARY = "differs"


def tool_core(tool):
    """What decides whether two tools are the same tool: everything but the number, the offset number (they belong to the project
    or the toolbox) and where the tool came from."""
    definition = None if tool.definition is None else {k: v for k, v in tool.definition.items() if k != "number"}
    return replace(tool, number=0, offset_number=None, definition=definition, origin_library="", origin_name="")


EMPTY_CONTENT = {  # what an empty library of each kind is made of
    "materials": {"materials": MaterialLibrary()},
    "workholding": {"workholding": ()},
    "tools": {"tools": ()},
}


def default_contour(program: Program) -> Contour:
    """A first contour for a new contour block: a plain shaft along the raw part."""
    radius = program.raw_part.outer_radius_mm / 2
    steps = (LineStep(Point(radius, -DEFAULT_CONTOUR_LENGTH_MM)),)
    return build_contour("contour1", "Contour 1", ContourDefinition(Point(radius, 0), steps))


STUB_TURNING_TOOL = TurningDefinition(  # the plain stub tools of the first versions: rectangles with two cutting edges at the tip
    name="Outside tool", nose_radius_mm=0, side_edge_length_mm=STARTER_TOOL_WIDTH_MM, side_edge_angle_deg=RIGHT_ANGLE_DEG,
    front_edge_angle_deg=RIGHT_ANGLE_DEG, width_mm=STARTER_TOOL_HEIGHT_MM, length_mm=STARTER_TOOL_WIDTH_MM,
)
STUB_BORING_TOOL = BoringDefinition(
    name="Boring bar", nose_radius_mm=0, wall_edge_length_mm=STARTER_TOOL_HEIGHT_MM, wall_edge_angle_deg=RIGHT_ANGLE_DEG,
    end_edge_angle_deg=RIGHT_ANGLE_DEG, front_width_mm=STARTER_TOOL_WIDTH_MM, bar_width_mm=STARTER_TOOL_WIDTH_MM,
    length_mm=STARTER_TOOL_HEIGHT_MM,
)
NEW_PROJECT_USES_STUB_TOOLS = False  # the tests switch this on (tests/__init__.py): a new project then starts with the two stub tools (T18: a real one has none)


def starter_tools() -> tuple:
    """The tools a new project starts with: the standard turning tool and boring bar (the stubs for the tests)."""
    if NEW_PROJECT_USES_STUB_TOOLS:
        return make_tool("turning", 1, STUB_TURNING_TOOL), make_tool("boring", 2, STUB_BORING_TOOL)
    return make_tool("turning", 1, TurningDefinition()), make_tool("boring", 2, BoringDefinition())


def with_starter_tools(project: Project) -> Project:
    """The project with the two starter tools (for the tools that write the example projects)."""
    return replace(project, program=replace(project.program, tools=starter_tools()))


def new_project() -> Project:
    program = Program(
        raw_part=RawPart(DEFAULT_NEW_PART_MATERIAL, DEFAULT_NEW_PART_DIAMETER_MM, DEFAULT_NEW_PART_LENGTH_MM),
        tools=starter_tools() if NEW_PROJECT_USES_STUB_TOOLS else (),
        safety=Safety(NEW_SAFE_RADIUS_MM, NEW_SAFE_Z_MM, DEFAULT_CLEARANCE_MM),
    )
    return Project(program, ProjectSettings(), touched=())
