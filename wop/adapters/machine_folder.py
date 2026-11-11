"""The machines folder (LIB3): one file per machine, next to the settings file.

A file is a machine file as `machine_files` writes it (so it can be shared and imported), with two extra entries the
application keeps in it: the touched fields of the machine and the libraries it last used.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..core.constants import MACHINES_FOLDER_NAME
from ..core.lathe.machine import MachineDef, MachineError
from ..core.files.machine_io import machine_from_dict, machine_to_dict
from .library_files import LibraryFileError, clean_name
from .machine_files import ENCODING, JSON_INDENT, MACHINE_FILE_SUFFIX

TOUCHED_KEY = "touched"
LIBRARIES_KEY = "libraries"


def machines_folder(settings_path: Path) -> Path:
    return settings_path.parent / MACHINES_FOLDER_NAME


def machine_file_path(settings_path: Path, name: str) -> Path:
    return machines_folder(settings_path) / (clean_name(name) + MACHINE_FILE_SUFFIX)


def read_machine_folder(settings_path: Path) -> tuple[list[tuple[MachineDef, tuple[str, ...], tuple[tuple[str, str], ...]]], list[str]]:
    """The machines in the folder as (machine, touched fields, libraries), sorted by file name, and a message for every
    file that could not be used (it is left where it is)."""
    folder = machines_folder(settings_path)
    found, notes = [], []
    for path in sorted(folder.glob("*" + MACHINE_FILE_SUFFIX)) if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding=ENCODING))
            if not isinstance(data, dict):
                raise MachineError("not a machine file")
            machine = machine_from_dict(data)
            touched = data.get(TOUCHED_KEY, [])
            libraries = data.get(LIBRARIES_KEY, {})
            if not (isinstance(touched, list) and all(isinstance(t, str) for t in touched)):
                raise MachineError("wrong touched list")
            if not (isinstance(libraries, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in libraries.items())):
                raise MachineError("wrong libraries")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, MachineError, ValueError, KeyError, TypeError) as error:
            notes.append(f"The machine file {path.name} could not be used ({error}).")
            continue
        found.append((machine, tuple(touched), tuple(sorted(libraries.items()))))
    return found, notes


def write_machine_file(
    settings_path: Path, machine: MachineDef, touched: tuple[str, ...], libraries: tuple[tuple[str, str], ...]
) -> None:
    """Write one machine in one step; the folder is created if it is missing."""
    path = machine_file_path(settings_path, machine.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = machine_to_dict(machine)
    if touched:
        data[TOUCHED_KEY] = list(touched)
    if libraries:
        data[LIBRARIES_KEY] = dict(libraries)
    write_text_atomically(path, json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n", ENCODING)


def delete_machine_file(settings_path: Path, name: str) -> None:
    try:
        machine_file_path(settings_path, name).unlink()
    except (FileNotFoundError, LibraryFileError):
        pass
