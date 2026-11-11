"""Changes of a template text for the modifier buttons of the post editor (no toolkit).

Every function takes the whole text of a section and the selection (`start`, `end` as character positions; start == end: no
selection, the statement under the cursor is meant) and returns an `Edit` with the new text and the new selection. A change that
would make a line that does not read raises `TemplateEditError`. Templates are read line by line, so a selection over several lines
is changed line by line.

A statement is a run of characters without a space; a space inside `<...>` or `<text>...</text>` does not end it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..post.numbers import FLAG_OPTIONS, VALUE_OPTIONS
from ..post.template import TEXT_CLOSE, TEXT_OPEN, TemplateError, parse_line, split_words
from ..post.tokens import Token, find_token

COMMENT_MARK = "#"
CHANGED = "changed"
TOKEN_OR_TEXT = re.compile(re.escape(TEXT_OPEN) + r".*?" + re.escape(TEXT_CLOSE) + r"|<[^<>]*>")


class TemplateEditError(ValueError):
    """The change cannot be made; the message says why."""


@dataclass(frozen=True)
class Edit:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class TokenAt:
    """A token of the text: where it stands (the `<` to the `>`), its words, and the registered token."""

    start: int
    end: int
    words: tuple[str, ...]
    token: Token
    options: tuple[str, ...]  # the words after the name and its own words: the options as written


Lookup = Callable[[tuple[str, ...]], "tuple[Token, tuple[str, ...]] | None"]


# --- lines and statements ------------------------------------------------------------------


def _lines(text: str) -> list[tuple[int, int]]:
    """(start, end) of every line; the end does not include the line break."""
    spans, start = [], 0
    for line in text.split("\n"):
        spans.append((start, start + len(line)))
        start += len(line) + 1
    return spans


def _statements(line: str) -> list[tuple[int, int]]:
    """The statements of a line: runs without a space, where a space inside a token or protected text does not count."""
    keep = [False] * len(line)
    for match in TOKEN_OR_TEXT.finditer(line):
        for position in range(match.start(), match.end()):
            keep[position] = True
    spans, begin = [], None
    for position, char in enumerate(line):
        inside = not char.isspace() or keep[position]
        if inside and begin is None:
            begin = position
        elif not inside and begin is not None:
            spans.append((begin, position))
            begin = None
    if begin is not None:
        spans.append((begin, len(line)))
    return spans


def _statement_at(line: str, column: int) -> tuple[int, int] | None:
    spans = _statements(line)
    for begin, end in spans:
        if begin <= column <= end:
            return begin, end  # the statement under the cursor, or the one that ends where the cursor stands
    after = [span for span in spans if span[0] > column]
    return after[0] if after else None


def _enclosing_brackets(line: str, column: int) -> tuple[int, int] | None:
    """The innermost `[ ... ]` around a column (the positions of the brackets themselves), ignoring brackets inside text."""
    protected = [False] * len(line)
    for match in re.finditer(re.escape(TEXT_OPEN) + r".*?" + re.escape(TEXT_CLOSE), line):
        for position in range(match.start(), match.end()):
            protected[position] = True
    stack: list[int] = []
    best: tuple[int, int] | None = None
    for position, char in enumerate(line):
        if protected[position]:
            continue
        if char == "[":
            stack.append(position)
        elif char == "]" and stack:
            opening = stack.pop()
            if opening < column <= position and (best is None or opening >= best[0]):
                best = (opening, position)
    return best


def _check_cut(line: str, a: int, b: int) -> None:
    """A selection must not start or end inside a token or protected text."""
    for match in TOKEN_OR_TEXT.finditer(line):
        if match.start() < a < match.end() or match.start() < b < match.end():
            raise TemplateEditError("the selection cuts a token in half: select the whole token")


def _pieces(text: str, start: int, end: int) -> list[tuple[int, int, int]]:
    """(line start, piece start, piece end) of the part of every line the selection touches; no selection: the statement
    under the cursor. Empty pieces and comment lines are left out."""
    pieces = []
    for line_start, line_end in _lines(text):
        line = text[line_start:line_end]
        if line.lstrip().startswith(COMMENT_MARK):
            continue
        if start == end:
            if not line_start <= start <= line_end:
                continue
            found = _statement_at(line, start - line_start)
            if found is not None:
                pieces.append((line_start, line_start + found[0], line_start + found[1]))
            continue
        a, b = max(start, line_start), min(end, line_end)
        if a < b and line[a - line_start:b - line_start].strip():
            _check_cut(line, a - line_start, b - line_start)
            pieces.append((line_start, a, b))
    return pieces


def _check_line(line: str) -> None:
    try:
        parse_line(line)
    except TemplateError as error:
        raise TemplateEditError(f"that would not read: {error.message}") from None


def _rebuild(text: str, changes: list[tuple[int, int, str]]) -> Edit:
    """Apply (start, end, new text) changes (not overlapping), check the lines they are in, select the changed places."""
    new_text, shift, marks = text, 0, []
    for start, end, replacement in sorted(changes):
        new_text = new_text[:start + shift] + replacement + new_text[end + shift:]
        marks.append((start + shift, start + shift + len(replacement)))
        shift += len(replacement) - (end - start)
    for line_start, line_end in _lines(new_text):
        if any(line_start <= a <= line_end for a, _b in marks):
            line = new_text[line_start:line_end]
            if not line.lstrip().startswith(COMMENT_MARK):
                _check_line(line)
    return Edit(new_text, marks[0][0], marks[-1][1])


# --- tokens -------------------------------------------------------------------------------------


def _token_words(match_text: str, position: int) -> tuple[str, ...]:
    return split_words(match_text[1:-1], position)


def token_at(text: str, start: int, end: int, lookup: Lookup = find_token) -> TokenAt | None:
    """The token the cursor is in, or the first token of the selection."""
    for match in TOKEN_OR_TEXT.finditer(text):
        if match.group().startswith(TEXT_OPEN):
            continue
        inside = match.start() <= start <= match.end() if start == end else match.start() < end and start < match.end()
        if inside:
            words = _token_words(match.group(), match.start())
            found = lookup(words)
            if found is None:
                return None
            token, rest = found
            return TokenAt(match.start(), match.end(), words, token, tuple(rest[token.args:]))
    return None


def _allowed_options(token: Token) -> frozenset[str]:
    return token.options | ({CHANGED} if token.changeable else frozenset())


def available_options(token: Token) -> list[tuple[str, str, bool]]:
    """(option, what it does, takes a value) for the options of a token, in alphabetical order."""
    found = []
    for name in sorted(_allowed_options(token)):
        meaning = FLAG_OPTIONS.get(name) or VALUE_OPTIONS.get(name, "")
        found.append((name, meaning, name in VALUE_OPTIONS))
    return found


def written_options(at: TokenAt) -> dict[str, str]:
    """The options a token has now: name -> value ("" for a flag)."""
    found: dict[str, str] = {}
    for word in at.options:
        name, _equals, value = word.partition("=")
        found[name] = value
    return found


def set_option(text: str, at: TokenAt, name: str, value: str | None) -> Edit:
    """Put an option into the token (`value` for a value option, None for a flag); the option is replaced when it is there."""
    words = [word for word in at.words if word.partition("=")[0] != name]
    if value is not None:
        words.append(f'{name}="{value}"' if (" " in value or not value) else f"{name}={value}")
    else:
        words.append(name)
    return _rebuild(text, [(at.start, at.end, "<" + " ".join(words) + ">")])


def remove_option(text: str, at: TokenAt, name: str) -> Edit:
    words = [word for word in at.words if word.partition("=")[0] != name]
    return _rebuild(text, [(at.start, at.end, "<" + " ".join(words) + ">")])


def _add_changed(piece: str, lookup: Lookup) -> tuple[str, int]:
    """`changed` added to every token of the piece that can have it and does not have it yet. Returns the new piece and how many tokens changed."""
    count = 0

    def one(match: re.Match) -> str:
        nonlocal count
        if match.group().startswith(TEXT_OPEN):
            return match.group()
        words = _token_words(match.group(), 0)
        found = lookup(words)
        if found is None or not found[0].changeable or CHANGED in words:
            return match.group()
        count += 1
        return match.group()[:-1] + " " + CHANGED + ">"

    return TOKEN_OR_TEXT.sub(one, piece), count


def _remove_changed(piece: str) -> str:
    def one(match: re.Match) -> str:
        if match.group().startswith(TEXT_OPEN):
            return match.group()
        words = [word for word in _token_words(match.group(), 0) if word != CHANGED]
        return "<" + " ".join(words) + ">"

    return TOKEN_OR_TEXT.sub(one, piece)


def _has_changed(piece: str) -> bool:
    return any(CHANGED in _token_words(match.group(), 0) for match in TOKEN_OR_TEXT.finditer(piece) if not match.group().startswith(TEXT_OPEN))


# --- the buttons --------------------------------------------------------------------------------


def _bracketed(text: str, start: int, end: int) -> tuple[int, int] | None:
    """The bracket pair of a selection that is `[ ... ]`, or the bracket pair the cursor is inside (the positions of the brackets)."""
    for line_start, line_end in _lines(text):
        line = text[line_start:line_end]
        if start == end:
            if line_start <= start <= line_end:
                found = _enclosing_brackets(line, start - line_start)
                return None if found is None else (line_start + found[0], line_start + found[1])
            continue
        a, b = max(start, line_start), min(end, line_end)
        if a < b:
            chunk = line[a - line_start:b - line_start]
            if chunk.strip().startswith("[") and chunk.strip().endswith("]"):
                return a + chunk.index("["), a + chunk.rindex("]")
    return None


def _line_end(text: str, line_start: int) -> int:
    found = text.find("\n", line_start)
    return len(text) if found < 0 else found


def _wrap(text: str, start: int, end: int, changed: bool, lookup: Lookup) -> Edit:
    changes: list[tuple[int, int, str]] = []
    counted = 0
    for line_start, a, b in _pieces(text, start, end):
        piece = text[a:b]
        inside_brackets = a > line_start and text[a - 1] == "[" and b < _line_end(text, line_start) and text[b] == "]"
        if inside_brackets and not changed:
            continue  # it is optional already
        if a > line_start and text[a - 1] == " " and not piece.startswith(" ") and not inside_brackets:
            a, piece = a - 1, " " + piece  # the space in front of a statement goes into the brackets, so it vanishes with it
        if changed:
            piece, count = _add_changed(piece, lookup)
            counted += count
        changes.append((a, b, piece if inside_brackets else "[" + piece + "]"))
    if not changes:
        raise TemplateEditError("that is optional already" if _pieces(text, start, end) else "put the cursor into a statement or select it first")
    if changed and not counted:
        raise TemplateEditError("no token there can be 'changed' (or they all are already)")
    return _rebuild(text, changes)


def apply_changed(text: str, start: int, end: int, lookup: Lookup = find_token) -> Edit:
    """Make the statement optional and `changed`: `F<F>` becomes `[ F<F changed>]` (the space in front goes inside). On a part that
    is `[ ... changed ]` already it takes the brackets and `changed` away again; on a part that is optional already it adds `changed`."""
    found = _bracketed(text, start, end)
    if found is not None:
        opening, closing = found
        inner = text[opening + 1:closing]
        if _has_changed(inner):
            return _rebuild(text, [(opening, closing + 1, _remove_changed(inner))])
        inner, count = _add_changed(inner, lookup)
        if not count:
            raise TemplateEditError("no token there can be 'changed'")
        return _rebuild(text, [(opening + 1, closing, inner)])
    return _wrap(text, start, end, True, lookup)


def apply_optional(text: str, start: int, end: int, lookup: Lookup = find_token) -> Edit:
    """Make the statement optional: `X<X>` becomes `[X<X>]`."""
    if _bracketed(text, start, end) is not None:
        raise TemplateEditError("that is optional already")
    return _wrap(text, start, end, False, lookup)


def apply_unwrap(text: str, start: int, end: int) -> Edit:
    """Take one level of brackets away; the tokens inside stay as they are."""
    found = _bracketed(text, start, end)
    if found is None:
        raise TemplateEditError("there are no brackets around the cursor or the selection")
    opening, closing = found
    return _rebuild(text, [(opening, closing + 1, text[opening + 1:closing])])


def apply_protect(text: str, start: int, end: int) -> Edit:
    """Protect text: `<text>...</text>` keeps characters like < > [ ] and spaces as they are. On protected text it takes the marks away."""
    changes = []
    for _line, a, b in _pieces(text, start, end):
        piece = text[a:b]
        if piece.startswith(TEXT_OPEN) and piece.endswith(TEXT_CLOSE) and len(piece) >= len(TEXT_OPEN) + len(TEXT_CLOSE):
            changes.append((a, b, piece[len(TEXT_OPEN):-len(TEXT_CLOSE)]))
        else:
            changes.append((a, b, TEXT_OPEN + piece + TEXT_CLOSE))
    if not changes:
        raise TemplateEditError("put the cursor into a statement or select it first")
    return _rebuild(text, changes)


def apply_comment(text: str, start: int, end: int) -> Edit:
    """Comment the lines out with `# ` (a line that is commented out is not read); on commented lines it takes the mark away."""
    chosen = [(line_start, line_end) for line_start, line_end in _lines(text)
              if (line_start <= start <= line_end if start == end else line_start < end and start <= line_end)]
    chosen = [(a, b) for a, b in chosen if text[a:b].strip()]
    if not chosen:
        raise TemplateEditError("put the cursor into a line or select lines first")
    changes = []
    uncomment = all(text[a:b].lstrip().startswith(COMMENT_MARK) for a, b in chosen)
    for line_start, line_end in chosen:
        line = text[line_start:line_end]
        if uncomment:
            mark = line.index(COMMENT_MARK)
            after = mark + 1 + (1 if line[mark + 1:mark + 2] == " " else 0)
            changes.append((line_start, line_end, line[:mark] + line[after:]))
        else:
            changes.append((line_start, line_end, COMMENT_MARK + " " + line))
    return _rebuild(text, changes)
