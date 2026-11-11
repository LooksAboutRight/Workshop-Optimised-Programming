"""Colour sets of the pictures (requirement V4), without any GUI toolkit.

The pictures (program, contour editor, 3D view) take all their colours from a
`ColorSet`. The window builds one from its OS theme with `color_set_for` and hands
it to the model, so the pictures follow a light or a dark theme. A set whose
`background` is None draws no background rectangle: the window shows through, so
there is no box in a different colour. Files (`wop_run.py`) use `LIGHT_COLORS`,
which has a white background of the full picture size.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import ui_constants as ui
from . import view3d_constants as v3

HEX_DIGITS_PER_CHANNEL = 2
HEX_BASE = 16
CHANNEL_MAX = 255
LUMINANCE_WEIGHTS = (0.299, 0.587, 0.114)


@dataclass(frozen=True)
class ColorSet:
    background: str | None  # None: no background rectangle
    text: str
    key_text: str
    stock_fill: str
    stock_stroke: str
    residual_fill: str
    residual_stroke: str
    axis: str
    axis_3d: str
    rapid: str
    finding: str
    block_colors: tuple[str, ...]  # cutting moves: one colour per block, repeating
    cut_3d: str  # cutting moves in the 3D view
    rapid_3d: str
    tool_cutter: str  # the tool shown while stepping through (V2)
    tool_holder: str
    far_side_fill: str = ui.FAR_SIDE_FILL  # the mirrored material on the far side of the axis
    far_side_stroke: str = ui.FAR_SIDE_STROKE
    finished_outline: str = ui.FINISHED_OUTLINE_COLOR  # the finished shape of the chosen block


LIGHT_COLORS = ColorSet(
    background=ui.LIGHT_BACKGROUND,
    text=ui.LIGHT_TEXT,
    key_text=ui.KEY_TEXT_COLOR,
    stock_fill=ui.STOCK_FILL,
    stock_stroke=ui.STOCK_STROKE,
    residual_fill=ui.RESIDUAL_FILL,
    residual_stroke=ui.RESIDUAL_STROKE,
    axis=ui.AXIS_COLOR,
    axis_3d=v3.AXIS_COLOR,
    rapid=ui.RAPID_COLOR,
    finding=ui.FINDING_COLOR,
    block_colors=ui.BLOCK_COLORS,
    cut_3d=v3.PATH_CUT_COLOR,
    rapid_3d=v3.PATH_RAPID_COLOR,
    tool_cutter=ui.TOOL_CUTTER_COLOR,
    tool_holder=ui.TOOL_HOLDER_COLOR,
)

DARK_COLORS = ColorSet(
    background=ui.DARK_BACKGROUND,
    text=ui.DARK_TEXT,
    key_text=ui.DARK_KEY_TEXT_COLOR,
    stock_fill=ui.DARK_STOCK_FILL,
    stock_stroke=ui.DARK_STOCK_STROKE,
    residual_fill=ui.DARK_RESIDUAL_FILL,
    residual_stroke=ui.DARK_RESIDUAL_STROKE,
    axis=ui.DARK_AXIS_COLOR,
    axis_3d=ui.DARK_AXIS_3D_COLOR,
    rapid=ui.DARK_RAPID_COLOR,
    finding=ui.DARK_FINDING_COLOR,
    block_colors=ui.DARK_BLOCK_COLORS,
    cut_3d=ui.DARK_CUT_3D_COLOR,
    rapid_3d=ui.DARK_RAPID_3D_COLOR,
    tool_cutter=ui.DARK_TOOL_CUTTER_COLOR,
    tool_holder=ui.DARK_TOOL_HOLDER_COLOR,
    far_side_fill=ui.DARK_FAR_SIDE_FILL,
    far_side_stroke=ui.DARK_FAR_SIDE_STROKE,
    finished_outline=ui.DARK_FINISHED_OUTLINE_COLOR,
)


def _luminance(hex_color: str) -> float:
    """Brightness 0..1 of "#rrggbb". Raises ValueError for anything else."""
    if len(hex_color) != ui.HEX_COLOR_LENGTH or not hex_color.startswith("#"):
        raise ValueError(f"not a #rrggbb colour: {hex_color!r}")
    channels = [
        int(hex_color[1 + i * HEX_DIGITS_PER_CHANNEL : 1 + (i + 1) * HEX_DIGITS_PER_CHANNEL], HEX_BASE)
        for i in range(len(LUMINANCE_WEIGHTS))
    ]
    return sum(w * c for w, c in zip(LUMINANCE_WEIGHTS, channels)) / CHANNEL_MAX


def is_dark(hex_color: str) -> bool:
    return _luminance(hex_color) < ui.DARK_THEME_LUMINANCE_LIMIT


def color_set_for(window_color: str, text_color: str) -> ColorSet:
    """The set for a window with these colours ("#rrggbb"): light or dark, no background rectangle.

    Unusable colours (not "#rrggbb") give the light set without background.
    """
    try:
        base = DARK_COLORS if is_dark(window_color) else LIGHT_COLORS
        text = text_color if len(text_color) == ui.HEX_COLOR_LENGTH and text_color.startswith("#") else base.text
    except ValueError:
        base, text = LIGHT_COLORS, LIGHT_COLORS.text
    return replace(base, background=None, text=text)


def _channels(hex_color: str) -> list[int]:
    _luminance(hex_color)  # raises ValueError for anything but "#rrggbb"
    return [
        int(hex_color[1 + i * HEX_DIGITS_PER_CHANNEL : 1 + (i + 1) * HEX_DIGITS_PER_CHANNEL], HEX_BASE)
        for i in range(len(LUMINANCE_WEIGHTS))
    ]


def mix_colors(first: str, second: str, share: float) -> str:
    """The colour `share` of the way from `first` to `second` (both "#rrggbb"; 0 gives first, 1 gives second)."""
    mixed = [round(a + (b - a) * share) for a, b in zip(_channels(first), _channels(second))]
    return "#" + "".join(f"{channel:0{HEX_DIGITS_PER_CHANNEL}x}" for channel in mixed)
