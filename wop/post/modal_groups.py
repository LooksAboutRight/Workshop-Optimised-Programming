"""The modal groups of a post file: which G and M codes cancel each other.

The section `[modal_groups]` has one line per group, `name = G0 G1 G2 G3`. A code is written the way the user likes (G0, G00, g0: one code, see `normalize_word`). The names of the fixed groups (`FIXED_MODAL_GROUPS`) are known to the
program; every other name is a group of the user. A code is in one group only. The code table of the post gets its group from here: the
group of a code is the group whose line holds the code (compared by the first word, so `G10 L2` is `G10`).
"""

from __future__ import annotations

import re

from .post_constants import FIXED_MODAL_GROUPS

CODE_WORD = re.compile(r"^[A-Za-z]\d+(\.\d+)?$")
GROUP_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
FIXED_NAMES = tuple(name for name, _meaning, _modal in FIXED_MODAL_GROUPS)
NON_MODAL = frozenset(name for name, _meaning, modal in FIXED_MODAL_GROUPS if not modal)
MEANINGS = {name: meaning for name, meaning, _modal in FIXED_MODAL_GROUPS}
COMMENT_IN_PARENTHESES = re.compile(r"\([^)]*\)")


class ModalGroupError(ValueError):
    """The groups cannot be read. `line` is the line inside the section (0: no place)."""

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


def normalize_word(word: str) -> str:
    """A code word in one form: capitals, the number without leading zeros in front and trailing zeros behind the point, so that
    G00, G0 and g0 are the same code (as they are for a controller) and G38.20 is G38.2."""
    whole, _dot, fraction = word[1:].partition(".")
    fraction = fraction.rstrip("0")
    return word[:1].upper() + (whole.lstrip("0") or "0") + ("." + fraction if fraction else "")


def code_word(text: str) -> str:
    """The word of a code that decides its group: the first word, normalized (`G10 L2` is `G10`, `G00` is `G0`)."""
    words = text.split()
    return normalize_word(words[0]) if words and CODE_WORD.match(words[0]) else (words[0].upper() if words else "")


def normalize_code(text: str) -> str:
    """The text of a code in one form for comparing: the first word normalized, the other words as they are."""
    words = text.split()
    return " ".join([code_word(text), *words[1:]]) if words else ""


def parse_modal_groups(entries: list[tuple[int, str, str]]) -> dict[str, tuple[str, ...]]:
    """The groups from `name = codes` lines (line number, name, rest) as name -> codes in capitals, in the order written."""
    groups: dict[str, tuple[str, ...]] = {}
    owner: dict[str, str] = {}
    for number, name, value in entries:
        if not GROUP_NAME.match(name):
            raise ModalGroupError(f"{name!r} is not a group name (lower case letters, digits and _, starting with a letter)", number)
        if name in groups:
            raise ModalGroupError(f"the modal group {name!r} is written twice", number)
        words: list[str] = []
        for word in value.replace(",", " ").split():
            if not CODE_WORD.match(word):
                raise ModalGroupError(f"{word!r} does not look like a code (a letter and a number, like G1 or G54.1)", number)
            word = normalize_word(word)
            if word in owner and owner[word] != name:
                raise ModalGroupError(f"{word} is in two modal groups: {owner[word]} and {name}", number)
            owner[word] = name
            if word not in words:
                words.append(word)
        groups[name] = tuple(words)
    return groups


def group_of_word(groups: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Code word -> name of its group."""
    return {word: name for name, words in groups.items() for word in words}
