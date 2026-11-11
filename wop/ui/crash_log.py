"""A black-box recorder for the crashes that leave no message (toolkit-free).

A crash inside a library (Qt, OpenGL, a compiled module) ends the program at once and Python prints nothing. `faulthandler` writes the
Python stack of every thread to a file when the process receives a fatal signal or Windows exception (access violation, stack overflow,
abort). There is no watchdog for a freeze on purpose: it dumped the stacks from a second thread while the other threads ran, and on a slow
computer that dump itself ended the program with a segmentation fault.
"""

from __future__ import annotations

import faulthandler
from datetime import datetime
from pathlib import Path
from typing import TextIO

CRASH_FILE_NAME = "crash.log"
MAX_CRASH_BYTES = 500_000  # a bigger file is kept as crash.log.old and a new one is started
OLD_SUFFIX = ".old"
ENCODING = "utf-8"


class CrashLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_CRASH_BYTES:
            path.replace(path.with_name(path.name + OLD_SUFFIX))
        self._file: TextIO = open(path, "a", encoding=ENCODING, newline="\n", buffering=1)  # faulthandler needs a real file that stays open
        self._file.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} start ---\n")
        faulthandler.enable(file=self._file, all_threads=True)

    def stop(self) -> None:
        """The program ends in the normal way: a marker, so a log without it shows a crash."""
        try:
            self._file.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} end ---\n")
            self._file.flush()
        except (OSError, ValueError):
            pass


def install(path: Path) -> CrashLog | None:
    """Start recording to `path`. None (nothing changed) when the file cannot be opened."""
    try:
        return CrashLog(path)
    except OSError:
        return None
