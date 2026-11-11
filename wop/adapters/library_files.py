"""Library files (LIB1): one JSON file per library, in one folder per kind next to the settings file."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..core.constants import (
    EXAMPLE_LIBRARY_NAME,
    LIBRARIES_FOLDER_NAME,
    LIBRARY_FILE_SUFFIX,
    LIBRARY_NAME_FORBIDDEN_CHARS,
)

ENCODING = "utf-8"
JSON_INDENT = 2


class LibraryFileError(ValueError):
    """A library file is missing, damaged or of the wrong kind."""


def library_folder(settings_path: Path, kind: str) -> Path:
    return settings_path.parent / LIBRARIES_FOLDER_NAME / kind


def library_file(settings_path: Path, kind: str, name: str) -> Path:
    return library_folder(settings_path, kind) / (clean_name(name) + LIBRARY_FILE_SUFFIX)


def clean_name(name: str) -> str:
    """A name that is a safe file name: the characters a file system refuses become '_'."""
    text = "".join("_" if c in LIBRARY_NAME_FORBIDDEN_CHARS or ord(c) < 32 else c for c in name).strip().strip(".")
    if not text:
        raise LibraryFileError("a library needs a name")
    return text


def library_names(settings_path: Path, kind: str) -> tuple[str, ...]:
    """The Example, then the libraries found in the folder (sorted); the Example file name is not used twice."""
    folder = library_folder(settings_path, kind)
    found = sorted(p.stem for p in folder.glob("*" + LIBRARY_FILE_SUFFIX)) if folder.is_dir() else []
    return (EXAMPLE_LIBRARY_NAME,) + tuple(n for n in found if n.casefold() != EXAMPLE_LIBRARY_NAME.casefold())


def library_exists(settings_path: Path, kind: str, name: str) -> bool:
    return any(n.casefold() == clean_name(name).casefold() for n in library_names(settings_path, kind))


def unique_library_name(settings_path: Path, kind: str, wanted: str) -> str:
    name, number = clean_name(wanted), 2
    while library_exists(settings_path, kind, name):
        name, number = f"{clean_name(wanted)} {number}", number + 1
    return name


def load_library_data(path: Path, kind: str) -> dict:
    """The data of a library file. Raises LibraryFileError."""
    try:
        data = json.loads(path.read_text(encoding=ENCODING))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LibraryFileError(f"{path.name}: {error}") from error
    if not isinstance(data, dict) or data.get("library") != kind:
        raise LibraryFileError(f"{path.name} is not a {kind} library")
    return data


def read_library(settings_path: Path, kind: str, name: str) -> dict:
    path = library_file(settings_path, kind, name)
    if not path.exists():
        raise LibraryFileError(f"the library {name!r} is not there")
    return load_library_data(path, kind)


def write_library(settings_path: Path, kind: str, name: str, data: dict) -> None:
    """Write the file in one step; the folder is created if it is missing."""
    path = library_file(settings_path, kind, name)
    write_text_atomically(path, json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n", ENCODING)


def delete_library_file(settings_path: Path, kind: str, name: str) -> None:
    library_file(settings_path, kind, name).unlink()


def rename_library_file(settings_path: Path, kind: str, name: str, new_name: str) -> None:
    os.rename(library_file(settings_path, kind, name), library_file(settings_path, kind, new_name))


def import_library_file(settings_path: Path, kind: str, source: Path) -> str:
    """Copy a library file (somebody else's) into the folder under a free name. Returns that name."""
    load_library_data(source, kind)  # refuses a file of another kind or a damaged one
    name = unique_library_name(settings_path, kind, source.stem)
    target = library_file(settings_path, kind, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return name
