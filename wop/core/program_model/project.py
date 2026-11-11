"""A project: the program plus the settings that belong to the file (requirement B4).

The postprocessor and the default tool change position belong to the machine."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import DEFAULT_WORK_OFFSET
from ..lathe.machine import MachineDef
from .program import Program
from .touched import Touched
from .units import XInputMode


@dataclass(frozen=True)
class ProjectSettings:
    title: str = "WOP program"
    x_mode: XInputMode = XInputMode.DIAMETER  # G-code mode of the program (B11)
    work_offset: str = DEFAULT_WORK_OFFSET  # the work offset (G54 ...) the header of the program calls


@dataclass(frozen=True)
class Project:
    program: Program
    settings: ProjectSettings = ProjectSettings()
    machine: MachineDef | None = None  # a copy of the machine the program is made for (M9)
    touched: Touched = None  # fields the user has edited (U6); None: not recorded, all count as touched
