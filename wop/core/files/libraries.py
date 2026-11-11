"""Libraries (LIB1): the content of the materials, workholding and tool libraries as data.

The settings hold the content of the active library of each kind (`AppSettings`); the files
(`adapters/library_files.py`) hold the libraries themselves. The library called "Example" is
built in: it has no file, it is always there, and the first change made while it is active
forks it into the user's own library.
"""

from __future__ import annotations

from dataclasses import replace

from .app_settings import AppSettings, SettingsError
from ..constants import (
    EXAMPLE_CHUCK_NAME,
    EXAMPLE_JAWS_NAME,
    EXAMPLE_LIBRARY_NAME,
    LIBRARY_FORMAT_VERSION,
    LIBRARY_KIND_MATERIALS,
    LIBRARY_KIND_TOOLS,
    EXAMPLE_TOOL_NAME_PREFIX,
    LIBRARY_KIND_WORKHOLDING,
)
from ..material import MaterialError, MaterialLibrary
from .material_io import library_from_dict, library_to_dict
from ..tooling.tool import ToolError
from .tool_io import tool_from_dict, tool_to_dict, toolbox_from_dict, toolbox_to_dict
from ..tooling.toolbox import ToolboxError, check_toolboxes
from ..tool_types import TOOL_TYPES, make_tool
from ..lathe.workholding import CHUCK_KIND, JAWS_KIND, WorkholdingError
from .workholding_io import item_from_dict, item_to_dict
from ..workholding_types import example_item

LIBRARY_KINDS = (LIBRARY_KIND_MATERIALS, LIBRARY_KIND_WORKHOLDING, LIBRARY_KIND_TOOLS)
_LIBRARY_LABELS = (
    (LIBRARY_KIND_MATERIALS, "materials"),
    (LIBRARY_KIND_WORKHOLDING, "workholding"),
    (LIBRARY_KIND_TOOLS, "tools"),
)


def library_label(kind: str) -> str:
    return dict(_LIBRARY_LABELS)[kind]


def is_example(name: str) -> bool:
    return name.casefold() == EXAMPLE_LIBRARY_NAME.casefold()


def active_library(settings: AppSettings, kind: str) -> str:
    """The name of the library in use for a kind; the Example when none was chosen."""
    return dict(settings.libraries).get(kind, EXAMPLE_LIBRARY_NAME)


def with_active_library(settings: AppSettings, kind: str, name: str) -> AppSettings:
    chosen = dict(settings.libraries)
    chosen[kind] = name
    return replace(settings, libraries=tuple(sorted(chosen.items())))


def content_of(settings: AppSettings, kind: str) -> tuple:
    """The content of a kind as a comparable value (to see whether it changed)."""
    if kind == LIBRARY_KIND_MATERIALS:
        return (settings.materials,)
    if kind == LIBRARY_KIND_WORKHOLDING:
        return (settings.workholding,)
    return (settings.tools, settings.toolboxes, settings.default_toolbox)


def has_content(settings: AppSettings, kind: str) -> bool:
    if kind == LIBRARY_KIND_MATERIALS:
        return bool(settings.materials.user)
    return any(content_of(settings, kind))


def _example_tools():
    tools = []
    for number, tool_type in enumerate(TOOL_TYPES.types(), start=1):
        definition = replace(tool_type.default(), number=number, name=f"{EXAMPLE_TOOL_NAME_PREFIX} {tool_type.label.lower()}")
        tools.append(make_tool(tool_type.type_name, number, definition))
    return tuple(tools)


def with_example_content(settings: AppSettings, kind: str) -> AppSettings:
    """The settings with the content of the Example library of a kind."""
    if kind == LIBRARY_KIND_MATERIALS:
        return replace(settings, materials=MaterialLibrary())
    if kind == LIBRARY_KIND_WORKHOLDING:
        items = (example_item(JAWS_KIND, EXAMPLE_JAWS_NAME), example_item(CHUCK_KIND, EXAMPLE_CHUCK_NAME))
        return replace(settings, workholding=items)
    return replace(settings, tools=_example_tools(), toolboxes=(), default_toolbox=None)


def content_to_dict(settings: AppSettings, kind: str) -> dict:
    """The content of the library of a kind, ready for its file."""
    data: dict = {"library": kind, "format": LIBRARY_FORMAT_VERSION}
    if kind == LIBRARY_KIND_MATERIALS:
        data["materials"] = library_to_dict(settings.materials)
    elif kind == LIBRARY_KIND_WORKHOLDING:
        data["items"] = [item_to_dict(item) for item in settings.workholding]
    else:
        data["tools"] = [tool_to_dict(tool) for tool in settings.tools]
        data["toolboxes"] = [toolbox_to_dict(box) for box in settings.toolboxes]
        if settings.default_toolbox is not None:
            data["default_toolbox"] = settings.default_toolbox
    return data


def with_content_from_dict(settings: AppSettings, kind: str, data: dict) -> AppSettings:
    """The settings with the content of a library file. Wrong data raises SettingsError."""
    try:
        if data["library"] != kind:
            raise SettingsError(f"this is a {data['library']!r} library, not a {kind!r} one")
        if data["format"] != LIBRARY_FORMAT_VERSION:
            raise SettingsError(f"unsupported library format {data['format']!r}")
        if kind == LIBRARY_KIND_MATERIALS:
            return replace(settings, materials=library_from_dict(data["materials"]))
        if kind == LIBRARY_KIND_WORKHOLDING:
            items = tuple(item_from_dict(item) for item in data["items"])
            _unique([item.name for item in items], "a workholding item")
            return replace(settings, workholding=items)
        tools = tuple(tool_from_dict(item) for item in data["tools"])
        _unique([tool.name for tool in tools], "a tool")
        boxes = tuple(toolbox_from_dict(item) for item in data.get("toolboxes", ()))
        default = data.get("default_toolbox")
        if default is not None and not isinstance(default, str):
            raise SettingsError("default_toolbox must be a name")
        check_toolboxes(boxes, default, tools)
        return replace(settings, tools=tools, toolboxes=boxes, default_toolbox=default)
    except SettingsError:
        raise
    except (MaterialError, WorkholdingError, ToolError, ToolboxError) as error:
        raise SettingsError(str(error)) from error
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SettingsError(f"invalid library data: {error!r}") from error


def _unique(names: list[str], what: str) -> None:
    folded = [name.casefold() for name in names]
    if len(set(folded)) != len(folded):
        raise SettingsError(f"{what} is listed twice")
