"""Groundwork for styles per block type (nothing in the program uses a second style yet).

A style is one way to do the operation of a block type (a facing that cuts in one direction or the other, a turning that
works the contour differently). Every block type has one DEFAULT style: the way the block works today. A block type that
gets a second way registers it here with a label, a two-sentence hint and the key the project stores; the window can then
offer a dropdown from `styles_for`. Whatever a style does it must pass the same contract (`contract_problems`): the same
removed region as the default style, the block starts and ends at the safe point, and no operation leaves the part
differently from what the default style leaves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..constants import STYLE_REMOVED_AREA_TOLERANCE_MM2
from ..geometry.region import Region

DEFAULT_STYLE_KEY = "standard"


@dataclass(frozen=True)
class StyleInfo:
    key: str  # stored in the project
    label: str  # shown in the dropdown
    hint: str = ""  # two sentences for the hover text
    function: Callable | None = None  # what the block type calls to plan with this style (None: the block's own planning)


class StyleError(ValueError):
    pass


class StyleRegistry:
    def __init__(self) -> None:
        self._styles: dict[str, dict[str, StyleInfo]] = {}

    def register(self, block_type: str, info: StyleInfo) -> StyleInfo:
        styles = self._styles.setdefault(block_type, {})
        if info.key in styles:
            raise StyleError(f"block type {block_type!r} has the style {info.key!r} already")
        styles[info.key] = info
        return info

    def unregister(self, block_type: str, key: str) -> None:
        """Take a style away again (a style file that fails its check, or a test cleaning up). The default style stays."""
        if key != DEFAULT_STYLE_KEY:
            self._styles.get(block_type, {}).pop(key, None)

    def supports(self, block_type: str) -> bool:
        """True when the block type has a style function (the types without one have no style dropdown)."""
        return bool(self._styles.get(block_type, {}).get(DEFAULT_STYLE_KEY, StyleInfo("", "")).function)

    def styles_for(self, block_type: str) -> tuple[StyleInfo, ...]:
        """The styles of a type; the default one always comes first (a type without any has just the default)."""
        found = self._styles.get(block_type, {})
        default = found.get(DEFAULT_STYLE_KEY, StyleInfo(DEFAULT_STYLE_KEY, "Standard"))
        return (default, *(info for key, info in found.items() if key != DEFAULT_STYLE_KEY))

    def get(self, block_type: str, key: str) -> StyleInfo:
        for info in self.styles_for(block_type):
            if info.key == key or (not key and info.key == DEFAULT_STYLE_KEY):
                return info
        raise StyleError(f"block type {block_type!r} has no style {key!r}")


STYLES = StyleRegistry()


def contract_problems(default_removed: Region, default_end, removed: Region, end) -> list[str]:
    """What is wrong with a style compared with the default style of the same block (empty: it passes).

    `removed` is the region the block removes, `end` the last position of its operations.
    """
    problems = []
    difference = default_removed.difference(removed).area + removed.difference(default_removed).area
    if difference > STYLE_REMOVED_AREA_TOLERANCE_MM2:
        problems.append(f"removes another region than the standard style (difference {difference:.3f} mm2)")
    if end != default_end:
        problems.append("does not end where the standard style ends")
    return problems
