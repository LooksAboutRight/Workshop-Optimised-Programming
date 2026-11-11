"""Importer for LinuxCNC ini files (requirements M2, M8)."""

from __future__ import annotations

from pathlib import Path

from .linuxcnc_ini import IniError, read_machine_from_ini
from .machine_import import IMPORTERS, ImportFormatError, ImportResult, MachineImporter


@IMPORTERS.register
class LinuxCncIniImporter(MachineImporter):
    importer_id = "linuxcnc_ini"
    label = "LinuxCNC ini file"
    file_filter = "LinuxCNC ini (*.ini)"

    def read(self, path: Path) -> ImportResult:
        try:
            reading = read_machine_from_ini(path)
        except (IniError, OSError) as error:
            raise ImportFormatError(f"{Path(path).name} is not a LinuxCNC ini file: {error}") from error
        return ImportResult(reading.machine, reading.found, reading.notes)
