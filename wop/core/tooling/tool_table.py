"""Tool table entries (requirements T4 to T7).

Controller independent: offsets and sizes in mm. Reading and writing the
LinuxCNC tool.tbl file is done by the adapter. Words the adapter does not
understand are kept in unparsed_words and written back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..constants import MAX_TOOL_ORIENTATION


class ToolTableError(ValueError):
    """The tool table data is not usable."""


@dataclass(frozen=True)
class ToolTableEntry:
    number: int
    pocket: int
    x_offset_mm: float = 0
    z_offset_mm: float = 0
    diameter_mm: float = 0
    front_angle_deg: float = 0
    back_angle_deg: float = 0
    orientation: int = 0
    comment: str = ""
    unparsed_words: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.number < 0:
            raise ToolTableError("tool number must not be negative")
        if not 0 <= self.orientation <= MAX_TOOL_ORIENTATION:
            raise ToolTableError(
                f"tool {self.number}: orientation must be 0 to {MAX_TOOL_ORIENTATION}"
            )


@dataclass(frozen=True)
class ToolTable:
    entries: tuple[ToolTableEntry, ...] = ()

    def __post_init__(self) -> None:
        numbers = [entry.number for entry in self.entries]
        if len(set(numbers)) != len(numbers):
            raise ToolTableError("a tool number is used twice")

    def find(self, number: int) -> ToolTableEntry | None:
        for entry in self.entries:
            if entry.number == number:
                return entry
        return None

    def with_entry(self, entry: ToolTableEntry) -> ToolTable:
        """Replace the entry with the same number, or append a new one."""
        if self.find(entry.number) is None:
            return ToolTable(self.entries + (entry,))
        return ToolTable(
            tuple(entry if old.number == entry.number else old for old in self.entries)
        )

    def without(self, number: int) -> ToolTable:
        return ToolTable(tuple(e for e in self.entries if e.number != number))

    def renamed(self, number: int, comment: str) -> ToolTable:
        entry = self.find(number)
        if entry is None:
            raise ToolTableError(f"tool {number} does not exist")
        return self.with_entry(replace(entry, comment=comment))
