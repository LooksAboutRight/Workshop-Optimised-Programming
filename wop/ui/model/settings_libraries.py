"""Materials, the libraries, the settings file and files that change while the program runs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ...adapters.app_settings_files import load_app_settings, save_app_settings
from ...adapters.library_files import clean_name, delete_library_file, import_library_file, library_file, library_folder, library_names as library_file_names, LibraryFileError, read_library, rename_library_file, unique_library_name, write_library
from ...adapters.machine_folder import delete_machine_file, write_machine_file
from ...core.files.app_settings import AppSettings, SettingsError
from ...core.constants import EXAMPLE_LIBRARY_NAME, LIBRARIES_FOLDER_NAME, LIBRARY_FILE_SUFFIX, MACHINES_FOLDER_NAME, USER_LIBRARY_NAME
from ...core.files.libraries import active_library, content_of, content_to_dict, has_content, is_example, LIBRARY_KINDS, library_label, with_active_library, with_content_from_dict, with_example_content
from ...core.material import builtin_materials, Material, MaterialError, MaterialLibrary
from .helpers import EMPTY_CONTENT, ModelError


class SettingsMixin:
    """Materials, the libraries, the settings file and files that change while the program runs. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    @property
    def materials(self) -> MaterialLibrary:
        return self.app_settings.materials

    def add_material(self, name: str, specific_cutting_force: float | None) -> str:
        """Add a material to the user list (saved with the settings). Returns the name as stored."""
        try:
            material = Material(name.strip(), specific_cutting_force)
        except MaterialError as error:
            raise ModelError(str(error)) from error
        self._set_app_settings(replace(self.app_settings, materials=self.materials.with_material(material)))
        self._changed(dirty=False)  # the form lists change; the program does not
        return material.name

    def material_marks(self, name: str) -> str:
        """Short note for the list of materials: built-in, changed built-in or the user's own."""
        user = self.materials.is_user_defined(name)
        builtin = any(m.name.casefold() == name.casefold() for m in builtin_materials())
        if builtin and user:
            return "built-in, changed"
        return "built-in" if builtin else ""

    def unique_material_name(self, wanted: str) -> str:
        name, number = wanted, 2
        while self.materials.find(name) is not None:
            name, number = f"{wanted} {number}", number + 1
        return name

    def save_material(self, old_name: str | None, name: str, specific_cutting_force: float | None) -> str:
        """Change a material, or add it when `old_name` is None. Returns the name as stored.

        Changing a built-in material keeps the change as the user's version of it (the built-in one
        comes back when that is deleted). Renaming a built-in one makes a new material. The raw part
        follows when it uses the renamed material.
        """
        try:
            material = Material(name.strip(), specific_cutting_force)
        except MaterialError as error:
            raise ModelError(str(error)) from error
        library = self.materials
        renamed = old_name is not None and old_name.casefold() != material.name.casefold()
        if (old_name is None or renamed) and library.find(material.name) is not None:
            raise ModelError(f"there is already a material called {material.name!r}")
        if renamed:
            library = library.without(old_name)
        self._set_app_settings(replace(self.app_settings, materials=library.with_material(material)))
        raw = self.program.raw_part
        if renamed and raw.material.casefold() == old_name.casefold():
            self.set_raw_part(replace(raw, material=material.name))
        else:
            self._changed(dirty=False)
        return material.name

    def delete_material(self, name: str) -> str:
        """Delete a material of the user, or bring a changed built-in one back. Returns what happened."""
        if not self.materials.is_user_defined(name):
            raise ModelError(f"{name!r} is built in and cannot be deleted")
        builtin_back = any(m.name.casefold() == name.casefold() for m in builtin_materials())
        self._set_app_settings(replace(self.app_settings, materials=self.materials.without(name)))
        self._changed(dirty=False)
        return "back to the built-in values" if builtin_back else "deleted"

    def material_in_use(self, name: str) -> bool:
        return self.program.raw_part.material.casefold() == name.casefold()

    def set_last_folder(self, path: Path, export: bool = False) -> None:
        """Remember the folder of a file the user opened or saved (the file dialogs start there); G-code files have a folder of their own."""
        folder = str(path.parent)
        key = "last_export_folder" if export else "last_folder"
        if folder != getattr(self.app_settings, key):
            self._set_app_settings(replace(self.app_settings, **{key: folder}))

    def set_window_layout(self, geometry: str, panel_sizes: tuple[int, ...]) -> None:
        """Remember the place and size of the window and the width of its three columns."""
        if (geometry, panel_sizes) != (self.app_settings.window_geometry, self.app_settings.panel_sizes):
            self._set_app_settings(replace(self.app_settings, window_geometry=geometry, panel_sizes=panel_sizes))

    def dialog_geometry(self, name: str) -> str:
        """The size and place a dialog had when it was closed last (Qt's own text form); empty: none known."""
        return dict(self.app_settings.dialog_geometry).get(name, "")

    def set_dialog_geometry(self, name: str, geometry: str) -> None:
        """Remember the size and place of a dialog."""
        known = dict(self.app_settings.dialog_geometry)
        if known.get(name) != geometry:
            known[name] = geometry
            self._set_app_settings(replace(self.app_settings, dialog_geometry=tuple(sorted(known.items()))))

    def set_legend_visible(self, visible: bool) -> None:
        if visible != self.app_settings.legend_visible:
            self._set_app_settings(replace(self.app_settings, legend_visible=visible))

    def _load_libraries(self) -> None:
        """Put the content of the active library of each kind into the settings (at start).

        Old settings files held the content themselves: it moves into a library file of its own.
        A library that is gone or damaged is replaced by the Example, with a message.
        """
        settings, notes, migrated = self.app_settings, [], False
        chosen = dict(settings.libraries)
        for kind in LIBRARY_KINDS:
            if kind not in chosen and has_content(settings, kind):
                name = USER_LIBRARY_NAME
                if self.settings_path is not None:
                    name = unique_library_name(self.settings_path, kind, USER_LIBRARY_NAME)
                    try:
                        write_library(self.settings_path, kind, name, content_to_dict(settings, kind))
                    except OSError as error:
                        notes.append(f"The {library_label(kind)} library could not be moved to a file ({error}).")
                settings, migrated = with_active_library(settings, kind, name), True
                continue
            settings, note = self._with_library(settings, kind, active_library(settings, kind))
            if note:
                notes.append(note)
        self.app_settings = settings
        if notes:
            self.settings_message = " ".join(filter(None, [self.settings_message] + notes))
        if (migrated or notes) and self.settings_path is not None:
            try:
                save_app_settings(self.settings_path, settings)
            except OSError as error:
                self.settings_message = f"The settings could not be saved ({error})."

    def _apply_machine_libraries(self, name: str) -> bool:
        """Use the libraries a machine of the list last used. A library that is gone is replaced by the Example.
        True if a library was changed."""
        remembered = dict(dict(self.app_settings.machine_libraries).get(name, ()))
        changed = False
        for kind in LIBRARY_KINDS:
            wanted = remembered.get(kind)
            if wanted is None or wanted.casefold() == self.active_library_name(kind).casefold():
                continue
            settings, note = self._with_library(self.app_settings, kind, wanted)
            self._set_app_settings(settings, library_switch=True)
            changed = True
            if note:
                self.settings_message = " ".join(filter(None, [self.settings_message, note]))
        return changed

    def _with_library(self, settings: AppSettings, kind: str, name: str) -> tuple[AppSettings, str]:
        """The settings with the content of a library, and a message when the Example had to be used instead."""
        if is_example(name) or self.settings_path is None:
            return with_active_library(with_example_content(settings, kind), kind, EXAMPLE_LIBRARY_NAME), ""
        try:
            loaded = with_content_from_dict(settings, kind, read_library(self.settings_path, kind, name))
            return with_active_library(loaded, kind, name), ""
        except (LibraryFileError, SettingsError) as error:
            note = f"The {library_label(kind)} library {name!r} could not be used ({error}); the Example library is used."
            return with_active_library(with_example_content(settings, kind), kind, EXAMPLE_LIBRARY_NAME), note

    def active_library_name(self, kind: str) -> str:
        return active_library(self.app_settings, kind)

    def library_folder_path(self, kind: str):
        """The folder of the libraries of a kind (made if it is not there yet); None when the settings are only in memory."""
        if self.settings_path is None:
            return None
        folder = library_folder(self.settings_path, kind)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def library_file_path(self, kind: str):
        """The file of the library in use; None for the Example (it has no file) or without a settings folder."""
        if self.settings_path is None or is_example(self.active_library_name(kind)):
            return None
        return library_file(self.settings_path, kind, self.active_library_name(kind))

    def library_names(self, kind: str) -> tuple[str, ...]:
        """The Example and the libraries in the folder; without a settings folder the active one too."""
        if self.settings_path is not None:
            return library_file_names(self.settings_path, kind)
        active = self.active_library_name(kind)
        return (EXAMPLE_LIBRARY_NAME,) if is_example(active) else (EXAMPLE_LIBRARY_NAME, active)

    def _library_name_free(self, kind: str, name: str) -> str:
        try:
            name = clean_name(name)
        except LibraryFileError as error:
            raise ModelError(str(error)) from error
        if name.casefold() in {n.casefold() for n in self.library_names(kind)}:
            raise ModelError(f"there is already a {library_label(kind)} library called {name!r}")
        return name

    def switch_library(self, kind: str, name: str) -> str:
        """Use another library of a kind. The projects keep their own copies. Returns what happened."""
        if name.casefold() not in {n.casefold() for n in self.library_names(kind)}:
            raise ModelError(f"there is no {library_label(kind)} library called {name!r}")
        settings, note = self._with_library(self.app_settings, kind, name)
        if note:
            raise ModelError(note)
        self._set_app_settings(settings, library_switch=True)
        self._library_changed()
        return f"{library_label(kind)} library: {self.active_library_name(kind)}"

    def new_library(self, kind: str, name: str) -> str:
        """Start an empty library of a kind and use it."""
        name = self._library_name_free(kind, name)
        empty = self._with_content_cleared(self.app_settings, kind)
        self._write_new_library(empty, kind, name)
        self._set_app_settings(with_active_library(empty, kind, name), library_switch=True)
        self._library_changed()
        return f"new {library_label(kind)} library: {name}"

    def save_library_as(self, kind: str, name: str) -> str:
        """Write the content in use as a new library and use that one (the way to keep a changed Example)."""
        name = self._library_name_free(kind, name)
        self._write_new_library(self.app_settings, kind, name)
        self._set_app_settings(with_active_library(self.app_settings, kind, name), library_switch=True)
        self._library_changed()
        return f"{library_label(kind)} library saved as {name}"

    def import_library(self, kind: str, source: Path) -> str:
        """Take over a library file somebody gave us and use it."""
        if self.settings_path is None:
            raise ModelError("libraries can only be imported when the settings are kept in a folder")
        try:
            name = import_library_file(self.settings_path, kind, source)
        except (LibraryFileError, OSError) as error:
            raise ModelError(f"the file could not be used as a {library_label(kind)} library: {error}") from error
        return self.switch_library(kind, name)

    def delete_library(self, kind: str, name: str) -> str:
        """Delete a library file. When it is the one in use the Example takes its place. The Example cannot be deleted."""
        if is_example(name):
            raise ModelError("the Example library is built in and cannot be deleted")
        if self.settings_path is None or name.casefold() not in {n.casefold() for n in self.library_names(kind)}:
            raise ModelError(f"there is no {library_label(kind)} library called {name!r}")
        try:
            delete_library_file(self.settings_path, kind, name)
        except OSError as error:
            raise ModelError(f"the library could not be deleted ({error})") from error
        if self.active_library_name(kind).casefold() == name.casefold():
            self.switch_library(kind, EXAMPLE_LIBRARY_NAME)
        return f"{library_label(kind)} library {name} deleted"

    def rename_library(self, kind: str, name: str, new_name: str) -> str:
        """Give a library file another name (the one in use stays in use). The Example cannot be renamed."""
        if is_example(name):
            raise ModelError("the Example library is built in and cannot be renamed")
        if self.settings_path is None or name.casefold() not in {n.casefold() for n in self.library_names(kind)}:
            raise ModelError(f"there is no {library_label(kind)} library called {name!r}")
        new_name = self._library_name_free(kind, new_name)
        try:
            rename_library_file(self.settings_path, kind, name, new_name)
        except OSError as error:
            raise ModelError(f"the library could not be renamed ({error})") from error
        if self.active_library_name(kind).casefold() == name.casefold():
            self._set_app_settings(with_active_library(self.app_settings, kind, new_name), library_switch=True)
        self._changed(dirty=False)
        return f"{library_label(kind)} library renamed to {new_name}"

    @staticmethod
    def _with_content_cleared(settings: AppSettings, kind: str) -> AppSettings:
        return replace(settings, **EMPTY_CONTENT[kind])

    def _write_new_library(self, settings: AppSettings, kind: str, name: str) -> None:
        if self.settings_path is None:
            return
        try:
            write_library(self.settings_path, kind, name, content_to_dict(settings, kind))
        except OSError as error:
            raise ModelError(f"the library could not be written ({error})") from error

    def _library_changed(self) -> None:
        """The content of a library was replaced: what was chosen in a view may not exist any more."""
        self.selected_workholding = None
        self._changed(dirty=False)

    def _set_app_settings(self, settings: AppSettings, library_switch: bool = False) -> None:
        """Keep the settings and write them. A file that cannot be written is reported, not fatal (U5).

        The content of a library that changed is written to the file of the active library. The Example
        has no file: the first change forks it into "My library" (library_switch: the content was only
        replaced by choosing a library, nothing is written).
        """
        changed = []
        if not library_switch:
            changed = [k for k in LIBRARY_KINDS if content_of(settings, k) != content_of(self.app_settings, k)]
        for kind in changed:
            if is_example(active_library(settings, kind)):
                name = USER_LIBRARY_NAME
                if self.settings_path is not None:
                    name = unique_library_name(self.settings_path, kind, USER_LIBRARY_NAME)
                settings = with_active_library(settings, kind, name)
        machine = getattr(self, "project", None) and self.project.machine
        if machine is not None and settings.libraries != self.app_settings.libraries and any(
            m.name == machine.name for m in settings.machines
        ):  # the machine of the project remembers the libraries in use
            remembered = dict(settings.machine_libraries)
            remembered[machine.name] = settings.libraries
            settings = replace(settings, machine_libraries=tuple(sorted(remembered.items())))
        before = self._machine_records(self.app_settings)
        after = self._machine_records(settings)
        self.app_settings = settings
        if self.settings_path is None:
            return
        try:
            for kind in changed:
                write_library(self.settings_path, kind, active_library(settings, kind), content_to_dict(settings, kind))
            for name, record in after.items():
                if before.get(name) != record:
                    write_machine_file(self.settings_path, *record)
            for name in before.keys() - after.keys():
                delete_machine_file(self.settings_path, name)
            save_app_settings(self.settings_path, settings)
        except OSError as error:
            self.settings_message = f"The settings could not be saved ({error})."
        self._remember_disk_state()

    def _disk_state(self) -> tuple:
        """Name, time and size of the library and machine files: what the program has to notice when someone else changes them."""
        if self.settings_path is None:
            return ()
        entries = []
        for folder_name in (LIBRARIES_FOLDER_NAME, MACHINES_FOLDER_NAME):
            folder = self.settings_path.parent / folder_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*" + LIBRARY_FILE_SUFFIX)):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(entries)

    def _remember_disk_state(self) -> None:
        self._saved_disk_state = self._disk_state()

    def reload_changed_files(self) -> str:
        """Take over libraries and machines that were changed outside the program (an editor, another PC, a copied file).

        Every change the program makes is written at once, so the files are the truth. Returns a message for the
        window ("" when nothing changed).
        """
        if self.settings_path is None or self._disk_state() == self._saved_disk_state:
            return ""
        settings, message = load_app_settings(self.settings_path)
        self.app_settings = settings
        self.settings_message = message
        self._load_libraries()
        self._load_machines()
        self._remember_disk_state()
        self._changed(dirty=False)
        return "Libraries or machines were changed outside the program: they were read again." + (f" {message}" if message else "")
