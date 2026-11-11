"""The model of the post editor (no toolkit): the text of one post file, changed section by section, checked, with sample output.

The window shows pages: the post itself, its settings, the code table, the features and one page per concept. Every change
goes into the text; `text` is what is saved. Nothing here writes a file: that is `AppModel`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

from ..core.program_model.units import XInputMode
from ..post.base import PostError
from ..post.concepts import CONCEPTS
from ..post.post_definition import (
    POST_SECTIONS,
    SETTING_HELP,
    Code,
    PostDefinition,
    PostFileError,
    PostFileSettings,
    check_section,
    parse_codes,
    parse_post,
    read_modal_groups,
    read_settings,
    work_offset_number,
)
from ..post.modal_groups import CODE_WORD, COMMENT_IN_PARENTHESES, FIXED_NAMES, MEANINGS, code_word, group_of_word
from ..post.post_constants import FIXED_CODES, WORK_OFFSET_CODE_PREFIX
from ..post.variables import FUNCTION_NAME_END, Variable, VariableError, parse_variables, read_functions
from ..post.post_text import PostText, entries, set_key
from ..post.samples import render_sample
from ..post.tokens import TOKENS, Token
from .ui_constants import POST_EDITOR_TOKEN_GROUPS

NEW_POST_NAME = "New post"
TOKENS_AND_TEXT = re.compile(r"<text>.*?</text>|<[^<>]*>")  # a token or protected text: no hint inside
DEPENDENCIES = {"header": ("tool_entry", "note_entry")}  # concepts a concept calls (<list tools>, <list notes>)


@dataclass(frozen=True)
class Preview:
    """The sample output of a concept. `error` replaces the output; `line` and `column` (1-based, in the section) say where."""

    present: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    error: str = ""
    line: int | None = None
    column: int | None = None
    note: str = ""  # for example that the section comes from the default post


@dataclass(frozen=True)
class TokenButton:
    text: str  # what is put into the template
    label: str  # on the button
    help: str  # the tooltip
    group: str


def token_group(token: Token) -> str:
    name = token.name
    for group, test in POST_EDITOR_TOKEN_GROUPS:
        if test(name):
            return group
    return "Other"


class PostEditorModel:
    def __init__(self, post_id: str, text: str, shipped: bool, fallback: PostDefinition | None, unreadable: str = "") -> None:
        self.post_id = post_id
        self.unreadable = unreadable  # why the file cannot be read as text (a read-only placeholder with nothing in it: only Delete works)
        self.shipped = shipped  # read-only: "Save as copy" makes a post of the user
        self.fallback = fallback
        self._saved = text
        self._text = PostText.from_text(text)

    # --- the text ----------------------------------------------------------------------

    @property
    def text(self) -> str:
        return self._text.to_text()

    @property
    def dirty(self) -> bool:
        return self.text != PostText.from_text(self._saved).to_text()

    def mark_saved(self, post_id: str | None = None) -> None:
        if post_id is not None:
            self.post_id = post_id
        self.shipped = False
        self._saved = self.text

    def problem(self) -> PostFileError | None:
        """The first problem of the whole file, or None."""
        try:
            parse_post(self.text, self.post_id, self.fallback)
        except PostFileError as error:
            return error
        return None

    def page_problems(self) -> dict[str, str]:
        """The first problem of each page that has one: page ("post", "settings", "codes", "features" or a concept) -> text.
        The pages with a problem are shown in red; what is wrong is shown on the page itself."""
        if self.problem() is None:
            return {}
        found: dict[str, str] = {}
        only_post = PostText(self._text.preamble, {"post": self._text.sections.get("post", [])})
        try:
            parse_post(only_post.to_text(), self.post_id, self.fallback)
        except PostFileError as error:
            found["post"] = str(error)
        unknown = [name for name in self._text.sections if name not in POST_SECTIONS and name not in CONCEPTS]
        if unknown and "post" not in found:
            found["post"] = f"unknown section [{unknown[0]}]"
        for page, check in (
            ("settings", lambda: read_settings(entries(self._text.body("settings")))),
            ("modal_groups", lambda: read_modal_groups(entries(self._text.body("modal_groups")))),
            ("codes", lambda: parse_codes(entries(self._text.body("codes")), self._groups())),
        ):
            try:
                check()
            except PostFileError as error:
                found[page] = str(error)
        for concept in self.concept_keys():
            problem = self.section_problem(concept)
            if problem is not None:
                found[concept] = str(problem)
        if not found:  # a problem that belongs to no page (for example a line without an equals sign): the file as a whole
            found["post"] = str(self.problem())
        return found

    # --- the post itself ---------------------------------------------------------------

    def meta(self, key: str) -> str:
        return next((value for _n, name, value in entries(self._text.body("post")) if name == key), "")

    def set_meta(self, key: str, value: str) -> None:
        body = self._text.body("post") or "format_version = 1"
        self._text.set_body("post", set_key(body, key, value.strip()))

    @property
    def name(self) -> str:
        return self.meta("name") or self.post_id

    # --- settings ----------------------------------------------------------------------

    def settings(self) -> PostFileSettings:
        """The settings as they read now (the defaults when a value is wrong: `problem` says which)."""
        try:
            return read_settings(entries(self._text.body("settings")))
        except PostFileError:
            return PostFileSettings()

    def set_setting(self, key: str, value: str) -> None:
        self._text.set_body("settings", set_key(self._text.body("settings"), key, value))

    @staticmethod
    def setting_names() -> tuple[str, ...]:
        return tuple(field.name for field in fields(PostFileSettings))

    @staticmethod
    def setting_help(key: str) -> str:
        return SETTING_HELP.get(key, "")

    # --- codes ----------------------------------------------------------------------------

    def codes(self) -> list[tuple[str, str, str]]:
        """(name, code, modal group) in the order of the file; the group comes from the modal groups, it is not written in the table."""
        group_of = group_of_word(self._groups())
        found = []
        for _n, key, value in entries(self._text.body("codes")):
            code = value.partition("|")[0].strip()
            found.append((key, code, group_of.get(code_word(code), "")))
        return found

    def set_codes(self, rows: list[tuple[str, str, str]]) -> None:
        lines = []
        for name, code, _group in rows:
            if name.strip() or code.strip():
                lines.append(f"{name.strip()} = {code.strip()}")
        self._text.set_body("codes", "\n".join(lines))

    def code_rows(self) -> list[tuple[str, str, str, bool, str]]:
        """(name, code, modal group, fixed, heading or meaning) of every row of the code table: the fixed ones first (all of them, in their
        order, an empty code means the controller has no such function), then the codes of the user in the order of the file."""
        written = {name: (code, group) for name, code, group in self.codes()}
        rows = [(name, *written.get(name, ("", "")), True, meaning) for name, meaning, _heading in FIXED_CODES]
        fixed = {name for name, _meaning, _heading in FIXED_CODES}
        rows += [(name, code, group, False, "") for name, code, group in self.codes() if name not in fixed and work_offset_number(name) is None]
        return rows

    def work_offset_rows(self) -> list[tuple[str, str, str]]:
        """(name, code, modal group) of the work offsets of the code table (`work_offset_1` ...), in the order of their numbers."""
        found = [(work_offset_number(name), name, code, group) for name, code, group in self.codes() if work_offset_number(name) is not None]
        return [(name, code, group) for _number, name, code, group in sorted(found)]

    @staticmethod
    def work_offset_name(position: int) -> str:
        """The code name of the work offset at `position` in the list (1 is the first)."""
        return f"{WORK_OFFSET_CODE_PREFIX}{position}"

    @staticmethod
    def code_headings() -> dict[str, str]:
        """Fixed code name -> the heading it stands under."""
        return {name: heading for name, _meaning, heading in FIXED_CODES}

    def set_code_rows(self, rows: list[tuple[str, str]]) -> None:
        """Write the codes (name, code) in this order. A fixed code or a work offset that is empty is left out, a code of the user is kept."""
        fixed = {name for name, _meaning, _heading in FIXED_CODES}
        lines = []
        for name, code in rows:
            name, code = name.strip(), code.strip()
            if (name in fixed or work_offset_number(name) is not None) and not code:
                continue
            if name or code:
                lines.append(f"{name} = {code}".rstrip())
        if lines:
            self._text.set_body("codes", chr(10).join(lines))
        else:
            self._text.remove("codes")

    def literal_hints(self, concept: str) -> list[str]:
        """Words of the template that are a code of the code table written out: a hint to use `<code name>`, not a problem."""
        if not self.has_section(concept):
            return []
        names: dict[str, str] = {}
        for name, code, _group in self.codes():
            names.setdefault(code_word(code), name)
        found: list[str] = []
        for line in self.section(concept).split(chr(10)):
            if line.lstrip().startswith("#"):
                continue
            outside = COMMENT_IN_PARENTHESES.sub(" ", TOKENS_AND_TEXT.sub(" ", line))
            for word in outside.replace("[", " ").replace("]", " ").split():
                name = names.get(code_word(word)) if CODE_WORD.match(word) else None
                hint = f"{word} is in the code table as {name}: write <code {name}>" if name else ""
                if hint and hint not in found:
                    found.append(hint)
        return found

    def code_table(self) -> dict[str, Code]:
        try:
            return parse_codes(entries(self._text.body("codes")), self._groups())
        except PostFileError:
            return {}

    def group_of_code(self, code: str) -> str:
        """The modal group a code text would have now (empty: none)."""
        return group_of_word(self._groups()).get(code_word(code), "")

    def ungrouped_codes(self) -> list[str]:
        """The names of the codes of the table that are in no modal group (each is its own group)."""
        return [name for name, _code, group in self.codes() if not group]

    # --- modal groups ------------------------------------------------------------------------------

    def _groups(self) -> dict[str, tuple[str, ...]]:
        try:
            return read_modal_groups(entries(self._text.body("modal_groups")))
        except PostFileError:
            return {}

    def modal_groups(self) -> list[tuple[str, str, bool]]:
        """(name, codes as written, fixed) of every modal group: the fixed ones first (always all of them, in their order), then the
        groups of the user in the order of the file."""
        written: dict[str, str] = {}
        for _n, key, value in entries(self._text.body("modal_groups")):
            written.setdefault(key, value.strip())
        rows = [(name, written.get(name, ""), True) for name in FIXED_NAMES]
        rows += [(name, codes, False) for name, codes in written.items() if name not in FIXED_NAMES]
        return rows

    @staticmethod
    def modal_group_meaning(name: str) -> str:
        return MEANINGS.get(name, "")

    def set_modal_groups(self, rows: list[tuple[str, str]]) -> None:
        """Write the groups (name, codes) in this order. A fixed group without codes is left out, a group of the user is kept."""
        lines = []
        for name, codes in rows:
            name, codes = name.strip(), codes.strip()
            if name in FIXED_NAMES and not codes:
                continue
            if name or codes:
                lines.append(f"{name} = {codes}".rstrip())
        if lines:
            self._text.set_body("modal_groups", "\n".join(lines))
        else:
            self._text.remove("modal_groups")

    # --- concepts ----------------------------------------------------------------------------

    @staticmethod
    def concepts() -> tuple[str, ...]:
        return tuple(CONCEPTS)

    def has_section(self, concept: str) -> bool:
        return self._text.has(concept) or self.is_function(concept)  # a custom concept is always the post's own

    # --- custom concepts (functions) and their variables -------------------------------------------

    def functions(self) -> list[tuple[str, str]]:
        """(name, description) of the custom concepts in the order of the file."""
        return [(name, value) for _n, name, value in entries(self._text.body("functions"))]

    def function_names(self) -> list[str]:
        return [name for name, _description in self.functions()]

    def concept_keys(self) -> tuple[str, ...]:
        """The built-in concepts and then the custom ones."""
        return (*CONCEPTS, *self.function_names())

    def is_function(self, concept: str) -> bool:
        return concept in self.function_names()

    def function_description(self, name: str) -> str:
        return dict(self.functions()).get(name, "")

    def _write_functions(self, rows: list[tuple[str, str]]) -> None:
        if rows:
            self._text.set_body("functions", chr(10).join(f"{name} = {description}".rstrip() for name, description in rows))
        else:
            self._text.remove("functions")

    def add_function(self, name: str, description: str) -> None:
        """Add a custom concept with an empty template. Raises ValueError with the reason when the name does not work."""
        name = name.strip()
        rows = self.functions() + [(name, description.strip())]
        try:
            read_functions([(number, row_name, row_description) for number, (row_name, row_description) in enumerate(rows, start=1)], frozenset({*POST_SECTIONS, *CONCEPTS}))
        except VariableError as error:
            raise ValueError(error.message) from None
        self._write_functions(rows)
        self._text.set_body(name, "")

    def set_function_description(self, name: str, description: str) -> None:
        self._write_functions([(row, description.strip() if row == name else text) for row, text in self.functions()])

    def remove_function(self, name: str) -> None:
        """Remove a custom concept with its template and its variables."""
        self._write_functions([(row, text) for row, text in self.functions() if row != name])
        self._text.remove(name)
        self._text.remove(f"{name}{FUNCTION_NAME_END}")

    def variables_text(self, name: str) -> str:
        return self._text.body(f"{name}{FUNCTION_NAME_END}")

    def set_variables_text(self, name: str, text: str) -> None:
        if text.strip():
            self._text.set_body(f"{name}{FUNCTION_NAME_END}", text)
        else:
            self._text.remove(f"{name}{FUNCTION_NAME_END}")

    def variables(self, name: str) -> tuple[Variable, ...]:
        """The variables of a custom concept as they read now; none when they do not read (`variables_problem` says why)."""
        try:
            return parse_variables(entries(self.variables_text(name)))
        except VariableError:
            return ()

    def variables_problem(self, name: str) -> PostFileError | None:
        try:
            parse_variables(entries(self.variables_text(name)))
        except VariableError as error:
            return PostFileError(error.message, f"{name}{FUNCTION_NAME_END}", error.line)
        return None

    def section(self, concept: str) -> str:
        return self._text.body(concept)

    def set_section(self, concept: str, body: str) -> None:
        self._text.set_body(concept, body)

    def use_default(self, concept: str) -> None:
        """Leave the section out: the default post supplies it."""
        self._text.remove(concept)

    def own_from_default(self, concept: str) -> str:
        """Make the section this post's own, starting with the text of the default post. Returns the text."""
        sources = self._default_sources(concept)
        body = "\n".join(sources)
        self._text.set_body(concept, body)
        return body

    def default_section(self, concept: str) -> str:
        """The text of the concept in the default post (empty when it has none)."""
        return "\n".join(self._default_sources(concept))

    def _default_sources(self, concept: str) -> tuple[str, ...]:
        definition = self.fallback
        while definition is not None:
            if concept in definition.sources:
                return definition.sources[concept]
            definition = definition.fallback
        return ()

    def section_problem(self, concept: str) -> PostFileError | None:
        if not self.has_section(concept):
            return None
        if self.is_function(concept):
            problem = self.variables_problem(concept)
            if problem is not None:
                return problem
        return check_section(concept, self.section(concept), self.code_table(), self.variables(concept) if self.is_function(concept) else ())

    # --- tokens --------------------------------------------------------------------------------

    def tokens_for(self, concept: str) -> list[Token]:
        return [t for t in TOKENS.values() if t.concepts is None or concept in t.concepts]

    def token_buttons(self, concept: str) -> list[TokenButton]:
        """What the token grid offers for a concept: one button per token, one per code of the code table."""
        buttons: list[TokenButton] = []
        for variable in self.variables(concept) if self.is_function(concept) else ():
            unit = f" {variable.unit}" if variable.unit else ""
            buttons.append(TokenButton(f"<{variable.name}>", variable.name, f"{variable.label} ({variable.type}{unit}), default {variable.default}", "Variables"))
        for token in self.tokens_for(concept):
            group = token_group(token)
            options = sorted(token.options | ({"changed"} if token.changeable else set()))
            tip = f"{token.description}\nExample: {token.example}" if token.example else token.description
            if options:
                tip += "\nOptions: " + ", ".join(options)
            if token.name == "code":
                for name, code, _group in self.codes():
                    buttons.append(TokenButton(f"<code {name}>", f"code {name}", f"the code {code}\n{tip}", "Codes and numbers"))
                continue
            buttons.append(TokenButton(f"<{token.name}>", token.name, tip, group))
        return buttons

    # --- sample output --------------------------------------------------------------------------

    def preview(self, concept: str, x_mode: XInputMode = XInputMode.DIAMETER) -> Preview:
        """What the concept writes for the sample values (see `post/samples.py`); its own problem instead when it has one."""
        own = self.has_section(concept)
        if own:
            problem = self.section_problem(concept)
            if problem is not None:
                return Preview(error=problem.message, line=problem.line or None, column=None if problem.position is None else problem.position + 1)
        try:
            read_modal_groups(entries(self._text.body("modal_groups")))  # checked for the error
            parse_codes(entries(self._text.body("codes")), self._groups())  # checked for the error
            read_settings(entries(self._text.body("settings")))
        except PostFileError as error:
            return Preview(error=str(error))
        reduced = self._reduced(concept)
        try:
            definition = parse_post(reduced.to_text(), self.post_id, self.fallback)
        except PostFileError as error:
            return Preview(error=str(error))
        note = "" if own else "this post has no section of its own: the default post writes it"
        try:
            present = render_sample(definition, concept, True, x_mode)
            absent = render_sample(definition, concept, False, x_mode)
        except PostError as error:
            message = str(error)
            if "there is no default post" in message:
                message = f"[{concept}] is neither in this post nor in the default post. A program that needs it cannot be written."
            return Preview(error=message, note=note)
        return Preview(tuple(present), tuple(absent), note=note)

    def _reduced(self, concept: str) -> PostText:
        """The file with only what this concept needs: a problem in another concept does not stop the sample."""
        keep = {"post", "settings", "codes", "modal_groups", concept, *DEPENDENCIES.get(concept, ())}
        if self.is_function(concept):
            keep |= {"functions", f"{concept}{FUNCTION_NAME_END}"}
        reduced = self._text.copy()
        for name in list(reduced.sections):
            if name not in keep:
                reduced.remove(name)
        # a dependency with a problem would stop the sample: leave it out (the default post takes over)
        for name in DEPENDENCIES.get(concept, ()):
            if reduced.has(name) and check_section(name, reduced.body(name), self.code_table()) is not None:
                reduced.remove(name)
        return reduced
