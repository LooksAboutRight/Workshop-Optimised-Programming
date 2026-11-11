"""Read and write the application settings file in the user's app folder (requirement U5)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..core.files.user_folder import user_folder
from ..core.files.app_settings import AppSettings, SettingsError, settings_from_dict, settings_to_dict

SETTINGS_FILE_NAME = "settings.json"
DAMAGED_SUFFIX = ".bad"
ENCODING = "utf-8"
JSON_INDENT = 2


def default_settings_path() -> Path:
    """The per-user place for settings (see core/user_folder.py)."""
    return user_folder() / SETTINGS_FILE_NAME


def save_app_settings(path: Path, settings: AppSettings) -> None:
    """Write the file in one step; the folder is created if it is missing."""
    write_text_atomically(path, json.dumps(settings_to_dict(settings), indent=JSON_INDENT, ensure_ascii=False) + "\n", ENCODING)


def load_app_settings(path: Path) -> tuple[AppSettings, str]:
    """The settings and a message for the user ("" when all is well).

    No file: defaults, no message. A damaged file: defaults and a message; the file is kept
    under another name so that nothing the user typed is lost when the settings are saved again.
    """
    if not path.exists():
        return AppSettings(), ""
    try:
        data = json.loads(path.read_text(encoding=ENCODING))
        if not isinstance(data, dict):
            raise SettingsError("the file does not hold settings")
        return settings_from_dict(data), ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SettingsError) as error:
        kept = path.with_name(path.name + DAMAGED_SUFFIX)
        try:
            os.replace(path, kept)
            where = f"the damaged file was kept as {kept.name}"
        except OSError:
            where = "the damaged file could not be set aside"
        return AppSettings(), f"The settings file could not be used ({error}); defaults are used, {where}."
