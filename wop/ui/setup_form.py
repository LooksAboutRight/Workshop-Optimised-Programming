"""The Setup entry of the flow list: raw part, material and safe positions in one form (U3, R7).

`SetupForm` is flat (the form fields are made from the dataclass, see block_forms.py). The part
is bar stock of unlimited length (the default) or has a length; the stick-out and the front Z belong to
the Workholding section. The two functions turn the form into the raw part and the safe positions and back.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from ..core.blocks.base import Safety
from ..core.constants import DEFAULT_FRONT_Z_MM, DEFAULT_WORK_OFFSET
from ..core.contour import Contour
from ..core.program_model.raw_outline import raw_part_from_outline
from ..core.program_model.units import XInputMode
from ..core.program_model.program import Program
from ..core.program_model.raw_part import RawPart
from ..core.lathe.workholding import GripMode, Workholding
from .app_constants import (
    DEFAULT_NEW_PART_MATERIAL,
    SAFE_RADIUS_BEYOND_PART_MM,
    SAFE_Z_IN_FRONT_MM,
    DEFAULT_CLEARANCE_MM,
    DEFAULT_NEW_PART_DIAMETER_MM,
    DEFAULT_NEW_PART_LENGTH_MM,
    DEFAULT_STOCK_INSIDE_MM,
)

SETUP_TITLE = "Setup"
PROJECT_HEADING = "Project settings"
NO_MACHINE_TEXT = "(none)"
PROJECT_COPY_SUFFIX = " (copy in project)"
NOT_IN_POST_SUFFIX = " (not in the post)"  # a work offset of the project that the post of the machine has not got
MACHINE_SETTINGS_BUTTON = "Machine settings..."
DRAW_RAW_PART_BUTTON = "Draw the raw part..."
PLAIN_BAR_BUTTON = "Back to a plain bar or tube"
PART_HEADING = "Part"
SAFE_DISTANCES_HEADING = "Safe distances"
WORKHOLDING_HEADING = "Workholding"


def safe_positions(outer_diameter_mm: float, front_z_mm: float) -> tuple[float, float]:
    """The safe radius and the safe Z that follow a part: its outer radius plus a margin, the front face plus a margin."""
    return outer_diameter_mm / 2 + SAFE_RADIUS_BEYOND_PART_MM, front_z_mm + SAFE_Z_IN_FRONT_MM


NEW_SAFE_RADIUS_MM, NEW_SAFE_Z_MM = safe_positions(DEFAULT_NEW_PART_DIAMETER_MM, DEFAULT_FRONT_Z_MM)  # a new project

@dataclass(frozen=True)
class SetupForm:
    """The fields in the order the form shows them; `form_headings` puts the section headings in."""

    title: str = "WOP program"  # the project settings come first
    machine: str = ""  # name of the machine of the project; empty: none
    machine_settings: str = ""  # not a value: the form shows a button that opens the machine settings
    x_mode: XInputMode = XInputMode.DIAMETER  # G-code mode of the program
    work_offset: str = DEFAULT_WORK_OFFSET  # the work offset (G54 ...) the header of the program calls
    material: str = DEFAULT_NEW_PART_MATERIAL
    draw_raw_part: str = ""  # not a value: a button that opens the sketch editor for the shape of the raw part
    plain_bar: str = ""  # not a value: a button that goes back to a plain bar or tube (shown while the raw part is drawn)
    outer_diameter_mm: float = DEFAULT_NEW_PART_DIAMETER_MM
    inner_diameter_mm: float = 0  # 0: solid bar
    stock_runs_through: bool = True  # bar stock: the length is unlimited
    length_mm: float = DEFAULT_NEW_PART_LENGTH_MM + DEFAULT_STOCK_INSIDE_MM  # always shown, greyed out for bar stock
    change_radius_mm: float = NEW_SAFE_RADIUS_MM  # tool change position X
    change_z_mm: float = NEW_SAFE_Z_MM  # tool change position Z
    safe_radius_mm: float = NEW_SAFE_RADIUS_MM  # safe position X: blocks travel at this radius
    safe_z_mm: float = NEW_SAFE_Z_MM  # safe position Z
    clearance_mm: float = DEFAULT_CLEARANCE_MM  # the distance kept inside a block, the same for X and Z
    length_outside_mm: float = DEFAULT_NEW_PART_LENGTH_MM  # the stick-out (free length)
    front_z_mm: float = DEFAULT_FRONT_Z_MM
    workholding: str = ""  # name of the jaws or chuck body; empty: none (the flat clamping plane is checked)
    jaw_anchor: str = ""  # the point of the jaws that sits on the part; empty: the jaws stay as drawn
    grip_inside: bool = False  # the jaws expand in the bore of a tube
    raw_outline: Contour | None = field(default=None, repr=False)  # not shown: the drawn raw part; the greyed numbers are worked out from it
    jaw_names: tuple[str, ...] = field(default=(), compare=False)  # not shown: which names in the list are jaws
    machine_choices: tuple[tuple[str, str], ...] = field(default=(), compare=False)  # not shown: (name, text) of the machines
    work_offset_choices: tuple[str, ...] = field(default=(), compare=False)  # not shown: the work offsets of the post of the machine (empty: the post writes none)


def _setup_form_fields(self: SetupForm) -> tuple[str, ...]:
    """The fields shown: the point and the grip only matter with jaws (the workholding says which it is)."""
    jaws = bool(self.workholding) and self.workholding in self.jaw_names
    hidden = {"raw_outline"} | (set() if self.raw_outline is not None else {"plain_bar"}) | (set() if jaws else {"jaw_anchor", "grip_inside"})
    return tuple(f.name for f in fields(self) if f.name not in hidden)


def _setup_form_choices(self: SetupForm) -> dict[str, list[tuple[str, str]]]:
    offsets = [(code, code) for code in self.work_offset_choices]
    if self.work_offset not in self.work_offset_choices:  # the project keeps its offset when the post has not got it
        offsets.append((self.work_offset, self.work_offset + (NOT_IN_POST_SUFFIX if offsets else "")))
    return {"machine": [("", NO_MACHINE_TEXT), *self.machine_choices], "work_offset": offsets}


def _setup_form_buttons(self: SetupForm) -> dict[str, str]:
    return {"machine_settings": MACHINE_SETTINGS_BUTTON, "draw_raw_part": DRAW_RAW_PART_BUTTON, "plain_bar": PLAIN_BAR_BUTTON}


def _setup_form_headings(self: SetupForm) -> dict[str, str]:
    return {"title": PROJECT_HEADING, "material": PART_HEADING, "change_radius_mm": SAFE_DISTANCES_HEADING, "length_outside_mm": WORKHOLDING_HEADING}


def _setup_form_disabled(self: SetupForm) -> frozenset[str]:
    """The length is always there, but cannot be edited for bar stock; a drawn raw part brings its own numbers; a post with no work
    offsets writes none, so the field is of no use."""
    no_offsets = frozenset() if self.work_offset_choices else frozenset({"work_offset"})
    if self.raw_outline is not None:
        return no_offsets | {"outer_diameter_mm", "inner_diameter_mm", "stock_runs_through", "length_mm", "length_outside_mm", "front_z_mm"}
    return no_offsets | ({"length_mm"} if self.stock_runs_through else frozenset())


SetupForm.form_fields = _setup_form_fields  # type: ignore[attr-defined]
SetupForm.field_choices = _setup_form_choices  # type: ignore[attr-defined]
SetupForm.form_buttons = _setup_form_buttons  # type: ignore[attr-defined]
SetupForm.form_headings = _setup_form_headings  # type: ignore[attr-defined]
SetupForm.form_disabled = _setup_form_disabled  # type: ignore[attr-defined]


def _chosen_name(holding: Workholding | None) -> str:
    """The one name the dropdown shows: the jaws (they bring their chuck body), else the chuck body alone."""
    if holding is None:
        return ""
    if holding.jaws is not None:
        return holding.jaws.name
    return "" if holding.chuck is None else holding.chuck.name


def setup_from_program(program: Program) -> SetupForm:
    raw, safety = program.raw_part, program.safety
    through = raw.length_mm is None
    holding = program.workholding
    return SetupForm(
        material=raw.material,
        outer_diameter_mm=raw.outer_diameter_mm,
        inner_diameter_mm=raw.inner_diameter_mm,
        length_outside_mm=raw.length_outside_mm,
        stock_runs_through=through,
        length_mm=SetupForm.length_mm if through else raw.length_mm,
        front_z_mm=raw.front_z_mm,
        change_radius_mm=safety.change_point_x,
        change_z_mm=safety.change_point_z,
        safe_radius_mm=safety.safe_radius_mm,
        safe_z_mm=safety.safe_z_mm,
        clearance_mm=safety.clearance_mm,
        workholding=_chosen_name(holding),
        jaw_anchor="" if holding is None else holding.anchor,
        grip_inside=holding is not None and holding.grip is GripMode.INSIDE,
        raw_outline=raw.outline,
    )


def setup_to_parts(form: SetupForm) -> tuple[RawPart, Safety]:
    """The raw part and the safe positions of the form. Raises RawPartError for a part that cannot exist."""
    if form.raw_outline is not None:  # the numbers of a drawn raw part come from the drawing
        raw = raw_part_from_outline(form.material, form.raw_outline)
        return raw, Safety(form.safe_radius_mm, form.safe_z_mm, form.clearance_mm, form.change_radius_mm, form.change_z_mm)
    raw = RawPart(
        form.material,
        form.outer_diameter_mm,
        form.length_outside_mm,
        inner_diameter_mm=form.inner_diameter_mm,
        length_mm=None if form.stock_runs_through else form.length_mm,
        front_z_mm=form.front_z_mm,
    )
    return raw, Safety(form.safe_radius_mm, form.safe_z_mm, form.clearance_mm, form.change_radius_mm, form.change_z_mm)


def stock_summary(form: SetupForm) -> str:
    """The line shown under the form: the length of the part, and how much of it is behind the clamping plane."""
    if form.stock_runs_through:
        return "Bar stock: the length is not limited."
    inside = form.length_mm - form.length_outside_mm
    if inside <= 0:
        return f"Length {form.length_mm:g} mm: the stick-out ({form.length_outside_mm:g} mm) is more than the part."
    return f"Length {form.length_mm:g} mm: {form.length_outside_mm:g} mm stick out, {inside:g} mm in the chuck."
