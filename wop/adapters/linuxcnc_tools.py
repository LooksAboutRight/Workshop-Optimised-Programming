"""LinuxCNC tool table (tool.tbl): read, write, backup, restore, apply (T4 to T7).

A line looks like:  T1 P1 X+0.1 Z+0.2 D+12.5 I+95 J+85 Q2 ;comment
Lengths in the file are in machine units; the core works in mm.
Words that are not understood are kept and written back unchanged.
Blank lines and lines holding only a comment are not kept when the file is
written again.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from wop.core.tooling.tool_table import ToolTable, ToolTableEntry, ToolTableError
from wop.core.program_model.units import UnitSystem, length_from_mm, length_to_mm

from . import linuxcnc_constants as names

_WORD = re.compile(r"^([A-Za-z])(.*)$")


class ToolTableBusy(RuntimeError):
    """The tool table cannot be changed while a program is running."""


def _number(text: str, line_number: int) -> float:
    try:
        return float(text)
    except ValueError:
        raise ToolTableError(f"line {line_number}: {text!r} is not a number") from None


def parse_tool_table(text: str, unit: UnitSystem = UnitSystem.METRIC) -> ToolTable:
    entries = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        body, _, comment = raw_line.partition(names.TOOL_TABLE_COMMENT_MARK)
        words = body.split()
        if not words:
            continue
        values: dict[str, float] = {}
        unparsed: list[str] = []
        for word in words:
            match = _WORD.match(word)
            if match is None:
                raise ToolTableError(f"line {line_number}: cannot read {word!r}")
            letter = match.group(1).upper()
            if letter in "TPXZDIJQ":
                values[letter] = _number(match.group(2), line_number)
            else:
                unparsed.append(word)
        if "T" not in values:
            raise ToolTableError(f"line {line_number}: no tool number (T)")
        number = int(values["T"])
        entries.append(
            ToolTableEntry(
                number=number,
                pocket=int(values.get("P", number)),
                x_offset_mm=length_to_mm(values.get("X", 0), unit),
                z_offset_mm=length_to_mm(values.get("Z", 0), unit),
                diameter_mm=length_to_mm(values.get("D", 0), unit),
                front_angle_deg=values.get("I", 0),
                back_angle_deg=values.get("J", 0),
                orientation=int(values.get("Q", 0)),
                comment=comment.strip(),
                unparsed_words=tuple(unparsed),
            )
        )
    return ToolTable(tuple(entries))


def format_tool_table(table: ToolTable, unit: UnitSystem = UnitSystem.METRIC) -> str:
    decimals = names.TOOL_TABLE_DECIMALS
    lines = []
    for entry in table.entries:
        words = [
            f"T{entry.number}",
            f"P{entry.pocket}",
            f"X{length_from_mm(entry.x_offset_mm, unit):+.{decimals}f}",
            f"Z{length_from_mm(entry.z_offset_mm, unit):+.{decimals}f}",
            f"D{length_from_mm(entry.diameter_mm, unit):+.{decimals}f}",
            f"I{entry.front_angle_deg:+.{decimals}f}",
            f"J{entry.back_angle_deg:+.{decimals}f}",
            f"Q{entry.orientation}",
            *entry.unparsed_words,
        ]
        line = " ".join(words)
        if entry.comment:
            line += f" {names.TOOL_TABLE_COMMENT_MARK}{entry.comment}"
        lines.append(line)
    return "\n".join(lines) + "\n" if lines else ""


def read_tool_table(path: Path, unit: UnitSystem = UnitSystem.METRIC) -> ToolTable:
    return parse_tool_table(Path(path).read_text(encoding="utf-8"), unit)


def write_tool_table(table: ToolTable, path: Path, unit: UnitSystem = UnitSystem.METRIC) -> None:
    Path(path).write_text(format_tool_table(table, unit), encoding="utf-8", newline="\n")


# --- backup and restore (T6) ---------------------------------------------------


def backup_tool_table(path: Path, now: datetime | None = None) -> Path:
    """Copy the file next to itself under a new name; an existing backup is never replaced."""
    path = Path(path)
    stamp = (now or datetime.now()).strftime(names.BACKUP_TIME_FORMAT)
    backup = path.with_name(path.name + names.BACKUP_SUFFIX + stamp)
    if backup.exists():
        raise ToolTableError(f"backup {backup.name} already exists")
    shutil.copy2(path, backup)
    return backup


def list_backups(path: Path) -> list[Path]:
    """Backups of this tool table, oldest first."""
    path = Path(path)
    return sorted(path.parent.glob(path.name + names.BACKUP_SUFFIX + "*"))


def restore_tool_table(backup: Path, path: Path) -> None:
    """Put a backup back; the result is byte-identical to the backup."""
    shutil.copyfile(backup, path)


def apply_program_tool_table(
    table: ToolTable,
    path: Path,
    unit: UnitSystem,
    is_program_running: Callable[[], bool],
    now: datetime | None = None,
) -> Path | None:
    """Write the program's tool table to the machine file after making a backup (T6, T7).

    Refuses (and writes nothing) while a program is running. Returns the backup
    path, or None if there was no file to back up.
    """
    if is_program_running():
        raise ToolTableBusy("a program is running: the tool table was not changed")
    backup = backup_tool_table(path, now) if Path(path).exists() else None
    write_tool_table(table, path, unit)
    return backup
