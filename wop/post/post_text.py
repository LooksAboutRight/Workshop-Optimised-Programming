"""The text of a post file as sections, for the editor: read it, change one section, write it back.

Comments and blank lines inside a section stay where they are. The lines before the first section (the comment at the top of
a file) stay too. This module does not check anything: `parse_post` does.
"""

from __future__ import annotations

import re

from .concepts import CONCEPTS
from .post_definition import POST_SECTIONS, SECTION

CANONICAL_ORDER = (*POST_SECTIONS, *CONCEPTS)
KEY_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


class PostText:
    def __init__(self, preamble: list[str] | None = None, sections: dict[str, list[str]] | None = None) -> None:
        self.preamble: list[str] = preamble or []
        self.sections: dict[str, list[str]] = sections or {}

    @classmethod
    def from_text(cls, text: str) -> "PostText":
        preamble: list[str] = []
        sections: dict[str, list[str]] = {}
        current: list[str] | None = None
        for line in text.replace("\r\n", "\n").split("\n"):
            match = SECTION.match(line.strip())
            if match and not line[:1].isspace():
                current = sections.setdefault(match.group(1), [])
            elif current is None:
                preamble.append(line)
            else:
                current.append(line)
        return cls(preamble, sections)

    def copy(self) -> "PostText":
        return PostText(list(self.preamble), {name: list(lines) for name, lines in self.sections.items()})

    def to_text(self) -> str:
        parts: list[str] = []
        head = "\n".join(self.preamble).strip("\n")
        if head:
            parts.append(head)
        for name, lines in self.ordered():
            body = "\n".join(lines).strip("\n")
            parts.append(f"[{name}]\n{body}" if body else f"[{name}]")
        return "\n\n".join(parts) + "\n"

    def ordered(self) -> list[tuple[str, list[str]]]:
        """The sections in the order of the file as read; sections that were added come at their place in the canonical order."""
        return list(self.sections.items())

    def has(self, name: str) -> bool:
        return name in self.sections

    def body(self, name: str) -> str:
        return "\n".join(self.sections.get(name, [])).strip("\n")

    def set_body(self, name: str, body: str) -> None:
        lines = body.replace("\r\n", "\n").split("\n")
        if name in self.sections:
            self.sections[name] = lines
            return
        rank = CANONICAL_ORDER.index(name) if name in CANONICAL_ORDER else len(CANONICAL_ORDER)
        items = list(self.sections.items())
        position = len(items)
        for index, (existing, _lines) in enumerate(items):
            if (CANONICAL_ORDER.index(existing) if existing in CANONICAL_ORDER else len(CANONICAL_ORDER)) > rank:
                position = index
                break
        items.insert(position, (name, lines))
        self.sections = dict(items)

    def remove(self, name: str) -> None:
        self.sections.pop(name, None)


def entries(body: str) -> list[tuple[int, str, str]]:
    """(line number in the section, key, value) of the `key = value` lines; other lines are skipped."""
    found = []
    for number, line in enumerate(body.split("\n"), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = KEY_LINE.match(line)
        if match:
            found.append((number, match.group(1), match.group(2).strip()))
    return found


def set_key(body: str, key: str, value: str) -> str:
    """The section text with `key = value`: the line of the key is changed, or one is added at the end."""
    lines = body.split("\n") if body else []
    for index, line in enumerate(lines):
        match = KEY_LINE.match(line)
        if match and match.group(1) == key and not line.lstrip().startswith("#"):
            lines[index] = f"{key} = {value}"
            return "\n".join(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(f"{key} = {value}")
    return "\n".join(lines)
