"""Helpers shared by the cutting blocks."""

from __future__ import annotations

import math

from .constants import GEOMETRY_TOLERANCE_MM, MAX_PASS_LEVELS


def pass_levels(start: float, end: float, max_step_mm: float) -> list[float]:
    """Positions of the passes between start (the surface) and end, equal steps.

    The first pass is one step away from the start and the last one is exactly
    at end. If start and end are the same (or end lies in the wrong
    direction by the caller's choice) there are no passes.
    """
    distance = end - start
    if abs(distance) <= GEOMETRY_TOLERANCE_MM:
        return []
    count = math.ceil(abs(distance) / max_step_mm - GEOMETRY_TOLERANCE_MM)
    if count > MAX_PASS_LEVELS:
        raise ValueError(
            f"cuts of at most {max_step_mm:g} mm over {abs(distance):g} mm would need {count} passes (the limit is {MAX_PASS_LEVELS}): "
            "check the depth of cut or the peck depth"
        )
    return [start + distance * index / count for index in range(1, count + 1)]


def levels(start: float, end: float, critical: list[float], max_step: float) -> list[float]:
    """Pass positions from start to end. Every critical position gets a pass of its own,
    so a flat piece of the outline is never left with a strip of material in front of it."""
    sign = 1 if end > start else -1
    between = sorted({c for c in critical if sign * (c - start) > GEOMETRY_TOLERANCE_MM
                      and sign * (end - c) > GEOMETRY_TOLERANCE_MM}, key=lambda c: sign * c)
    levels: list[float] = []
    previous = start
    for stop in [*between, end]:
        levels += pass_levels(previous, stop, max_step)
        previous = stop
    return levels
