"""The user's own values for the conventions (see conventions.py): a file `conventions.json` in the user folder.

The file holds a plain object, name -> value, for example {"GROOVE_ONE_SIDED_CUT_MM": 1.5}. It holds only the values
that differ from the defaults. It is created empty ({}) by `ensure_file` when it does not exist, and written by
File > Preferences. It is read once, when the constants load, so a change needs a restart. The environment variable
WOP_CONVENTIONS names another file (tests, trying values out). A name that is not in the table, or a value the rule of
its entry does not allow, is ignored and reported in `problems()`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType

from .atomic_file import write_text_atomically
from ..conventions import CONVENTIONS, MARKER, check_value
from .user_folder import user_folder

FILE_NAME = "conventions.json"
ENVIRONMENT_VARIABLE = "WOP_CONVENTIONS"
ENCODING = "utf-8"
JSON_INDENT = 2
_problems: list[str] = []


def overrides_path() -> Path:
    named = os.environ.get(ENVIRONMENT_VARIABLE)
    return Path(named) if named else user_folder() / FILE_NAME


def problems() -> list[str]:
    """What was wrong in the file (empty when all is well)."""
    return list(_problems)


def _report(text: str) -> None:
    if text not in _problems:  # the two constants modules read the same file
        _problems.append(text)


def read_overrides(path: Path | None = None) -> object:
    """The decoded file; nothing (None) when there is no file or it cannot be read (the reason goes to `problems`)."""
    path = path or overrides_path()
    try:
        return json.loads(path.read_text(encoding=ENCODING))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        _problems.append(f"{path}: {error}")
        return None


def ensure_file(path: Path | None = None) -> bool:
    """Create the file empty when there is none. True when the file exists afterwards."""
    path = path or overrides_path()
    if path.exists():
        return True
    try:
        write_text_atomically(path, "{}", ENCODING)
        return True
    except OSError as error:
        _problems.append(f"{path}: cannot create the file: {error}")
        return False


def save_overrides(values: dict, path: Path | None = None) -> None:
    """Write the file with these values (name -> value); the old content is replaced. Raises OSError."""
    write_text_atomically(path or overrides_path(), json.dumps(values, indent=JSON_INDENT), ENCODING)


def _is_constant_name(name: str) -> bool:
    return name.isupper() and not name.startswith("_")


def editable_names(namespace: dict) -> list[str]:
    """The constants above the marker of a constants module (its globals, in the order of the file)."""
    names: list[str] = []
    for name, value in namespace.items():
        if name == MARKER:
            break
        if _is_constant_name(name) and isinstance(value, (bool, int, float, str)):
            names.append(name)
    return names


def fixed_constants(module: ModuleType) -> list[tuple[str, object]]:
    """The constants below the marker (name, value), in the order of the file: these are not editable."""
    namespace = vars(module)
    if MARKER not in namespace:
        return []
    names = list(namespace)
    after = names[names.index(MARKER) + 1:]
    return [(name, namespace[name]) for name in after if _is_constant_name(name) and name != "REPLACED_DEFAULTS"]


def valid_overrides(data: object, module: str, namespace: dict, report: bool = True) -> dict:
    """The entries of `data` (name -> value) that belong to `module` and are allowed; wrong ones are reported."""
    if not isinstance(data, dict):
        if report:
            _report("conventions file: the top level must be an object of name: value")
        return {}
    mine = {c.name: c for c in CONVENTIONS if c.module == module}
    valid: dict = {}
    for name, value in data.items():
        if name in mine:
            error = check_value(mine[name], value) if name in namespace else "not found in the constants"
            if error is None:
                valid[name] = value
            elif report:
                _report(f"{name}: {value!r}: {error}")
        elif report and not any(c.name == name for c in CONVENTIONS):
            _report(f"{name}: not a convention (see File > Preferences)")
    return valid


def apply_overrides(namespace: dict, module: str, path: Path | None = None) -> dict:
    """Replace the values of `namespace` (the globals of the constants module `module`) by those of the file.

    Returns name -> the default that was replaced.
    """
    data = read_overrides(path)
    replaced: dict = dict()
    if data is None:
        return replaced
    for name, value in valid_overrides(data, module, namespace).items():
        replaced[name] = namespace[name]
        keeps_whole = isinstance(namespace[name], int) and float(value).is_integer()
        namespace[name] = type(namespace[name])(value) if keeps_whole else value
    return replaced
