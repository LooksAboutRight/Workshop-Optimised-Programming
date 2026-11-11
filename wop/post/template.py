"""The template language of the post files: one line of a template is text, tokens and optional parts.

    G1 X<X> [ F<F changed> ]          text, a token, an optional part
    <text>(</text><comment text><text>)</text>   <text>...</text> is text that is taken as it is (also < > [ ] and spaces)

A token is `<name word word key=value ...>`: a registered name (longest match, see tokens.py), positional words, options.
An optional part `[ ... ]` is left out when every token inside it renders empty.
This module only reads the text. It knows no token and no value.
"""

from __future__ import annotations

from dataclasses import dataclass

TEXT_OPEN = "<text>"
TEXT_CLOSE = "</text>"


class TemplateError(ValueError):
    """A template that cannot be read. `position` counts characters from the start of the line (0 = first)."""

    def __init__(self, message: str, position: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


@dataclass(frozen=True)
class Literal:
    text: str
    protected: bool = False  # from <text>...</text>: spaces stay as they are


@dataclass(frozen=True)
class RawToken:
    """What stood between < and >: the words, not yet matched to a registered token."""

    words: tuple[str, ...]
    position: int


@dataclass(frozen=True)
class OptionalPart:
    parts: tuple["Node", ...]


Node = Literal | RawToken | OptionalPart


def split_words(inner: str, position: int) -> tuple[str, ...]:
    """Words separated by spaces; a double quote starts a piece that may hold spaces (`prefix="X "`)."""
    words: list[str] = []
    current: list[str] = []
    started = False
    quoted = False
    for index, char in enumerate(inner):
        if char == '"':
            quoted = not quoted
            started = True
        elif char.isspace() and not quoted:
            if started:
                words.append("".join(current))
                current, started = [], False
        else:
            current.append(char)
            started = True
    if quoted:
        raise TemplateError("a quote is not closed", position)
    if started:
        words.append("".join(current))
    return tuple(words)


def parse_line(text: str) -> tuple[Node, ...]:
    """The nodes of one template line."""
    nodes, end = _parse(text, 0, nested=False)
    if end != len(text):  # only a stray ] stops the top level early
        raise TemplateError("a ] without a [ before it", end)
    return nodes


def _parse(text: str, start: int, nested: bool) -> tuple[tuple[Node, ...], int]:
    nodes: list[Node] = []
    literal: list[str] = []

    def flush() -> None:
        if literal:
            nodes.append(Literal("".join(literal)))
            literal.clear()

    index = start
    while index < len(text):
        char = text[index]
        if text.startswith(TEXT_OPEN, index):
            close = text.find(TEXT_CLOSE, index + len(TEXT_OPEN))
            if close < 0:
                raise TemplateError("<text> is not closed by </text>", index)
            flush()
            nodes.append(Literal(text[index + len(TEXT_OPEN):close], protected=True))
            index = close + len(TEXT_CLOSE)
        elif char == "<":
            close = text.find(">", index)
            if close < 0:
                raise TemplateError("a < is not closed by a >", index)
            flush()
            words = split_words(text[index + 1:close], index)
            if not words:
                raise TemplateError("an empty token <>", index)
            nodes.append(RawToken(words, index))
            index = close + 1
        elif char == "[":
            flush()
            inner, end = _parse(text, index + 1, nested=True)
            if end >= len(text) or text[end] != "]":
                raise TemplateError("a [ is not closed by a ]", index)
            nodes.append(OptionalPart(inner))
            index = end + 1
        elif char == "]":
            if nested:
                flush()
                return tuple(nodes), index
            raise TemplateError("a ] without a [ before it", index)
        else:
            literal.append(char)
            index += 1
    flush()
    return tuple(nodes), index
