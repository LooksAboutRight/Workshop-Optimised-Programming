"""Where the per-user files of the application live (settings, machines, libraries, conventions)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER_NAME = "WOP"
PORTABLE_FOLDER_NAME = "user_data"
PROJECT_ROOT_LEVELS = 2  # wop/core/files/user_folder.py -> the project folder


def program_folder() -> Path:
    """The folder of the program: next to the .exe when built, otherwise the project folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[PROJECT_ROOT_LEVELS]


def user_folder(program_dir: Path | None = None) -> Path:
    """Where settings, machines, libraries and conventions live.

    Portable: a folder `user_data` next to the program (the built .exe, or the project folder) is used when it
    exists and can be written to. Otherwise %APPDATA%\\WOP on Windows, Application Support/WOP on macOS,
    ~/.config/WOP elsewhere.
    """
    portable = (program_dir or program_folder()) / PORTABLE_FOLDER_NAME
    if portable.is_dir() and os.access(portable, os.W_OK):
        return portable
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / APP_FOLDER_NAME
