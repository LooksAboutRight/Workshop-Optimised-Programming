"""The tokens a template may use. One registry drives the engine, the checks, the docs and (later) the token grid of the window.

A token is a name, a one-line description, an example, the concepts it works in and the options it accepts. Its value comes
from a function that reads the operation being written (`render.scope`), what the engine remembers (`render.state`) or the
whole program (`render.context`). A value is a number (written with the options), a text, a list of lines or None (empty).
Empty is not an error: an optional part with only empty tokens disappears. A value that must exist but does not raises
PostError.

Rule for new tokens: a token is a value or an "if changed" rule, never a script.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ..core.geometry import ArcSegment, Point
from ..core.program_model.operations import DrillMode, ThreadTaper
from ..core.program_model.units import XInputMode
from .base import PostError
from .concepts import ARCS, DRILL_CYCLES, MOVES, SPINDLE, THREADS
from .token_codes import (  # noqa: F401 (the code tokens live in token_codes.py)
    _code, _comp_code, _prepare_code, _prepare_compensation, _prepare_spindle_code, _prepare_units, _spindle_code, _units_code,
)
from .numbers import NUMBER_OPTIONS, TEXT_OPTIONS, OptionError, Options, parse_options
from .post_constants import WOP_VERSION_TEXT
from .template import RawToken, TemplateError

DIAMETER_FACTOR = 2
POSITION_TOLERANCE_MM = 1e-9
EVERYWHERE = None  # the `concepts` of a token that works in every concept
ISO_DATE_FORMAT = "%Y-%m-%d"
TAPER_CODES = {ThreadTaper.NONE: 0, ThreadTaper.ENTRY: 1, ThreadTaper.EXIT: 2, ThreadTaper.BOTH: 3}

Evaluate = Callable[["object", tuple, Options], "float | int | str | list[str] | None"]


@dataclass(frozen=True)
class Token:
    name: str
    description: str
    example: str
    evaluate: Evaluate
    concepts: frozenset[str] | None = None  # None: in every concept
    options: frozenset[str] = frozenset()
    kind: str = "text"  # "number", "text" or "lines" (a line of its own: it expands to several lines)
    number_format: str = "coordinate"  # coordinate, feed, speed, one (one decimal) or count (whole numbers)
    radial: str = ""  # "mode": a radius written as a diameter when the program is in diameter mode; "radius": a radius that stays one
    changeable: bool = False  # accepts the option `changed`
    memory: bool = False  # the engine decides `changed` by comparing with what this token wrote last time
    args: int = 0  # words after the name that belong to the token, not to the options
    prepare: Callable[[tuple, dict], tuple] | None = None  # turns the words into what evaluate needs, with the codes of the post
    dimension: str | None = None  # what the number measures in an inch program: "length" (also a feed), "surface" (constant surface speed), "none"; None: a length for a coordinate or feed format, else none


DIMENSION_LENGTH = "length"
DIMENSION_SURFACE_SPEED = "surface"
DIMENSION_NONE = "none"


def dimension_of(token: Token) -> str:
    """What the number of a token measures (the engine converts it when the program is written in inches)."""
    if token.dimension is not None:
        return token.dimension
    return DIMENSION_LENGTH if token.kind == "number" and token.number_format in ("coordinate", "feed") else DIMENSION_NONE


TOKENS: dict[str, Token] = {}


def register(token: Token) -> Token:
    if token.name in TOKENS:
        raise ValueError(f"token {token.name!r} is registered twice")
    TOKENS[token.name] = token
    return token


# --- finding and checking a token in a template --------------------------------------------

@dataclass(frozen=True)
class BoundToken:
    token: Token
    args: tuple
    options: Options
    position: int


def find_token(words: tuple[str, ...]) -> tuple[Token, tuple[str, ...]] | None:
    """The token with the longest name that the words start with, and the words after the name."""
    for length in range(len(words), 0, -1):
        token = TOKENS.get(" ".join(words[:length]))
        if token is not None:
            return token, words[length:]
    return None


def bind(raw: RawToken, concept: str, codes: dict, variables: dict | None = None) -> BoundToken:
    if variables and raw.words and raw.words[0] in variables:  # a variable of this custom concept
        token = variables[raw.words[0]].token
        try:
            options = parse_options(raw.words[1:], frozenset(token.options))
        except OptionError as error:
            raise TemplateError(f"<{token.name}>: {error}", raw.position) from None
        return BoundToken(token, (), options, raw.position)
    found = find_token(raw.words)
    if found is None:
        raise TemplateError(f"unknown token <{' '.join(raw.words)}>", raw.position)
    token, rest = found
    if token.concepts is not None and concept not in token.concepts:
        where = ", ".join(sorted(token.concepts))
        raise TemplateError(f"<{token.name}> is not allowed in [{concept}]; it works in: {where}", raw.position)
    if len(rest) < token.args:
        raise TemplateError(f"<{token.name}> needs {token.args} word(s) after the name", raw.position)
    args, option_words = rest[:token.args], rest[token.args:]
    allowed = token.options | ({"changed"} if token.changeable else set())
    try:
        options = parse_options(option_words, frozenset(allowed))
    except OptionError as error:
        raise TemplateError(f"<{token.name}>: {error}", raw.position) from None
    if token.prepare is not None:
        try:
            args = token.prepare(args, codes)
        except PostError as error:
            raise TemplateError(f"<{token.name}>: {error}", raw.position) from None
    return BoundToken(token, args, options, raw.position)


# --- helpers for the value functions ------------------------------------------------------

def _scope(render, key: str):
    return render.scope.get(key)


def _need(render, key: str, token_name: str):
    value = render.scope.get(key)
    if value is None:
        raise PostError(f"<{token_name}> has no value here")
    return value


def x_factor(render, options: Options, radial: str) -> int:
    """2 when an X value is written as a diameter."""
    if options.has("diameter"):
        return DIAMETER_FACTOR
    if options.has("by_mode"):
        return DIAMETER_FACTOR if render.engine.settings.x_mode is XInputMode.DIAMETER else 1
    if options.has("radius") or not radial:
        return 1
    if radial == "radius":
        return 1
    return DIAMETER_FACTOR if render.engine.settings.x_mode is XInputMode.DIAMETER else 1


def wants_contour(render, options: Options) -> bool:
    """The point of the nominal contour instead of the tool path: asked for with `contour`, refused with `path`, else what the
    post does (cutter compensation) for a move that has a contour point."""
    if options.has("path"):
        return False
    return options.has("contour") or bool(render.scope.get("comp"))


def pick(render, options: Options, key: str, contour_key: str):
    """The value of `key` of the move, or of `contour_key` when the contour is wanted and the move has it."""
    if wants_contour(render, options):
        value = render.scope.get(contour_key)
        if value is not None:
            return value
    return render.scope.get(key)


def _axis(name: str, axis: str) -> Evaluate:
    """X or Z of the end point of a move; incremental from the last position; `changed` when it differs from the last position."""

    def evaluate(render, _args, options: Options):
        value = pick(render, options, axis, f"c{axis}")
        if value is None:
            return None
        last = getattr(render.state, f"c{axis}" if wants_contour(render, options) else axis)
        if options.has("changed"):
            forced = render.engine.preview  # the sample output of the editor: all changed or none
            if forced is False or (forced is None and last is not None and abs(value - last) <= POSITION_TOLERANCE_MM):
                return None
        if options.has("incremental"):
            if last is None:
                raise PostError(f"<{name} incremental> needs a known position before it")
            value -= last
        return value * (x_factor(render, options, "mode") if axis == "x" else 1)

    return evaluate


def _plain(key: str, contour_key: str | None = None) -> Evaluate:
    """A value from the scope as it is (empty when there is none); the contour version when the contour is wanted."""

    def evaluate(render, _args, options: Options):
        return _scope(render, key) if contour_key is None else pick(render, options, key, contour_key)

    return evaluate


def _radial(key: str, contour_key: str) -> Evaluate:
    def evaluate(render, _args, options: Options):
        value = pick(render, options, key, contour_key)
        if value is None:
            return None
        return value * x_factor(render, options, "mode")

    return evaluate


def _arc_center(axis: str) -> Evaluate:
    """I and K: the centre relative to the start (`absolute`: the centre itself). They stay radius values unless `diameter`."""

    def evaluate(render, _args, options: Options):
        use = wants_contour(render, options) and render.scope.get(f"cc{axis}") is not None and render.scope.get(f"cs{axis}") is not None
        center = render.scope[f"cc{axis}" if use else f"center_{axis}"]
        start = render.scope[f"cs{axis}" if use else f"start_{axis}"]
        value = center if options.has("absolute") else center - start
        return value * (DIAMETER_FACTOR if axis == "x" and options.has("diameter") else 1)

    return evaluate


def _arc_radius(render, _args, options: Options):
    """R: the radius of the arc, negative for an arc of more than half a circle."""
    scope = render.scope
    if wants_contour(render, options) and scope.get("cx") is not None and scope.get("ccx") is not None and scope.get("csx") is not None:
        arc = ArcSegment(
            Point(scope["csx"], scope["csz"]), Point(scope["cx"], scope["cz"]), Point(scope["ccx"], scope["ccz"]), scope["direction"],
        )
    else:
        arc = ArcSegment(scope["start"], scope["end"], scope["center"], scope["direction"])
    return arc.radius if arc.sweep <= math.pi else -arc.radius


def _feed(render, _args, options: Options):
    value = _need(render, "feed", "F")
    if options.has("per_minute"):
        rpm = render.state.rpm
        if rpm is None:
            raise PostError("a feed per minute needs the spindle speed: the spindle was not started before it")
        return value * rpm
    return value


def _prepare_x_mode(_args: tuple, codes: dict) -> tuple:
    return tuple(codes[name].text if name in codes else None for name in ("diameter_mode", "radius_mode"))


def _x_mode_code(render, args, _options: Options):
    return args[0] if render.engine.settings.x_mode is XInputMode.DIAMETER else args[1]


def _line_number(advance: bool) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        state, settings = render.state, render.engine.definition.settings
        if advance:
            state.line_number = settings.line_number_start if state.line_number is None else state.line_number + settings.line_number_step
        if state.line_number is None:
            return None
        return f"{settings.line_number_prefix}{state.line_number}"

    return evaluate


# --- the tools -----------------------------------------------------------------------------

def tool_info(render, selector: str):
    """The tool a selector means at this place of the program: the one being changed to (or the one of a list entry), the one
    before or after it, the first or the last."""
    entry = render.scope.get("tool")
    if selector == "tool" and entry is not None:
        return entry
    context, state = render.context, render.state
    sequence = context.tool_sequence
    index = state.tool_index
    if selector == "first tool":
        number = sequence[0] if sequence else None
    elif selector == "last tool":
        number = sequence[-1] if sequence else None
    elif selector == "tool":
        number = state.tool_number
    elif selector == "previous tool":
        number = sequence[index - 1] if index is not None and index > 0 else None
    else:  # next tool: before the first change it is the first tool; a tool that is not in the sequence has no neighbours
        following = (0 if state.tool_cursor == 0 else None) if index is None else index + 1
        number = sequence[following] if following is not None and following < len(sequence) else None
    if number is None:
        return None
    return context.tools.get(number) or _bare_tool(number)


def _bare_tool(number: int):
    from .context import ToolInfo

    return ToolInfo(number, offset_number=number)


TOOL_FIELDS = (
    ("number", "number", "5", "count", lambda tool: tool.number),
    ("name", "name", "Rough 80 degrees", "text", lambda tool: tool.name or None),
    ("offset", "offset number", "5", "count", lambda tool: tool.offset_number),
    ("type", "type", "holder", "text", lambda tool: tool.kind or None),
    ("material", "material", "carbide", "text", lambda tool: tool.material or None),
    ("nose radius", "nose radius in mm", "0.4", "coordinate", lambda tool: tool.nose_radius_mm),
    ("tip direction", "imaginary tip number 1 to 9", "3", "count", lambda tool: tool.tip_direction),
)
TOOL_SELECTORS = (
    ("tool", "the tool being changed to (in a tool list: the tool of the entry)"),
    ("previous tool", "the tool before it (empty at the first)"),
    ("next tool", "the tool after it (empty at the last)"),
    ("first tool", "the first tool of the program"),
    ("last tool", "the last tool of the program"),
)


def _tool_value(selector: str, getter) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        tool = tool_info(render, selector)
        return None if tool is None else getter(tool)

    return evaluate


for _selector, _meaning in TOOL_SELECTORS:
    for _field, _label, _example, _format, _getter in TOOL_FIELDS:
        register(Token(
            f"{_selector} {_field}" if _selector != "tool" else f"tool {_field}",
            f"{_label} of {_meaning}", _example, _tool_value(_selector, _getter),
            options=NUMBER_OPTIONS if _format != "text" else TEXT_OPTIONS,
            kind="text" if _format == "text" else "number", number_format="coordinate" if _format == "text" else _format,
        ))


# --- blocks, project, time ---------------------------------------------------------------

def _block(offset: int | None, field_name: str) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        blocks, current = render.context.blocks, render.state.block
        if field_name == "count":
            return len(blocks)
        if current is None:
            return None
        if offset is None:
            return {"name": current.name or None, "number": current.number, "type": current.type_name}[field_name]
        numbers = [block.number for block in blocks]
        if current.number not in numbers:
            return None
        index = numbers.index(current.number) + offset
        return blocks[index].name or None if 0 <= index < len(blocks) else None

    return evaluate


def _context_text(name: str) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        return getattr(render.context, name) or None

    return evaluate


def _context_number(name: str) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        return getattr(render.context, name)

    return evaluate


def _date(setting: str | None) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        form = ISO_DATE_FORMAT if setting is None else getattr(render.engine.definition.settings, setting)
        return render.context.now.strftime(form)

    return evaluate


def _spindle_ramp(render, _args, _options: Options):
    """The lines that slow the spindle down in steps (post settings spindle_ramp_*), from the template [spindle_ramp_step]; nothing without a ramp."""
    return render.engine.spindle_ramp()


def _list_tools(render, _args, _options: Options):
    lines: list[str] = []
    for tool in render.context.tools_in_use:
        lines += render.engine.render_concept("tool_entry", {"tool": tool})
    return lines


def _list_notes(render, _args, _options: Options):
    lines: list[str] = []
    for note in render.scope.get("notes", ()):
        lines += render.engine.render_concept("note_entry", {"note": note})
    return lines


# --- threads and drills ------------------------------------------------------------------

def _thread_root(render, _args, options: Options):
    op = render.scope["op"]
    crest = op.start_x + op.peak_offset_mm
    root = crest - op.depth_mm if op.outside else crest + op.depth_mm
    return root * x_factor(render, options, "mode")


def _taper(value_of: Callable) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        op = render.scope["op"]
        if op.taper is ThreadTaper.NONE or op.taper_distance_mm <= 0:
            return None
        return value_of(op)

    return evaluate


def _op(attribute: str, factor: bool | str = False) -> Evaluate:
    """`factor`: True doubles in diameter mode; "options" doubles only when the template asks (`diameter`, `by_mode`)."""
    radial = "mode" if factor is True else ""

    def evaluate(render, _args, options: Options):
        value = getattr(render.scope["op"], attribute)
        return None if value is None else value * (x_factor(render, options, radial) if factor else 1)

    return evaluate


def _text_of(key: str) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        return render.scope.get(key) or None

    return evaluate


def _define() -> None:
    every = EVERYWHERE
    coordinate = frozenset({"incremental", "absolute", "diameter", "radius", "contour", "path"}) | NUMBER_OPTIONS
    for name, axis, label in (("X", "x", "X of the end point"), ("Z", "z", "Z of the end point")):
        register(Token(
            name, f"{label} of the move; empty when the move has none (a move of one axis)", "20" if axis == "x" else "-5.5",
            _axis(name, axis), MOVES, coordinate, "number", radial="mode" if axis == "x" else "", changeable=True,
        ))
    register(Token("X start", "X where the arc starts", "20", _radial("start_x", "csx"), ARCS | THREADS,
                   coordinate, "number", radial="mode"))
    register(Token("Z start", "Z where the arc starts", "0", _plain("start_z", "csz"), ARCS | THREADS, NUMBER_OPTIONS, "number"))
    register(Token("I", "arc centre in X, from the start (radius unless `diameter`)", "-3", _arc_center("x"), ARCS,
                   NUMBER_OPTIONS | {"absolute", "diameter", "contour", "path"}, "number"))
    register(Token("K", "arc centre in Z, from the start", "2", _arc_center("z"), ARCS,
                   NUMBER_OPTIONS | {"absolute", "contour", "path"}, "number"))
    register(Token("R", "arc radius, negative for more than a half circle", "5", _arc_radius, ARCS,
                   NUMBER_OPTIONS | {"contour", "path"}, "number"))
    register(Token("F", "feed (per revolution; `per_minute` uses the spindle speed)", "0.2",
                   _feed, ARCS | {"feed"} | DRILL_CYCLES, NUMBER_OPTIONS | {"per_minute"}, "number", "feed", changeable=True, memory=True))
    register(Token("S", "spindle speed (rpm, or m/min for constant surface speed; ft/min in an inch program)", "1200", _plain("value"), SPINDLE,
                   NUMBER_OPTIONS, "number", "speed", changeable=True, memory=True, dimension=DIMENSION_SURFACE_SPEED))
    register(Token("S max", "speed limit for constant surface speed (empty without a limit)", "3000", _plain("rpm_limit"),
                   SPINDLE, NUMBER_OPTIONS, "number", "speed"))
    register(Token("dwell", "dwell time in seconds", "1.5", _plain("seconds"), frozenset({"dwell", "spindle_ramp_step"}), NUMBER_OPTIONS, "number", "feed",
                   dimension=DIMENSION_NONE))
    register(Token("code", "a code of the code table of the post (the word after it is the name); `changed`: empty when the "
                   "last code of its modal group was this one", "G0", _code, every, frozenset(), "text", args=1, changeable=True,
                   prepare=_prepare_code))
    register(Token("spindle code", "the code that starts the spindle the way the block asks, clockwise (`spindle_cw`) or counter-clockwise (`spindle_ccw`) of the code table; `changed`: "
                   "empty when the last code of its modal group was this one", "M3", _spindle_code, SPINDLE, frozenset(), "text", changeable=True,
                   prepare=_prepare_spindle_code))
    register(Token("x mode code", "the code of `diameter_mode` or `radius_mode` of the code table (empty when the post has none)",
                   "G7", _x_mode_code, every, frozenset(), "text", prepare=_prepare_x_mode))
    register(Token("units code", "the code of `units_mm` or `units_inch` of the code table, as the unit of the machine says (empty when the post has none)",
                   "G21", _units_code, every, frozenset(), "text", prepare=_prepare_units))
    register(Token("N", "the last line number written (empty before the first)", "N20", _line_number(False), every,
                   frozenset(), "text"))
    register(Token("N next", "the next line number (prefix, start and step are settings of the post)", "N30", _line_number(True),
                   every, frozenset(), "text"))
    register(Token("comp code", "G41 / G42 on the lead-in and G40 on the lead-out of a compensated finishing pass, when the post has "
                   "cutter_compensation = yes (codes comp_left, comp_right, comp_off of the code table); else empty", "G42",
                   _comp_code, frozenset({"feed", "arc_ccw", "arc_cw"}), frozenset(), "text", prepare=_prepare_compensation))
    # the program
    for name, label, example, attribute in (
        ("project title", "title of the project", "Shaft 12", "project_title"),
        ("machine name", "name of the machine", "Lathe", "machine_name"),
        ("WOP version", "version of WOP", WOP_VERSION_TEXT, "wop_version"),
        ("material", "material of the raw part", "steel", "material"),
        ("work offset", "work offset of the project (G54 ...), chosen in the Setup form", "G54", "work_offset"),
    ):
        register(Token(name, label, example, _context_text(attribute), every, TEXT_OPTIONS, "text"))
    register(Token("post name", "name of this post (from its file)", "LinuxCNC", _post_name, every, TEXT_OPTIONS, "text"))
    register(Token("x values", "diameters or radii: how X is written in this program", "diameters", _x_values, every,
                   TEXT_OPTIONS, "text"))
    register(Token("part diameter", "outer diameter of the raw part", "40", _context_number("part_diameter_mm"), every,
                   NUMBER_OPTIONS, "number"))
    register(Token("part length", "length of the raw part (empty for bar stock)", "60", _context_number("part_length_mm"), every,
                   NUMBER_OPTIONS, "number"))
    register(Token("program number", "program number of the post settings", "1000", _program_number, every,
                   TEXT_OPTIONS, "text"))
    register(Token("date", "date (the format is a setting of the post)", "17.10.2026", _date("date_format"), every,
                   TEXT_OPTIONS, "text"))
    register(Token("time", "time of day (the format is a setting of the post)", "14:30", _date("time_format"), every,
                   TEXT_OPTIONS, "text"))
    register(Token("date iso", "date as 2026-10-17", "2026-10-17", _date(None), every, TEXT_OPTIONS, "text"))
    register(Token("tool count", "number of tools in the program", "3", _tool_count, every, NUMBER_OPTIONS, "number", "count"))
    register(Token("estimated time", "estimated machining time in minutes (feed moves, rapids at a fixed rate)", "12.5",
                   _context_number("estimated_time_min"), every, NUMBER_OPTIONS, "number", "one"))
    register(Token("path length", "length of all moves in mm", "4200", _context_number("path_length_mm"), every, NUMBER_OPTIONS,
                   "number"))
    register(Token("block name", "name of the block being written", "Rough", _block(None, "name"), every, TEXT_OPTIONS, "text"))
    register(Token("block number", "number of the block as in the flow list", "2", _block(None, "number"), every, NUMBER_OPTIONS,
                   "number", "count"))
    register(Token("block type", "type of the block", "turning", _block(None, "type"), every, TEXT_OPTIONS, "text"))
    register(Token("block count", "number of blocks of the program", "6", _block(None, "count"), every, NUMBER_OPTIONS, "number",
                   "count"))
    register(Token("next block name", "name of the next block (empty at the last)", "Finish", _block(1, "name"), every,
                   TEXT_OPTIONS, "text"))
    register(Token("previous block name", "name of the block before (empty at the first)", "Face", _block(-1, "name"), every,
                   TEXT_OPTIONS, "text"))
    # text
    register(Token("comment text", "the text of a comment", "turn the part", _text_of("text"), frozenset({"comment"}),
                   TEXT_OPTIONS, "text"))
    register(Token("note", "one note of the header", "INCOMPLETE - DO NOT RUN", _text_of("note"), frozenset({"note_entry"}),
                   TEXT_OPTIONS, "text"))
    # lines of their own
    register(Token("list tools", "one line per tool of the program, from [tool_entry]", "", _list_tools, frozenset({"header", "setup"}),
                   kind="lines"))
    register(Token("spindle ramp", "the steps that slow the spindle down before it stops (settings spindle_ramp_step, spindle_ramp_dwell, spindle_ramp_min; template "
                   "[spindle_ramp_step]); put it in front of the stop code. Nothing when the spindle is off or the ramp is off", "", _spindle_ramp,
                   frozenset({"tool_change", "spindle_stop", "footer"}), kind="lines"))
    register(Token("list notes", "one line per note, from [note_entry]", "", _list_notes, frozenset({"header"}), kind="lines"))
    # thread
    thread = frozenset({"thread_cycle", "thread_two_block", "thread_passes"})
    register(Token("pitch", "thread pitch", "1.5", _op("pitch_mm"), thread, NUMBER_OPTIONS, "number", "feed"))
    register(Token("thread depth", "full depth of the thread (radial)", "0.92", _op("depth_mm", "options"), thread, NUMBER_OPTIONS | {"by_mode", "diameter", "radius"}, "number"))
    register(Token("first cut", "depth of the first pass", "0.2", _op("first_cut_mm", "options"), thread, NUMBER_OPTIONS | {"by_mode", "diameter", "radius"}, "number"))
    register(Token("peak offset", "distance from the start to the crest (radial, negative for an outside thread)", "-0.5",
                   _op("peak_offset_mm", "options"), thread, NUMBER_OPTIONS | {"by_mode", "diameter", "radius"}, "number"))
    register(Token("degression", "degression of the passes", "1", _op("degression"), thread, NUMBER_OPTIONS, "number", "one"))
    register(Token("compound angle", "infeed angle in degrees", "29.5", _op("compound_angle_deg"), thread, NUMBER_OPTIONS,
                   "number", "one"))
    register(Token("spring passes", "passes without infeed at the end", "2", _op("spring_passes"), thread, NUMBER_OPTIONS,
                   "number", "count"))
    register(Token("taper distance", "length of the tapered run-out (empty without a taper)", "3",
                   _taper(lambda op: op.taper_distance_mm), thread, NUMBER_OPTIONS, "number"))
    register(Token("taper code", "0 none, 1 entry, 2 exit, 3 both (empty without a taper)", "1",
                   _taper(lambda op: TAPER_CODES[op.taper]), thread, NUMBER_OPTIONS, "number", "count"))
    register(Token("thread start X", "X where the cycle starts", "21", _op("start_x", True), thread,
                   coordinate, "number", radial="mode"))
    register(Token("thread start Z", "Z where the cycle starts", "2", _op("start_z"), thread, NUMBER_OPTIONS, "number"))
    register(Token("thread end Z", "Z where the thread ends", "-20", _op("end_z"), thread, NUMBER_OPTIONS, "number"))
    register(Token("thread root X", "X at the bottom of the thread", "18", _thread_root, thread, coordinate, "number",
                   radial="mode"))
    # drilling cycle
    drill = DRILL_CYCLES
    for name, label, attribute in (
        ("drill retract Z", "Z of the start (the clearance in front of the material)", "retract_z"),
        ("drill end Z", "Z of the bottom of the hole", "end_z"),
        ("drill exit Z", "Z the drill goes back to at the end (empty: the start)", "exit_z"),
        ("drill entry Z", "Z of the surface of the material (empty: the start)", "entry_z"),
        ("drill peck", "depth of one peck (empty for a plain drill)", "peck_depth_mm"),
        ("drill dwell", "dwell at the bottom in seconds (empty without one)", "dwell_s"),
    ):
        register(Token(name, label, "-10", _drill_value(attribute), drill, NUMBER_OPTIONS, "number",
                       dimension=DIMENSION_NONE if attribute == "dwell_s" else None))
    register(Token("drill mode", "drill, peck or peck full retract", "peck", _drill_mode, drill, TEXT_OPTIONS, "text"))


def _drill_value(attribute: str) -> Evaluate:
    def evaluate(render, _args, _options: Options):
        operation = render.scope["op"]
        value = getattr(operation, attribute)
        if attribute == "peck_depth_mm" and operation.effective_mode is DrillMode.DRILL:
            return None  # a plain drill has no peck, whatever the field says
        if attribute == "exit_z" and value is not None:
            render.engine.exit_written = True  # the template takes the drill out itself
        return value or None if attribute == "dwell_s" else value

    return evaluate


def _drill_mode(render, _args, _options: Options):
    return render.scope["op"].effective_mode.value


def _post_name(render, _args, _options: Options):
    return render.engine.definition.name


def _x_values(render, _args, _options: Options):
    return "diameters" if render.engine.settings.x_mode is XInputMode.DIAMETER else "radii"


def _program_number(render, _args, _options: Options):
    return render.engine.definition.settings.program_number or None


def _tool_count(render, _args, _options: Options):
    return len(render.context.tools_in_use)


_define()
