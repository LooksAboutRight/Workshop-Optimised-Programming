"""Stock and residual material (requirement: residual part after each block).
"""

from __future__ import annotations

from .raw_outline import outline_stock
from .raw_part import RawPart
from ..geometry.region import Region


def stock_region(raw_part: RawPart) -> Region:
    """Half section of the raw part outside the jaws, as an area in X/Z."""
    if raw_part.outline is not None:
        return outline_stock(raw_part)
    return Region.rectangle(
        raw_part.inner_radius_mm,
        raw_part.clamp_z_mm,
        raw_part.outer_radius_mm,
        raw_part.front_z_mm,
    )
