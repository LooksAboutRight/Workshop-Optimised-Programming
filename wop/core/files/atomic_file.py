"""Write a text file in one step (a crash cannot leave half a file behind), with LF line ends."""

from __future__ import annotations

import os
from pathlib import Path

TEMPORARY_SUFFIX = ".tmp"
DEFAULT_ENCODING = "utf-8"


def write_text_atomically(path: Path, text: str, encoding: str = DEFAULT_ENCODING) -> None:
    """Write `text` (with a line end at its end) to a temporary file next to `path` and put it in place; the folder is made when it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + TEMPORARY_SUFFIX)
    with open(temporary, "w", encoding=encoding, newline="") as handle:  # newline="": no CRLF on Windows
        handle.write(text if text.endswith("\n") else text + "\n")
    os.replace(temporary, path)
