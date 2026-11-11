"""Describe the input form of a block (or of any dataclass) without any GUI toolkit.

The description comes from the dataclass fields and their type hints, so a new
block type gets its form without extra work (requirement B10). The window code
only turns a list of FieldSpec into widgets.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import math

from ..core.constants import NO_TOOL_NUMBER
from ..core.contour import NO_CONTOUR
from ..core.program_model.units import XInputMode

HIDDEN_FIELDS = ("block_id", "comment", "angle_deg", "cutting")  # angle_deg: the line step form of W8 handles it; cutting: a checkbox of the tool shape editor
UNIT_SUFFIXES = (
    ("_mm_per_rev", "mm/rev"),
    ("_mm_min", "mm/min"),
    ("_mm", "mm"),
    ("_deg", "deg"),
    ("_n_mm2", "N/mm2"),
    ("_s", "s"),
    ("_rpm", "RPM"),
    ("_kw", "kW"),
)
RADIUS_SUFFIX = "radius_mm"
TRUE_RADIUS_FIELDS = ("radius_mm", "nose_radius_mm")  # a size, not a position: never shown as a diameter
TAPER_FIELDS = ("taper_deg",)  # an included angle, shown in degrees or as the rise of the diameter per 100 mm (its own button)
TAPER_RISE_LENGTH_MM = 100
TAPER_RISE_CHOICE = "rise per 100 mm"  # the preference TAPER_INPUT that shows the rise first
TAPER_ANGLE_LABEL = "Taper, included angle"
TAPER_RISE_LABEL = "Taper, rise of the diameter per 100 mm"
POINT_X = "x"
POINT_Z = "z"
TOOL_FIELD = "tool_number"
CONTOUR_FIELD = "contour_id"
NO_CONTOUR_LABEL = "(none)"
NO_TOOL_LABEL = "No tool chosen"
MATERIAL_FIELD = "material"
POSTPROCESSOR_FIELD = "postprocessor"
WORKHOLDING_FIELD = "workholding"
JAW_ANCHOR_FIELD = "jaw_anchor"
NO_WORKHOLDING_LABEL = "(none)"
AS_DRAWN_LABEL = "(as drawn)"
# Labels that differ from the field name (the field names are in saved files and stay).
LABEL_OVERRIDES = {
    "holder_code": "Holder code (ISO 5608)",
    "bar_code": "Boring bar code (ISO 6261)",
    "insert_code": "Insert code (ISO 1832)",
    "insert_size": "Insert size",
    "insert_type": "Insert type",
    "length_outside_mm": "Stick-out (free length)",
    "length_mm": "Length",
    "overtravel_mm": "Overtravel past the centre (or bore)",
    "finish_pass": "Finishing pass",
    "cutter_compensation": "Cutter compensation",
    "finish_feed_mm_per_rev": "Feed",
    "finish_spindle_value": "Spindle speed",
    "line_angle_deg": "Angle to -Z (to chuck)",
    "dwell_s": "Dwell time",
    "drill_mode": "Drill mode",
    "peck_mode": "Retract after a peck",
    "depth_z_mm": "Depth (absolute Z)",
    "depth_to_full_diameter": "Depth to full diameter",
    "peck_depth_mm": "Peck depth",
    "standalone": "Usable on its own (offered in the pickers)",
    "workholding": "Workholding",
    "chuck": "Chuck body",
    "clearance_mm": "Clearance (X and Z)",
    "stock_runs_through": "Bar stock (unlimited length)",
    "change_radius_mm": "Tool change position, X radius",
    "change_z_mm": "Tool change position, Z",
    "machine_change_radius_mm": "Tool change in machine coordinates, X radius",
    "machine_change_z_mm": "Tool change in machine coordinates, Z",
    "safe_radius_mm": "Safe position, X radius",
    "safe_z_mm": "Safe position, Z",
    "jaw_anchor": "Jaw point on the part",
    "grip_inside": "Grip inside (tube held from the bore)",
    "jaw_count": "Number of jaws",
    "jaw_width_deg": "Width of one jaw",
}
FIELD_NOTES = {
    "taper_deg": "0: straight. Positive: larger towards the chuck. The target diameter is the one at Z 0. The button shows the included angle (deg) or the rise of the diameter per 100 mm (/100).",
    "designation": (
        "Metric M8, M8x1, M17.3x0.73, trapezoidal Tr40x7, inch 1/4-20 UNC or #10-24. Fills pitch, crest radius, depth and "
        "compound angle for the side chosen above; the messages name the major, pitch and minor diameter. Changing one of "
        "those numbers by hand makes the thread a custom one and clears this field."
    ),
    "depth_to_full_diameter": (
        "Ticked: the depth is where the hole has its full diameter, the point of the drill goes deeper. "
        "Not ticked: the tip of the drill reaches the depth."
    ),
    "thread_depth_mm": "Empty: the ISO metric depth from the pitch (G76 K). The first cut depth is G76 J.",
    "degression": "1 = the same depth every pass, 2 = the same area every pass, above 2 = decreasing area and many passes (G76 R).",
    "compound_angle_deg": "How far successive passes are offset along the thread so one flank cuts more; typical 29, 29.5 or 30 (G76 Q).",
    "taper_distance_mm": "Length of the tapered entry or exit along the thread, at most half the thread length (G76 E); the same as the depth gives 45 degrees.",
}
NEW_MATERIAL = "__new_material__"  # value of the "New..." entry of the material list
NEW_MATERIAL_LABEL = "New..."
MULTILINE_FIELDS = ("text",)
RADIUS_TO_DIAMETER = 2
VARIABLE_PREFIX = "variable:"  # the path of the field of a variable of a custom function
NOT_IN_POST = " (not in this post)"
FRACTION = 0.5  # sorts the variables between the function field and the field after it


class FormError(ValueError):
    """The typed text is not a valid value for the field."""


class FieldKind(Enum):
    FLOAT = auto()
    OPTIONAL_FLOAT = auto()  # empty text means "not set"
    INT = auto()
    TEXT = auto()
    MULTILINE = auto()
    BOOL = auto()
    CHOICE = auto()
    BUTTON = auto()  # no value: a push button that asks the window to do something (the label is its text)


@dataclass(frozen=True)
class Choice:
    value: Any
    label: str


@dataclass(frozen=True)
class FieldSpec:
    path: tuple[str, ...]  # field name, or names into nested dataclasses
    label: str
    kind: FieldKind
    unit: str = ""
    choices: tuple[Choice, ...] = ()
    is_radius: bool = False  # shown as a diameter when the program works in diameter mode
    is_taper: bool = False  # an included angle, shown in degrees or as a rise per 100 mm (`taper_to_display`)
    note: str = ""  # a text shown under the field
    heading: str = ""  # a section heading shown above the field (with a divider line when it is not the first)
    enabled: bool = True  # False: shown greyed out and not editable
    same_line: bool = False  # shown on the same line as the field before it
    relative_to: str = ""  # an end position that can also be shown as a length from the field with this name (Abs./Rel.)
    button_text: str = ""  # BUTTON: the text on the button
    relative_label: str = ""  # the label while it is shown as a length
    preview: str = ""  # CHOICE of styles: the block type whose style pictures are shown when an entry of the list is hovered
    minimum: float | None = None  # a number outside these limits is refused
    maximum: float | None = None

    def display_label(self, x_mode: XInputMode) -> str:
        if self.is_radius and x_mode is XInputMode.DIAMETER:
            return self.label.replace("radius", "diameter")
        return self.label


@dataclass(frozen=True)
class FunctionVariable:
    """One variable of a custom function of the post, as the form shows it."""

    name: str
    label: str
    type: str  # float, int, uint, bool or string
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""


@dataclass(frozen=True)
class FunctionChoice:
    """A function the Machine function block offers: its key (stored in the block), its label, the note and its variables."""

    key: str
    label: str
    description: str = ""
    variables: tuple[FunctionVariable, ...] = ()


@dataclass(frozen=True)
class FormContext:
    """What the choices of tool and contour fields are made from."""

    tools: tuple[tuple[int, str], ...] = ()  # (number, name)
    contours: tuple[tuple[str, str], ...] = ()  # (id, name)
    materials: tuple[str, ...] = ()  # names; with none, the material field is plain text
    postprocessors: tuple[tuple[str, str], ...] = ()  # (id, label); with none, the field is plain text
    functions: tuple[FunctionChoice, ...] | None = None  # the functions of the post; None: the function field is plain text
    workholding: tuple[tuple[str, str], ...] | None = None  # (name, label) of the items on offer; None: plain text
    jaw_points: tuple[str, ...] = ()  # the named points of the chosen jaws


# --- building the description ---------------------------------------------------


def _words(name: str) -> str:
    for suffix, _unit in UNIT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ").capitalize()


def _unit(name: str) -> str:
    for suffix, unit in UNIT_SUFFIXES:
        if name.endswith(suffix):
            return unit
    return ""


def _optional_inner(hint: Any) -> tuple[Any, bool]:
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        options = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(options) == 1 and len(options) != len(typing.get_args(hint)):
            return options[0], True
    return hint, False


def _named_choice(name: str, hint: Any, label: str, context: FormContext) -> tuple[str, tuple[Choice, ...]] | None:
    """A field that is chosen from a list the program holds (the tool, the contour, the material, ...): (its label, its choices)."""
    if name == TOOL_FIELD:
        return "Tool", (Choice(NO_TOOL_NUMBER, NO_TOOL_LABEL),) + tuple(Choice(n, f"T{n} {tool_name}") for n, tool_name in context.tools)
    if name == CONTOUR_FIELD:
        return "Contour", (Choice(NO_CONTOUR, NO_CONTOUR_LABEL),) + tuple(Choice(i, contour_name) for i, contour_name in context.contours)
    if hint is not str:
        return None
    if name == MATERIAL_FIELD and context.materials:
        return label, tuple(Choice(material, material) for material in context.materials) + (Choice(NEW_MATERIAL, NEW_MATERIAL_LABEL),)
    if name == POSTPROCESSOR_FIELD and context.postprocessors:
        return "Postprocessor", tuple(Choice(i, text) for i, text in context.postprocessors)
    if name == WORKHOLDING_FIELD and context.workholding is not None:
        return label, (Choice("", NO_WORKHOLDING_LABEL),) + tuple(Choice(chosen, text) for chosen, text in context.workholding)
    if name == JAW_ANCHOR_FIELD and context.workholding is not None:
        return label, (Choice("", AS_DRAWN_LABEL),) + tuple(Choice(point, point) for point in context.jaw_points)
    return None


def _float_spec(name: str, optional: bool, path: tuple[str, ...], label: str, label_prefix: str) -> FieldSpec:
    unit = _unit(name)
    is_radius = (name.endswith(RADIUS_SUFFIX) and name not in TRUE_RADIUS_FIELDS) or name == POINT_X
    if name == POINT_X:  # the x of a point is a radius
        label, unit = label_prefix + "X radius", "mm"
    elif name == POINT_Z:
        label, unit = label_prefix + "Z", "mm"
    kind = FieldKind.OPTIONAL_FLOAT if optional else FieldKind.FLOAT
    return FieldSpec(path, label, kind, unit, is_radius=is_radius, is_taper=name in TAPER_FIELDS, note=FIELD_NOTES.get(name, ""))


def _typed_spec(name: str, hint: Any, optional: bool, path: tuple[str, ...], label: str, label_prefix: str) -> FieldSpec | None:
    """The spec of a field by its type; None for a type with no simple form (tuples and so on)."""
    if isinstance(hint, type) and issubclass(hint, Enum):
        return FieldSpec(path, label, FieldKind.CHOICE, choices=tuple(Choice(member, str(member.value)) for member in hint))
    if hint is bool:
        return FieldSpec(path, label, FieldKind.BOOL, note=FIELD_NOTES.get(name, ""))
    if hint is int:
        return FieldSpec(path, label, FieldKind.INT, _unit(name))
    if hint is float:
        return _float_spec(name, optional, path, label, label_prefix)
    if hint is str:
        return FieldSpec(path, label, FieldKind.MULTILINE if name in MULTILINE_FIELDS else FieldKind.TEXT)
    return None


def _specs(cls: type, prefix: tuple[str, ...], label_prefix: str, context: FormContext) -> list:
    hints = typing.get_type_hints(cls)
    specs: list[FieldSpec] = []
    for field in dataclasses.fields(cls):
        if field.name in HIDDEN_FIELDS:
            continue
        path = prefix + (field.name,)
        label = label_prefix + LABEL_OVERRIDES.get(field.name, _words(field.name))
        hint, optional = _optional_inner(hints[field.name])
        named = _named_choice(field.name, hint, label, context)
        if named is not None:
            specs.append(FieldSpec(path, named[0], FieldKind.CHOICE, choices=named[1]))
        elif isinstance(hint, type) and dataclasses.is_dataclass(hint) and not issubclass(hint, Enum):
            specs += _specs(hint, path, label + ": ", context)
        else:
            spec = _typed_spec(field.name, hint, optional, path, label, label_prefix)
            if spec is not None:
                specs.append(spec)
    return specs


def _place(spec: FieldSpec, wanted: tuple[str, ...]) -> float:
    """The place of a field in the listed order; the variables of a function come right after the function field."""
    name = spec.path[0]
    if name.startswith(VARIABLE_PREFIX):
        return wanted.index("function") + FRACTION if "function" in wanted else len(wanted)
    return wanted.index(name)


def _variable_spec(variable: FunctionVariable) -> FieldSpec:
    path = (VARIABLE_PREFIX + variable.name,)
    if variable.type == "bool":
        return FieldSpec(path, variable.label, FieldKind.BOOL)
    if variable.type == "string":
        return FieldSpec(path, variable.label, FieldKind.TEXT)
    kind = FieldKind.FLOAT if variable.type == "float" else FieldKind.INT
    return FieldSpec(path, variable.label, kind, variable.unit, minimum=variable.minimum, maximum=variable.maximum)


def _with_function_fields(obj: Any, specs: list, context: FormContext) -> list:
    """The function field of an object (the Machine function block) as a dropdown of the functions of the post, and the fields of the
    variables of the chosen function after it."""
    named = getattr(obj, "form_function_field", None)
    if not callable(named) or context.functions is None:
        return specs
    name = named()
    current = getattr(obj, name)
    found = next((f for f in context.functions if f.key == current), None)
    choices = [Choice(f.key, f.label) for f in context.functions]
    if found is None:
        choices.append(Choice(current, current.replace("_", " ").capitalize() + NOT_IN_POST))
    result: list = []
    for spec in specs:
        if spec.path == (name,):
            note = "" if found is None else found.description
            result.append(dataclasses.replace(spec, kind=FieldKind.CHOICE, choices=tuple(choices), note=note))
            if found is not None:
                result += [_variable_spec(variable) for variable in found.variables]
        else:
            result.append(spec)
    return result


def form_for(obj: Any, context: FormContext = FormContext()) -> list[FieldSpec]:
    """The fields of a dataclass instance (a block, the raw part, the settings ...)."""
    specs = _specs(type(obj), (), "", context)
    options = getattr(obj, "field_choices", None)  # an object may offer dropdowns for some of its text fields
    if callable(options):
        lists = options()
        specs = [
            dataclasses.replace(spec, kind=FieldKind.CHOICE, choices=tuple(Choice(v, text) for v, text in lists[spec.path[0]]))
            if len(spec.path) == 1 and spec.path[0] in lists else spec
            for spec in specs
        ]
    specs = _with_function_fields(obj, specs, context)
    shown = getattr(obj, "form_fields", None)  # an object may show only the fields that matter for its current values
    if callable(shown):
        wanted = shown()
        specs = sorted((spec for spec in specs if spec.path[0] in wanted or spec.path[0].startswith(VARIABLE_PREFIX)), key=lambda spec: _place(spec, wanted))
    headings = getattr(obj, "form_headings", None)  # an object may divide its form into sections: field -> heading
    if callable(headings):
        titles = headings()
        specs = [dataclasses.replace(s, heading=titles.get(s.path[0], "")) if len(s.path) == 1 else s for s in specs]
    hidden = getattr(obj, "form_hidden", None)  # an object may hide fields of a nested dataclass: "spindle.mode"
    if callable(hidden):
        gone = hidden()
        specs = [s for s in specs if ".".join(s.path) not in gone]
    previews = getattr(obj, "form_preview", None)  # fields whose dropdown shows pictures of the entries: field -> block type
    if callable(previews):
        shown_for = previews()
        specs = [dataclasses.replace(s, preview=shown_for[s.path[0]]) if len(s.path) == 1 and s.path[0] in shown_for else s for s in specs]
    notes = getattr(obj, "form_notes", None)  # an object may put a note under a field: name -> text
    if callable(notes):
        texts = notes()
        specs = [dataclasses.replace(s, note=texts[s.path[0]]) if len(s.path) == 1 and s.path[0] in texts else s for s in specs]
    labels = getattr(obj, "form_labels", None)  # an object may word a label differently from other blocks: name -> text
    if callable(labels):
        texts = labels()
        specs = [dataclasses.replace(s, label=texts[".".join(s.path)]) if ".".join(s.path) in texts else s for s in specs]
    ends = getattr(obj, "form_relative_ends", None)  # end positions that can be shown as a length: field -> (start, label)
    if callable(ends):
        given = ends()
        specs = [
            dataclasses.replace(s, relative_to=given[s.path[0]][0], relative_label=given[s.path[0]][1])
            if len(s.path) == 1 and s.path[0] in given else s
            for s in specs
        ]
    same_line = getattr(obj, "form_same_line", None)  # fields shown on the line of the one before
    if callable(same_line):
        joined = same_line()
        specs = [dataclasses.replace(s, same_line=True) if len(s.path) == 1 and s.path[0] in joined else s for s in specs]
    buttons = getattr(obj, "form_buttons", None)  # fields that are push buttons: field -> text on the button
    if callable(buttons):
        texts = buttons()
        specs = [
            dataclasses.replace(s, kind=FieldKind.BUTTON, label="", button_text=texts[s.path[0]])
            if len(s.path) == 1 and s.path[0] in texts else s
            for s in specs
        ]
    disabled = getattr(obj, "form_disabled", None)  # an object may grey out fields that do not matter right now
    if callable(disabled):
        off = disabled()
        specs = [dataclasses.replace(s, enabled=False) if s.path[0] in off else s for s in specs]
    return specs


def form_state(obj: Any) -> tuple:
    """Which fields an object shows and which are greyed out; the form is rebuilt when this changes."""
    shown, disabled = getattr(obj, "form_fields", None), getattr(obj, "form_disabled", None)
    key = getattr(obj, "form_key", None)  # the fields depend on more than the list of names (the variables of a function)
    return (shown() if callable(shown) else None, disabled() if callable(disabled) else None, key() if callable(key) else None)


# --- reading and changing values -------------------------------------------------


def get_value(obj: Any, path: tuple[str, ...]) -> Any:
    if path[0].startswith(VARIABLE_PREFIX):
        return obj.variable_value(path[0][len(VARIABLE_PREFIX):])
    for name in path:
        obj = getattr(obj, name)
    return obj


def set_value(obj: Any, path: tuple[str, ...], value: Any) -> Any:
    """A copy of obj with the value at path replaced (the dataclasses are frozen)."""
    head, rest = path[0], path[1:]
    if head.startswith(VARIABLE_PREFIX):
        return obj.with_variable(head[len(VARIABLE_PREFIX):], value)
    new = value if not rest else set_value(getattr(obj, head), rest, value)
    return dataclasses.replace(obj, **{head: new})


def to_display(spec: FieldSpec, value: Any, x_mode: XInputMode) -> Any:
    if spec.kind is FieldKind.INT and isinstance(value, float):
        return int(value)  # a whole number kept as a float in the block
    if value is None and spec.kind in (FieldKind.FLOAT, FieldKind.INT):
        return 0
    if value is None and spec.kind is FieldKind.TEXT:
        return ""
    if value is None and spec.kind is FieldKind.BOOL:
        return False
    if spec.is_radius and value is not None and x_mode is XInputMode.DIAMETER:
        return value * RADIUS_TO_DIAMETER
    return value


def taper_to_display(angle_deg: float, as_rise: bool) -> float:
    """An included angle as shown: in degrees, or the rise of the diameter over 100 mm of length."""
    return TAPER_RISE_LENGTH_MM * 2 * math.tan(math.radians(angle_deg) / 2) if as_rise else angle_deg


def taper_from_display(value: float, as_rise: bool) -> float:
    """The included angle in degrees from what was typed (`taper_to_display` the other way)."""
    return math.degrees(2 * math.atan(value / (2 * TAPER_RISE_LENGTH_MM))) if as_rise else value


def taper_label(as_rise: bool) -> tuple[str, str]:
    """The label and the unit of a taper as shown."""
    return (TAPER_RISE_LABEL, "mm") if as_rise else (TAPER_ANGLE_LABEL, "deg")


def from_display(spec: FieldSpec, value: Any, x_mode: XInputMode) -> Any:
    if spec.is_radius and value is not None and x_mode is XInputMode.DIAMETER:
        return value / RADIUS_TO_DIAMETER
    return value


def end_to_length(start: float, end: float) -> float:
    """The length from a start to an end that lies behind it (Z falls towards the chuck)."""
    return start - end


def length_to_end(start: float, length: float) -> float:
    return start - length


def parse_text(spec: FieldSpec, text: str) -> Any:
    """Turn typed text into a value. Raises FormError with a message for the user."""
    text = text.strip()
    if spec.kind is FieldKind.OPTIONAL_FLOAT and not text:
        return None
    if spec.kind in (FieldKind.FLOAT, FieldKind.OPTIONAL_FLOAT):
        try:
            number = float(text.replace(",", "."))
        except ValueError:
            raise FormError(f"{spec.label}: '{text}' is not a number") from None
        return check_limits(spec, number)
    if spec.kind is FieldKind.INT:
        try:
            whole = int(text)
        except ValueError:
            raise FormError(f"{spec.label}: '{text}' is not a whole number") from None
        return check_limits(spec, whole)
    return text


def check_limits(spec: FieldSpec, value: float) -> float:
    """The number, or a FormError when it is outside the limits of the field."""
    if (spec.minimum is not None and value < spec.minimum) or (spec.maximum is not None and value > spec.maximum):
        low = "no limit" if spec.minimum is None else f"{spec.minimum:g}"
        high = "no limit" if spec.maximum is None else f"{spec.maximum:g}"
        raise FormError(f"{spec.label}: {value:g} is outside the limits ({low} to {high})")
    return value
