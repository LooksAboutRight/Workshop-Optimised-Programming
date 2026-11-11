"""The material as chains: the bar made from the raw part, and the loops of what earlier blocks left.

Rule of the analytic planner: everything is exact chains of lines and arcs; a polygon is only made to draw a picture. A bar that
nobody has cut is exact here. What earlier blocks left is a `Region`: its loops are exact too (`Region`); `chains_of_region` reads
them.
"""

from __future__ import annotations

from ..constants import CHAIN_SNAP_MM, GEOMETRY_TOLERANCE_MM
from ..geometry import Point
from ..program_model.raw_part import RawPart
from ..geometry.region import Region
from ..program_model.stock import stock_region
from ..geometry.chains import Loop, loops_of_region, oriented, polygon_loop


def stock_chains(raw_part: RawPart) -> list[Loop]:
    """The half section of the raw part outside the jaws: a rectangle (the same area as `stock_region`), or the drawn shape."""
    if raw_part.outline is not None:
        return loops_of_region(stock_region(raw_part))
    corners = [
        Point(raw_part.inner_radius_mm, raw_part.clamp_z_mm), Point(raw_part.outer_radius_mm, raw_part.clamp_z_mm),
        Point(raw_part.outer_radius_mm, raw_part.front_z_mm), Point(raw_part.inner_radius_mm, raw_part.front_z_mm),
    ]
    return [oriented(polygon_loop(corners), True)]


def is_uncut(residual: Region, raw_part: RawPart) -> bool:
    """True when the residual is the whole bar (no block has cut anything yet)."""
    bar = stock_region(raw_part)
    return residual.difference(bar).area <= GEOMETRY_TOLERANCE_MM and bar.difference(residual).area <= GEOMETRY_TOLERANCE_MM


def chains_of_region(region: Region, cleaned: bool = False) -> list[Loop]:
    """The loops of a region. `cleaned`: earlier cuts can leave needles and zigzags along the border (edges that nearly lie on each
    other); the border is opened by the snap distance and simplified first. Cleaning always moves a clean border a little, so it is
    only used when the loops as they are fail."""
    if cleaned:
        region = region.offset(-CHAIN_SNAP_MM).offset(CHAIN_SNAP_MM).simplified(CHAIN_SNAP_MM)
    return loops_of_region(region)
