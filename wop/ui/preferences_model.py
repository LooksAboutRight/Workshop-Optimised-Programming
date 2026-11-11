"""The data behind File > Preferences (toolkit-free): the conventions with their defaults and the user's values.

The rows come from the table in core/conventions.py; the defaults come from the constants modules themselves, so the
window cannot drift from the code. Only values that differ from the default are written to the file. A change applies
after a restart: the model knows whether the file now differs from what the running program uses.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from pathlib import Path

from ..core.files import convention_overrides
from ..core.conventions import CHOICE, CONVENTIONS, MATERIAL, WHOLE_NON_NEGATIVE, WHOLE_POSITIVE, Convention, check_value, conventions_by_group, rule_text

TABLE_LINE_LIMIT = 6  # a fixed value longer than this many lines is shown with one item per line
TABLE_INDENT = "    "
FIXED_TEXT_HEADER = "# Fixed values: these cannot be changed in Preferences (tables, standards, internal tolerances)."


@dataclass(frozen=True)
class PreferenceRow:
    convention: Convention
    default: object
    value: object  # what the file will hold (the default when the user has not changed it)
    running: object  # what the running program uses

    @property
    def changed(self) -> bool:
        return self.value != self.default

    @property
    def needs_restart(self) -> bool:
        return self.value != self.running

    @property
    def rule_text(self) -> str:
        return rule_text(self.convention)


def value_text(value: object) -> str:
    """A value as it is shown in a box."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    return str(value)


class PreferencesModel:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or convention_overrides.overrides_path()
        self._modules = {module: importlib.import_module(module) for module in dict.fromkeys(c.module for c in CONVENTIONS)}
        self._defaults: dict[str, object] = {}
        self._running: dict[str, object] = {}
        for convention in CONVENTIONS:
            module = self._modules[convention.module]
            self._running[convention.name] = getattr(module, convention.name)
            self._defaults[convention.name] = module.REPLACED_DEFAULTS.get(convention.name, self._running[convention.name])
        self.problems: list[str] = []  # what was wrong in the file when it was read
        self._values: dict[str, object] = dict(self._defaults)
        self._read_file()

    def _read_file(self) -> None:
        known_before = len(convention_overrides.problems())
        data = convention_overrides.read_overrides(self.path)
        self.problems += convention_overrides.problems()[known_before:]  # a file that is not readable at all
        if data is None:
            return
        if not isinstance(data, dict):
            self.problems.append("the file must hold an object of name: value")
            return
        for convention in CONVENTIONS:
            if convention.name in data:
                error = check_value(convention, data[convention.name])
                if error:
                    self.problems.append(f"{convention.name}: {error} (the default is used)")
                else:
                    self._values[convention.name] = self._typed(convention, data[convention.name])
        known = {c.name for c in CONVENTIONS}
        self.problems += [f"{name}: not a convention (ignored, removed at the next save)" for name in data if name not in known]

    def _typed(self, convention: Convention, value: object) -> object:
        """Whole numbers stay whole where the constant is a whole number."""
        default = self._defaults[convention.name]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and float(value).is_integer():
            if isinstance(default, int) or convention.rule in (WHOLE_POSITIVE, WHOLE_NON_NEGATIVE, CHOICE):
                return int(value)
        return value

    # --- rows --------------------------------------------------------------------------------------

    def row(self, name: str) -> PreferenceRow:
        convention = next(c for c in CONVENTIONS if c.name == name)
        return PreferenceRow(convention, self._defaults[name], self._values[name], self._running[name])

    def groups(self) -> list[tuple[str, list[PreferenceRow]]]:
        return [(group, [self.row(c.name) for c in conventions]) for group, conventions in conventions_by_group()]

    # --- editing -----------------------------------------------------------------------------------

    def set_text(self, name: str, text: str) -> str | None:
        """Try the text typed in a box. Nothing when it was taken, otherwise what is wrong (the value is kept)."""
        convention = self.row(name).convention
        if convention.rule == MATERIAL:
            return self.set_value(name, text.strip())
        if convention.rule == CHOICE:
            for choice in convention.choices:  # the dropdown gives the text of a choice (a word or a number)
                if value_text(choice) == text.strip():
                    return self.set_value(name, choice)
        try:
            number = float(text.strip().replace(",", "."))
        except ValueError:
            return f"not a number; allowed: {rule_text(convention)}"
        return self.set_value(name, number)

    def set_value(self, name: str, value: object) -> str | None:
        convention = self.row(name).convention
        error = check_value(convention, value)
        if error:
            return error
        self._values[name] = self._typed(convention, value)
        return None

    def reset(self, name: str) -> None:
        self._values[name] = self._defaults[name]

    # --- file --------------------------------------------------------------------------------------

    def changed_values(self) -> dict[str, object]:
        """What the file holds: only the values that differ from the defaults, in the order of the table."""
        return {c.name: self._values[c.name] for c in CONVENTIONS if self._values[c.name] != self._defaults[c.name]}

    def needs_restart(self) -> bool:
        return any(self._values[c.name] != self._running[c.name] for c in CONVENTIONS)

    def save(self) -> None:
        """Write the file. Raises OSError."""
        convention_overrides.save_overrides(self.changed_values(), self.path)

    # --- the fixed constants -------------------------------------------------------------------------

    def fixed_text(self) -> str:
        """All constants below the marker as text (name = value, tables one item per line). Not editable."""
        lines: list[str] = [FIXED_TEXT_HEADER, ""]
        for module_name, module in self._modules.items():
            lines += [f"# {module_name}", ""]
            for name, value in convention_overrides.fixed_constants(module):
                lines += _constant_lines(name, value)
            lines.append("")
        return "\n".join(lines)


def _constant_lines(name: str, value: object) -> list[str]:
    if isinstance(value, (tuple, list)) and len(value) > TABLE_LINE_LIMIT:
        return [f"{name} ="] + [f"{TABLE_INDENT}{item!r}" for item in value]
    if isinstance(value, dict) and len(value) > 1:
        return [f"{name} ="] + [f"{TABLE_INDENT}{key!r}: {item!r}" for key, item in value.items()]
    return [f"{name} = {value!r}"]
