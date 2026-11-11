"""What the turning blocks share (requirements X6, X7, X8): the side and the direction, the radius of the hole an inside block starts
from, the note for a solid bar, and the finishing allowance the nose radius suggests. The planning itself is the analytic planner's
(`wop/core/analytic`), called by the contour block (`turning_contour.py`).
"""

from __future__ import annotations

from dataclasses import replace

from ..constants import GEOMETRY_TOLERANCE_MM, TURNING_FINISH_ALLOWANCE_NOSE_FACTOR
from ..geometry.region import Region
from .base import BlockResult
from .turning_job import PassDirection, TurningSide  # noqa: F401  (the names the blocks import from here)


def inside_stock_radius(residual: Region, z_low: float, z_high: float) -> float:
    """The smallest radius of the material over the Z range of the cut: the hole the boring tool starts from.

    Only the range of the cut counts: a blind hole leaves a core on the axis behind its bottom,
    which must not make the whole part look solid. A result of 0 means there is no hole there.
    """
    whole = residual.bounds
    band = residual.intersection(Region.rectangle(whole.min_x, z_low, whole.max_x, z_high)).bounds
    return whole.min_x if band is None else band.min_x


INSIDE_ON_SOLID_NOTE = (
    "inside turning starts in solid material (no hole along the cut): a boring bar cannot plunge, "
    "drill a hole first (drilling block) unless the tool can cut at the centre"
)


def with_solid_note(result: BlockResult, stock_radius: float) -> BlockResult:
    """The result with a note when an inside block starts on the axis (there is no hole to begin in); the collision
    checks decide whether the tool can do it, the note says what to look at."""
    if stock_radius > GEOMETRY_TOLERANCE_MM:
        return result
    return replace(result, messages=(INSIDE_ON_SOLID_NOTE, *result.messages))


def nose_radius_presets(block, tool):
    """The block with the finishing allowance the nose radius of the tool suggests (the depth of cut does not follow it).

    A tool without a nose radius (sharp, or a plain starter tool) suggests nothing: the block stays as it is.
    """
    nose = tool.nose_radius_mm
    if nose <= 0:
        return block
    return replace(block, finish_allowance_mm=TURNING_FINISH_ALLOWANCE_NOSE_FACTOR * nose)
