"""Read and write machine definition files."""

from __future__ import annotations

import json
from pathlib import Path

from ..core.files.atomic_file import write_text_atomically
from ..core.lathe.machine import MachineDef, MachineError
from ..core.files.machine_io import machine_from_dict, machine_to_dict

MACHINE_FILE_SUFFIX = ".machine.json"
ENCODING = "utf-8"
JSON_INDENT = 2


def save_machine(path: Path, machine: MachineDef) -> None:
    write_text_atomically(path, json.dumps(machine_to_dict(machine), indent=JSON_INDENT, ensure_ascii=False) + "\n", ENCODING)


def load_machine(path: Path) -> MachineDef:
    try:
        data = json.loads(path.read_text(encoding=ENCODING))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MachineError(f"cannot read {path.name}: {error}") from error
    if not isinstance(data, dict):
        raise MachineError(f"{path.name} is not a machine file")
    return machine_from_dict(data)
