"""Spindle speed and cutting speed at a radius (used by the power estimate and the machine check)."""

from __future__ import annotations

import math

from ..constants import MM_PER_M, SPINDLE_MIN_RADIUS_MM
from ..program_model.operations import SpindleMode, SpindleSetting


def rpm_at(setting: SpindleSetting, radius_mm: float) -> float:
    """Spindle speed in RPM when cutting at the given radius."""
    if setting.mode is SpindleMode.CONSTANT_RPM:
        return setting.value
    radius = max(radius_mm, SPINDLE_MIN_RADIUS_MM)
    rpm = setting.value * MM_PER_M / (2 * math.pi * radius)
    return rpm if setting.rpm_limit is None else min(rpm, setting.rpm_limit)


def cutting_speed_at(setting: SpindleSetting, radius_mm: float) -> float:
    """Cutting speed in m/min at the given radius (below the set value when RPM-limited)."""
    return 2 * math.pi * max(radius_mm, 0) * rpm_at(setting, radius_mm) / MM_PER_M
