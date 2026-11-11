"""Importers of machine definitions, one per file format (requirement M8).

An importer is one file in this folder: a class that says its id, its label and the file types it
reads, and a `read` method that returns what it found and what it did not find. It is registered
in `IMPORTERS`; nothing else changes when a format is added (Mach3 and others later). The user
says which format a file has; the importer only checks that the file is of that kind.
File format knowledge stays in the adapters, never in core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..core.lathe.machine import MachineDef


class ImportFormatError(ValueError):
    """The file is not of the kind the user chose (the message says so)."""


@dataclass(frozen=True)
class ImportResult:
    machine: MachineDef  # values the file did not give are None or the defaults
    found: frozenset[str]  # names of the MachineDef fields the file really gave
    notes: tuple[str, ...] = ()  # what was missing or assumed, for the user


class MachineImporter(ABC):
    importer_id: str = ""  # stable, never shown
    label: str = ""  # shown in the list of file types
    file_filter: str = ""  # for the file dialog, for example "LinuxCNC ini (*.ini)"

    @abstractmethod
    def read(self, path: Path) -> ImportResult:
        """Read the file. Raises ImportFormatError if it is not of this importer's kind."""


class ImporterRegistry:
    def __init__(self) -> None:
        self._importers: dict[str, MachineImporter] = {}

    def register(self, importer_class: type[MachineImporter]) -> type[MachineImporter]:
        importer = importer_class()
        if not importer.importer_id or not importer.label:
            raise ValueError("an importer needs an id and a label")
        if importer.importer_id in self._importers:
            raise ValueError(f"importer {importer.importer_id!r} is already registered")
        self._importers[importer.importer_id] = importer
        return importer_class

    def get(self, importer_id: str) -> MachineImporter:
        if importer_id not in self._importers:
            raise ValueError(f"unknown importer {importer_id!r}")
        return self._importers[importer_id]

    def all(self) -> list[MachineImporter]:
        return list(self._importers.values())


IMPORTERS = ImporterRegistry()
