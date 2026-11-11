"""Where a groove blade plunges (pure numbers, no material, no tool path).

Z values are the tip Z of the blade: the blade covers [z, z + blade]. The front wall (higher Z) comes first: a plunge
surrounded by material, kept one one-sided cut away from the wall, then one at the wall that cuts only that strip
with air on its other side (a blade that cuts on one side only must not cut wide). From there the groove is cut in
steps of the one-sided cut towards the chuck, the last plunge at the wall nearer the chuck. So every plunge after
the first has air on its front side and engages at most the one-sided cut, however wide the groove is.
"""

from __future__ import annotations

from ..constants import GEOMETRY_TOLERANCE_MM, MAX_GROOVE_PLUNGES


def _covered(z: float, blade: float, cleared: list[tuple[float, float]]) -> bool:
    """True when the plunge at z cuts only air: all of [z, z + blade] is inside what is cleared already."""
    position = z
    for low, high in sorted(cleared):
        if low <= position + GEOMETRY_TOLERANCE_MM:
            position = max(position, high)
    return position >= z + blade - GEOMETRY_TOLERANCE_MM


def rough_plunges(low: float, high: float, blade: float, one_sided_mm: float) -> list[float]:
    """Tip Z of the roughing plunges in the order they are made; the groove is [low, high] (walls included)."""
    if high - low <= blade + GEOMETRY_TOLERANCE_MM:
        return [low]  # the blade fills the groove
    top = high - blade  # the highest position of the blade
    side = min(one_sided_mm, blade)
    if (top - low) / side > MAX_GROOVE_PLUNGES:
        raise ValueError(
            f"a groove of {high - low:g} mm cut in steps of {side:g} mm would need more than {MAX_GROOVE_PLUNGES} plunges: "
            "check the groove width and the one-sided cut"
        )
    full = side >= blade - GEOMETRY_TOLERANCE_MM  # a one-sided cut as wide as the blade: no first plunge needed
    wanted = [top] if full else [max(low, top - side), top]
    z = wanted[0] - side
    while z > low + GEOMETRY_TOLERANCE_MM:
        wanted.append(z)
        z -= side
    wanted.append(low)
    cleared: list[tuple[float, float]] = []
    plunges: list[float] = []
    for z in wanted:
        z = min(max(z, low), top)
        if _covered(z, blade, cleared):
            continue
        plunges.append(z)
        cleared.append((z, z + blade))
    return plunges


def finish_steps(low: float, high: float, blade: float, stop_early_mm: float) -> list[tuple[float, float | None]]:
    """The finishing plunges: (tip Z of the plunge, tip Z the pass along the bottom ends at or None).

    The front wall first. A groove of up to two blades is covered by the two plunges. A wider one gets a pass along
    the bottom from the front plunge that ends stop_early_mm before the other wall (so the side of the blade never
    works on that wall); then the plunge at that wall and a pass of the same length back, which covers the end of the
    first pass by one whole blade width.
    """
    top = high - blade
    if top - low <= GEOMETRY_TOLERANCE_MM:
        return [(low, None)]
    if top - (low + blade) <= GEOMETRY_TOLERANCE_MM:
        return [(top, None), (low, None)]
    stop = min(stop_early_mm, blade)
    return [(top, low + stop), (low, low + stop)]
