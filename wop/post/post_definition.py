"""A post file (`name.post.ini`) read into a definition: settings, code table, features and the templates, checked.

The text is read here; reading and writing the file on disk is `wop/adapters/post_files.py`.

    [post]            name, description, format_version
    [settings]        number format, line numbers, comments, styles of thread and drilling ...
    [codes]           name = CODE                   (a template says <code name>, never a G or M of its own)
    [modal_groups]    group = G0 G1 G2 G3           (which codes cancel each other; the code table gets its group from here)
    [functions]       name = description            (custom concepts: each has a section [name] with its template and an
                                                     optional section [name_variables], see variables.py)
    [rapid] ...       one section per concept (see concepts.py); every line is a template; `#` at the start is a comment
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields

from .base import Feature, PostInfo
from .concepts import CONCEPTS
from .post_constants import (
    COORDINATE_DECIMALS,
    COORDINATE_DECIMALS_INCH,
    DEFAULT_LINE_NUMBER_PREFIX,
    DEFAULT_LINE_NUMBER_START,
    DEFAULT_LINE_NUMBER_STEP,
    EXAMPLE_DATE_FORMAT,
    EXAMPLE_TIME_FORMAT,
    FEED_DECIMALS,
    FEED_DECIMALS_INCH,
    POST_FILE_FORMAT_VERSION,
    SPEED_DECIMALS,
    WORK_OFFSET_CODE_PREFIX,
)
from .modal_groups import NON_MODAL, ModalGroupError, code_word, group_of_word, normalize_code, parse_modal_groups
from .template import Literal, Node, OptionalPart, RawToken, TemplateError, parse_line
from .tokens import BoundToken, bind
from .variables import FUNCTION_NAME_END, Function, Variable, VariableError, parse_variables, read_functions

SECTION = re.compile(r"^\[([a-z][a-z0-9_]*)\]$")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
YES = ("yes", "true", "on", "1")
NO = ("no", "false", "off", "0")
THREADING_STYLES = ("cycle", "two_block", "passes")
DRILLING_STYLES = ("expanded", "cycle")
LINE_ENDINGS = {"lf": "\n", "crlf": "\r\n"}
POST_SECTIONS = ("post", "settings", "codes", "modal_groups", "functions")
WORK_OFFSET_NAME = re.compile("^" + re.escape(WORK_OFFSET_CODE_PREFIX) + r"(\d+)$")


def work_offset_number(name: str) -> int | None:
    """The number of a code name of the work offset family (`work_offset_3` is 3); None for every other name."""
    match = WORK_OFFSET_NAME.match(name)
    return int(match.group(1)) if match else None


class PostFileError(ValueError):
    """The post file cannot be used. `section` and `line` (1-based, in the file) say where; `position` is the column in a template."""

    def __init__(self, message: str, section: str = "", line: int = 0, position: int | None = None) -> None:
        where = f"[{section}] " if section else ""
        where += f"line {line}" if line else ""
        where += f", column {position + 1}" if position is not None else ""
        super().__init__(f"{where.strip()}: {message}" if where.strip() else message)
        self.message = message
        self.section = section
        self.line = line
        self.position = position


@dataclass(frozen=True)
class PostFileSettings:
    decimals: int = COORDINATE_DECIMALS
    feed_decimals: int = FEED_DECIMALS
    speed_decimals: int = SPEED_DECIMALS
    decimals_inch: int = COORDINATE_DECIMALS_INCH  # decimals of coordinates in an inch program
    feed_decimals_inch: int = FEED_DECIMALS_INCH
    zeros: bool = False  # keep trailing zeros
    point: bool = False  # always a decimal point
    line_ending: str = "lf"
    file_extension: str = ".ngc"
    encoding: str = "utf-8"
    line_numbers: bool = False  # number every line that is not a comment (prefix, start and step below)
    line_number_prefix: str = DEFAULT_LINE_NUMBER_PREFIX
    line_number_start: int = DEFAULT_LINE_NUMBER_START
    line_number_step: int = DEFAULT_LINE_NUMBER_STEP
    comment_replace: str = ""  # what a comment may not hold and what is written instead: `( -> [, ) -> ]`
    comment_upper: bool = False
    comment_allowed: str = ""  # the characters a comment may hold; the rest becomes a space; empty: everything
    x_diameters: bool = False  # the controller takes X as a diameter (a feature: diameter mode)
    arcs_in_diameters: bool = False  # ... and can write arcs while X is a diameter (a feature: arcs in diameter mode)
    cutter_compensation: bool = False  # write the nominal contour and G41 / G42 / G40 for the moves of a compensated finishing pass
    threading_style: str = "cycle"
    drilling_style: str = "expanded"
    program_number: str = ""
    date_format: str = EXAMPLE_DATE_FORMAT
    time_format: str = EXAMPLE_TIME_FORMAT

    @property
    def newline(self) -> str:
        return LINE_ENDINGS[self.line_ending]


SETTING_HELP = {
    "decimals": "decimals of coordinates", "feed_decimals": "decimals of feeds", "speed_decimals": "decimals of speeds",
    "decimals_inch": "decimals of coordinates in an inch program", "feed_decimals_inch": "decimals of feeds in an inch program",
    "zeros": "keep trailing zeros (yes/no)", "point": "always write a decimal point (yes/no)",
    "line_ending": "lf or crlf", "file_extension": "extension of the G-code file", "encoding": "text encoding of the file",
    "line_numbers": "number every line that is not a comment (yes/no)", "line_number_prefix": "letter(s) in front of a line number", "line_number_start": "first line number",
    "line_number_step": "step of the line numbers",
    "comment_replace": "characters a comment may not hold and what is written instead, separated by commas: ( -> [, ) -> ]",
    "comment_upper": "comments in capital letters (yes/no)", "comment_allowed": "the characters a comment may hold",
    "x_diameters": "the controller takes X as a diameter (yes/no)", "arcs_in_diameters": "the controller can write arcs while X is a diameter (yes/no)",
    "cutter_compensation": "write the contour and G41 / G42 / G40 for compensated finishing passes (yes/no); no: the tool path",
    "threading_style": "cycle, two_block or passes", "drilling_style": "expanded or cycle",
    "program_number": "text for <program number>", "date_format": "format of <date> (strftime)", "time_format": "format of <time>",
}


CODE_FEATURES = (  # a function the controller has when its code is in the code table
    (Feature.CONSTANT_SURFACE_SPEED, "css"), (Feature.COOLANT_FLOOD, "coolant_flood"), (Feature.COOLANT_MIST, "coolant_mist"),
    (Feature.PROGRAM_STOP, "program_stop"), (Feature.OPTIONAL_STOP, "optional_stop"), (Feature.DWELL, "dwell"),
    (Feature.SPINDLE_STOP, "spindle_stop"), (Feature.SPINDLE_REVERSE, "spindle_ccw"),
)


@dataclass(frozen=True)
class Code:
    text: str
    group: str = ""  # the modal group of the code (from `[modal_groups]`, empty: none): codes of one group cancel each other; `changed` compares inside it
    modal: bool = True  # False: the group is not modal (non_modal), `changed` never suppresses the code


@dataclass(frozen=True)
class BoundOptional:
    parts: tuple["BoundNode", ...]


BoundNode = Literal | BoundToken | BoundOptional
Line = tuple[BoundNode, ...]


@dataclass(frozen=True)
class PostDefinition:
    post_id: str
    name: str
    description: str = ""
    settings: PostFileSettings = PostFileSettings()
    codes: dict[str, Code] = field(default_factory=dict, hash=False)
    modal_groups: dict[str, tuple[str, ...]] = field(default_factory=dict, hash=False)  # name -> the codes of the group
    functions: dict[str, Function] = field(default_factory=dict, hash=False)  # the custom concepts of the post (not those of the default post)
    templates: dict[str, tuple[Line, ...]] = field(default_factory=dict, hash=False)
    sources: dict[str, tuple[str, ...]] = field(default_factory=dict, hash=False)  # the text of every section, for the editor
    fallback: "PostDefinition | None" = None

    @property
    def features(self) -> frozenset[Feature]:
        """What the controller can do, worked out from the post: a function is there when its code is in the code table (an empty
        code is not written to the file), a tool change when the post has the template for it (its own or the default post's), diameters and arcs in diameter mode from the two settings. A thread can always be written (as a cycle or as
        passes, see `threading_style`)."""
        found = {Feature.THREAD_CYCLE}
        for feature, name in CODE_FEATURES:
            if name in self.codes:
                found.add(feature)
        if "arc_ccw" in self.codes and "arc_cw" in self.codes:
            found.add(Feature.ARCS)
        if self.settings.x_diameters:
            found.add(Feature.DIAMETER_MODE)
        if self.settings.arcs_in_diameters:
            found.add(Feature.ARCS_IN_DIAMETER_MODE)
        if self.lines_for("tool_change") is not None:
            found.add(Feature.TOOL_CHANGE)
        return frozenset(found)

    @property
    def work_offsets(self) -> tuple[str, ...]:
        """The work offsets of the controller (G54 ...): the codes `work_offset_1`, `work_offset_2` ... of the code table, in the order of
        their numbers. Empty: the post does not choose a work offset."""
        found = sorted((number, code.text) for name, code in self.codes.items() if (number := work_offset_number(name)) is not None)
        return tuple(text for _number, text in found)

    @property
    def info(self) -> PostInfo:
        return PostInfo(self.post_id, self.name, self.features, self.functions)

    def lines_for(self, concept: str) -> tuple[Line, ...] | None:
        """The template lines of a concept: this post's, else the default post's; None when neither has the concept."""
        if concept in self.templates:
            return self.templates[concept]
        return None if self.fallback is None else self.fallback.lines_for(concept)


def replace_pairs(value: str) -> tuple[tuple[str, str], ...]:
    """`( -> [, ) -> ]` as (("(", "["), (")", "]")): what is written instead of what, separated by commas."""
    pairs = []
    for item in (part.strip() for part in value.split(",")) if value.strip() else ():
        old, arrow, new = item.partition("->")
        old, new = old.strip(), new.strip()
        if not arrow or not old:
            raise ValueError(f"comment_replace: {item!r} should be written like  ( -> [")
        pairs.append((old, new))
    return tuple(pairs)


def _bool(value: str, key: str, section: str, line: int) -> bool:
    if value.lower() in YES:
        return True
    if value.lower() in NO:
        return False
    raise PostFileError(f"{key} must be yes or no", section, line)


def read_settings(entries: list[tuple[int, str, str]]) -> PostFileSettings:
    known = {item.name: item for item in fields(PostFileSettings)}
    values: dict[str, object] = {}
    for line, key, value in entries:
        if key not in known:
            raise PostFileError(f"unknown setting {key!r}; the settings are: {', '.join(sorted(known))}", "settings", line)
        kind = known[key].type
        if kind == "bool":
            values[key] = _bool(value, key, "settings", line)
        elif kind == "int":
            if not value.lstrip("-").isdigit():
                raise PostFileError(f"{key} must be a whole number", "settings", line)
            values[key] = int(value)
        else:
            values[key] = value
    settings = PostFileSettings(**values)
    for line, key, value in entries:
        if key == "threading_style" and value not in THREADING_STYLES:
            raise PostFileError(f"threading_style must be one of: {', '.join(THREADING_STYLES)}", "settings", line)
        if key == "drilling_style" and value not in DRILLING_STYLES:
            raise PostFileError(f"drilling_style must be one of: {', '.join(DRILLING_STYLES)}", "settings", line)
        if key == "line_ending" and value not in LINE_ENDINGS:
            raise PostFileError("line_ending must be lf or crlf", "settings", line)
        if key == "comment_replace":
            try:
                replace_pairs(value)
            except ValueError as error:
                raise PostFileError(str(error), "settings", line) from None
    return settings


def _bind_nodes(
    nodes: tuple[Node, ...], concept: str, codes: dict[str, Code], variables: dict[str, Variable] | None = None,
) -> tuple[BoundNode, ...]:
    bound: list[BoundNode] = []
    for node in nodes:
        if isinstance(node, RawToken):
            bound.append(bind(node, concept, codes, variables))
        elif isinstance(node, OptionalPart):
            bound.append(BoundOptional(_bind_nodes(node.parts, concept, codes, variables)))
        else:
            bound.append(node)
    return tuple(bound)


def _check_line_tokens(nodes: tuple[BoundNode, ...], line: str) -> None:
    """A token that expands to several lines must stand alone on its line."""
    def lines_tokens(items) -> list[BoundToken]:
        found = []
        for item in items:
            if isinstance(item, BoundToken) and item.token.kind == "lines":
                found.append(item)
            elif isinstance(item, BoundOptional):
                found += lines_tokens(item.parts)
        return found

    found = lines_tokens(nodes)
    if not found:
        return
    others = [n for n in nodes if not (isinstance(n, Literal) and not n.protected and not n.text.strip())]
    if len(others) != 1 or others[0] is not found[0]:
        raise TemplateError(f"<{found[0].token.name}> must stand alone on its line", found[0].position)


def _code_tokens(nodes: tuple[BoundNode, ...]) -> list[BoundToken]:
    found: list[BoundToken] = []
    for node in nodes:
        if isinstance(node, BoundToken) and node.token.name == "code":
            found.append(node)
        elif isinstance(node, BoundOptional):
            found += _code_tokens(node.parts)
    return found


def _check_modal_groups(nodes: tuple[BoundNode, ...]) -> None:
    """Two different codes of one modal group in one line cancel each other: the controller refuses such a line."""
    seen: dict[str, BoundToken] = {}
    for node in _code_tokens(nodes):
        text, key, modal = node.args[:3]
        if not modal:
            continue
        before = seen.get(key)
        if before is not None and normalize_code(before.args[0]) != normalize_code(text):
            raise TemplateError(f"{before.args[0]} and {text} are in the same modal group ({key}): they cannot be in one line", node.position)
        seen.setdefault(key, node)


def _compile(
    concept: str, lines: list[tuple[int, str]], codes: dict[str, Code], variables: dict[str, Variable] | None = None,
) -> tuple[Line, ...]:
    compiled: list[Line] = []
    for number, text in lines:
        try:
            nodes = _bind_nodes(parse_line(text), concept, codes, variables)
            _check_line_tokens(nodes, text)
            _check_modal_groups(nodes)
        except TemplateError as error:
            raise PostFileError(error.message, concept, number, error.position) from None
        compiled.append(nodes)
    return tuple(compiled)


def parse_codes(entries: list[tuple[int, str, str]], groups: dict[str, tuple[str, ...]] | None = None) -> dict[str, Code]:
    """The code table from `name = CODE` lines (line number, name, rest); each code gets its modal group from `groups`."""
    group_of = group_of_word(groups or {})
    codes: dict[str, Code] = {}
    for number, key, value in entries:
        if not NAME.match(key):
            raise PostFileError(f"{key!r} is not a name (lower case letters, digits and _)", "codes", number)
        if "|" in value:
            raise PostFileError(f"{key}: the modal group is not written in the code table: put the code into the section [modal_groups]", "codes", number)
        if not value.strip():
            raise PostFileError(f"{key} has no code: leave the line out when the controller has no such function", "codes", number)
        code_text = value.strip()
        group = group_of.get(code_word(code_text), "")
        codes[key] = Code(code_text, group, group not in NON_MODAL)
    return codes


def read_modal_groups(entries: list[tuple[int, str, str]]) -> dict[str, tuple[str, ...]]:
    try:
        return parse_modal_groups(entries)
    except ModalGroupError as error:
        raise PostFileError(error.message, "modal_groups", error.line) from None


def check_section(concept: str, text: str, codes: dict[str, Code], variables: tuple[Variable, ...] = ()) -> PostFileError | None:
    """The first problem of the templates of one concept, with line and column inside the text; None when it is fine."""
    lines = [
        (number, line.strip()) for number, line in enumerate(text.split("\n"), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    try:
        _compile(concept, lines, codes, {variable.name: variable for variable in variables})
    except PostFileError as error:
        return error
    return None


def parse_post(text: str, post_id: str, fallback: PostDefinition | None = None) -> PostDefinition:
    """Read and check the text of a post file. Raises PostFileError with the place of the first problem."""
    sections: dict[str, list[tuple[int, str]]] = {}
    header_lines: dict[str, int] = {}
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        match = SECTION.match(line.strip())
        if match and not raw[:1].isspace():
            current = match.group(1)
            if current == "supports":
                raise PostFileError("the section [supports] is gone: what the controller can do follows from the code table and the settings", line=number)
            if current in sections:
                raise PostFileError(f"section [{current}] twice", line=number)
            sections[current] = []
            header_lines[current] = number
        elif current is None:
            if line.strip() and not line.lstrip().startswith("#"):
                raise PostFileError("text before the first section", line=number)
        elif line.strip() and not line.lstrip().startswith("#"):
            sections[current].append((number, line.strip()))

    def pairs(section: str) -> list[tuple[int, str, str]]:
        entries = []
        for number, line in sections.get(section, []):
            key, equals, value = line.partition("=")
            if not equals:
                raise PostFileError("a line of the form key = value is needed", section, number)
            entries.append((number, key.strip(), value.strip()))
        return entries

    meta = {key: value for _n, key, value in pairs("post")}
    for _n, key, _v in pairs("post"):
        if key not in ("name", "description", "format_version"):
            raise PostFileError(f"unknown entry {key!r}", "post")
    if meta.get("format_version", "") != str(POST_FILE_FORMAT_VERSION):
        raise PostFileError(f"format_version = {POST_FILE_FORMAT_VERSION} is needed in [post]", "post")
    groups = read_modal_groups(pairs("modal_groups"))
    codes = parse_codes(pairs("codes"), groups)
    try:
        described = read_functions(pairs("functions"), frozenset({*POST_SECTIONS, *CONCEPTS}))
    except VariableError as error:
        raise PostFileError(error.message, "functions", error.line) from None
    known = {*POST_SECTIONS, *CONCEPTS, *described, *(f"{name}{FUNCTION_NAME_END}" for name in described)}
    for name, number in header_lines.items():
        if name not in known:
            raise PostFileError(f"unknown section [{name}]", line=number)
    functions: dict[str, Function] = {}
    for name, description in described.items():
        try:
            variables = parse_variables(pairs(f"{name}{FUNCTION_NAME_END}"))
        except VariableError as error:
            raise PostFileError(error.message, f"{name}{FUNCTION_NAME_END}", error.line) from None
        functions[name] = Function(name, description, variables)
    templates = {
        name: _compile(name, lines, codes) for name, lines in sections.items() if name in CONCEPTS
    }
    for name, function in functions.items():  # a function without a section writes nothing
        templates[name] = _compile(name, sections.get(name, []), codes, {variable.name: variable for variable in function.variables})
    sources = {name: tuple(line for _n, line in lines) for name, lines in sections.items() if name in CONCEPTS or name in functions}
    return PostDefinition(
        post_id=post_id, name=meta.get("name", post_id), description=meta.get("description", ""),
        settings=read_settings(pairs("settings")), codes=codes, modal_groups=groups, functions=functions,
        templates=templates, sources=sources, fallback=fallback,
    )
