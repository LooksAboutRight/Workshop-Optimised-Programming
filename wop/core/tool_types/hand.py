"""The hand of a tool (shared by the tool types that have one)."""

from __future__ import annotations

from enum import Enum


class ToolHand(Enum):
    RIGHT = "right hand"
    LEFT = "left hand"
