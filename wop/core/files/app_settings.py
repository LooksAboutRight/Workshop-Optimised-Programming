"""The settings of the application itself, kept between runs (requirement U5).

Not part of a project: the user's materials and the state of the legend. Later the
machines, the default machine and the colours. The app works without the file.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import APP_SETTINGS_FORMAT_VERSION
from ..material import MaterialError, MaterialLibrary
from ..lathe.machine import MachineDef, MachineError
from .machine_io import machine_from_dict, machine_to_dict
from .material_io import library_from_dict, library_to_dict
from ..tooling.tool import Tool, ToolError
from ..tooling.toolbox import Toolbox
from .tool_io import tool_from_dict, tool_to_dict
from ..lathe.workholding import WorkholdingError, WorkholdingItem
from .workholding_io import item_from_dict, item_to_dict


class SettingsError(ValueError):
    """The settings data is damaged or from a newer version."""


@dataclass(frozen=True)
class AppSettings:
    materials: MaterialLibrary = MaterialLibrary()
    legend_visible: bool = True
    machines: tuple[MachineDef, ...] = ()  # the user's machines (M9); names are unique
    default_machine: str | None = None  # name of the machine a new project starts with
    machine_touched: tuple[str, ...] = ()  # touched fields of the machines (U6), keys as in core/touched.py
    workholding: tuple[WorkholdingItem, ...] = ()  # the user's chucks and jaws (R6); names are unique
    # Content above is that of the active library of each kind (LIB1, core/libraries.py); the library files hold it.
    tools: tuple[Tool, ...] = ()  # the tools of the active tool library (LIB2); names unique
    libraries: tuple[tuple[str, str], ...] = ()  # (kind, name of the active library); no entry: the Example
    machine_libraries: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()  # per machine name: the libraries it last used
    last_folder: str = ""  # the folder of the last project or other file the user opened or saved; the file dialogs start there
    last_export_folder: str = ""  # the folder of the last G-code file; the export dialog starts there
    window_geometry: str = ""  # size and place of the main window (Qt's own text form); empty: the default
    panel_sizes: tuple[int, ...] = ()  # widths of the three columns, 0 = closed; empty: the default
    dialog_geometry: tuple[tuple[str, str], ...] = ()  # (name of a dialog, its size and place in Qt's own text form), sorted by name; no entry: the default
    toolboxes: tuple[Toolbox, ...] = ()  # content of the active tool library, like `tools` (T17); names unique
    default_toolbox: str | None = None  # the toolbox a new project starts with; None: no tools


def settings_to_dict(settings: AppSettings, include_content: bool = False) -> dict:
    """The settings as data. The content of the libraries and the machines are not part of the settings file (they are in
    the files of their folders); `include_content` writes them in, as the files of older versions had them."""
    data = {
        "format": APP_SETTINGS_FORMAT_VERSION,
        "legend_visible": settings.legend_visible,
        "default_machine": settings.default_machine,
    }
    if include_content:
        data["machines"] = [machine_to_dict(machine) for machine in settings.machines]
        data["machine_touched"] = list(settings.machine_touched)
    if settings.libraries:
        data["libraries"] = dict(settings.libraries)
    if settings.last_folder:
        data["last_folder"] = settings.last_folder
    if settings.last_export_folder:
        data["last_export_folder"] = settings.last_export_folder
    if settings.window_geometry:
        data["window_geometry"] = settings.window_geometry
    if settings.panel_sizes:
        data["panel_sizes"] = list(settings.panel_sizes)
    if settings.dialog_geometry:
        data["dialog_geometry"] = dict(settings.dialog_geometry)
    if not include_content:
        return data
    data["materials"] = library_to_dict(settings.materials)
    if settings.tools:
        data["tools"] = [tool_to_dict(tool) for tool in settings.tools]
    if settings.workholding:
        data["workholding"] = [item_to_dict(item) for item in settings.workholding]
    return data


def settings_from_dict(data: dict) -> AppSettings:
    """Rebuild the settings. A missing entry gets its default; wrong data raises SettingsError."""
    try:
        if data["format"] != APP_SETTINGS_FORMAT_VERSION:
            raise SettingsError(f"unsupported settings format {data['format']!r}")
        defaults = AppSettings()
        materials = library_from_dict(data["materials"]) if "materials" in data else defaults.materials
        legend = data.get("legend_visible", defaults.legend_visible)
        if not isinstance(legend, bool):
            raise SettingsError(f"legend_visible must be true or false, got {legend!r}")
        machines = tuple(machine_from_dict(item) for item in data.get("machines", ()))
        names = [machine.name.casefold() for machine in machines]
        if len(set(names)) != len(names):
            raise SettingsError("a machine is listed twice")
        default = data.get("default_machine", defaults.default_machine)
        if "machines" in data and default is not None and default not in [machine.name for machine in machines]:
            default = None  # the machine was removed by hand: no default (without a list the machine files decide)
        touched = data.get("machine_touched", [])
        if not (isinstance(touched, list) and all(isinstance(key, str) for key in touched)):
            raise SettingsError("machine_touched must be a list of text")
        items = tuple(item_from_dict(item) for item in data.get("workholding", ()))
        item_names = [item.name.casefold() for item in items]
        if len(set(item_names)) != len(item_names):
            raise SettingsError("a workholding item is listed twice")
        chosen = data.get("libraries", {})
        if not (isinstance(chosen, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in chosen.items())):
            raise SettingsError("libraries must map a kind to a name")
        tools = tuple(tool_from_dict(item) for item in data.get("tools", ()))
        # The window's own memory is never worth refusing the file for: a wrong entry is just forgotten.
        folder, geometry, sizes = data.get("last_folder", ""), data.get("window_geometry", ""), data.get("panel_sizes", ())
        export_folder = data.get("last_export_folder", "")
        sizes_ok = isinstance(sizes, list) and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in sizes)
        dialogs = data.get("dialog_geometry", {})
        dialogs = dialogs if isinstance(dialogs, dict) else {}
        dialog_geometry = tuple(sorted((name, text) for name, text in dialogs.items() if isinstance(name, str) and isinstance(text, str)))
        return AppSettings(
            materials, legend, machines, default, tuple(touched), items, tools, tuple(sorted(chosen.items())),
            last_folder=folder if isinstance(folder, str) else "",
            last_export_folder=export_folder if isinstance(export_folder, str) else "",
            window_geometry=geometry if isinstance(geometry, str) else "",
            panel_sizes=tuple(sizes) if sizes_ok else (),
            dialog_geometry=dialog_geometry,
        )
    except SettingsError:
        raise
    except (MaterialError, MachineError, WorkholdingError, ToolError) as error:
        raise SettingsError(str(error)) from error
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SettingsError(f"invalid settings data: {error!r}") from error
