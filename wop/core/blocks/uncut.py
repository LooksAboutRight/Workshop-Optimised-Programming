"""Report what a block left uncut (requirement X8)."""

from __future__ import annotations

from ..constants import UNREACHED_MIN_AREA_MM2
from ..geometry.region import Region

UNREACHED_REMEDY = (
    "use a tool that reaches it (thinner, other tip angle or direction), "
    "or machine it with another block, or accept that it stays"
)


def report_uncut(label: str, planned: Region, current: Region) -> tuple[Region, list[str]]:
    """Pieces of `planned` that are still in `current` (not cut) and big enough to matter.

    Returns the planned region without those pieces, and one message per piece
    with its area, position and a remedy.
    """
    removed = planned
    messages: list[str] = []
    for polygon in planned.intersection(current).polygons():
        piece = Region.from_points(list(polygon.exterior))
        if piece.area < UNREACHED_MIN_AREA_MM2:
            continue
        box = piece.bounds
        messages.append(
            f"{label}: {piece.area:.2f} mm2 stays uncut around radius "
            f"{(box.min_x + box.max_x) / 2:.2f}, Z {(box.min_z + box.max_z) / 2:.2f} "
            f"(the tool cannot reach it). Remedy: {UNREACHED_REMEDY}"
        )
        removed = removed.difference(piece)
    return removed, messages
