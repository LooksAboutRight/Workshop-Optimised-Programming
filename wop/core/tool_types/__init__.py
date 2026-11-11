"""Tool types. Every module in this package registers its type when imported; a new type is one new file."""

import importlib
import pkgutil

from .base import TOOL_TYPES, ToolType, definition_of, info_of, make_tool  # noqa: F401

for _module in pkgutil.iter_modules(__path__):
    if _module.name != "base":
        importlib.import_module(f"{__name__}.{_module.name}")
