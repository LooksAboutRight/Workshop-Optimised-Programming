"""The tool a block gets when it needs none (a machine function) and no tool is chosen: nothing is cut with it."""

from __future__ import annotations

from functools import cache

from ..constants import NO_TOOL_NUMBER
from ..tool_types import make_tool
from ..tool_types.turning import TurningDefinition
from .tool import Tool


@cache
def stand_in_tool() -> Tool:
    return make_tool("turning", NO_TOOL_NUMBER, TurningDefinition())
