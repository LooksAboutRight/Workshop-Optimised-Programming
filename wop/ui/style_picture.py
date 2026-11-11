"""The pictures of a block style: its path on every sample of its block type, as SVG text (toolkit free).

Made on demand from the style's own code (the same samples the tests check every style on), never stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..adapters.style_samples import PICTURE_PADDING, PICTURE_PADDING_MM, StyleSample, samples_for
from ..core.blocks.base import BlockError
from ..core.geometry import Point
from ..core.program_model.program import plan_program
from . import ui_constants as ui
from .svg_preview import render_svg
from .theme import ColorSet

NUMBER_ATTRIBUTE = re.compile(r'(stroke-width|stroke-dasharray)="([^"]*)"')


@dataclass(frozen=True)
class StylePicture:
    caption: str  # the name of the sample
    svg: str  # empty when the style cannot be drawn on this sample
    problem: str = ""  # why not


def _thicker(svg: str, factor: float) -> str:
    """The lines and dashes of a picture that is shown at a fraction of its size, made thicker so they stay visible."""
    def scale(match: re.Match) -> str:
        numbers = " ".join(f"{float(number) * factor:g}" for number in match.group(2).split())
        return f'{match.group(1)}="{numbers}"'

    return NUMBER_ATTRIBUTE.sub(scale, svg)


def _fit(sample: StyleSample) -> tuple[Point, Point]:
    low, high = sample.focus
    pad = max(high.x - low.x, high.z - low.z) * PICTURE_PADDING + PICTURE_PADDING_MM
    return Point(low.x - pad, low.z - pad), Point(high.x + pad, high.z + pad)


def style_pictures(block_type: str, key: str, colors: ColorSet) -> list[StylePicture]:
    """One picture per sample of the block type, with the style of that key."""
    pictures = []
    for sample in samples_for(block_type):
        try:
            plan = plan_program(sample.program(key))
        except BlockError as error:
            pictures.append(StylePicture(sample.name, "", str(error)))
            continue
        if plan.left_out:
            pictures.append(StylePicture(sample.name, "", plan.left_out[0].reason))
            continue
        svg = render_svg(plan, colors=colors, with_legend=False, fit=_fit(sample), order_colors=(ui.STYLE_PATH_FIRST_COLOR, ui.STYLE_PATH_LAST_COLOR), rapids=sample.rapids)
        pictures.append(StylePicture(sample.name, _thicker(svg, ui.STYLE_PICTURE_LINE_FACTOR)))
    return pictures
