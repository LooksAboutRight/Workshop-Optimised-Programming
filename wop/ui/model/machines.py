"""The machines of the user, the machine of the project and the machine files."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

from ...adapters.app_settings_files import save_app_settings
from ...adapters.machine_files import save_machine
from ...adapters.machine_folder import read_machine_folder, write_machine_file
from ...adapters import machine_import_linuxcnc, machine_import_wop  # noqa: F401  (they register the importers in IMPORTERS)
from ...adapters.machine_import import IMPORTERS, ImportFormatError
from ...core.files.app_settings import AppSettings
from ...core.lathe.machine import MachineDef
from ...core.blocks.machine_function import fixed_kind, function_label, FunctionValue
from ...core.constants import FIXED_FUNCTION_NAMES
from ...core.program_model.project import Project
from ...core.program_model.touched import forget_owner, is_touched, mark_touched, mark_untouched, rename_owner
from ...post.base import function_feature
from ...post.variables import check_values, VariableError
from ..block_forms import FunctionChoice, FunctionVariable
from ..machine_form import DEFAULT_MACHINE_NAME, machine_from_form, MachineForm, touched_form_fields
from .helpers import ModelError, new_project


_VALUE_FIELD = {"float": "number", "int": "number", "uint": "number", "bool": "flag", "string": "text"}


class MachinesMixin:
    """The machines of the user, the machine of the project and the machine files. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def available_machine_functions(self) -> tuple[FunctionChoice, ...]:
        """The functions the Machine function block offers (B13) from the postprocessor: the fixed ones for which its code table has a
        code, then its own custom functions."""
        info = self.post_library.choose(self.postprocessor_id)[0].info
        offered = [
            FunctionChoice(name, function_label(name))
            for name in FIXED_FUNCTION_NAMES
            if function_feature(fixed_kind(name)) in info.supported
        ]
        for name, function in info.functions.items():
            variables = tuple(
                FunctionVariable(v.name, v.label, v.type, v.minimum, v.maximum, v.unit) for v in function.variables
            )
            offered.append(FunctionChoice(name, function_label(name), function.description, variables))
        return tuple(offered)

    def function_problem(self, block) -> str:
        """Why a Machine function block will be left out of the output with the current postprocessor (empty: it will not)."""
        function = getattr(block, "function", None)
        if function is None or not hasattr(block, "values"):
            return ""
        info = self.post_library.choose(self.postprocessor_id)[0].info
        if function in FIXED_FUNCTION_NAMES:
            return "" if function_feature(fixed_kind(function)) in info.supported else f"the post has no {function_label(function)}"
        definition = info.functions.get(function)
        if definition is None:
            return f"the post has no function {function_label(function)}"
        try:
            check_values(definition.variables, {item.name: item.value for item in block.values})
        except VariableError as error:
            return error.message
        return ""

    def function_defaults(self, function: str) -> tuple[FunctionValue, ...]:
        """The values a Machine function block starts with when it gets this function: the default of each variable."""
        definition = self.post_library.choose(self.postprocessor_id)[0].info.functions.get(function)
        if definition is None:
            return ()
        values = ()
        for variable in definition.variables:
            values += (FunctionValue(variable.name, **{_VALUE_FIELD[variable.type]: variable.default}),)
        return values

    @property
    def machine(self) -> MachineDef | None:
        """The machine of the project: a copy, so the project opens on a PC that lacks the machine (M9)."""
        return self.project.machine

    def set_machine(self, machine: MachineDef | None, dirty: bool = True) -> None:
        """Set (or clear) the machine of the project; the program is checked against it."""
        self.project = replace(self.project, machine=machine)
        self._follow_the_machine()
        self._changed(dirty=dirty)

    @property
    def machines(self) -> tuple[MachineDef, ...]:
        return self.app_settings.machines

    @property
    def default_machine(self) -> str | None:
        return self.app_settings.default_machine

    def find_machine(self, name: str) -> MachineDef | None:
        return next((m for m in self.machines if m.name == name), None)

    def machine_owner(self, name: str) -> str:
        return f"machine:{name}"

    def is_machine_field_touched(self, name: str, field: str) -> bool:
        return is_touched(self.app_settings.machine_touched, self.machine_owner(name), (field,))

    def set_machine_field_touched(self, name: str, field: str, touched: bool = True) -> None:
        mark = mark_touched if touched else mark_untouched
        keys = mark(self.app_settings.machine_touched, self.machine_owner(name), (field,))
        if keys != self.app_settings.machine_touched:
            self._set_app_settings(replace(self.app_settings, machine_touched=keys))

    def _sync_project_machine(self) -> bool:
        """The machine of the project is the entry of the machine list with the same name, when the list has one.

        The user sees that entry (Setup, the machine dialog, its postprocessor), so it is the one that must be used; the
        copy in the project only serves when the list has no such machine (a project opened on another PC). True when
        the copy had to be replaced; the user is told (`take_notice`)."""
        machine = self.project.machine
        listed = None if machine is None else self.find_machine(machine.name)
        if machine is None or listed is None or listed == machine:
            return False
        parts = []
        for item in fields(MachineDef):
            old, new = getattr(machine, item.name), getattr(listed, item.name)
            if old != new:
                parts.append(f"{item.name} {old} -> {new}" if item.name == "postprocessor" else item.name)
        self.project = replace(self.project, machine=listed)
        self._notices.append(
            f"Machine {machine.name!r}: the project had an older copy than your machine list, so the entry of your list is used "
            f"({', '.join(parts)}). Save the project to keep it."
        )
        self._follow_the_machine()
        return True

    def _use_default_machine(self) -> bool:
        """A project without a machine gets the default machine of the user's list (the user is told). True when it was set."""
        default = self.find_machine(self.default_machine) if self.default_machine else None
        if self.project.machine is not None or default is None:
            return False
        self.project = replace(self.project, machine=default)
        self._notices.append(f"The project had no machine, so the default machine {default.name!r} is used. Save the project to keep it.")
        self._follow_the_machine()
        return True

    def take_notice(self) -> str:
        """What the user should be told since the last call (empty: nothing); the notices are cleared."""
        text, self._notices = " ".join(self._notices), []
        return text

    def _new_project(self) -> Project:
        default = self.find_machine(self.default_machine) if self.default_machine else None
        return self._with_default_toolbox(replace(new_project(), machine=default))

    def use_machine(self, name: str | None) -> None:
        """Make a machine of the list the machine of the project (a copy of it); None: no machine."""
        if name is None:
            self.set_machine(None)
            return
        machine = self.find_machine(name)
        if machine is None:
            raise ModelError(f"there is no machine {name!r} in the list")
        self.set_machine(machine)
        if self._apply_machine_libraries(name):  # the machine brings the libraries it last used
            self._library_changed()

    def save_machine(self, machine: MachineDef, old_name: str | None = None) -> None:
        """Add a machine to the list, or replace the one called `old_name` (also when it is renamed).

        The project's copy follows when the project uses that machine.
        """
        previous = old_name if old_name is not None else machine.name
        clash = self.find_machine(machine.name)
        if clash is not None and machine.name != previous:
            raise ModelError(f"there is already a machine called {machine.name!r}")
        listed = [machine if m.name == previous else m for m in self.machines]
        if self.find_machine(previous) is None:
            listed.append(machine)
        settings = replace(self.app_settings, machines=tuple(listed))
        if machine.name != previous:
            keys = rename_owner(settings.machine_touched, self.machine_owner(previous), self.machine_owner(machine.name))
            default = machine.name if settings.default_machine == previous else settings.default_machine
            settings = replace(settings, machine_touched=keys, default_machine=default)
        self._set_app_settings(settings)
        if self.project.machine is not None and self.project.machine.name == previous:
            self.set_machine(machine)
        else:
            self._changed(dirty=False)

    def delete_machine(self, name: str) -> None:
        """Remove a machine from the list. A project that uses it keeps its copy."""
        if self.find_machine(name) is None:
            raise ModelError(f"there is no machine {name!r} in the list")
        settings = replace(
            self.app_settings,
            machines=tuple(m for m in self.machines if m.name != name),
            default_machine=None if self.default_machine == name else self.default_machine,
            machine_touched=forget_owner(self.app_settings.machine_touched, self.machine_owner(name)),
        )
        self._set_app_settings(settings)
        self._changed(dirty=False)

    def set_default_machine(self, name: str | None) -> None:
        """The machine a new project starts with (loaded at startup); None: none."""
        if name is not None and self.find_machine(name) is None:
            raise ModelError(f"there is no machine {name!r} in the list")
        self._set_app_settings(replace(self.app_settings, default_machine=name))
        self._changed(dirty=False)

    def unique_machine_name(self, wanted: str) -> str:
        names = {m.name.casefold() for m in self.machines}
        name, number = wanted, 2
        while name.casefold() in names:
            name, number = f"{wanted} {number}", number + 1
        return name

    def new_machine(self) -> str:
        """Add an empty machine to the list (all values not given yet). Returns its name."""
        name = self.unique_machine_name(DEFAULT_MACHINE_NAME)
        self.save_machine(machine_from_form(MachineForm(name=name)))
        return name

    def add_project_machine_to_list(self) -> str:
        """Put the project's own copy of its machine in the list (a project opened on another PC)."""
        machine = self.project.machine
        if machine is None:
            raise ModelError("the project has no machine")
        name = self.unique_machine_name(machine.name)
        self.save_machine(replace(machine, name=name))
        return name

    def importer_choices(self) -> list[tuple[str, str, str]]:
        """(id, label, file filter) of the machine file formats the user can import."""
        return [(i.importer_id, i.label, i.file_filter) for i in IMPORTERS.all()]

    def import_machine(self, importer_id: str, path: Path) -> tuple[str, list[str]]:
        """Read a machine file of the format the user chose into a new list entry.

        Returns its name and the notes for the user: what was assumed and what is still missing.
        The values the file gave count as touched; the others stay untouched (U6).
        """
        try:
            result = IMPORTERS.get(importer_id).read(path)
        except (ImportFormatError, ValueError) as error:
            raise ModelError(str(error)) from error
        name = self.unique_machine_name(result.machine.name)
        machine = replace(result.machine, name=name)
        self.save_machine(machine)
        for field in touched_form_fields(result.found, machine):
            self.set_machine_field_touched(name, field)
        notes = list(result.notes)
        missing = machine.missing_values()
        if missing:
            notes.append("still to enter: " + ", ".join(missing))
        return name, notes

    def export_machine(self, name: str, path: Path) -> None:
        """Write a machine of the list to a WOP machine file."""
        machine = self.find_machine(name)
        if machine is None:
            raise ModelError(f"there is no machine {name!r} in the list")
        try:
            save_machine(path, machine)
        except OSError as error:
            raise ModelError(f"cannot write {path.name}: {error}") from error

    def _machine_records(self, settings: AppSettings) -> dict:
        """What each machine file holds: machine, touched fields (the key without its owner) and libraries."""
        records = {}
        for machine in settings.machines:
            prefix = self.machine_owner(machine.name) + "/"
            touched = tuple(sorted(k[len(prefix):] for k in settings.machine_touched if k.startswith(prefix)))
            records[machine.name] = (machine, touched, dict(settings.machine_libraries).get(machine.name, ()))
        return records

    def _load_machines(self) -> None:
        """Read the machines from their folder (at start). Machines an old settings file held itself move into files.
        A default machine that is gone gives way to the first machine there is."""
        if self.settings_path is None:
            return
        settings = self.app_settings
        files, notes = read_machine_folder(self.settings_path)
        self._saved_default = settings.default_machine
        machines = [machine for machine, _touched, _libraries in files]
        names = {machine.name.casefold() for machine in machines}
        keys, libraries = [], []
        for machine, touched, own_libraries in files:
            keys += [self.machine_owner(machine.name) + "/" + field for field in touched]
            if own_libraries:
                libraries.append((machine.name, own_libraries))
        moved = [machine for machine in settings.machines if machine.name.casefold() not in names]
        for machine in moved:  # from an old settings file
            prefix = self.machine_owner(machine.name) + "/"
            keys += [k for k in settings.machine_touched if k.startswith(prefix)]
        machines += moved
        default = settings.default_machine
        if default is None or default not in {machine.name for machine in machines}:
            default = machines[0].name if machines else None
        settings = replace(
            settings, machines=tuple(machines), machine_touched=tuple(sorted(keys)),
            machine_libraries=tuple(sorted(libraries)), default_machine=default,
        )
        records = self._machine_records(settings)
        self.app_settings = settings
        if notes:
            self.settings_message = " ".join(filter(None, [self.settings_message] + notes))
        try:
            for machine in moved:
                write_machine_file(self.settings_path, *records[machine.name])
            if moved or default != self._saved_default:
                save_app_settings(self.settings_path, settings)
        except OSError as error:
            self.settings_message = f"The machines could not be moved to files ({error})."
