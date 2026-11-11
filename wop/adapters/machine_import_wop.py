"""Importer for the own machine file (requirement M8)."""

from __future__ import annotations

from pathlib import Path

from ..core.lathe.machine import MachineError
from .machine_files import MACHINE_FILE_SUFFIX, load_machine
from .machine_import import IMPORTERS, ImportFormatError, ImportResult, MachineImporter


@IMPORTERS.register
class WopMachineImporter(MachineImporter):
    importer_id = "wop_machine"
    label = "WOP machine file"
    file_filter = f"WOP machine (*{MACHINE_FILE_SUFFIX} *.json)"

    def read(self, path: Path) -> ImportResult:
        try:
            machine = load_machine(Path(path))
        except MachineError as error:
            raise ImportFormatError(f"{Path(path).name} is not a WOP machine file: {error}") from error
        # The file always holds name, units, X mode and capabilities; the rest counts as found when it is set.
        found = {"name", "unit_system", "default_x_mode", "capabilities"}
        optional = ("axes", "min_rpm", "max_rpm", "spindle_power_kw", "max_velocity_x_mm_min", "max_velocity_z_mm_min", "change_radius_mm", "change_z_mm", "machine_change_radius_mm", "machine_change_z_mm")
        found.update(name for name in optional if getattr(machine, name) not in (None, (), ""))
        return ImportResult(machine, frozenset(found))
