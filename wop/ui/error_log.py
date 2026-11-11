"""A log file for what the program writes to its error output (toolkit-free).

A Python error inside a button or field handler is only printed by Qt, never raised, and the windowed .exe has no console:
without this the user would see nothing happen. `ErrorLog` replaces `sys.stderr`: everything goes to a file (and to the
old error output when there is one), and a Python traceback is counted so the window can tell the user.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

LOG_FILE_NAME = "wop.log"
OLD_SUFFIX = ".old"
MAX_LOG_BYTES = 1_000_000  # a bigger file is kept as wop.log.old and a new one is started
TRACEBACK_MARK = "Traceback (most recent call last)"
ENCODING = "utf-8"


class ErrorLog:
    def __init__(self, path: Path, console: TextIO | None = None) -> None:
        self.path = path
        self.console = console
        self.errors = 0  # tracebacks seen since the start
        self._file = self._open(path)
        self._file.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} start ---\n")

    @staticmethod
    def _open(path: Path) -> TextIO:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_name(path.name + OLD_SUFFIX))
        return open(path, "a", encoding=ENCODING, newline="\n", buffering=1)  # line buffered: a crash loses nothing

    def write(self, text: str) -> int:
        if TRACEBACK_MARK in text:
            self.errors += 1
        try:
            self._file.write(text)
        except (OSError, ValueError):  # a log that cannot be written must not make things worse
            pass
        if self.console is not None:
            try:
                self.console.write(text)
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self) -> None:
        for stream in (self._file, self.console):
            if stream is not None:
                try:
                    stream.flush()
                except (OSError, ValueError):
                    pass

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        self.flush()
        self._file.close()


def install(path: Path) -> ErrorLog | None:
    """Make `sys.stderr` an ErrorLog that writes to `path`. None (nothing changed) when the file cannot be opened."""
    try:
        log = ErrorLog(path, sys.stderr)
    except OSError:
        return None
    sys.stderr = log
    return log
