"""The cutting values of the example projects: mild steel, coated carbide inserts, a lathe of about 2.5 kW (the author's).

Close enough to real work not to confuse a user who looks at them, not optimised. Used by `make_example_project.py` and `make_block_examples.py`
(`with_values`); the pawn and the rest machining example are saved from the window, with the same numbers.
"""

from __future__ import annotations

from dataclasses import fields, replace

from wop.core.program_model.operations import SpindleMode, SpindleSetting

CSS_LIMIT_RPM = 3000.0  # the top speed of the lathe


def css(metres_per_minute: float) -> SpindleSetting:
    return SpindleSetting(SpindleMode.CONSTANT_SURFACE_SPEED, metres_per_minute, rpm_limit=CSS_LIMIT_RPM)


def rpm(revolutions_per_minute: float) -> SpindleSetting:
    return SpindleSetting(SpindleMode.CONSTANT_RPM, revolutions_per_minute)


# a value that a block type does not have is left out by `with_values`; the depth of cut and the allowance stay as the block has them
ROUGHING = dict(spindle=css(150), feed_mm_per_rev=0.2, finish_feed_mm_per_rev=0.1, finish_spindle_value=180.0)  # outside, VNMG insert
FACING = dict(spindle=css(150), feed_mm_per_rev=0.15, depth_of_cut_mm=1.0, finish_feed_mm_per_rev=0.1, finish_spindle_value=180.0)
BORING = dict(spindle=css(100), feed_mm_per_rev=0.08, depth_of_cut_mm=0.5, finish_feed_mm_per_rev=0.05, finish_spindle_value=120.0)  # a small bar
GROOVING = dict(spindle=css(80), feed_mm_per_rev=0.06)  # a blade of 4 mm
DRILLING = dict(spindle=rpm(1400), feed_mm_per_rev=0.1, peck_depth_mm=3.0)  # a drill of 6 mm
THREADING = dict(spindle=rpm(500))  # a thread of 1.5 mm pitch on 30 mm
CUSTOM_PATH = dict(spindle=css(150), feed_mm_per_rev=0.15)


def with_values(block, values: dict):
    """The block with these values (only the ones a block of its type has; a peck depth only where the block pecks)."""
    names = {field.name for field in fields(block)}
    chosen = {name: value for name, value in values.items() if name in names}
    if "peck_depth_mm" in chosen and getattr(block, "peck_depth_mm", None) is None:
        del chosen["peck_depth_mm"]
    return replace(block, **chosen)
